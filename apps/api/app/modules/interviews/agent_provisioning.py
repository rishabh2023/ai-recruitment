"""Per-stage voice-agent provisioning (F-009).

Ensures every AI funnel stage is bound to a Hunar agent that understands the stage's intent:
1. already bound (`HunarAgentConfig`) → reuse;
2. an existing account agent matches the role + stage → bind it (reuse, no duplicate);
3. otherwise create one from the stage intent (`agent_spec`) and bind it.

The binding is what `InterviewDispatchService._resolve_agent_id` prefers over the global
`HUNAR_DEFAULT_AGENT_ID`, so provisioning is what makes each role talk with the right agent.
Idempotent: a bound stage is never re-provisioned; matching prefers an existing agent over
creating a duplicate; a low-confidence match is declined in favour of creating a correct agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.hunar.agent_spec import (
    StageIntent,
    agent_profile,
    build_agent_spec,
    stage_intent,
    stage_topics,
)
from app.integrations.hunar.client import HunarClient, HunarError
from app.integrations.llm import LLMProvider, get_llm_provider
from app.modules.audit.log import write_audit
from app.modules.jobs.models import Job
from app.modules.organizations.models import Organization
from app.modules.workflows.models import (
    HunarAgentConfig,
    JobWorkflow,
    JobWorkflowStage,
    JobWorkflowVersion,
    StageCriteria,
)


class AgentProvisioningError(Exception):
    """Raised when a stage could not be bound to an agent (create/list failed)."""


class AgentProvisioningService:
    def __init__(
        self,
        session: Session,
        client: HunarClient,
        *,
        actor_user_id: UUID | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self._s = session
        self._client = client
        self._actor = actor_user_id
        # LLM does the semantic intent match; the deterministic name match is the offline fallback.
        self._llm = llm or get_llm_provider()

    def ensure_stage_agent(self, stage: JobWorkflowStage, *, job_title: str, company: str, org_id: UUID) -> tuple[str, str]:
        """Return (hunar_agent_id, source) where source ∈ {bound, matched, created}.

        Only meaningful for AI stages; callers should skip non-AI stages.
        """
        existing = self._s.scalars(
            select(HunarAgentConfig)
            .where(HunarAgentConfig.job_workflow_stage_id == stage.id)
            .order_by(HunarAgentConfig.created_at.desc())
            .limit(1)
        ).first()
        if existing and (existing.hunar_agent_id or "").strip():
            return existing.hunar_agent_id, "bound"

        criteria = self._s.scalars(
            select(StageCriteria.name).where(StageCriteria.job_workflow_stage_id == stage.id)
        ).all()
        intent = stage_intent(
            job_title=job_title,
            company=company,
            stage_name=stage.name,
            information_requirements=stage.information_requirements,
            purpose=stage.purpose or "",
            criteria=list(criteria),
        )

        agent_id = self._match_existing(intent)
        source = "matched"
        if agent_id is None:
            agent_id = self._create(intent)
            source = "created"

        # Persist the product-safe profile so the UI can show what this stage's agent does and the
        # recruiter can edit it. Accurate for created agents; a faithful description for matched.
        self._s.add(
            HunarAgentConfig(
                job_workflow_stage_id=stage.id, hunar_agent_id=agent_id,
                configuration_version="f009", spec=agent_profile(intent),
            )
        )
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="interview.agent_provisioned", entity_type="job_workflow_stage", entity_id=stage.id,
            meta={"hunar_agent_id": agent_id, "source": source, "role": intent.role, "stage": intent.stage_name},
        )
        self._s.flush()
        return agent_id, source

    # --- helpers ----------------------------------------------------------------
    def _match_existing(self, intent: StageIntent) -> str | None:
        """Reuse an existing account agent that fits this stage's intent, or None to create one.

        Primary path is a semantic LLM match over the ACTIVE agents (role + stage purpose +
        fields to collect). If the LLM is unavailable or declines, a conservative deterministic
        name match is the fallback: the role must appear in the agent's name (so a Sales stage
        never binds a Full-Stack agent), and ambiguity is declined in favour of creating a correct
        agent."""
        try:
            data = self._client.list_agents()
        except HunarError:
            return None
        agents = data.get("results") if isinstance(data, dict) else data
        active = [
            a for a in (agents or [])
            if a.get("id") and (a.get("status") or "ACTIVE").upper() == "ACTIVE"
        ]
        if not active:
            return None
        chosen = self._match_with_llm(intent, active) or self._match_by_name(intent, active)
        # Only reuse an agent that actually collects/assesses everything this stage needs — its
        # information_requirements AND, for interview stages, its success criteria. This stops a
        # screening agent being reused for a Technical Assessment (whose criteria a screener lacks)
        # and stops evidence going unpopulated. A non-covering match is declined → create a fit one.
        required_keys = [key for key, _ in stage_topics(intent)]
        if chosen and not self._covers_requirements(chosen, required_keys):
            return None
        return chosen

    def _match_with_llm(self, intent: StageIntent, active: list[dict]) -> str | None:
        candidates = [
            {"id": a["id"], "name": a.get("name") or "", "objective": a.get("objective")}
            for a in active
        ]
        try:
            chosen = self._llm.match_agent(
                role=intent.role, stage_purpose=intent.purpose or intent.stage_name,
                company=intent.company, collect=list(intent.collect), candidates=candidates,
            )
        except Exception:  # noqa: BLE001 — matching is advisory; never break provisioning on it
            return None
        valid = {str(a["id"]) for a in active}
        return chosen if chosen and str(chosen) in valid else None

    def _match_by_name(self, intent: StageIntent, active: list[dict]) -> str | None:
        role = intent.role.lower().strip()
        if not role:
            return None
        stage_token = intent.stage_name.lower().split()[0] if intent.stage_name else ""
        role_matches: list[str] = []
        for a in active:
            name = (a.get("name") or "").lower()
            if role not in name:
                continue
            if stage_token and (stage_token in name or "screen" in name):
                return a["id"]
            role_matches.append(a["id"])
        return role_matches[0] if len(role_matches) == 1 else None

    def update_stage_agent(
        self,
        stage: JobWorkflowStage,
        *,
        objective: str,
        collects: list[str],
        job_title: str,
        company: str,
        org_id: UUID,
    ) -> "HunarAgentConfig":
        """Edit what a stage's agent does (objective + fields to collect) and push it to the bound
        Hunar agent. The edit is stored on the binding regardless (so it survives a failed push and
        is applied on the next provision); the Hunar update is best-effort and only attempted when
        a live client is available."""
        cfg = self._s.scalars(
            select(HunarAgentConfig)
            .where(HunarAgentConfig.job_workflow_stage_id == stage.id)
            .order_by(HunarAgentConfig.created_at.desc())
            .limit(1)
        ).first()
        if cfg is None or not (cfg.hunar_agent_id or "").strip():
            raise AgentProvisioningError("This stage has no voice agent to edit yet.")

        clean_collects = [str(k).strip() for k in (collects or []) if str(k).strip()]
        intent = stage_intent(
            job_title=job_title, company=company, stage_name=stage.name,
            information_requirements=clean_collects, purpose=stage.purpose or "",
        )
        # Rebuild the full Hunar spec from the edited fields, then apply the recruiter's objective.
        spec = build_agent_spec(intent)
        objective = (objective or "").strip()
        if objective:
            spec["objective"] = objective
        try:
            self._client.update_agent(cfg.hunar_agent_id, spec)
        except Exception as exc:  # noqa: BLE001 — best-effort push; the stored edit must persist
            # Non-fatal (Hunar rejected it, or no key/network): keep the stored edit and record
            # that the live agent wasn't updated, so it can be reconciled at next provision.
            write_audit(
                self._s, org_id=org_id, actor_user_id=self._actor,
                action="interview.agent_update_failed", entity_type="job_workflow_stage",
                entity_id=stage.id, meta={"hunar_agent_id": cfg.hunar_agent_id, "error": str(exc)},
            )

        profile = agent_profile(intent)
        profile["objective"] = spec["objective"]
        cfg.spec = profile
        write_audit(
            self._s, org_id=org_id, actor_user_id=self._actor,
            action="interview.agent_edited", entity_type="job_workflow_stage", entity_id=stage.id,
            meta={"hunar_agent_id": cfg.hunar_agent_id, "collects": clean_collects},
        )
        self._s.flush()
        return cfg

    def _covers_requirements(self, agent_id: str, collect) -> bool:
        """True if the agent's result schema includes every field the stage must collect, so its
        extracted results populate evidence. ``interest``/``interested`` are treated as the same
        field. If the agent can't be fetched, reuse is not blocked (fail open)."""
        required = {str(c).strip().lower() for c in (collect or []) if str(c).strip()}
        if not required:
            return True
        try:
            agent = self._client.get_agent(agent_id)
        except HunarError:
            return True
        schema = agent.get("result_schema")
        keys = schema.keys() if isinstance(schema, dict) else (agent.get("result_variables") or [])
        have = {str(k).strip().lower() for k in keys}

        def canon(s: str) -> str:
            return "interest" if s in ("interest", "interested") else s

        return {canon(r) for r in required}.issubset({canon(k) for k in have})

    def _create(self, intent: StageIntent) -> str:
        spec = build_agent_spec(intent)
        try:
            resp = self._client.create_agent(spec)
        except HunarError as exc:
            raise AgentProvisioningError(f"Could not create a voice agent for '{intent.role} — {intent.stage_name}': {exc}") from exc
        agent_id = str(resp.get("id") or "")
        if not agent_id:
            raise AgentProvisioningError("Hunar create_agent returned no id.")
        return agent_id


