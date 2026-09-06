"""SourcingService — Flow B (People Search & Outreach) orchestration.

Responsibilities (platform-owned, per docs/architecture.md §Search/Outreach):

- Suggest a normalized search query from a job's approved/latest JD metadata, so the recruiter
  starts from something useful instead of a blank form.
- Run people search against the configured provider. If that provider is unavailable — no key,
  a plan gate (Apollo Free plan returns 403), or a transport error — fall back to the offline
  `sample` provider and **clearly flag** the results as sample data. Never fail silently and
  never present sample data as live.
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

from app.integrations.llm import ExtractedJob
from app.integrations.people_search.base import (
    ExternalCandidate,
    PeopleSearchQuery,
    PeopleSearchResult,
)
from app.integrations.people_search.registry import get_people_search_provider
from app.integrations.people_search.sample import SampleProvider
from app.modules.audit.log import write_audit
from app.modules.candidates.models import Candidate, JobCandidate
from app.modules.candidates.service import CandidateService
from app.modules.jobs.models import Job, JobVersion


class SourcingUnavailableError(RuntimeError):
    """Raised when neither the configured provider nor the fallback can run (unexpected)."""


@dataclass(frozen=True)
class SearchOutcome:
    result: PeopleSearchResult
    provider: str  # provider that actually produced results
    requested_provider: str  # provider the platform is configured to use
    is_sample: bool  # True when sample data was returned instead of live results
    notice: str | None  # human-readable reason shown to the recruiter when degraded


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
        """Run a search, falling back to sample data (clearly flagged) on provider failure."""
        requested = (requested_provider or "sample").lower()
        if requested == "sample":
            result = SampleProvider().search(query)
            return SearchOutcome(
                result=result, provider="sample", requested_provider="sample",
                is_sample=True,
                notice="Showing sample profiles. Configure a live people-search provider to search real candidates.",
            )
        try:
            provider = get_people_search_provider(requested)
            result = provider.search(query)
            return SearchOutcome(
                result=result, provider=requested, requested_provider=requested,
                is_sample=False, notice=None,
            )
        except Exception as exc:  # provider missing/plan-gated/transport — degrade, don't fail
            reason = _short_reason(exc)
            fallback = SampleProvider().search(query)
            write_audit(
                self._s, org_id=job.org_id, actor_user_id=self._actor,
                action="sourcing.provider_unavailable", entity_type="job", entity_id=job.id,
                reason=f"{requested}: {reason}",
                meta={"requested_provider": requested},
            )
            return SearchOutcome(
                result=fallback, provider="sample", requested_provider=requested,
                is_sample=True,
                notice=(
                    f"The {requested.title()} people-search provider is not available "
                    f"({reason}). Showing sample profiles so you can try the flow."
                ),
            )

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
