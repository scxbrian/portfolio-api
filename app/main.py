"""HTTP routes only. Logic lives in db.py and github.py."""
import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from . import db, github
from .config import ALLOWED_ORIGINS, PUBLISH_TOPIC

app = FastAPI(title="Portfolio API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)
db.init_db()


def readme_changed(event: dict) -> bool:
    """True if any commit in the push added or modified a README."""
    for commit in event.get("commits", []):
        touched = commit.get("added", []) + commit.get("modified", [])
        if any(path.lower() == "readme.md" for path in touched):
            return True
    return False


def handle_push(event: dict) -> str:
    repo = event["repository"]
    name = repo["name"]

    # Only the default branch counts; feature branches shouldn't touch the site.
    if event.get("ref") != f"refs/heads/{repo.get('default_branch', 'main')}":
        return "ignored: not the default branch"

    existing = db.get_project(name)
    summary = repo.get("description")
    if not summary:
        if existing and existing["summary"] and not readme_changed(event):
            summary = existing["summary"]  # README untouched: skip the re-fetch
        else:
            summary = github.fetch_readme_summary(name)

    db.upsert_project({
        "repo_name": name,
        "repo_url": repo["html_url"],
        "language": repo.get("language"),
        "summary": summary,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "published": int(PUBLISH_TOPIC in repo.get("topics", [])),
    })
    return f"stored {name}"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/projects")
def projects():
    return db.list_published()


@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()  # raw bytes: the signature covers exactly these
    if not github.valid_signature(body, request.headers.get("X-Hub-Signature-256", "")):
        raise HTTPException(status_code=401, detail="invalid signature")
    if request.headers.get("X-GitHub-Event") != "push":
        return {"status": "ignored"}
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid JSON")
    result = await run_in_threadpool(handle_push, event)
    return {"status": result}