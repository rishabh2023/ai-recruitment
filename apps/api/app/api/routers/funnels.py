"""Funnels — org-owned reusable hiring funnels (workflow templates).

A funnel is a reusable stage blueprint. Applying it to a job ("use") copies its stages into
that job's own versioned workflow snapshot, so one funnel can drive many jobs and each job
stays independent. Editing a funnel's stages creates a new funnel version; jobs that already
adopted an earlier version are unaffected until the funnel is re-applied.

Writes (create/edit/rename/archive/use) are admin-only (org configuration); list/view are
available to any member.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.api.errors import DomainError
from app.api.schemas import (
    CriterionOut,
    FunnelCreateIn,
    FunnelDetailOut,
    FunnelPresetOut,
    FunnelRenameIn,
    FunnelStageSpecOut,
    FunnelStagesIn,
    FunnelSummaryOut,
    FunnelUseIn,
    StageEditIn,
    WorkflowVersionOut,
)
from app.db.session import get_session
from app.modules.jobs.models import Job
from app.modules.workflows.models import WorkflowTemplate, WorkflowTemplateVersion
from app.modules.workflows.service import (
    WorkflowService,
    WorkflowTemplateNotFound,
    WorkflowTemplateService,
)

router = APIRouter(prefix="/funnels", tags=["funnels"])

_EXEC_TYPES = {"ai", "human", "system"}
_CRITERION_KINDS = {"numeric", "rule"}


def _require_admin(principal: Principal) -> None:
    if principal.role != "admin":
        raise DomainError("Only an admin can manage funnels.", code="forbidden", status_code=403)


def _validate_stages(stages: list[StageEditIn]) -> None:
    if not stages:
        raise DomainError("A funnel needs at least one stage.", code="validation_error", status_code=422)
    for s in stages:
        if not s.name.strip():
            raise DomainError("Every stage needs a name.", code="validation_error", status_code=422)
        if s.execution_type not in _EXEC_TYPES:
            raise DomainError(f"Invalid execution_type '{s.execution_type}'.", code="validation_error", status_code=422)
        for c in s.criteria:
            if c.kind not in _CRITERION_KINDS:
                raise DomainError(f"Invalid criterion kind '{c.kind}'.", code="validation_error", status_code=422)


def _svc(session: Session, principal: Principal) -> WorkflowTemplateService:
    return WorkflowTemplateService(session, principal.user_id)


def _summary(t: WorkflowTemplate, version: WorkflowTemplateVersion | None, stage_count: int) -> FunnelSummaryOut:
    return FunnelSummaryOut(
        id=t.id, name=t.name, version=version.version if version else 0,
        stage_count=stage_count, archived=t.archived_at is not None, created_at=t.created_at,
    )


def _detail(svc: WorkflowTemplateService, t: WorkflowTemplate) -> FunnelDetailOut:
    version = svc.latest_version(t.id)
    stages = svc.stages_for_version(version.id) if version else []
    out_stages = []
    for st in stages:
        cfg = st.config or {}
        out_stages.append(
            FunnelStageSpecOut(
                stage_order=st.stage_order, name=st.name, purpose=cfg.get("purpose"),
                execution_type=st.execution_type,
                information_requirements=list(cfg.get("information_requirements") or []),
                requires_human_approval=bool(cfg.get("requires_human_approval", False)),
                criteria=[
                    CriterionOut(name=c["name"], kind=c.get("kind", "numeric"), weight=c.get("weight"))
                    for c in (cfg.get("criteria") or [])
                ],
            )
        )
    return FunnelDetailOut(
        id=t.id, name=t.name, version=version.version if version else 0,
        archived=t.archived_at is not None, stages=out_stages,
    )


@router.get("", response_model=list[FunnelSummaryOut])
def list_funnels(
    include_archived: bool = False,
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
):
    svc = _svc(session, principal)
    return [_summary(t, v, n) for (t, v, n) in svc.list_templates(principal.org_id, include_archived)]


@router.post("", response_model=FunnelDetailOut, status_code=201)
def create_funnel(body: FunnelCreateIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _require_admin(principal)
    if not body.name.strip():
        raise DomainError("A funnel needs a name.", code="validation_error", status_code=422)
    _validate_stages(body.stages)
    svc = _svc(session, principal)
    t = svc.create_template(principal.org_id, body.name.strip(), [s.model_dump() for s in body.stages])
    return _detail(svc, t)


@router.get("/presets", response_model=list[FunnelPresetOut])
def list_presets(principal: Principal = Depends(get_principal)):
    """Built-in starter funnels a recruiter can instantiate into their library. Read-only and
    code-defined; using one creates a normal funnel via POST /funnels."""
    from app.modules.workflows.presets import PRESETS

    return [
        FunnelPresetOut(
            key=p["key"], name=p["name"], description=p["description"],
            stages=[
                FunnelStageSpecOut(
                    stage_order=i, name=s["name"], purpose=s.get("purpose"),
                    execution_type=s["execution_type"],
                    information_requirements=list(s.get("information_requirements") or []),
                    requires_human_approval=bool(s.get("requires_human_approval", False)),
                    criteria=[
                        CriterionOut(name=c["name"], kind=c.get("kind", "numeric"), weight=c.get("weight"))
                        for c in (s.get("criteria") or [])
                    ],
                )
                for i, s in enumerate(p["stages"], start=1)
            ],
        )
        for p in PRESETS
    ]


@router.get("/{funnel_id}", response_model=FunnelDetailOut)
def get_funnel(funnel_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    svc = _svc(session, principal)
    t = svc._template_or_none(principal.org_id, funnel_id)
    if t is None:
        raise DomainError("Funnel not found.", code="not_found", status_code=404)
    return _detail(svc, t)


@router.put("/{funnel_id}/stages", response_model=FunnelDetailOut)
def edit_funnel_stages(funnel_id: UUID, body: FunnelStagesIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _require_admin(principal)
    _validate_stages(body.stages)
    svc = _svc(session, principal)
    try:
        svc.edit_stages(principal.org_id, funnel_id, [s.model_dump() for s in body.stages])
    except WorkflowTemplateNotFound:
        raise DomainError("Funnel not found.", code="not_found", status_code=404)
    return _detail(svc, svc._template_or_raise(principal.org_id, funnel_id))


@router.patch("/{funnel_id}", response_model=FunnelDetailOut)
def rename_funnel(funnel_id: UUID, body: FunnelRenameIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _require_admin(principal)
    if not body.name.strip():
        raise DomainError("A funnel needs a name.", code="validation_error", status_code=422)
    svc = _svc(session, principal)
    try:
        t = svc.rename(principal.org_id, funnel_id, body.name.strip())
    except WorkflowTemplateNotFound:
        raise DomainError("Funnel not found.", code="not_found", status_code=404)
    return _detail(svc, t)


@router.post("/{funnel_id}/archive", response_model=FunnelSummaryOut)
def archive_funnel(funnel_id: UUID, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    _require_admin(principal)
    svc = _svc(session, principal)
    try:
        t = svc.archive(principal.org_id, funnel_id)
    except WorkflowTemplateNotFound:
        raise DomainError("Funnel not found.", code="not_found", status_code=404)
    v = svc.latest_version(t.id)
    n = len(svc.stages_for_version(v.id)) if v else 0
    return _summary(t, v, n)


@router.post("/{funnel_id}/use", response_model=WorkflowVersionOut, status_code=201)
def use_funnel(funnel_id: UUID, body: FunnelUseIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    """Adopt this funnel into a job: copy its stages into a new UNAPPROVED workflow version on
    the job. The recruiter reviews and approves it on the job's Workflow tab."""
    _require_admin(principal)
    svc = _svc(session, principal)
    t = svc._template_or_none(principal.org_id, funnel_id)
    if t is None:
        raise DomainError("Funnel not found.", code="not_found", status_code=404)
    version = svc.latest_version(t.id)
    if version is None or not svc.stages_for_version(version.id):
        raise DomainError("This funnel has no stages to apply.", code="conflict", status_code=409)
    job = session.get(Job, body.job_id)
    if job is None or job.org_id != principal.org_id:
        raise DomainError("Job not found.", code="not_found", status_code=404)
    jwv = WorkflowService(session, principal.user_id).adopt_template(job, version)
    return WorkflowVersionOut(id=jwv.id, version=jwv.version, approved=jwv.approved)
