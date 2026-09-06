"""Organizations & users (tenancy)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, created_at, updated_at, uuid_pk


class Organization(Base):
    __tablename__ = "organizations"

    id = uuid_pk()
    name = Column(Text, nullable=False)
    created_at = created_at()
    updated_at = updated_at()


class User(Base):
    __tablename__ = "users"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(Text, nullable=False)
    name = Column(Text)
    role = Column(Text, nullable=False)
    # Nullable: a user may exist before a password is set (e.g. invited, or legacy bootstrap).
    # A null hash can never authenticate (see security.passwords.verify_password).
    password_hash = Column(Text)
    created_at = created_at()
    updated_at = updated_at()

    __table_args__ = (
        UniqueConstraint("org_id", "email"),
        CheckConstraint("role IN ('recruiter','hiring_manager','admin')", name="role_valid"),
    )


class UserSession(Base):
    """Server-side session backing an HttpOnly cookie.

    The raw session token is returned to the client once (in the cookie) and never stored; only
    its SHA-256 hash lives here, so a database leak cannot be replayed as a live session. A
    session is valid when it is unrevoked and unexpired.
    """

    __tablename__ = "user_sessions"

    id = uuid_pk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(Text, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    created_at = created_at()

    __table_args__ = (Index("ix_user_sessions_user_id", "user_id"),)
