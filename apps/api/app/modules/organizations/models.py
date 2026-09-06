"""Organizations & users (tenancy)."""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

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


class OrgSettings(Base):
    """Per-organization configuration edited in the Settings screen.

    Holds people-search provider selection + API keys and the outbound-calling safety flag.
    `provider_keys` is a JSON map {provider_key: api_key}; these are secrets and are stored
    server-side only — the API never returns the raw key values, only which providers are
    configured. One row per organization.
    """

    __tablename__ = "org_settings"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    default_people_search_provider = Column(Text)
    provider_keys = Column(JSONB, nullable=False, server_default="{}")
    hunar_live_calls_enabled = Column(Boolean, nullable=False, server_default="false")
    created_at = created_at()
    updated_at = updated_at()
