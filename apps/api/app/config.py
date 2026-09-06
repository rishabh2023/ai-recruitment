"""Application settings (env-driven)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Load env from the repo root .env (base) and an optional apps/api/.env (per-service override),
# regardless of the current working directory. Real environment variables still take precedence
# over both, so exported vars (CI, Docker, tests) win. config.py lives at apps/api/app/config.py.
_APP_DIR = Path(__file__).resolve()
_ROOT_ENV = _APP_DIR.parents[3] / ".env"   # repository root
_API_ENV = _APP_DIR.parents[1] / ".env"    # apps/api/.env (optional local override)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(str(_ROOT_ENV), str(_API_ENV)), extra="ignore")

    database_url: str = "postgresql://recruitment:recruitment@localhost:5432/recruitment"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000"

    # Hunar voice AI (single provider).
    hunar_api_key: str = ""
    hunar_api_base_url: str = "https://api.voice.hunar.ai/external/v1"
    hunar_webhook_signing_key: str = ""
    # Agent used for AI stages that have no explicit HunarAgentConfig (demo/default).
    hunar_default_agent_id: str = ""
    # Public base URL of THIS API (e.g. an https tunnel in dev). When set, outbound calls
    # register Hunar webhook callbacks so status/result/recording come back automatically.
    public_base_url: str = ""
    # Safety switch: real outbound calls are placed ONLY when this is true (and a key is set).
    # Off by default so tests/dev never dial a real number unintentionally.
    hunar_live_calls_enabled: bool = False

    # Celery: eager runs tasks inline (no worker/broker needed) — the dev default. Set to
    # false in production and run a worker against redis_url.
    celery_task_always_eager: bool = True

    # Session-cookie auth. `session_cookie_secure` must be True in production (HTTPS);
    # left False so the cookie works over plain-HTTP localhost during development.
    session_cookie_name: str = "session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 12

    # People search (Flow B). Multi-provider by design (ADR-0001). `sample` is an offline,
    # no-key provider used to keep sourcing demonstrable while a paid Apollo key is
    # unavailable; set to `apollo` (with APOLLO_API_KEY) once a plan with Search access exists.
    # When a real provider is configured but unreachable/plan-gated, SourcingService falls back
    # to the sample provider and clearly flags the results as sample data.
    people_search_provider: str = "sample"
    apollo_api_key: str = ""

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
