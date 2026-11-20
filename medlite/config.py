"""Runtime settings.

Settings are built explicitly (from the environment plus overrides). Nothing in
the package reads ``sys.argv`` at import time, so importing MedLite from a
research script never inherits that script's command-line flags.
"""
import os
from dataclasses import dataclass, replace
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent
# Historical location beside baseline/med.py, so existing local databases keep working.
DEFAULT_DB_PATH = REPO_ROOT / "baseline" / "med.db"
DEFAULT_MODEL = "qwen2.5:0.5b"          # ~400 MB; any Ollama model name works
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

DISCLAIMER = ("Information only; not medical advice or a diagnosis. A database miss does not establish safety. "
              "Ask a doctor or pharmacist.")


def _env_flag(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    db_path: str = str(DEFAULT_DB_PATH)
    model: str = DEFAULT_MODEL
    ollama_url: str = DEFAULT_OLLAMA_URL
    log_queries: bool = False      # raw questions are only stored when explicitly enabled
    fuzzy: bool = True             # offer spelling suggestions (never auto-applied)
    use_llm: bool = False          # optional plain-language summary via a local model

    @classmethod
    def from_env(cls, **overrides):
        settings = cls(
            db_path=os.environ.get("MEDLITE_DB") or str(DEFAULT_DB_PATH),
            model=os.environ.get("MEDLITE_MODEL") or DEFAULT_MODEL,
            ollama_url=os.environ.get("MEDLITE_OLLAMA_URL") or DEFAULT_OLLAMA_URL,
            log_queries=_env_flag("MEDLITE_LOG_QUERIES"),
        )
        overrides = {key: value for key, value in overrides.items() if value is not None}
        return replace(settings, **overrides)
