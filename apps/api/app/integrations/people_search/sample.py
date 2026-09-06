"""Sample (offline) people-search provider.

The primary provider, Apollo, gates its Search API behind a paid plan — the current key
returns HTTP 403 (see docs/vendor-capability-matrix.md). To keep the People-Search &
Outreach journey (Flow B) demonstrable end-to-end without a paid key, this provider returns
**deterministic, clearly-labelled sample profiles** shaped exactly like a real provider's
normalized output.

It is never a silent stand-in: results carry `source="sample"` and the SourcingService flags
the response so the UI states plainly that these are sample profiles, not live data. When a
real provider (paid Apollo, PDL, …) is configured and reachable, that path is used instead.

Like the real profiles from Apollo search, sample profiles have no email/phone — those come
from enrichment (Phase 4). Missing data is modelled as absence, never an error.
"""

from __future__ import annotations

from .base import (
    ExternalCandidate,
    PeopleSearchQuery,
    PeopleSearchResult,
)

# A small, realistic bench of profiles across role families. Deterministic and offline.
_BENCH: list[dict[str, str]] = [
    {"id": "s-001", "full_name": "Aarav Mehta", "title": "Forward Deployed Engineer", "company": "Northwind Labs", "location": "Bengaluru, Karnataka, India", "seniority": "senior", "linkedin_url": "https://www.linkedin.com/in/sample-aarav-mehta", "skills": "python fastapi aws llm kubernetes"},
    {"id": "s-002", "full_name": "Priya Nair", "title": "Senior Backend Engineer", "company": "Cobalt Systems", "location": "Pune, Maharashtra, India", "seniority": "senior", "linkedin_url": "https://www.linkedin.com/in/sample-priya-nair", "skills": "python django postgres api distributed-systems"},
    {"id": "s-003", "full_name": "Rohan Gupta", "title": "Solutions Engineer", "company": "Vertex AI Solutions", "location": "Gurugram, Haryana, India", "seniority": "mid", "linkedin_url": "https://www.linkedin.com/in/sample-rohan-gupta", "skills": "customer python integrations cloud problem-solving"},
    {"id": "s-004", "full_name": "Sara Iyer", "title": "Machine Learning Engineer", "company": "Helix Data", "location": "Hyderabad, Telangana, India", "seniority": "mid", "linkedin_url": "https://www.linkedin.com/in/sample-sara-iyer", "skills": "python ml llm pytorch deployment"},
    {"id": "s-005", "full_name": "Vikram Singh", "title": "Staff Software Engineer", "company": "Meridian Cloud", "location": "Bengaluru, Karnataka, India", "seniority": "lead", "linkedin_url": "https://www.linkedin.com/in/sample-vikram-singh", "skills": "system-design backend aws go python"},
    {"id": "s-006", "full_name": "Ananya Rao", "title": "Account Executive", "company": "BrightPath Sales", "location": "Mumbai, Maharashtra, India", "seniority": "mid", "linkedin_url": "https://www.linkedin.com/in/sample-ananya-rao", "skills": "sales saas discovery negotiation quota"},
    {"id": "s-007", "full_name": "Daniel Costa", "title": "Customer Success Manager", "company": "Loop Retention", "location": "Lisbon, Portugal", "seniority": "mid", "linkedin_url": "https://www.linkedin.com/in/sample-daniel-costa", "skills": "customer-success onboarding retention saas"},
    {"id": "s-008", "full_name": "Mei Lin", "title": "Full Stack Engineer", "company": "Cascade Apps", "location": "Singapore", "seniority": "mid", "linkedin_url": "https://www.linkedin.com/in/sample-mei-lin", "skills": "typescript react node python api"},
    {"id": "s-009", "full_name": "Omar Haddad", "title": "Platform Engineer", "company": "Dunes Tech", "location": "Dubai, United Arab Emirates", "seniority": "senior", "linkedin_url": "https://www.linkedin.com/in/sample-omar-haddad", "skills": "kubernetes terraform aws python reliability"},
    {"id": "s-010", "full_name": "Elena Petrova", "title": "Data Engineer", "company": "Aurora Analytics", "location": "Berlin, Germany", "seniority": "mid", "linkedin_url": "https://www.linkedin.com/in/sample-elena-petrova", "skills": "python spark sql etl cloud"},
    {"id": "s-011", "full_name": "Karan Bhatt", "title": "Engineering Manager", "company": "Northwind Labs", "location": "Bengaluru, Karnataka, India", "seniority": "lead", "linkedin_url": "https://www.linkedin.com/in/sample-karan-bhatt", "skills": "leadership backend system-design hiring"},
    {"id": "s-012", "full_name": "Lucia Romano", "title": "Sales Development Representative", "company": "BrightPath Sales", "location": "Milan, Italy", "seniority": "junior", "linkedin_url": "https://www.linkedin.com/in/sample-lucia-romano", "skills": "sales outbound prospecting saas"},
]


class SampleProvider:
    """Offline provider returning deterministic sample profiles filtered by the query."""

    key = "sample"

    def search(self, query: PeopleSearchQuery) -> PeopleSearchResult:
        matched = [p for p in _BENCH if _matches(p, query)]
        # Deterministic order: keep bench order (already curated), then paginate.
        page = max(1, query.page)
        size = max(1, query.page_size)
        start = (page - 1) * size
        window = matched[start : start + size]
        return PeopleSearchResult(
            candidates=[_to_candidate(p) for p in window],
            total=len(matched),
            page=page,
            has_more=start + size < len(matched),
            provider="sample",
        )


def _matches(person: dict[str, str], query: PeopleSearchQuery) -> bool:
    """Loose OR-within-filter, AND-across-filters matching against sample fields.

    A filter with no terms does not constrain. Term comparison is case-insensitive substring,
    which is deliberately forgiving so the demo returns something useful for typical inputs.
    """
    title = person["title"].lower()
    location = person["location"].lower()
    seniority = person["seniority"].lower()
    haystack = f"{title} {person['company'].lower()} {person['skills']} {location}"

    if query.titles and not _any_hit(query.titles, title):
        return False
    if query.locations and not _any_hit(query.locations, location):
        return False
    if query.seniorities and not _any_hit(query.seniorities, seniority):
        return False
    for group in (query.keywords, query.skills):
        if group and not _any_hit(group, haystack):
            return False
    return True


def _any_hit(terms: list[str], haystack: str) -> bool:
    return any(t.strip() and t.strip().lower() in haystack for t in terms)


def _to_candidate(person: dict[str, str]) -> ExternalCandidate:
    return ExternalCandidate(
        source="sample",
        source_id=person["id"],
        full_name=person["full_name"],
        title=person["title"],
        company=person["company"],
        location=person["location"],
        phone=None,  # enrichment-only, mirrors real search behavior
        email=None,
        linkedin_url=person["linkedin_url"],
        raw={"seniority": person["seniority"], "sample": True},
    )
