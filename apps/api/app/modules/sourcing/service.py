"""SourcingService — Flow B (People Search & Outreach) orchestration.

Responsibilities (platform-owned, per docs/architecture.md §Search/Outreach):

- Suggest a normalized search query from a job's approved/latest JD metadata, so the recruiter
  starts from something useful instead of a blank form.
- Run people search against the provider the recruiter selected (or the configured default),
  across the real providers (Apollo, PDL, Proxycurl, Coresignal). Real data only: a provider
  that is unconfigured, plan-gated (Apollo Free returns 403), or failing raises
  SourcingProviderError with the real reason — the platform never fabricates results.
- Add selected external candidates into the job's pipeline as SOURCED, with provenance
  (`source`, `source_id`), de-duplicating by (source, source_id) within the job so a repeated
  add does not create duplicate participations.

This service does not enrich contacts or place calls — enrichment + outreach calls are Phase 4
and flow through the existing InterviewService/Hunar path once a candidate is in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.integrations.llm import ExtractedJob
from app.integrations.people_search.base import (
    EnrichmentResult,
    ExternalCandidate,
    PeopleSearchQuery,
    PeopleSearchResult,
)
from app.integrations.people_search.registry import (
    PROVIDER_LABELS,
    get_people_search_provider,
)
from app.modules.audit.log import write_audit
from app.modules.candidates.models import Candidate, JobCandidate
from app.modules.organizations.settings_service import SettingsService
from app.modules.candidates.service import CandidateService
from app.modules.jobs.models import Job, JobVersion


def provider_env_from_settings() -> dict[str, str]:
    """Provider API keys as an env mapping, sourced from settings (which loads .env).

    The registry looks up keys by env var name; settings is the single source of truth for
    config, so we hand it the same names. Only non-empty keys are included, so
    `configured_providers` reflects exactly what is usable."""
    values = {
        "APOLLO_API_KEY": settings.apollo_api_key,
        "PDL_API_KEY": settings.pdl_api_key,
        "PROXYCURL_API_KEY": settings.proxycurl_api_key,
        "CORESIGNAL_API_KEY": settings.coresignal_api_key,
    }
    env = {var: val for var, val in values.items() if (val or "").strip()}
    env["PEOPLE_SEARCH_PROVIDER"] = settings.people_search_provider
    return env


class SourcingUnavailableError(RuntimeError):
    """Raised when neither the configured provider nor the fallback can run (unexpected)."""


class SourcingProviderError(RuntimeError):
    """A real people-search provider was unconfigured, plan-gated, or failed. Carries the
    provider key so the API can surface an honest, actionable error (no fabricated data)."""

    def __init__(self, message: str, *, provider: str) -> None:
        super().__init__(message)
        self.provider = provider


@dataclass(frozen=True)
class SearchOutcome:
    result: PeopleSearchResult
    provider: str  # provider that actually produced results
    requested_provider: str  # provider the platform is configured to use
    is_sample: bool  # True when sample data was returned instead of live results
    notice: str | None  # human-readable reason shown to the recruiter when degraded


@dataclass(frozen=True)
class EnrichmentOutcome:
    phone: str | None
    email: str | None
    provider: str  # provider that produced the contact
    requested_provider: str  # provider the candidate was sourced from / configured
    is_sample: bool
    already_had_contact: bool
    notice: str | None


@dataclass(frozen=True)
class SourceCandidateInput:
    source: str
    source_id: str
    full_name: str
    title: str | None = None
    company: str | None = None
    location: str | None = None
    linkedin_url: str | None = None


class SourcingService:
    def __init__(self, session: Session, actor_user_id: UUID | None = None) -> None:
        self._s = session
        self._actor = actor_user_id

    # --- query suggestion -------------------------------------------------------
    def suggest_query(self, job: Job) -> PeopleSearchQuery:
        """Build a starting search query from the job's latest JD metadata (best-effort)."""
        extracted = self._latest_extracted(job)
        titles: list[str] = []
        locations: list[str] = []
        skills: list[str] = []
        seniorities: list[str] = []
        if extracted:
            if extracted.title:
                titles.append(extracted.title)
            if extracted.location:
                locations.append(extracted.location)
            skills = list(extracted.skills or [])[:6]
            seniorities = _seniority_from_experience(
                extracted.experience_min_years, extracted.experience_max_years
            )
        return PeopleSearchQuery(
            titles=titles, locations=locations, skills=skills, seniorities=seniorities
        )

    # --- search -----------------------------------------------------------------
    def search(
        self, job: Job, query: PeopleSearchQuery, requested_provider: str
    ) -> SearchOutcome:
        """Run a real people search against the chosen provider.

        No sample fallback: results come only from the real provider the recruiter selected
        (or the configured default). A provider that is unconfigured, plan-gated, or failing
        raises SourcingProviderError with the real reason — the platform never substitutes
        fabricated data for a failed lookup."""
        requested = (requested_provider or "").lower() or None
        try:
            env = SettingsService(self._s).provider_env(job.org_id)
            provider = get_people_search_provider(requested or env.get("PEOPLE_SEARCH_PROVIDER"), env=env)
        except ValueError as exc:
            raise SourcingProviderError(str(exc), provider=requested or "default") from exc
        try:
            result = provider.search(query)
        except Exception as exc:  # transport / plan gate / vendor error
            reason = _short_reason(exc)
            write_audit(
                self._s, org_id=job.org_id, actor_user_id=self._actor,
                action="sourcing.provider_error", entity_type="job", entity_id=job.id,
                reason=f"{provider.key}: {reason}", meta={"provider": provider.key},
            )
            label = PROVIDER_LABELS.get(provider.key, provider.key)
            raise SourcingProviderError(f"{label} search failed: {reason}", provider=provider.key) from exc
        return SearchOutcome(
            result=result, provider=provider.key, requested_provider=provider.key,
            is_sample=provider.key == "sample", notice=None,
        )

    # --- enrichment (reveal contact for outreach) -------------------------------
    def enrich(self, job_candidate: JobCandidate) -> EnrichmentOutcome:
        """Reveal a sourced candidate's phone/email so an outreach call can be placed.

        Idempotent: if the candidate already has a phone, returns it unchanged. Uses the real
        provider the candidate was sourced from; if that provider cannot enrich (Apollo's async
        webhook / plan gate, or a transport error) it raises SourcingProviderError with the
        real reason — no fabricated contact. Persists phone/email on the Candidate + as facts
        with provenance, moves SOURCED → OUTREACH_PENDING, and audits."""
        candidate = self._s.get(Candidate, job_candidate.candidate_id)
        job = self._s.get(Job, job_candidate.job_id)
        if candidate.phone:
            return EnrichmentOutcome(
                phone=candidate.phone, email=candidate.email, provider=candidate.source or "",
                requested_provider=candidate.source or "", is_sample=candidate.source == "sample",
                already_had_contact=True,
                notice="This candidate already has a contact number.",
            )

        provider_used = (candidate.source or "").lower()
        result = self._run_enrichment(job, provider_used, candidate.source_id or "", candidate.full_name)
        is_sample = provider_used == "sample"
        notice = None

        if result.phone:
            candidate.phone = result.phone
            self.record_fact_on(job_candidate, "phone", result.phone, source=provider_used)
        if result.email and not candidate.email:
            candidate.email = result.email
            self.record_fact_on(job_candidate, "email", result.email, source=provider_used)
        if job_candidate.pipeline_state == "SOURCED":
            job_candidate.pipeline_state = "OUTREACH_PENDING"
        self._s.flush()
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="sourcing.candidate_enriched", entity_type="job_candidate",
            entity_id=job_candidate.id, to_state="OUTREACH_PENDING",
            meta={"provider": provider_used, "is_sample": is_sample,
                  "revealed": [k for k, v in (("phone", result.phone), ("email", result.email)) if v]},
        )
        if not result.phone:
            raise SourcingProviderError(
                f"{PROVIDER_LABELS.get(provider_used, provider_used)} did not return a phone "
                f"number for this candidate (contact reveal may require a paid plan).",
                provider=provider_used,
            )
        return EnrichmentOutcome(
            phone=result.phone, email=result.email, provider=provider_used,
            requested_provider=provider_used, is_sample=is_sample, already_had_contact=False,
            notice=notice,
        )

    def _run_enrichment(self, job: Job, provider_key: str, source_id: str, full_name: str | None):
        """Enrich via the real provider the candidate was sourced from. No fallback."""
        try:
            provider = get_people_search_provider(provider_key, env=SettingsService(self._s).provider_env(job.org_id))
        except ValueError as exc:
            raise SourcingProviderError(str(exc), provider=provider_key or "default") from exc
        try:
            return provider.enrich(source_id, full_name=full_name)
        except Exception as exc:
            reason = _short_reason(exc)
            write_audit(
                self._s, org_id=job.org_id, actor_user_id=self._actor,
                action="sourcing.enrichment_error", entity_type="job", entity_id=job.id,
                reason=f"{provider.key}: {reason}", meta={"provider": provider.key},
            )
            label = PROVIDER_LABELS.get(provider.key, provider.key)
            raise SourcingProviderError(f"{label} enrichment failed: {reason}", provider=provider.key) from exc

    def record_fact_on(self, job_candidate: JobCandidate, key: str, value: str, *, source: str) -> None:
        CandidateService(self._s, self._actor).record_fact(job_candidate, key, value, source=source)

    # --- add to pipeline --------------------------------------------------------
    def add_to_pipeline(
        self, job: Job, selections: list[SourceCandidateInput]
    ) -> list[JobCandidate]:
        """Add selected external candidates to the job as SOURCED. Skips duplicates by
        (source, source_id) already present on this job. Returns the created participations."""
        candidates_svc = CandidateService(self._s, self._actor)
        existing = self._existing_source_ids(job)
        created: list[JobCandidate] = []
        for sel in selections:
            if not sel.full_name.strip():
                continue
            key = (sel.source, sel.source_id)
            if key in existing:
                continue
            existing.add(key)
            known: dict[str, str] = {}
            if sel.title:
                known["current_title"] = sel.title
            if sel.company:
                known["current_company"] = sel.company
            if sel.linkedin_url:
                known["linkedin_url"] = sel.linkedin_url
            jc = candidates_svc.import_candidate(
                job,
                full_name=sel.full_name.strip(),
                location=sel.location,
                source=sel.source,
                source_id=sel.source_id,
                known_facts=known,
            )
            created.append(jc)
        write_audit(
            self._s, org_id=job.org_id, actor_user_id=self._actor,
            action="sourcing.candidates_added", entity_type="job", entity_id=job.id,
            meta={"added": len(created), "requested": len(selections)},
        )
        return created

    # --- helpers ----------------------------------------------------------------
    def _latest_extracted(self, job: Job) -> ExtractedJob | None:
        jv = self._s.scalars(
            select(JobVersion)
            .where(JobVersion.job_id == job.id)
            .order_by(JobVersion.version.desc())
            .limit(1)
        ).first()
        if jv is None or not jv.extracted:
            return None
        try:
            return ExtractedJob(**jv.extracted)
        except TypeError:
            return None

    def _existing_source_ids(self, job: Job) -> set[tuple[str, str]]:
        rows = self._s.execute(
            select(Candidate.source, Candidate.source_id)
            .join(JobCandidate, JobCandidate.candidate_id == Candidate.id)
            .where(JobCandidate.job_id == job.id, Candidate.source_id.is_not(None))
        ).all()
        return {(src or "", sid) for src, sid in rows if sid}


def _seniority_from_experience(lo: int | None, hi: int | None) -> list[str]:
    """Map an experience range to Apollo-style seniority buckets (also honored by sample)."""
    years = hi if hi is not None else lo
    if years is None:
        return []
    if years <= 2:
        return ["junior"]
    if years <= 5:
        return ["mid"]
    if years <= 9:
        return ["senior"]
    return ["lead"]


def _short_reason(exc: Exception) -> str:
    msg = str(exc).strip() or exc.__class__.__name__
    if "403" in msg:
        return "requires a paid plan (HTTP 403)"
    if "API_KEY is required" in msg or "not implemented" in msg.lower():
        return "not configured"
    return msg[:120]
