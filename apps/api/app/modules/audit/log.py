"""Shared audit helper.

Consequential actions across services record an AuditEvent through this one function, so the
audit shape stays consistent (see docs/domain.md — audit requirements).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from .models import AuditEvent


def write_audit(
    session: Session,
    *,
    org_id: UUID,
    action: str,
    entity_type: str,
    entity_id: UUID,
    actor_user_id: UUID | None = None,
    from_state: str | None = None,
    to_state: str | None = None,
    reason: str | None = None,
    meta: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        org_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_state=from_state,
        to_state=to_state,
        reason=reason,
        meta=meta or {},
    )
    session.add(event)
    return event
