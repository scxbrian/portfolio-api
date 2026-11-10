"""All settings come from environment variables (or a local .env file)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "scxbrian")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
PUBLISH_TOPIC = os.getenv("PUBLISH_TOPIC", "portfolio")
DB_PATH = Path(os.getenv("DB_PATH", BASE_DIR / "data" / "portfolio.db"))
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "https://briankennedy.vercel.app,http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if origin.strip()
]