import os


def _csv(name: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, "").split(",") if v.strip()]


def api_keys() -> list[str]:
    # key ids are key_1, key_2, ... in this order
    return _csv("LLM_API_KEYS")


def allowed_origins() -> list[str]:
    return _csv("ALLOWED_ORIGINS") or ["http://localhost:3000"]


def database_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:////data/app.db")
    for prefix in ("sqlite:///",):
        if url.startswith(prefix):
            return url[len(prefix):]
    return url


def model() -> str:
    return os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")


def default_system_prompt() -> str:
    return os.getenv("DEFAULT_SYSTEM_PROMPT", "You are a helpful, concise assistant.")


def simulation_enabled() -> bool:
    return os.getenv("ENABLE_FAILURE_SIMULATION", "false").strip().lower() == "true"


def cache_type() -> str:
    return os.getenv("CACHE_TYPE", "disk")  # disk | local


def cache_dir() -> str:
    return os.getenv("CACHE_DIR", "/data/cache")


def mock_response() -> str | None:
    # Optional: makes litellm answer locally without any provider call (tests, offline demos)
    return os.getenv("LLM_MOCK_RESPONSE") or None
