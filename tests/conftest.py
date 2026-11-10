"""Test setup. Settings are placed in the environment before the app is
imported, so tests never touch your real .env or your real database."""
import os
import tempfile
from pathlib import Path

os.environ["WEBHOOK_SECRET"] = "test-secret"
os.environ["PUBLISH_TOPIC"] = "portfolio"
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "test.db")