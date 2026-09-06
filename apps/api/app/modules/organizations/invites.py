"""Team invitations — invite a teammate to an org with a role, and accept the invite.

An admin creates an invite (email + role); the platform returns a one-time token (surfaced as
an accept link) that is shown once and stored only as a hash. The invitee accepts by setting a
password, which creates/activates their user and logs them in. No email is sent — the admin
shares the link — matching the assignment scope (avoid enterprise identity plumbing).

HTTP-free, like auth.py; the API layer turns the returned session token into a cookie.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.security.passwords import hash_password

from .models import User, UserInvite

DEFAULT_INVITE_TTL = timedelta(days=7)
ROLES = ("recruiter", "hiring_manager", "admin")


class InviteError(Exception):
    """Raised for an invalid invite operation (bad role, taken email, bad/expired token)."""


@dataclass(frozen=True)
class CreatedInvite:
    invite: UserInvite
    token: str  # raw token, shown once


@dataclass(frozen=True)
class AcceptedInvite:
    user: User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_invite(
    session: Session, *, org_id: UUID, email: str, role: str, name: str | None,
    invited_by: UUID | None, ttl: timedelta = DEFAULT_INVITE_TTL,
) -> CreatedInvite:
    email = email.strip().lower()
    if not email:
        raise InviteError("An email is required.")
    if role not in ROLES:
        raise InviteError(f"Role must be one of: {', '.join(ROLES)}.")
    if session.scalars(select(User).where(User.email == email)).first() is not None:
        raise InviteError("A user with this email already exists.")
    # Supersede any existing pending invite for the same email in this org.
    for prior in session.scalars(
        select(UserInvite).where(
            UserInvite.org_id == org_id, UserInvite.email == email,
            UserInvite.accepted_at.is_(None), UserInvite.revoked_at.is_(None),
        )
    ).all():
        prior.revoked_at = _now()

    token = secrets.token_urlsafe(32)
    invite = UserInvite(
        org_id=org_id, email=email, name=(name or None), role=role,
        token_hash=_hash_token(token), expires_at=_now() + ttl, invited_by=invited_by,
    )
    session.add(invite)
    session.flush()
    return CreatedInvite(invite=invite, token=token)


def list_pending(session: Session, org_id: UUID) -> list[UserInvite]:
    return list(
        session.scalars(
            select(UserInvite)
            .where(
                UserInvite.org_id == org_id,
                UserInvite.accepted_at.is_(None),
                UserInvite.revoked_at.is_(None),
            )
            .order_by(UserInvite.created_at.desc())
        )
    )


def revoke_invite(session: Session, org_id: UUID, invite_id: UUID) -> None:
    invite = session.get(UserInvite, invite_id)
    if invite is None or invite.org_id != org_id:
        raise InviteError("Invite not found.")
    if invite.accepted_at is None and invite.revoked_at is None:
        invite.revoked_at = _now()
        session.flush()


def peek_invite(session: Session, token: str) -> UserInvite:
    """Return the redeemable invite for a token, or raise (for the accept screen to preview)."""
    invite = session.scalars(
        select(UserInvite).where(UserInvite.token_hash == _hash_token(token))
    ).first()
    if invite is None:
        raise InviteError("This invite link is invalid.")
    if invite.revoked_at is not None:
        raise InviteError("This invite has been revoked.")
    if invite.accepted_at is not None:
        raise InviteError("This invite has already been used.")
    expires = invite.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= _now():
        raise InviteError("This invite has expired.")
    return invite


def accept_invite(session: Session, *, token: str, password: str, name: str | None) -> AcceptedInvite:
    invite = peek_invite(session, token)
    if not password or len(password) < 6:
        raise InviteError("Choose a password of at least 6 characters.")
    if session.scalars(select(User).where(User.email == invite.email)).first() is not None:
        raise InviteError("A user with this email already exists.")
    user = User(
        org_id=invite.org_id, email=invite.email,
        name=(name or invite.name or None), role=invite.role,
        password_hash=hash_password(password),
    )
    session.add(user)
    invite.accepted_at = _now()
    session.flush()
    return AcceptedInvite(user=user)
