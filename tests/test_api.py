import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import db, github  # github is used in the next step
from app.main import app

SECRET = b"test-secret"
client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_db():
    """Every test starts with an empty projects table."""
    with db.connect() as conn:
        conn.execute("DELETE FROM projects")


def post_signed(body: bytes, event_type: str = "push"):
    """Send a webhook signed the way GitHub signs it."""
    signature = "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhook",
        content=body,
        headers={"X-GitHub-Event": event_type, "X-Hub-Signature-256": signature},
    )


def push_event(name="demo", topics=("portfolio",), description="A demo project",
               ref="refs/heads/main", commits=None):
    """A minimal fake GitHub push payload."""
    return {
        "ref": ref,
        "commits": commits or [],
        "repository": {
            "name": name,
            "html_url": f"https://github.com/scxbrian/{name}",
            "language": "Python",
            "description": description,
            "default_branch": "main",
            "topics": list(topics),
        },
    }


# ---- basic routes ----

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_projects_starts_empty():
    assert client.get("/api/projects").json() == []


# ---- the locked door ----

def test_unsigned_webhook_is_rejected():
    response = client.post("/webhook", content=b"{}", headers={"X-GitHub-Event": "push"})
    assert response.status_code == 401


def test_wrong_signature_is_rejected():
    response = client.post(
        "/webhook",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": "sha256=" + "0" * 64},
    )
    assert response.status_code == 401


def test_rejected_webhook_stores_nothing():
    body = json.dumps(push_event()).encode()
    client.post("/webhook", content=body, headers={"X-GitHub-Event": "push"})
    assert db.get_project("demo") is None


def test_valid_signature_with_bad_json_is_a_400():
    assert post_signed(b"not json").status_code == 400


def test_non_push_events_are_ignored():
    body = json.dumps(push_event()).encode()
    response = post_signed(body, event_type="ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert db.get_project("demo") is None

    # ---- the publish gate ----

def test_repo_with_topic_is_published():
    response = post_signed(json.dumps(push_event()).encode())
    assert response.json() == {"status": "stored demo"}
    names = [p["repo_name"] for p in client.get("/api/projects").json()]
    assert names == ["demo"]


def test_repo_without_topic_is_stored_but_hidden():
    post_signed(json.dumps(push_event(name="notes", topics=())).encode())
    assert db.get_project("notes") is not None
    assert client.get("/api/projects").json() == []


def test_removing_the_topic_hides_the_project_again():
    post_signed(json.dumps(push_event()).encode())
    post_signed(json.dumps(push_event(topics=())).encode())
    assert client.get("/api/projects").json() == []


# ---- branch filter ----

def test_push_to_other_branch_is_ignored():
    response = post_signed(json.dumps(push_event(ref="refs/heads/feature")).encode())
    assert response.json() == {"status": "ignored: not the default branch"}
    assert db.get_project("demo") is None


# ---- idempotency ----

def test_same_push_twice_makes_one_row():
    body = json.dumps(push_event()).encode()
    post_signed(body)
    post_signed(body)
    assert len(client.get("/api/projects").json()) == 1


# ---- where the summary comes from ----

def test_description_is_used_and_readme_is_not_fetched(monkeypatch):
    def fail(name):
        raise AssertionError("README should not be fetched")

    monkeypatch.setattr(github, "fetch_readme_summary", fail)
    post_signed(json.dumps(push_event(description="From description")).encode())
    assert db.get_project("demo")["summary"] == "From description"


def test_readme_is_the_fallback_when_there_is_no_description(monkeypatch):
    monkeypatch.setattr(github, "fetch_readme_summary", lambda name: "From README")
    post_signed(json.dumps(push_event(description=None)).encode())
    assert db.get_project("demo")["summary"] == "From README"


def test_untouched_readme_is_not_fetched_again(monkeypatch):
    monkeypatch.setattr(github, "fetch_readme_summary", lambda name: "First summary")
    post_signed(json.dumps(push_event(description=None)).encode())

    def fail(name):
        raise AssertionError("README should not be fetched again")

    monkeypatch.setattr(github, "fetch_readme_summary", fail)
    other_commit = [{"added": [], "modified": ["app.py"]}]
    post_signed(json.dumps(push_event(description=None, commits=other_commit)).encode())
    assert db.get_project("demo")["summary"] == "First summary"


def test_changed_readme_is_fetched_again(monkeypatch):
    monkeypatch.setattr(github, "fetch_readme_summary", lambda name: "First summary")
    post_signed(json.dumps(push_event(description=None)).encode())

    monkeypatch.setattr(github, "fetch_readme_summary", lambda name: "Second summary")
    readme_commit = [{"added": [], "modified": ["README.md"]}]
    post_signed(json.dumps(push_event(description=None, commits=readme_commit)).encode())
    assert db.get_project("demo")["summary"] == "Second summary"


# ---- response shape and CORS ----

def test_project_fields_match_the_frontend_contract():
    post_signed(json.dumps(push_event()).encode())
    project = client.get("/api/projects").json()[0]
    assert set(project) == {"repo_name", "repo_url", "language", "summary", "updated_at"}


def test_cors_allows_the_configured_site():
    response = client.get("/api/projects", headers={"Origin": "https://site.test"})
    assert response.headers["access-control-allow-origin"] == "https://site.test"


def test_cors_does_not_allow_other_sites():
    response = client.get("/api/projects", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in response.headers