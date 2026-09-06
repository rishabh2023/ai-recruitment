"""SettingsService — per-organization configuration (Settings screen).

Owns the org's people-search provider selection + API keys and the outbound-calling safety
flag. Provider API keys are secrets: they are stored server-side and NEVER returned to the
client — the API exposes only which providers are configured.

Provider keys resolve org-first, then fall back to process config (.env), so a key entered in
Settings takes effect immediately without a redeploy, while env keys still work as a default.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.integrations.people_search.registry import KNOWN_PROVIDERS
from app.modules.audit.log import write_audit

from .models import OrgSettings, User

# Env var name -> settings attribute for the process-level (.env) provider keys.
_ENV_KEY_ATTR = {
    "APOLLO_API_KEY": "apollo_api_key",
    "PDL_API_KEY": "pdl_api_key",
    "PROXYCURL_API_KEY": "proxycurl_api_key",
    "CORESIGNAL_API_KEY": "coresignal_api_key",
}


class SettingsService:
    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id

    def get_or_create(self, org_id: UUID) -> OrgSettings:
        row = self._s.scalars(select(OrgSettings).where(OrgSettings.org_id == org_id)).first()
        if row is None:
            row = OrgSettings(org_id=org_id, provider_keys={}, hunar_live_calls_enabled=False)
            self._s.add(row)
            self._s.flush()
        return row

    def provider_env(self, org_id: UUID) -> dict[str, str]:
        """Provider keys as an env mapping: process config (.env) overlaid by org keys.

        Used by the people-search registry so a key saved in Settings is picked up at once."""
        env: dict[str, str] = {}
        for var, attr in _ENV_KEY_ATTR.items():
            val = getattr(app_settings, attr, "") or ""
            if val.strip():
                env[var] = val
        row = self._s.scalars(select(OrgSettings).where(OrgSettings.org_id == org_id)).first()
        if row:
            for provider_key, api_key in (row.provider_keys or {}).items():
                var = KNOWN_PROVIDERS.get(provider_key)
                if var and (api_key or "").strip():
                    env[var] = api_key
        env["PEOPLE_SEARCH_PROVIDER"] = self.default_provider(org_id, row)
        return env

    def default_provider(self, org_id: UUID, row: OrgSettings | None = None) -> str:
        row = row if row is not None else self._s.scalars(
            select(OrgSettings).where(OrgSettings.org_id == org_id)
        ).first()
        return (row.default_people_search_provider if row and row.default_people_search_provider
                else app_settings.people_search_provider)

    def live_calls_enabled(self, org_id: UUID) -> bool:
        """Org flag OR the process-level safety switch; a real call also still needs a key."""
        row = self._s.scalars(select(OrgSettings).where(OrgSettings.org_id == org_id)).first()
        return bool((row and row.hunar_live_calls_enabled) or app_settings.hunar_live_calls_enabled)

    # --- mutations (admin) ------------------------------------------------------
    def update(
        self,
        org_id: UUID,
        *,
        default_provider: str | None = None,
        live_calls_enabled: bool | None = None,
        provider_keys: dict[str, str | None] | None = None,
    ) -> OrgSettings:
        """Apply Settings changes. `provider_keys` values: a non-empty string sets/replaces a
        key, an empty string or None clears it. Raw keys are never echoed back."""
        row = self.get_or_create(org_id)
        changed: list[str] = []
        if default_provider is not None:
            row.default_people_search_provider = default_provider or None
            changed.append("default_provider")
        if live_calls_enabled is not None:
            row.hunar_live_calls_enabled = bool(live_calls_enabled)
            changed.append("live_calls_enabled")
        if provider_keys is not None:
            keys = dict(row.provider_keys or {})
            for provider_key, api_key in provider_keys.items():
                if provider_key not in KNOWN_PROVIDERS:
                    continue
                if api_key and api_key.strip():
                    keys[provider_key] = api_key.strip()
                    changed.append(f"key:{provider_key}:set")
                else:
                    keys.pop(provider_key, None)
                    changed.append(f"key:{provider_key}:cleared")
            row.provider_keys = keys
        self._s.flush()
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="settings.updated", entity_type="org_settings", entity_id=row.id,
            meta={"changed": changed},  # never logs raw key values
        )
        return row

    def list_users(self, org_id: UUID) -> list[User]:
        return list(
            self._s.scalars(
                select(User).where(User.org_id == org_id).order_by(User.created_at.asc())
            )
        )
