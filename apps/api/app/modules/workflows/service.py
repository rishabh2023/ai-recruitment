"""WorkflowService — resolve/draft a job's hiring workflow and approve it.

Drafts are produced from the LLM adapter (or an org template) and are always **unapproved**
until a human approves them (docs/intent.md: consequential AI-generated configuration requires
human approval). Persists a per-job versioned workflow snapshot so later template edits do not
change a running job (docs/architecture.md §45.4). Does not commit.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.llm import ExtractedJob, LLMProvider, get_llm_provider
from app.modules.audit.log import write_audit
from app.modules.jobs.models import Job

from .models import (
    JobWorkflow,
    JobWorkflowStage,
    JobWorkflowVersion,
    StageCriteria,
    WorkflowStageTemplate,
    WorkflowTemplateVersion,
)


class WorkflowService:
    def __init__(
        self,
        session: Session,
        actor_user_id: UUID | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self._s = session
        self._actor = actor_user_id
        self._llm = llm or get_llm_provider()

    def _get_or_create_job_workflow(self, job: Job) -> JobWorkflow:
        jw = self._s.scalars(
            select(JobWorkflow).where(JobWorkflow.job_id == job.id)
        ).first()
        if jw is None:
            jw = JobWorkflow(job_id=job.id)
            self._s.add(jw)
            self._s.flush()
        return jw

    def _next_version(self, job_workflow_id: UUID) -> int:
        return (
            self._s.scalar(
                select(func.coalesce(func.max(JobWorkflowVersion.version), 0)).where(
                    JobWorkflowVersion.job_workflow_id == job_workflow_id
                )
            )
            + 1
        )

    def draft_workflow_for_job(self, job: Job, extracted: ExtractedJob) -> JobWorkflowVersion:
        """Create an UNAPPROVED workflow version with stages + criteria drafted by the LLM."""
        jw = self._get_or_create_job_workflow(job)
        version = JobWorkflowVersion(
            job_workflow_id=jw.id, version=self._next_version(jw.id), approved=False
        )
        self._s.add(version)
        self._s.flush()

        for ds in self._llm.draft_workflow(extracted):
            stage = JobWorkflowStage(
                job_workflow_version_id=version.id,
                stage_order=ds.order,
                name=ds.name,
                purpose=ds.purpose,
                execution_type=ds.execution_type,
                information_requirements=list(ds.information_requirements),
            )
            self._s.add(stage)
            self._s.flush()
            for c in ds.criteria:
                self._s.add(
                    StageCriteria(
                        job_workflow_stage_id=stage.id,
                        name=c.name, kind=c.kind, weight=c.weight, config=c.config,
                    )
                )
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="workflow.drafted", entity_type="job_workflow_version",
            entity_id=version.id, meta={"version": version.version},
        )
        return version

    def adopt_template(self, job: Job, template_version: WorkflowTemplateVersion) -> JobWorkflowVersion:
        """Build an UNAPPROVED job workflow version from an org template's stages."""
        jw = self._get_or_create_job_workflow(job)
        jw.source_template_id = template_version.template_id
        version = JobWorkflowVersion(
            job_workflow_id=jw.id, version=self._next_version(jw.id), approved=False
        )
        self._s.add(version)
        self._s.flush()
        templates = self._s.scalars(
            select(WorkflowStageTemplate)
            .where(WorkflowStageTemplate.template_version_id == template_version.id)
            .order_by(WorkflowStageTemplate.stage_order.asc())
        ).all()
        for st in templates:
            self._s.add(
                JobWorkflowStage(
                    job_workflow_version_id=version.id,
                    stage_order=st.stage_order,
                    name=st.name,
                    execution_type=st.execution_type,
                )
            )
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="workflow.adopted_template", entity_type="job_workflow_version",
            entity_id=version.id, meta={"template_version_id": str(template_version.id)},
        )
        return version

    def approve_workflow_version(
        self, version: JobWorkflowVersion, approver_user_id: UUID
    ) -> JobWorkflowVersion:
        """Human approval gate — required before a job can be activated/provisioned."""
        version.approved = True
        version.approved_by = approver_user_id
        version.approved_at = datetime.now(timezone.utc)
        self._s.flush()
        job = self._s.get(Job, self._job_id_for_version(version))
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=approver_user_id,
            action="workflow.approved", entity_type="job_workflow_version",
            entity_id=version.id, to_state="approved",
        )
        return version

    def _job_id_for_version(self, version: JobWorkflowVersion) -> UUID:
        jw = self._s.get(JobWorkflow, version.job_workflow_id)
        return jw.job_id
