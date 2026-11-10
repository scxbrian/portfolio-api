"""One-time import of your existing repos: python seed.py

Safe to run again at any time. It updates rows instead of duplicating them.
"""
from app import db, github
from app.config import PUBLISH_TOPIC

db.init_db()

for repo in github.list_repos():
    if repo["fork"] or repo["archived"]:
        continue
    published = PUBLISH_TOPIC in repo.get("topics", [])
    db.upsert_project({
        "repo_name": repo["name"],
        "repo_url": repo["html_url"],
        "language": repo["language"],
        "summary": repo["description"] or github.fetch_readme_summary(repo["name"]),
        "updated_at": repo["pushed_at"],
        "published": int(published),
    })
    print(("published " if published else "hidden    ") + repo["name"])