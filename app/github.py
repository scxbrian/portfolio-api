"""Everything that talks to, or about, GitHub. Standard library only."""
import hashlib
import hmac
import json
import re
from urllib.request import Request, urlopen

from .config import GITHUB_USERNAME, WEBHOOK_SECRET


def valid_signature(body: bytes, header: str) -> bool:
    """Check GitHub's HMAC-SHA256 signature so only GitHub can publish."""
    if not WEBHOOK_SECRET:
        return False
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    expected = ("sha256=" + digest).encode()
    return hmac.compare_digest(expected, (header or "").encode())


def summarise(markdown: str, limit: int = 200) -> str:
    """First plain paragraph of a README, trimmed.

    This is extraction, not AI. When you want real summaries, replace this one
    function with an LLM call and nothing else in the project has to change.
    """
    paragraph, in_code = [], False
    for line in markdown.splitlines():
        line = line.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        skip = in_code or not line or line.startswith(("#", "![", "[![", "<", "|", "---"))
        if skip:
            if paragraph:
                break
            continue
        paragraph.append(line)

    # Drop bold/code markers and turn [text](url) links into plain text.
    text = re.sub(r"[*`]|\[([^\]]*)\]\([^)]*\)", r"\1", " ".join(paragraph))
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def fetch_readme_summary(repo_name: str):
    for branch in ("main", "master"):
        url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{repo_name}/{branch}/README.md"
        try:
            with urlopen(url, timeout=10) as resp:
                return summarise(resp.read().decode("utf-8", "replace"))
        except OSError:  # 404, timeout, no network
            continue
    return None


def list_repos():
    url = f"https://api.github.com/users/{GITHUB_USERNAME}/repos?per_page=100&sort=pushed"
    request = Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "portfolio-api"},
    )
    with urlopen(request, timeout=10) as resp:
        return json.load(resp)