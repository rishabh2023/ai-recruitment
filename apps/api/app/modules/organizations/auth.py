"""Authentication service: password login and server-side sessions.

Pure of HTTP concerns (no cookies, no FastAPI). The HTTP layer (``app/api``) turns the opaque
token this module issues into an HttpOnly cookie and back. Sessions are stored in Postgres so
they survive restarts and can be revoked explicitly (logout); Redis is reserved for ephemeral
coordination per PROJECT.md.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.security.passwords import verify_password

from .models import User, UserSession

DEFAULT_SESSION_TTL = timedelta(hours=12)
_TOKEN_BYTES = 32


@dataclass(frozen=True)
class AuthedUser:
    org_id: UUID
    user_id: UUID
    role: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate(session: Session, *, email: str, password: str) -> User | None:
    """Return the matching user for valid credentials, else ``None``.

    Email match is case-insensitive. A wrong password and a user with no password set are
    indistinguishable to the caller (both ``None``), avoiding account enumeration.
    """
    user = session.scalars(select(User).where(User.email == email.strip().lower())).first()
    if user is None:
        # Match the cost of a real verification to reduce timing signal.
        verify_password(password, None)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_session(session: Session, *, user: User, ttl: timedelta = DEFAULT_SESSION_TTL) -> str:
    """Create a session row for ``user`` and return the raw token (store in a cookie).

    Only the token's hash is persisted; the raw value is unrecoverable afterwards.
    """
    token = secrets.token_urlsafe(_TOKEN_BYTES)
    row = UserSession(
        user_id=user.id,
        org_id=user.org_id,
        token_hash=_hash_token(token),
        expires_at=_now() + ttl,
    )
    session.add(row)
    session.flush()
    return token


def resolve_session(session: Session, token: str | None) -> AuthedUser | None:
    """Resolve a raw session token to its principal, or ``None`` if invalid/expired/revoked."""
    if not token:
        return None
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    expires_at = row.expires_at
    if expires_at.tzinfo is None:  # stored as UTC; make comparison tz-aware
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= _now():
        return None
    user = session.get(User, row.user_id)
    if user is None:  # user deleted out from under an unexpired session
        return None
    return AuthedUser(org_id=row.org_id, user_id=row.user_id, role=user.role)


def revoke_session(session: Session, token: str | None) -> None:
    """Revoke the session identified by ``token`` (idempotent)."""
    if not token:
        return
    row = session.scalars(
        select(UserSession).where(UserSession.token_hash == _hash_token(token))
    ).first()
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        session.flush()
