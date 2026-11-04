import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BASE_DIR / ".env")
DATABASE_PATH = os.getenv("DATABASE_PATH", "").strip() or str(BASE_DIR / "routewise.db")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "").strip()
SERPAPI_TIMEOUT_SECONDS = max(5, int(os.getenv("SERPAPI_TIMEOUT_SECONDS", "20")))
CORS_ORIGINS = [
    x.strip().rstrip("/") for x in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000,http://localhost:4173,http://127.0.0.1:4173"
    ).split(",") if x.strip()
]

def _int_env(name, default):
    """Blank or malformed values fall back to the default instead of crashing at import."""
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


# --- Meta multimodal evidence engine (all values read from the environment; nothing hard-coded) ---
META_PROVIDER = os.getenv("META_PROVIDER", "meta_model_api").strip().lower()
META_API_KEY = os.getenv("META_API_KEY", "").strip()          # server-side only; never returned to clients
META_MODEL = os.getenv("META_MODEL", "").strip()              # must be chosen explicitly; no default model id is assumed
META_API_BASE_URL = (os.getenv("META_API_BASE_URL", "").strip() or "https://api.meta.ai/v1").rstrip("/")
META_TIMEOUT_SECONDS = max(5, _int_env("META_TIMEOUT_SECONDS", 45))
EVIDENCE_MAX_UPLOAD_BYTES = max(1024, _int_env("EVIDENCE_MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
