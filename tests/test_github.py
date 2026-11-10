import hashlib
import hmac

from app import github

SECRET = b"test-secret"
BODY = b'{"hello": "world"}'
FENCE = "`" * 3


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()


# ---- signature checking ----

def test_valid_signature_is_accepted():
    assert github.valid_signature(BODY, sign(BODY))


def test_wrong_signature_is_rejected():
    assert not github.valid_signature(BODY, "sha256=" + "0" * 64)


def test_missing_signature_is_rejected():
    assert not github.valid_signature(BODY, "")


def test_tampered_body_is_rejected():
    assert not github.valid_signature(b'{"hello": "tampered"}', sign(BODY))


def test_non_ascii_header_is_rejected_without_crashing():
    assert not github.valid_signature(BODY, "sha256=é")


def test_empty_secret_rejects_everything(monkeypatch):
    monkeypatch.setattr(github, "WEBHOOK_SECRET", "")
    assert not github.valid_signature(BODY, sign(BODY))


# ---- README summaries ----

def test_summary_skips_heading_and_badges():
    readme = "# Title\n\n[![build](x.svg)](https://example.com)\n\nA small **FastAPI** service.\n\n## Install\nRun it.\n"
    assert github.summarise(readme) == "A small FastAPI service."


def test_summary_turns_links_into_plain_text():
    assert github.summarise("See [the docs](https://example.com) now.") == "See the docs now."


def test_summary_keeps_underscores_in_names():
    assert "repo_name" in github.summarise("Uses repo_name as the key.")


def test_summary_skips_code_blocks():
    readme = f"{FENCE}\nprint('x')\n{FENCE}\n\nReal text here.\n"
    assert github.summarise(readme) == "Real text here."


def test_long_summary_is_trimmed_at_a_word_boundary():
    result = github.summarise("word " * 100, limit=50)
    assert result.endswith("…")
    assert len(result) <= 51


def test_empty_readme_gives_empty_summary():
    assert github.summarise("") == ""