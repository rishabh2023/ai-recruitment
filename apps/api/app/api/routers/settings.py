"""Settings endpoints — per-organization configuration (admin-managed).

- GET /settings  → org name, people-search providers (+ configured flag), default provider,
  live-calling flag, and the team. Any authenticated user may read.
- PUT /settings  → update default provider, live-calling, and provider API keys. Admin only.

Provider API keys are write-only: they are never returned, only their configured state.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    ProviderOption,
    SettingsOut,
    SettingsUpdateIn,
    SettingsUserOut,
)
from app.db.session import get_session
from app.integrations.people_search.registry import (
    KNOWN_PROVIDERS,
    PROVIDER_LABELS,
    configured_providers,
)
from app.modules.organizations.models import Organization
from app.modules.organizations.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


def _view(session: Session, principal: Principal) -> SettingsOut:
    svc = SettingsService(session, principal.user_id)
    org = session.get(Organization, principal.org_id)
    env = svc.provider_env(principal.org_id)
    usable = set(configured_providers(env))
    providers = [
        ProviderOption(key=k, label=PROVIDER_LABELS.get(k, k), configured=k in usable)
        for k in KNOWN_PROVIDERS
    ]
    return SettingsOut(
        org_name=org.name if org else "",
        is_admin=principal.role == "admin",
        default_provider=svc.default_provider(principal.org_id),
        providers=providers,
        live_calls_enabled=svc.live_calls_enabled(principal.org_id),
        users=[
            SettingsUserOut(id=u.id, name=u.name, email=u.email, role=u.role)
            for u in svc.list_users(principal.org_id)
        ],
    )


@router.get("", response_model=SettingsOut)
def get_settings(session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    return _view(session, principal)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdateIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    if principal.role != "admin":
        raise DomainError("Only an admin can change organization settings.", code="forbidden", status_code=403)
    if body.default_provider is not None and body.default_provider not in KNOWN_PROVIDERS:
        raise DomainError("Unknown people-search provider.", code="validation_error", status_code=422)
    if body.provider_keys:
        for k in body.provider_keys:
            if k not in KNOWN_PROVIDERS:
                raise DomainError(f"Unknown provider '{k}'.", code="validation_error", status_code=422)
    SettingsService(session, principal.user_id).update(
        principal.org_id,
        default_provider=body.default_provider,
        live_calls_enabled=body.live_calls_enabled,
        provider_keys=body.provider_keys,
    )
    return _view(session, principal)
