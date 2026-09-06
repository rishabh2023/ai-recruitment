"""Audit events (immutable record of consequential actions)."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, created_at, uuid_pk


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(Text, nullable=False)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(UUID(as_uuid=True))
    from_state = Column(Text)
    to_state = Column(Text)
    reason = Column(Text)
    meta = Column("metadata", JSONB, nullable=False, server_default="{}")
    created_at = created_at()
