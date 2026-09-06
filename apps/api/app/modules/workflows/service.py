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
    WorkflowTemplate,
    WorkflowTemplateVersion,
)


class WorkflowEditError(Exception):
    """Raised when an edit to a workflow version is not allowed (e.g. it is approved)."""


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
            cfg = st.config or {}
            stage = JobWorkflowStage(
                job_workflow_version_id=version.id,
                stage_order=st.stage_order,
                name=st.name,
                purpose=cfg.get("purpose"),
                execution_type=st.execution_type,
                information_requirements=list(cfg.get("information_requirements") or []),
                requires_human_approval=bool(cfg.get("requires_human_approval", False)),
            )
            self._s.add(stage)
            self._s.flush()
            for c in cfg.get("criteria") or []:
                self._s.add(
                    StageCriteria(
                        job_workflow_stage_id=stage.id,
                        name=c["name"], kind=c.get("kind", "numeric"), weight=c.get("weight"),
                    )
                )
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="workflow.adopted_template", entity_type="job_workflow_version",
            entity_id=version.id, meta={"template_version_id": str(template_version.id)},
        )
        return version

    def replace_stages(self, version: JobWorkflowVersion, stages: list[dict]) -> JobWorkflowVersion:
        """Replace all stages + criteria of an UNAPPROVED version (recruiter review/customize).

        Stage order is normalized to the given sequence. Raises WorkflowEditError if the version
        is already approved (edits to an approved workflow require a new version)."""
        if version.approved:
            raise WorkflowEditError("This workflow is approved; edits require a new version.")
        for existing in self._s.scalars(
            select(JobWorkflowStage).where(JobWorkflowStage.job_workflow_version_id == version.id)
        ).all():
            self._s.delete(existing)  # criteria cascade via FK ON DELETE CASCADE
        self._s.flush()
        for i, sd in enumerate(stages, start=1):
            stage = JobWorkflowStage(
                job_workflow_version_id=version.id,
                stage_order=i,
                name=sd["name"],
                purpose=sd.get("purpose"),
                execution_type=sd["execution_type"],
                information_requirements=list(sd.get("information_requirements") or []),
                requires_human_approval=bool(sd.get("requires_human_approval", False)),
            )
            self._s.add(stage)
            self._s.flush()
            for c in sd.get("criteria") or []:
                self._s.add(
                    StageCriteria(
                        job_workflow_stage_id=stage.id,
                        name=c["name"], kind=c.get("kind", "numeric"), weight=c.get("weight"),
                    )
                )
        self._s.flush()
        job = self._s.get(Job, self._job_id_for_version(version))
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="workflow.stages_edited", entity_type="job_workflow_version",
            entity_id=version.id, meta={"stage_count": len(stages)},
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


class WorkflowTemplateNotFound(Exception):
    """Raised when a funnel (workflow template) does not exist for the org."""


def _stage_config(sd: dict) -> dict:
    """Rich stage fields (beyond name + execution_type) live in the stage template's JSONB
    config, so no per-column migration is needed as the stage shape evolves."""
    return {
        "purpose": sd.get("purpose"),
        "information_requirements": list(sd.get("information_requirements") or []),
        "requires_human_approval": bool(sd.get("requires_human_approval", False)),
        "criteria": [
            {"name": c["name"], "kind": c.get("kind", "numeric"), "weight": c.get("weight")}
            for c in (sd.get("criteria") or [])
            if str(c.get("name", "")).strip()
        ],
    }


