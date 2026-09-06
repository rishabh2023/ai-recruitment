"""Conversational hiring assistant — a bounded Claude tool-use loop over org-scoped, safe
operations (the same product actions the MCP server exposes, hosted in-process).

Safety posture (first version): read tools run freely; the only mutating tool is create_job
(creates a *draft*, fully reversible). Destructive/consequential actions — delete, archive,
launch calls, candidate decisions — are intentionally NOT exposed to the model; the assistant
directs the user to the relevant screen for those. Every tool is scoped to the caller's org
and uses the request's DB session, so the assistant can never act outside the tenant.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, get_principal
from app.config import settings
from app.db.session import get_session
from app.integrations.llm import ExtractedJob
from app.modules.candidates.models import Candidate, JobCandidate
from app.modules.jobs.models import Job, JobVersion
from app.modules.jobs.service import JobService
from app.modules.workflows.models import JobWorkflow, JobWorkflowVersion
from app.modules.workflows.service import WorkflowService, WorkflowTemplateService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assistant", tags=["assistant"])

_MAX_TOOL_ROUNDS = 8
_SYSTEM = (
    "You are the hiring copilot inside an AI-recruitment console. You lead the user through "
    "hiring one concrete step at a time — never dump a long checklist. Be warm, concise "
    "(2–4 sentences), and always end with the single next action or question. Use a few "
    "tasteful emojis to add warmth and signal state (e.g. 👋 ✅ 🎯 📄 🗂️ 🚀 ⚠️) — one or two per "
    "message, never a wall of them.\n\n"
    "Human-in-the-loop: confirming a job description and drafting a workflow are consequential, "
    "so the app shows the user a Confirm button before those run — don't claim they're done "
    "until the tool result says so. Do NOT approve/activate jobs, delete, archive, launch calls, "
    "or make candidate decisions; guide the user to do those on the relevant screen.\n\n"
    "The happy path for a new role is: (1) create the job, (2) add its job description — the "
    "user can paste the JD text right here in chat, OR click the 📎 to upload a PDF, "
    "(3) confirm the extracted details, (4) draft the hiring workflow, then (5) the user reviews "
    "and approves it and adds candidates on the Jobs screen.\n\n"
    "After you create a job, IMMEDIATELY ask the user to add the job description — tell them they "
    "can paste it here or attach a PDF with the 📎 button. When a JD is added, briefly summarize "
    "what you extracted (title, role family, a few key skills) and ask them to confirm. After "
    "they confirm, offer to draft the workflow. Keep the momentum: each reply moves them forward.\n\n"
    "Use tools to read live data and to perform the create/JD/draft steps. You CANNOT approve or "
    "activate a job, delete or archive, launch calls, or make candidate decisions — for those, "
    "point the user to the relevant screen (Jobs, Candidates, Funnels, Sourcing, Settings). "
    "Never invent data; if a tool returns an error or nothing, say so plainly and suggest the fix. "
    "Refer to jobs by title, never by raw id.\n\n"
    "IMPORTANT: earlier tool results may not be in this conversation, so you often will NOT know a "
    "job's id. Before any tool that needs a job_id (get_job, add_job_description, "
    "confirm_job_description, draft_workflow), call list_jobs first and match the job by its title "
    "to get the correct id. Never guess or fabricate an id."
)

_TOOLS = [
    {"name": "dashboard_summary", "description": "Org counts: active jobs, candidates in pipeline, needs review, awaiting result, failed calls, total jobs.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_jobs", "description": "List the org's jobs with id, title and status (draft/active/archived).", "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_candidates", "description": "List candidate participations across all jobs (name, job, stage, pipeline state).", "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_funnels", "description": "List the org's reusable hiring funnels (name, stage count).", "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_job", "description": "Get one job's current setup: status, whether a JD is added/confirmed, and whether a workflow is drafted. Use this to decide the next step.", "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "create_job", "description": "Create a new job as a DRAFT (title only). Returns the job id. After this, always ask for the job description.", "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}, "required": ["title"]}},
    {"name": "add_job_description", "description": "Attach a pasted job-description text to a job. Creates a new (unconfirmed) JD version and returns the extracted details to summarize. Use when the user pastes JD text in chat.", "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}, "jd_text": {"type": "string"}}, "required": ["job_id", "jd_text"]}},
    {"name": "confirm_job_description", "description": "Confirm the latest JD version for a job (the human gate before drafting a workflow). Call after the user confirms the extracted details look right.", "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
    {"name": "draft_workflow", "description": "Draft a hiring workflow (stages + criteria) for a job whose JD is confirmed. Returns the drafted stage names. The user reviews/approves it on the Jobs screen.", "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"]}},
]


def _parse_uuid(v: object):
    from uuid import UUID
    try:
        return UUID(str(v))
    except (ValueError, TypeError):
        return None


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ApproveAction(BaseModel):
    tool: str
    args: dict = {}


class ChatIn(BaseModel):
    messages: list[ChatMessage]
    approve: ApproveAction | None = None  # a consequential action the user confirmed; run it directly


class ChatLink(BaseModel):
    label: str
    href: str


class PendingAction(BaseModel):
    tool: str
    label: str  # human-readable, e.g. "Confirm the job description for “FDE”"
    args: dict = {}  # resolved args (e.g. {"job_id": ...}) echoed back on approval


class ChatOut(BaseModel):
    reply: str
    links: list[ChatLink] = []
    pending: PendingAction | None = None  # a consequential step awaiting the user's go-ahead


# Consequential tools that require an explicit human go-ahead before they run (human-in-the-loop).
# Reads and create-draft are auto; JD confirmation is a documented approval gate, and drafting a
# workflow generates configuration — both get a confirm step in the UI.
_CONFIRM_TOOLS = {"confirm_job_description", "draft_workflow"}


def _needs_confirmation(tool: str, args: dict, session: Session, org) -> bool:
    """Whether a consequential tool actually needs a human go-ahead now. A confirm on an
    already-confirmed JD is an idempotent no-op, so don't gate it — that lets the model move on
    (e.g. to drafting) in the same turn instead of re-asking."""
    if tool not in _CONFIRM_TOOLS:
        return False
    job = session.get(Job, _parse_uuid(args.get("job_id")))
    if job is None or job.org_id != org:
        return False  # let the tool run and return its own not-found error
    if tool == "confirm_job_description":
        jv = JobService(session).latest_job_version(job)
        return jv is not None and not jv.confirmed
    return True  # draft_workflow: always confirm the generative step


def _confirm_label(tool: str, args: dict, session: Session, org) -> str:
    job = session.get(Job, _parse_uuid(args.get("job_id")))
    title = job.title if (job and job.org_id == org) else "this job"
    if tool == "confirm_job_description":
        return f"Confirm the job description for “{title}” (locks it in as the source of truth)"
    if tool == "draft_workflow":
        return f"Draft the hiring workflow for “{title}”"
    return f"Run {tool}"


def _run_tool(name: str, args: dict, session: Session, principal: Principal, links: list[ChatLink]) -> object:
    org = principal.org_id
    if name == "dashboard_summary":
        jobs = session.scalars(select(Job).where(Job.org_id == org)).all()
        cand = session.scalar(
            select(func.count()).select_from(JobCandidate).join(Job, Job.id == JobCandidate.job_id).where(Job.org_id == org)
        )
        return {
            "total_jobs": len(jobs),
            "active_jobs": sum(1 for j in jobs if j.status == "active"),
            "draft_jobs": sum(1 for j in jobs if j.status == "draft"),
            "candidates_in_pipeline": cand or 0,
        }
    if name == "list_jobs":
        jobs = session.scalars(select(Job).where(Job.org_id == org).order_by(Job.created_at.desc())).all()
        return [{"id": str(j.id), "title": j.title, "status": j.status} for j in jobs]
    if name == "list_candidates":
        rows = session.execute(
            select(Candidate.full_name, Job.title, JobCandidate.pipeline_state)
            .join(Job, Job.id == JobCandidate.job_id)
            .join(Candidate, Candidate.id == JobCandidate.candidate_id)
            .where(Job.org_id == org).order_by(JobCandidate.created_at.desc())
        ).all()
        return [{"name": n, "job": t, "state": s} for (n, t, s) in rows]
    if name == "list_funnels":
        svc = WorkflowTemplateService(session, principal.user_id)
        return [{"name": t.name, "stages": n} for (t, _v, n) in svc.list_templates(org)]
    if name == "create_job":
        title = str(args.get("title", "")).strip()
        if not title:
            return {"error": "A job title is required."}
        job = JobService(session, principal.user_id).create_job(org, title)
        session.flush()  # request boundary (get_session) commits on success
        links.append(ChatLink(label=f"Open “{title}”", href=f"/jobs/{job.id}"))
        return {"created": True, "id": str(job.id), "title": title, "status": "draft",
                "next": "Ask the user for the job description (paste here or upload a PDF with 📎)."}

    # --- tools below act on a specific job; resolve + ownership-check it ---
    job_id = _parse_uuid(args.get("job_id"))
    job = session.get(Job, job_id) if job_id else None
    if name in ("get_job", "add_job_description", "confirm_job_description", "draft_workflow"):
        if job is None or job.org_id != org:
            return {"error": "That job was not found in your organization."}

    svc = JobService(session, principal.user_id)
    if name == "get_job":
        jv = svc.latest_job_version(job)
        wf = session.scalars(select(JobWorkflow).where(JobWorkflow.job_id == job.id)).first()
        approved = False
        if wf:
            approved = bool(session.scalar(
                select(func.count()).select_from(JobWorkflowVersion)
                .where(JobWorkflowVersion.job_workflow_id == wf.id, JobWorkflowVersion.approved.is_(True))
            ))
        return {"title": job.title, "status": job.status,
                "jd_added": jv is not None, "jd_confirmed": bool(jv and jv.confirmed),
                "workflow_drafted": wf is not None, "workflow_approved": approved}

    if name == "add_job_description":
        jd = str(args.get("jd_text", "")).strip()
        if len(jd) < 20:
            return {"error": "The job description looks too short — ask the user to paste the full JD or attach a PDF."}
        jv = svc.add_job_version(job, jd)
        session.flush()
        ex = jv.extracted or {}
        links.append(ChatLink(label=f"Open “{job.title}”", href=f"/jobs/{job.id}"))
        return {"added": True, "version": jv.version, "extracted": {
            "title": ex.get("title"), "role_family": ex.get("role_family"),
            "skills": (ex.get("skills") or [])[:8], "location": ex.get("location"),
        }, "next": "Summarize these details and ask the user to confirm before drafting the workflow."}

    if name == "confirm_job_description":
        jv = svc.latest_job_version(job)
        if jv is None:
            return {"error": "No job description has been added yet."}
        if jv.confirmed:
            return {"already_confirmed": True}
        svc.confirm_job_version(jv)
        session.flush()
        return {"confirmed": True, "next": "Offer to draft the hiring workflow."}

    if name == "draft_workflow":
        jv = svc.latest_job_version(job)
        if jv is None or not jv.confirmed:
            return {"error": "Confirm the job description first, then draft the workflow."}
        wf = session.scalars(select(JobWorkflow).where(JobWorkflow.job_id == job.id)).first()
        if wf and session.scalars(select(JobWorkflowVersion).where(JobWorkflowVersion.job_workflow_id == wf.id)).first():
            return {"error": "This job already has a workflow. The user can review it on the Jobs screen."}
        version = WorkflowService(session, principal.user_id).draft_workflow_for_job(job, ExtractedJob(**jv.extracted))
        session.flush()
        from app.modules.workflows.models import JobWorkflowStage
        stages = session.scalars(
            select(JobWorkflowStage).where(JobWorkflowStage.job_workflow_version_id == version.id)
            .order_by(JobWorkflowStage.stage_order.asc())
        ).all()
        links.append(ChatLink(label=f"Review workflow for “{job.title}”", href=f"/jobs/{job.id}"))
        return {"drafted": True, "stages": [s.name for s in stages],
                "next": "Tell the user the draft is ready to review and approve on the Jobs screen (you can't approve/activate)."}

    return {"error": f"Unknown tool {name}"}


@router.post("/chat", response_model=ChatOut)
def chat(body: ChatIn, session: Session = Depends(get_session), principal: Principal = Depends(get_principal)):
    if not settings.platform_llm_api_key:
        return ChatOut(reply="The assistant needs a Claude API key configured on the server (platform_llm_api_key) to chat. Meanwhile, use the shortcuts below.")

    links: list[ChatLink] = []

    # Human-in-the-loop approval: the user clicked Confirm on a proposed consequential action.
    # Execute exactly that action deterministically (no LLM re-planning), then reply.
    if body.approve is not None:
        if body.approve.tool not in _CONFIRM_TOOLS:
            return ChatOut(reply="⚠️ That action can't be confirmed here.")
        try:
            out = _run_tool(body.approve.tool, body.approve.args or {}, session, principal, links)
        except Exception as exc:
            logger.warning("assistant approved tool %s failed: %s", body.approve.tool, exc)
            return ChatOut(reply=f"⚠️ That didn't work: {exc}")
        if isinstance(out, dict) and out.get("error"):
            return ChatOut(reply=f"⚠️ {out['error']}")
        job = session.get(Job, _parse_uuid((body.approve.args or {}).get("job_id")))
        title = job.title if job else "the job"
        if body.approve.tool == "confirm_job_description":
            return ChatOut(reply=f"✅ Locked in the job description for “{title}”. Want me to draft the hiring workflow next? 🗂️", links=links)
        if body.approve.tool == "draft_workflow":
            stages = " → ".join(out.get("stages", [])) if isinstance(out, dict) else ""
            return ChatOut(reply=f"🗂️ Drafted your workflow: {stages}. Review and approve it on the Jobs screen when you're ready — approval and activation stay in your hands. 🚀", links=links)
        return ChatOut(reply="✅ Done.", links=links)

    import anthropic

    client = anthropic.Anthropic(api_key=settings.platform_llm_api_key, timeout=30.0, max_retries=1)
    messages: list[dict] = [{"role": m.role, "content": m.content} for m in body.messages if m.content.strip()]

    try:
        for _ in range(_MAX_TOOL_ROUNDS):
            resp = client.messages.create(
                model=settings.platform_llm_model, max_tokens=1024,
                system=_SYSTEM, tools=_TOOLS, messages=messages,
            )
            if resp.stop_reason == "tool_use":
                # Human-in-the-loop: if the model wants to run a consequential tool, stop and ask
                # the user to Confirm — the approved action then runs deterministically (above).
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use" and _needs_confirmation(block.name, dict(block.input or {}), session, principal.org_id):
                        pre = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
                        args = dict(block.input or {})
                        label = _confirm_label(block.name, args, session, principal.org_id)
                        return ChatOut(
                            reply=pre or f"Just to confirm — you'd like me to {label.lower()}? ⚠️",
                            links=links, pending=PendingAction(tool=block.name, label=label, args=args),
                        )
                messages.append({"role": "assistant", "content": resp.content})
                results = []
                for block in resp.content:
                    if getattr(block, "type", None) == "tool_use":
                        try:
                            out = _run_tool(block.name, block.input or {}, session, principal, links)
                        except Exception as exc:  # a tool failure is reported to the model, not the user
                            logger.warning("assistant tool %s failed: %s", block.name, exc)
                            out = {"error": str(exc)}
                        results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)})
                messages.append({"role": "user", "content": results})
                continue
            text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
            return ChatOut(reply=text or "Done.", links=links)
        return ChatOut(reply="I did a few steps but couldn't fully finish — try rephrasing or use the shortcuts.", links=links)
    except Exception as exc:
        logger.exception("assistant chat failed")
        return ChatOut(reply=f"Sorry — the assistant hit an error: {exc}", links=links)
