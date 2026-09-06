"""Request dependencies: DB session + authenticated principal.

Auth is server-side session cookies: `POST /auth/login` validates credentials and sets an
HttpOnly cookie holding an opaque token; here we resolve that token to the principal (org id
and role) on every request. Org id is taken from the session, never from the client body.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Cookie, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_session
from app.modules.organizations.auth import resolve_session

from .errors import DomainError


@dataclass(frozen=True)
class Principal:
    org_id: UUID
    user_id: UUID
    role: str


def get_principal(
    session: Session = Depends(get_session),
    session_cookie: str | None = Cookie(default=None, alias=settings.session_cookie_name),
) -> Principal:
    authed = resolve_session(session, session_cookie)
    if authed is None:
        raise DomainError("Not authenticated.", code="unauthorized", status_code=401)
    return Principal(org_id=authed.org_id, user_id=authed.user_id, role=authed.role)