class WorkflowTemplateService:
    """Org-owned reusable hiring funnels (workflow templates). Editing stages always creates a
    NEW template version so a job that already adopted an earlier version stays stable. Does
    not commit; the caller owns the transaction."""

    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id

    def _template_or_none(self, org_id: UUID, template_id: UUID) -> WorkflowTemplate | None:
        t = self._s.get(WorkflowTemplate, template_id)
        return t if t is not None and t.org_id == org_id else None

    def _template_or_raise(self, org_id: UUID, template_id: UUID) -> WorkflowTemplate:
        t = self._template_or_none(org_id, template_id)
        if t is None:
            raise WorkflowTemplateNotFound("Funnel not found.")
        return t

    def latest_version(self, template_id: UUID) -> WorkflowTemplateVersion | None:
        return self._s.scalars(
            select(WorkflowTemplateVersion)
            .where(WorkflowTemplateVersion.template_id == template_id)
            .order_by(WorkflowTemplateVersion.version.desc())
            .limit(1)
        ).first()

    def stages_for_version(self, version_id: UUID) -> list[WorkflowStageTemplate]:
        return list(
            self._s.scalars(
                select(WorkflowStageTemplate)
                .where(WorkflowStageTemplate.template_version_id == version_id)
                .order_by(WorkflowStageTemplate.stage_order.asc())
            )
        )

    def list_templates(self, org_id: UUID, include_archived: bool = False):
        """Return [(template, latest_version, stage_count)] newest-first."""
        q = select(WorkflowTemplate).where(WorkflowTemplate.org_id == org_id)
        if not include_archived:
            q = q.where(WorkflowTemplate.archived_at.is_(None))
        templates = list(self._s.scalars(q.order_by(WorkflowTemplate.created_at.desc())))
        out = []
        for t in templates:
            v = self.latest_version(t.id)
            count = (
                self._s.scalar(
                    select(func.count())
                    .select_from(WorkflowStageTemplate)
                    .where(WorkflowStageTemplate.template_version_id == v.id)
                )
                if v is not None
                else 0
            )
            out.append((t, v, count))
        return out

    def _write_stages(self, version_id: UUID, stages: list[dict]) -> None:
        for i, sd in enumerate(stages, start=1):
            self._s.add(
                WorkflowStageTemplate(
                    template_version_id=version_id,
                    stage_order=i,
                    name=sd["name"],
                    execution_type=sd["execution_type"],
                    config=_stage_config(sd),
                )
            )
        self._s.flush()

    def create_template(self, org_id: UUID, name: str, stages: list[dict]) -> WorkflowTemplate:
        template = WorkflowTemplate(org_id=org_id, name=name)
        self._s.add(template)
        self._s.flush()
        version = WorkflowTemplateVersion(template_id=template.id, version=1)
        self._s.add(version)
        self._s.flush()
        self._write_stages(version.id, stages)
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="funnel.created", entity_type="workflow_template", entity_id=template.id,
            meta={"name": name, "stage_count": len(stages)},
        )
        return template

    def edit_stages(self, org_id: UUID, template_id: UUID, stages: list[dict]) -> WorkflowTemplateVersion:
        """Create a NEW version with the given stages (older versions are never mutated)."""
        self._template_or_raise(org_id, template_id)
        current = self.latest_version(template_id)
        next_version = (current.version + 1) if current is not None else 1
        version = WorkflowTemplateVersion(template_id=template_id, version=next_version)
        self._s.add(version)
        self._s.flush()
        self._write_stages(version.id, stages)
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="funnel.stages_edited", entity_type="workflow_template", entity_id=template_id,
            meta={"version": next_version, "stage_count": len(stages)},
        )
        return version

    def rename(self, org_id: UUID, template_id: UUID, name: str) -> WorkflowTemplate:
        t = self._template_or_raise(org_id, template_id)
        t.name = name
        self._s.flush()
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="funnel.renamed", entity_type="workflow_template", entity_id=t.id,
            meta={"name": name},
        )
        return t

    def archive(self, org_id: UUID, template_id: UUID) -> WorkflowTemplate:
        t = self._template_or_raise(org_id, template_id)
        if t.archived_at is None:
            t.archived_at = datetime.now(timezone.utc)
            self._s.flush()
            write_audit(
                self._s, org_id=org_id, actor_user_id=self._actor,
                action="funnel.archived", entity_type="workflow_template", entity_id=t.id,
            )
        return t
