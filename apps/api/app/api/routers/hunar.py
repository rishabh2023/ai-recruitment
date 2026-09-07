"""Hunar voice-AI health + key management.

- GET /hunar/health  → current health (cached ~60s; ?refresh=1 forces a live probe). Any
  authenticated user may read. Never returns the key.
- PUT /hunar/key     → admin-only; validates the key against Hunar before saving it durably.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import HunarHealthOut, HunarKeyUpdateIn
from app.db.session import get_session
from app.integrations.hunar import keystore
from app.integrations.hunar.client import HunarError
from app.modules.audit.log import write_audit
from app.redis_client import cache_delete

router = APIRouter(prefix="/hunar", tags=["hunar"])


@router.get("/health", response_model=HunarHealthOut)
def get_health(
    refresh: bool = False,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    return keystore.check_health(session, refresh=refresh)


def _require_admin(principal: Principal) -> None:
    if principal.role != "admin":
        raise DomainError("Only an admin can update the voice-AI key.", code="forbidden", status_code=403)


@router.put("/key", response_model=HunarHealthOut)
def update_key(
    body: HunarKeyUpdateIn,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    _require_admin(principal)
    candidate = (body.api_key or "").strip()
    if not candidate:
        raise DomainError("Enter a voice-AI key.", code="validation_error", status_code=422)

    # Validate BEFORE persisting: a bad key must never be saved.
    try:
        keystore.build_client(candidate).list_numbers()
    except HunarError as exc:
        if exc.status_code in (401, 403):
            raise DomainError("That key was rejected by the voice-AI provider.", code="validation_error", status_code=422)
        raise DomainError("Couldn't reach the voice-AI provider to verify the key. Try again.", code="bad_gateway", status_code=502)

    keystore.set_override(session, candidate, actor_user_id=principal.user_id)
    write_audit(
        session,
        org_id=principal.org_id,
        action="hunar.key.updated",
        entity_type="hunar_key",
        entity_id=principal.org_id,  # global config; anchor the event to the acting org
        actor_user_id=principal.user_id,
        reason="voice-ai key rotated in-app",
    )
    cache_delete(keystore.HEALTH_CACHE_KEY)
    return keystore.check_health(session, refresh=True)
