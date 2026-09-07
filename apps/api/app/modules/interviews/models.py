"""Calls, attempts, results, and evaluation scores."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base, created_at, updated_at, uuid_pk

_NORMALIZED = (
    "normalized_status IN ('QUEUED','SCHEDULED','CALLING','CONNECTED','COMPLETED',"
    "'NO_ANSWER','RETRY_SCHEDULED','FAILED','CANCELLED')"
)


class Call(Base):
    __tablename__ = "calls"

    id = uuid_pk()
    job_candidate_id = Column(UUID(as_uuid=True), ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False)
    candidate_stage_run_id = Column(UUID(as_uuid=True), ForeignKey("candidate_stage_runs.id", ondelete="SET NULL"))
    hunar_call_id = Column(Text)
    request_id = Column(Text)
    vendor_status = Column(Text)
    normalized_status = Column(Text)
    created_at = created_at()
    updated_at = updated_at()

    __table_args__ = (CheckConstraint(_NORMALIZED, name="normalized_status_valid"),)


class CallAttempt(Base):
    __tablename__ = "call_attempts"

    id = uuid_pk()
    call_id = Column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    kind = Column(Text, nullable=False)
    vendor_status = Column(Text)
    normalized_status = Column(Text)
    scheduled_at = Column(DateTime(timezone=True))
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    created_at = created_at()

    __table_args__ = (
        UniqueConstraint("call_id", "attempt_number"),
        CheckConstraint("kind IN ('business','infrastructure')", name="kind_valid"),
    )


class StageResult(Base):
    __tablename__ = "stage_results"

    id = uuid_pk()
    candidate_stage_run_id = Column(UUID(as_uuid=True), ForeignKey("candidate_stage_runs.id", ondelete="CASCADE"), nullable=False)
    structured_result = Column(JSONB, nullable=False, server_default="{}")
    recording_url = Column(Text)
    transcript_summary = Column(Text)
    result_schema_version = Column(Text)
    # Platform-LLM recruiter assessment (recommendation + per-criterion notes + summary). Nullable
    # — populated best-effort after the result arrives; null if the LLM was unavailable.
    assessment = Column(JSONB)
    created_at = created_at()


class EvaluationScore(Base):
    __tablename__ = "evaluation_scores"

    id = uuid_pk()
    stage_result_id = Column(UUID(as_uuid=True), ForeignKey("stage_results.id", ondelete="CASCADE"), nullable=False)
    stage_criteria_id = Column(UUID(as_uuid=True), ForeignKey("stage_criteria.id", ondelete="SET NULL"))
    score = Column(Numeric)
    outcome = Column(Text)
    evidence = Column(JSONB, nullable=False, server_default="{}")
    created_at = created_at()
