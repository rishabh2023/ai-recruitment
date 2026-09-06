"""Settings endpoints — per-organization configuration (admin-managed).

- GET /settings  → org name, people-search providers (+ configured flag), default provider,
  live-calling flag, and the team. Any authenticated user may read.
- PUT /settings  → update default provider, live-calling, and provider API keys. Admin only.

Provider API keys are write-only: they are never returned, only their configured state.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    InviteCreatedOut,
    InviteCreateIn,
    PendingInviteOut,
    ProviderOption,
    SettingsOut,
    SettingsUpdateIn,
    SettingsUserOut,
)
from app.config import settings as app_settings
from app.db.session import get_session
from app.integrations.people_search.registry import (
    KNOWN_PROVIDERS,
    PROVIDER_LABELS,
    configured_providers,
)
from app.modules.organizations import invites as invite_svc
from app.modules.organizations.models import Organization
from app.modules.organizations.settings_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


def _require_admin(principal: Principal) -> None:
    if principal.role != "admin":
        raise DomainError("Only an admin can change organization settings.", code="forbidden", status_code=403)


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
        invites=[
            PendingInviteOut(id=i.id, email=i.email, name=i.name, role=i.role,
                             created_at=i.created_at, expires_at=i.expires_at)
            for i in invite_svc.list_pending(session, principal.org_id)
        ],
    )


@router.get("", response_model=SettingsOut)
def get_settings(session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    return _view(session, principal)


@router.post("/invites", response_model=InviteCreatedOut, status_code=201)
def create_invite(body: InviteCreateIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Invite a teammate (admin only). Returns a one-time accept link to share with them."""
    _require_admin(principal)
    try:
        created = invite_svc.create_invite(
            session, org_id=principal.org_id, email=body.email, role=body.role,
            name=body.name, invited_by=principal.user_id,
        )
    except invite_svc.InviteError as exc:
        raise DomainError(str(exc), code="validation_error", status_code=422)
    inv = created.invite
    accept_url = f"{app_settings.web_base_url.rstrip('/')}/accept-invite?token={created.token}"
    return InviteCreatedOut(
        id=inv.id, email=inv.email, name=inv.name, role=inv.role,
        expires_at=inv.expires_at, accept_url=accept_url,
    )


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Revoke a pending invite (admin only)."""
    _require_admin(principal)
    try:
        invite_svc.revoke_invite(session, principal.org_id, invite_id)
    except invite_svc.InviteError as exc:
        raise DomainError(str(exc), code="not_found", status_code=404)


@router.put("", response_model=SettingsOut)
def update_settings(body: SettingsUpdateIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _require_admin(principal)
    svc = SettingsService(session, principal.user_id)
    if body.org_name is not None:
        try:
            svc.rename_organization(principal.org_id, body.org_name)
        except ValueError as exc:
            raise DomainError(str(exc), code="validation_error", status_code=422)
    if body.default_provider is not None and body.default_provider not in KNOWN_PROVIDERS:
        raise DomainError("Unknown people-search provider.", code="validation_error", status_code=422)
    if body.provider_keys:
        for k in body.provider_keys:
            if k not in KNOWN_PROVIDERS:
                raise DomainError(f"Unknown provider '{k}'.", code="validation_error", status_code=422)
    if any(value is not None for value in (body.default_provider, body.live_calls_enabled, body.provider_keys)):
        svc.update(
            principal.org_id,
            default_provider=body.default_provider,
            live_calls_enabled=body.live_calls_enabled,
            provider_keys=body.provider_keys,
        )
    return _view(session, principal)