@dataclass
class StageAgentResult:
    """Per-stage outcome of a provisioning sweep, for surfacing back to the recruiter."""

    stage_id: UUID
    stage_name: str
    hunar_agent_id: str | None
    source: str | None  # bound | matched | created | None (when errored)
    error: str | None = None


def _job_and_org_for_version(session: Session, version: JobWorkflowVersion) -> tuple[Job, Organization]:
    jw = session.get(JobWorkflow, version.job_workflow_id)
    job = session.get(Job, jw.job_id) if jw else None
    if job is None:
        raise AgentProvisioningError("Workflow version is not attached to a job.")
    org = session.get(Organization, job.org_id)
    if org is None:
        raise AgentProvisioningError("Job is not attached to an organization.")
    return job, org


def provision_version_agents(
    session: Session,
    version: JobWorkflowVersion,
    client: HunarClient,
    *,
    actor_user_id: UUID | None = None,
) -> list[StageAgentResult]:
    """Ensure every AI stage of ``version`` is bound to an on-intent Hunar agent.

    Best-effort per stage: a single stage that fails to provision (Hunar rejects create, etc.)
    records a typed error and does not abort the sweep — the other stages still bind, and the
    failed stage falls back to the default at launch with a surfaced warning. Idempotent: a stage
    already bound is left untouched, so re-approving a funnel never creates duplicates.
    """
    job, org = _job_and_org_for_version(session, version)
    svc = AgentProvisioningService(session, client, actor_user_id=actor_user_id)
    stages = session.scalars(
        select(JobWorkflowStage)
        .where(JobWorkflowStage.job_workflow_version_id == version.id)
        .order_by(JobWorkflowStage.stage_order.asc())
    ).all()

    results: list[StageAgentResult] = []
    for stage in stages:
        if (stage.execution_type or "").lower() != "ai":
            continue  # only AI stages place voice calls
        try:
            agent_id, source = svc.ensure_stage_agent(
                stage, job_title=job.title, company=org.name, org_id=org.id
            )
            results.append(StageAgentResult(stage.id, stage.name, agent_id, source))
        except AgentProvisioningError as exc:
            write_audit(
                session, org_id=org.id, actor_user_id=actor_user_id,
                action="interview.agent_provision_failed", entity_type="job_workflow_stage",
                entity_id=stage.id, meta={"error": str(exc), "stage": stage.name},
            )
            results.append(StageAgentResult(stage.id, stage.name, None, None, error=str(exc)))
    return results


def provisioning_ready(session: Session, org_id: UUID) -> bool:
    """Provisioning creates vendor resources (Hunar agents), so it is gated by the same guard as
    live calls: a Hunar key must be resolvable AND live calls enabled for the org."""
    from app.integrations.hunar.keystore import resolve_api_key
    from app.modules.organizations.settings_service import SettingsService

    api_key, _ = resolve_api_key(session)
    if not api_key:
        return False
    return SettingsService(session).live_calls_enabled(org_id)


def maybe_provision_version_agents(
    session: Session, version: JobWorkflowVersion, *, actor_user_id: UUID | None = None
) -> list[StageAgentResult] | None:
    """Eager provisioning entrypoint used at funnel approval. Returns None (skipped) when the
    live-calls guard is not satisfied, so approval never fails just because Hunar is not
    configured — the stages simply fall back to the default until the guard is on."""
    from app.integrations.hunar.keystore import build_client, resolve_api_key

    try:
        _job, org = _job_and_org_for_version(session, version)
    except AgentProvisioningError:
        return None
    if not provisioning_ready(session, org.id):
        return None
    api_key, _ = resolve_api_key(session)
    return provision_version_agents(
        session, version, build_client(api_key), actor_user_id=actor_user_id
    )
