"""Request dependencies: DB session + authenticated principal.

Auth here is a development stub: the principal is taken from `X-Org-Id` / `X-User-Id` headers
and validated against the DB. Real session/token auth replaces this later (docs/interfaces.md).
Use `POST /dev/bootstrap` to create an org + recruiter and get these ids.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.organizations.models import User

from .errors import DomainError


@dataclass(frozen=True)
class Principal:
    org_id: UUID
    user_id: UUID
    role: str


def get_principal(
    session: Session = Depends(get_session),
    x_org_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
) -> Principal:
    if not x_org_id or not x_user_id:
        raise DomainError("Missing X-Org-Id / X-User-Id.", code="unauthorized", status_code=401)
    try:
        org_id, user_id = UUID(x_org_id), UUID(x_user_id)
    except ValueError:
        raise DomainError("X-Org-Id / X-User-Id must be UUIDs.", code="unauthorized", status_code=401)
    user = session.scalars(
        select(User).where(User.id == user_id, User.org_id == org_id)
    ).first()
    if user is None:
        raise DomainError("Principal not found for org.", code="unauthorized", status_code=401)
    return Principal(org_id=org_id, user_id=user_id, role=user.role)
