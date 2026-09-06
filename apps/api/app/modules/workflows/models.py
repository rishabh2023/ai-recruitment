"""Workflow templates, per-job workflow snapshot, stages, criteria, calling policy,
and the (recruiter-hidden) Hunar config mapping."""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from app.db.base import Base, created_at, uuid_pk

_EXEC_TYPES = "execution_type IN ('ai','human','system')"


class WorkflowTemplate(Base):
    __tablename__ = "workflow_templates"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    created_at = created_at()


class WorkflowTemplateVersion(Base):
    __tablename__ = "workflow_template_versions"

    id = uuid_pk()
    template_id = Column(UUID(as_uuid=True), ForeignKey("workflow_templates.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    created_at = created_at()

    __table_args__ = (UniqueConstraint("template_id", "version"),)


class WorkflowStageTemplate(Base):
    __tablename__ = "workflow_stage_templates"

    id = uuid_pk()
    template_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_template_versions.id", ondelete="CASCADE"), nullable=False)
    stage_order = Column(Integer, nullable=False)
    name = Column(Text, nullable=False)
    execution_type = Column(Text, nullable=False)
    config = Column(JSONB, nullable=False, server_default="{}")

    __table_args__ = (
        UniqueConstraint("template_version_id", "stage_order"),
        CheckConstraint(_EXEC_TYPES, name="exec_type_valid"),
    )


class CallingPolicy(Base):
    __tablename__ = "calling_policies"

    id = uuid_pk()
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"))
    allowed_days = Column(ARRAY(Text), nullable=False, server_default="{}")
    earliest_call_time = Column(Time)
    last_call_time = Column(Time)
    timezone = Column(Text)
    max_attempts = Column(Integer, nullable=False, server_default="3")
    retry_interval_hours = Column(Integer, nullable=False, server_default="6")
    language = Column(Text)
    created_at = created_at()

    __table_args__ = (
        CheckConstraint("max_attempts >= 0", name="max_attempts_nonneg"),
        CheckConstraint("retry_interval_hours >= 0", name="retry_interval_nonneg"),
    )


class JobWorkflow(Base):
    __tablename__ = "job_workflows"

    id = uuid_pk()
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    source_template_id = Column(UUID(as_uuid=True), ForeignKey("workflow_templates.id", ondelete="SET NULL"))
    created_at = created_at()


class JobWorkflowVersion(Base):
    __tablename__ = "job_workflow_versions"

    id = uuid_pk()
    job_workflow_id = Column(UUID(as_uuid=True), ForeignKey("job_workflows.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    approved = Column(Boolean, nullable=False, server_default="false")
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = Column(DateTime(timezone=True))  # set at approval; nullable
    created_at = created_at()

    __table_args__ = (UniqueConstraint("job_workflow_id", "version"),)


class JobWorkflowStage(Base):
    __tablename__ = "job_workflow_stages"

    id = uuid_pk()
    job_workflow_version_id = Column(UUID(as_uuid=True), ForeignKey("job_workflow_versions.id", ondelete="CASCADE"), nullable=False)
    stage_order = Column(Integer, nullable=False)
    name = Column(Text, nullable=False)
    purpose = Column(Text)
    execution_type = Column(Text, nullable=False)
    information_requirements = Column(JSONB, nullable=False, server_default="[]")
    transition_policy = Column(JSONB, nullable=False, server_default="{}")
    requires_human_approval = Column(Boolean, nullable=False, server_default="false")
    calling_policy_id = Column(UUID(as_uuid=True), ForeignKey("calling_policies.id", ondelete="SET NULL"))

    __table_args__ = (
        UniqueConstraint("job_workflow_version_id", "stage_order"),
        CheckConstraint(_EXEC_TYPES, name="exec_type_valid"),
    )


class StageCriteria(Base):
    __tablename__ = "stage_criteria"

    id = uuid_pk()
    job_workflow_stage_id = Column(UUID(as_uuid=True), ForeignKey("job_workflow_stages.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)
    weight = Column(Numeric)
    config = Column(JSONB, nullable=False, server_default="{}")
    created_at = created_at()

    __table_args__ = (CheckConstraint("kind IN ('numeric','rule')", name="kind_valid"),)


class HunarAgentConfig(Base):
    __tablename__ = "hunar_agent_configs"

    id = uuid_pk()
    job_workflow_stage_id = Column(UUID(as_uuid=True), ForeignKey("job_workflow_stages.id", ondelete="CASCADE"))
    hunar_agent_id = Column(Text, nullable=False)
    configuration_version = Column(Text)
    created_at = created_at()
