"""Central configuration, sourced from environment with safe defaults.

Everything tunable lives here so deployment is env-var driven and nothing is
hard-coded across the codebase. Import `settings` and read attributes.

On import we load a local .env file (if present) into the environment, so users
can keep settings in a simple file instead of setting OS env vars. This is a
tiny built-in loader — no third-party dependency required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader: KEY=value lines, '#' comments, optional quotes.

    Looks for a .env file in the current working directory and in the project
    root (two levels up from this file). Does NOT overwrite variables already
    set in the real environment, so hosting platforms still win.
    """
    candidates = [Path.cwd() / ".env",
                  Path(__file__).resolve().parent.parent / ".env"]
    seen = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                # don't clobber real environment variables
                if key and key not in os.environ:
                    os.environ[key] = val
        except OSError:
            pass


_load_dotenv()


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    # data source mode
    use_live_reddit: bool = _env_bool("CITYSCOPE_LIVE_REDDIT", False)
    use_live_rss: bool = _env_bool("CITYSCOPE_LIVE_RSS", False)
    use_live_geocode: bool = _env_bool("CITYSCOPE_LIVE_GEOCODE", False)
    use_live_bluesky: bool = _env_bool("CITYSCOPE_LIVE_BLUESKY", False)

    # caching
    cache_ttl_happenings: int = _env_int("CITYSCOPE_CACHE_TTL", 300)        # 5 min
    cache_ttl_discovery: int = _env_int("CITYSCOPE_DISCOVERY_TTL", 1800)    # 30 min
    cache_max_entries: int = _env_int("CITYSCOPE_CACHE_MAX", 500)

    # persistence + shared cache (both optional; absent -> in-memory fallbacks)
    database_url: str | None = os.environ.get("DATABASE_URL")
    redis_url: str | None = os.environ.get("REDIS_URL")
    # how long persisted happenings stay "fresh" before a refetch is triggered
    happenings_fresh_s: int = _env_int("CITYSCOPE_HAPPENINGS_FRESH", 900)   # 15 min

    # per-source timeouts & retries
    source_timeout_s: float = _env_float("CITYSCOPE_SOURCE_TIMEOUT", 8.0)
    http_retries: int = _env_int("CITYSCOPE_HTTP_RETRIES", 3)
    http_backoff_base_s: float = _env_float("CITYSCOPE_HTTP_BACKOFF", 0.5)

    # reddit
    reddit_client_id: str | None = os.environ.get("REDDIT_CLIENT_ID")
    reddit_client_secret: str | None = os.environ.get("REDDIT_CLIENT_SECRET")
    reddit_username: str = os.environ.get("REDDIT_USERNAME", "unknown")
    reddit_qpm: int = _env_int("CITYSCOPE_REDDIT_QPM", 50)

    # pipeline
    min_confidence: float = _env_float("CITYSCOPE_MIN_CONFIDENCE", 0.5)

    # llm classifier (off by default; keyword fallback otherwise)
    use_llm_classifier: bool = _env_bool("CITYSCOPE_LLM_CLASSIFIER", False)
    anthropic_api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
    llm_model: str = os.environ.get("CITYSCOPE_LLM_MODEL", "claude-haiku-4-5-20251001")

    # server
    log_level: str = os.environ.get("CITYSCOPE_LOG_LEVEL", "INFO")


settings = Settings()
