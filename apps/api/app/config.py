"""Application settings (env-driven)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://recruitment:recruitment@localhost:5432/recruitment"
    hunar_webhook_signing_key: str = ""
    cors_origins: str = "http://localhost:3000"

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        return url.replace("postgresql://", "postgresql+psycopg://", 1) if url.startswith("postgresql://") else url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
