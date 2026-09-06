"""Inbound webhook events (idempotent)."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, uuid_pk


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = uuid_pk()
    provider = Column(Text, nullable=False, server_default="hunar")
    event_type = Column(Text, nullable=False)
    dedup_key = Column(Text, nullable=False)
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"))
    raw = Column(JSONB, nullable=False, server_default="{}")
    signature_valid = Column(Boolean)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("provider", "dedup_key"),)  # idempotency
