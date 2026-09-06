"""Jobs & job versions."""

from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, Text, UniqueConstraint, Boolean, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, created_at, updated_at, uuid_pk


class Job(Base):
    __tablename__ = "jobs"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="draft")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = created_at()
    updated_at = updated_at()

    __table_args__ = (
        CheckConstraint("status IN ('draft','active','archived')", name="status_valid"),
    )


class JobVersion(Base):
    __tablename__ = "job_versions"

    id = uuid_pk()
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    jd_text = Column(Text)
    extracted = Column(JSONB, nullable=False, server_default="{}")
    confirmed = Column(Boolean, nullable=False, server_default="false")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = created_at()

    __table_args__ = (UniqueConstraint("job_id", "version"),)
