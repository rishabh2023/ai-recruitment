"""Provider-agnostic people-search boundary.

The assignment allows any people-search provider (Apollo.io, People Data Labs,
Proxycurl, Coresignal). Unlike the voice layer (Hunar is the single voice provider),
people search is intentionally multi-provider, so this is a thin abstraction with one
provider implementation active at a time, selected via configuration.

This is a *basic* boundary only: it normalizes results into a common shape and preserves
source provenance. It does not add ranking, enrichment, or persistence — those belong to
platform services. Concrete providers must never leak vendor-specific request/response
shapes past this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class PeopleSearchQuery:
    """Normalized search criteria the platform builds from a job/workflow.

    Fields are intentionally optional: not every provider supports every filter, and a
    provider must ignore (not error on) criteria it cannot honor.
    """

    titles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    seniorities: list[str] = field(default_factory=list)
    min_experience_years: int | None = None
    max_experience_years: int | None = None
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True)
class ExternalCandidate:
    """A single normalized candidate profile.

    Everything except `source` and `source_id` is optional on purpose: externally sourced
    candidates frequently lack a resume, phone, or full history. Missing data is modeled
    as absence, never as an error (see docs/domain.md — progressive profile).
    """

    source: str  # provider key, e.g. "apollo"
    source_id: str  # provider's stable id for provenance
    full_name: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    phone: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)  # untouched provider payload


@dataclass(frozen=True)
class EnrichmentResult:
    """Contact details revealed by an enrichment lookup for one sourced profile.

    Search endpoints return no email/phone (only `has_email`/`has_direct_phone` flags), so a
    separate enrichment step reveals them. Fields are optional: a provider may reveal only an
    email, only a phone, or (when async, e.g. Apollo's webhook flow) nothing synchronously.
    """

    source: str
    source_id: str
    phone: str | None = None
    email: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PeopleSearchResult:
    candidates: list[ExternalCandidate]
    total: int | None  # provider-reported total when available
    page: int
    has_more: bool
    provider: str


class PeopleSearchProvider(Protocol):
    """Interface every people-search provider implements.

    Implementations own auth, request/response shaping, timeouts, and pagination, and
    return normalized types only. They must set provenance (`source`, `source_id`) and
    keep the untouched payload in `raw`.
    """

    #: Stable provider key used in configuration and stored on candidates.
    key: str

    def search(self, query: PeopleSearchQuery) -> PeopleSearchResult: ...

    def enrich(self, source_id: str, *, full_name: str | None = None) -> EnrichmentResult:
        """Reveal contact details for a previously-sourced profile.

        Implementations that cannot enrich synchronously (e.g. Apollo delivers phone via an
        async webhook, or the plan lacks access) must raise, so the caller can degrade with a
        clear message rather than presenting empty contact data as success.
        """
        ...
