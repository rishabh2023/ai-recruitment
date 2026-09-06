"""Organizations & users (tenancy)."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, ForeignKey, Text, UniqueConstraint
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
    created_at = created_at()
    updated_at = updated_at()

    __table_args__ = (
        UniqueConstraint("org_id", "email"),
        CheckConstraint("role IN ('recruiter','hiring_manager','admin')", name="role_valid"),
    )
