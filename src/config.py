"""Shared paths and GB10 connection settings (read from .env, never hard-coded)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
IMG_DIR = DOCS_DIR / "img"

# Source dataset: https://huggingface.co/datasets/jennifer-fowler/UTSA-flood-images
# Expected beside this project folder unless FLOOD_DATA_DIR is set.
FLOOD_DATA = Path(os.environ.get("FLOOD_DATA_DIR", ROOT.parent / "Texas_Flood_Student_Data"))

SITES_JSON = DATA_DIR / "sites.json"
AI_JSON = DATA_DIR / "ai_results.json"
BRIEFINGS_JSON = DATA_DIR / "briefings.json"


def load_env():
    """Minimal .env reader so no extra dependency is needed."""
    env_file = ROOT / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
    missing = [k for k in ("VLM_BASE_URL", "VLM_MODEL", "VLM_API_KEY") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing {missing}. Copy .env.example to .env and fill it in.")
    return os.environ["VLM_BASE_URL"], os.environ["VLM_MODEL"], os.environ["VLM_API_KEY"]
