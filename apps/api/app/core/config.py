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
    # No default: must be set via DATABASE_URL env var or .env file.
    # See apps/api/.env.example for the expected format.
    DATABASE_URL: str
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
    # Free-tier Gemini model availability shifted several times during development:
    #   gemini-2.0-flash       → original default; daily quota exhausted on dev account
    #   gemini-2.5-flash       → replacement; only 20 RPD free-tier, exhausted quickly
    #   gemini-2.5-flash-lite  → quota available but too weak for the Coder node:
    #       it read the target file then returned ~29 output tokens ("done") instead
    #       of calling write_file, producing an empty diff every time
    #   gemini-3.5-flash       → exhausted (20 RPD) during Day 4 live testing
    #   gemini-3.1-flash-lite  → current default; confirmed working for structured
    #       output (Planner) and tool calling (Coder) in live Day 4 E2E testing
    # If you hit 429s, probe model availability before switching (see README).
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"
    # Selects which LLMClient implementation get_llm_client() returns.
    # Only "gemini" is implemented; add cases to llm_client.py to extend.
    LLM_PROVIDER: str = "gemini"
    # Maximum Coder→Tester retry iterations (Day 4 retry loop, not the tool loop).
    MAX_CODER_RETRIES: int = 2
    # Maximum tool-call iterations within a single Coder invocation.  Bounds
    # the inner tool-use loop so a confused model cannot loop forever inside
    # one run (distinct from MAX_CODER_RETRIES, which governs Coder↔Tester
    # retries across multiple invocations, coming on Day 4).
    MAX_CODER_TOOL_ITERATIONS: int = 15

    # --- Sandbox (e2b) ---
    # No default: the app must not start without a configured sandbox key.
    E2B_API_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings reads fields from env/file at runtime
