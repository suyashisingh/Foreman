"""Application configuration loaded from environment variables or a .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Values are read from the environment first,
    then from a .env file in the working directory if present.

    Fields without defaults (e.g. JWT_SECRET_KEY) cause the application to
    raise ``pydantic_core.ValidationError`` at import time if missing — the
    intended fail-fast behaviour.
    """

    # --- Database / cache ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://foreman:foreman_secret@localhost:5434/foreman"
    )
    REDIS_URL: str = "redis://localhost:6380"

    # --- Runtime ---
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # --- JWT ---
    # No default: the app must not start without a real secret key.
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 1440  # 24 h — convenient for dev, override in prod

    # --- Retrieval / embeddings ---
    # No default: the app must not start without a configured embedding provider.
    VOYAGE_API_KEY: str
    # voyage-code-3 is Voyage AI's code-specialized model (1024-dim, optimised for
    # semantic code search) — the natural fit for a codebase-RAG use case.
    VOYAGE_MODEL: str = "voyage-code-3"
    # Where cloned repos are staged on disk before/during chunking.
    REPO_CLONE_DIR: str = "/tmp/foreman-repos"

    # --- Agent / LLM ---
    # No default: the app must not start without a configured LLM provider key.
    GEMINI_API_KEY: str
    # gemini-2.5-flash confirmed working via live E2E testing. gemini-2.0-flash
    # was the original default but its free-tier quota was exhausted/zeroed on
    # the dev account, causing 429s during testing — switching to 2.5-flash
    # resolved it. Change this if your account has quota on 2.0-flash.
    GEMINI_MODEL: str = "gemini-2.5-flash"
    # Selects which LLMClient implementation get_llm_client() returns.
    # Only "gemini" is implemented; add cases to llm_client.py to extend.
    LLM_PROVIDER: str = "gemini"
    # Maximum Coder→Tester retry iterations (used in Part 2 Coder node).
    MAX_CODER_RETRIES: int = 2

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings reads fields from env/file at runtime
