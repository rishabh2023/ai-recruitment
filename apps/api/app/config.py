"""Application settings (env-driven)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://recruitment:recruitment@localhost:5432/recruitment"
    hunar_webhook_signing_key: str = ""
    cors_origins: str = "http://localhost:3000"

    # Session-cookie auth. `session_cookie_secure` must be True in production (HTTPS);
    # left False so the cookie works over plain-HTTP localhost during development.
    session_cookie_name: str = "session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 12

    # Platform LLM (product intelligence only: JD understanding, role classification, draft
    # workflow/rubric generation). When a key is set, JD extraction uses Claude; otherwise the
    # deterministic offline stub is used so the flow works and tests stay stable.
    platform_llm_api_key: str = ""
    platform_llm_model: str = "claude-haiku-4-5"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
