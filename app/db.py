"""SQLite access. Nothing outside this file writes SQL."""
import sqlite3
from contextlib import contextmanager

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    repo_name  TEXT PRIMARY KEY,
    repo_url   TEXT NOT NULL,
    language   TEXT,
    summary    TEXT,
    updated_at TEXT,
    published  INTEGER NOT NULL DEFAULT 0
)
"""

UPSERT = """
INSERT INTO projects (repo_name, repo_url, language, summary, updated_at, published)
VALUES (:repo_name, :repo_url, :language, :summary, :updated_at, :published)
ON CONFLICT(repo_name) DO UPDATE SET
    repo_url   = excluded.repo_url,
    language   = excluded.language,
    summary    = excluded.summary,
    updated_at = excluded.updated_at,
    published  = excluded.published
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.execute(SCHEMA)


def upsert_project(project: dict):
    with connect() as conn:
        conn.execute(UPSERT, project)


def get_project(repo_name: str):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE repo_name = ?", (repo_name,)
        ).fetchone()
    return dict(row) if row else None


def list_published():
    with connect() as conn:
        rows = conn.execute(
            "SELECT repo_name, repo_url, language, summary, updated_at "
            "FROM projects WHERE published = 1 ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]