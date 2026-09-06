"""JobService — job creation, JD versioning/extraction, confirmation, activation.

Enforces the human-approval gates from docs/intent.md and docs/experience.md:
imperfect JD extraction is never authoritative (recruiter must confirm), and a job cannot be
activated until its JD is confirmed AND a workflow version is approved. Does not commit; the
caller owns the transaction.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.llm import LLMProvider, get_llm_provider
from app.modules.audit.log import write_audit
from app.modules.workflows.models import JobWorkflow, JobWorkflowVersion

from .models import Job, JobVersion


class JobActivationError(Exception):
    """Raised when a job cannot be activated because a gate is unmet."""


class JobService:
    def __init__(
        self,
        session: Session,
        actor_user_id: UUID | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self._s = session
        self._actor = actor_user_id
        self._llm = llm or get_llm_provider()

    def create_job(self, org_id: UUID, title: str) -> Job:
        job = Job(org_id=org_id, title=title, status="draft", created_by=self._actor)
        self._s.add(job)
        self._s.flush()
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="job.created", entity_type="job", entity_id=job.id, to_state="draft",
        )
        return job

    def add_job_version(self, job: Job, jd_text: str) -> JobVersion:
        """Create the next JD version and extract normalized details (unconfirmed)."""
        next_version = (
            self._s.scalar(
                select(func.coalesce(func.max(JobVersion.version), 0)).where(
                    JobVersion.job_id == job.id
                )
            )
            + 1
        )
        extracted = self._llm.extract_job(jd_text)
        jv = JobVersion(
            job_id=job.id,
            version=next_version,
            jd_text=jd_text,
            extracted=extracted.to_dict(),
            confirmed=False,
            created_by=self._actor,
        )
        self._s.add(jv)
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="job.jd_extracted", entity_type="job_version", entity_id=jv.id,
            meta={"version": next_version},
        )
        return jv

    def confirm_job_version(self, job_version: JobVersion) -> JobVersion:
        """Recruiter confirms extracted details — the gate before workflow/provisioning."""
        job = self._s.get(Job, job_version.job_id)
        job_version.confirmed = True
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="job.jd_confirmed", entity_type="job_version", entity_id=job_version.id,
        )
        return job_version

    def latest_job_version(self, job: Job) -> JobVersion | None:
        return self._s.scalars(
            select(JobVersion)
            .where(JobVersion.job_id == job.id)
            .order_by(JobVersion.version.desc())
            .limit(1)
        ).first()

    def activate_job(self, job: Job) -> Job:
        """Activate only when the latest JD is confirmed and a workflow version is approved."""
        jv = self.latest_job_version(job)
        if jv is None or not jv.confirmed:
            raise JobActivationError("Latest JD version must be confirmed before activation.")
        if not self._has_approved_workflow(job):
            raise JobActivationError("An approved workflow version is required before activation.")
        from_state = job.status
        job.status = "active"
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="job.activated", entity_type="job", entity_id=job.id,
            from_state=from_state, to_state="active",
        )
        return job

    def _has_approved_workflow(self, job: Job) -> bool:
        return bool(
            self._s.scalar(
                select(func.count())
                .select_from(JobWorkflowVersion)
                .join(JobWorkflow, JobWorkflow.id == JobWorkflowVersion.job_workflow_id)
                .where(JobWorkflow.job_id == job.id, JobWorkflowVersion.approved.is_(True))
            )
        )
