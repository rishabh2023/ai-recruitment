"""Candidates, participation, field-level provenance, and stage runs."""

from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base, created_at, updated_at, uuid_pk

_RUN_STATES = (
    "status IN ('PENDING','BLOCKED','READY','SCHEDULED','IN_PROGRESS','AWAITING_RESULT',"
    "'NEEDS_REVIEW','COMPLETED','FAILED','CANCELLED','SKIPPED')"
)


class Candidate(Base):
    __tablename__ = "candidates"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(Text)
    phone = Column(Text)
    email = Column(Text)
    location = Column(Text)
    linkedin_url = Column(Text)
    source = Column(Text)
    source_id = Column(Text)
    created_at = created_at()
    updated_at = updated_at()


class JobCandidate(Base):
    __tablename__ = "job_candidates"

    id = uuid_pk()
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    candidate_id = Column(UUID(as_uuid=True), ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    current_stage_id = Column(UUID(as_uuid=True), ForeignKey("job_workflow_stages.id", ondelete="SET NULL"))
    pipeline_state = Column(Text)
    created_at = created_at()
    updated_at = updated_at()

    __table_args__ = (UniqueConstraint("job_id", "candidate_id"),)


class CandidateStageRun(Base):
    __tablename__ = "candidate_stage_runs"

    id = uuid_pk()
    job_candidate_id = Column(UUID(as_uuid=True), ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False)
    job_workflow_stage_id = Column(UUID(as_uuid=True), ForeignKey("job_workflow_stages.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False, server_default="PENDING")
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    created_at = created_at()
    updated_at = updated_at()

    __table_args__ = (CheckConstraint(_RUN_STATES, name="status_valid"),)


class CandidateFact(Base):
    __tablename__ = "candidate_facts"

    id = uuid_pk()
    job_candidate_id = Column(UUID(as_uuid=True), ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False)
    field_key = Column(Text, nullable=False)
    value = Column(Text)
    source = Column(Text)
    source_stage_run_id = Column(UUID(as_uuid=True), ForeignKey("candidate_stage_runs.id", ondelete="SET NULL"))
    confidence = Column(Text)
    collected_at = created_at()
