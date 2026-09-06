"""PDL Elasticsearch query construction — the recall-tuning that keeps a realistic JD from
returning zero results. Pure, network-free unit tests over PdlProvider._build_es_query."""

from __future__ import annotations

from app.integrations.people_search.base import PeopleSearchQuery
from app.integrations.people_search.pdl import PdlProvider, _clean_title


def _q(**kw) -> PeopleSearchQuery:
    base = dict(titles=[], keywords=[], locations=[], skills=[], seniorities=[], page=1, page_size=10)
    base.update(kw)
    return PeopleSearchQuery(**base)


def test_clean_title_strips_parentheticals_and_qualifiers():
    assert _clean_title("Full Stack Engineer (MERN)") == "full stack engineer"
    assert _clean_title("Backend Engineer / Platform") == "backend engineer"
    assert _clean_title("Data Analyst, Growth") == "data analyst"


def test_title_uses_match_phrase_not_exact_terms():
    # An exact `terms` keyword match on the raw title matches nobody; a phrase match on the
    # cleaned title matches real-world "full stack engineer" titles.
    q = PdlProvider._build_es_query(_q(titles=["Full Stack Engineer (MERN)"]))
    title_bool = q["bool"]["must"][0]["bool"]
    assert title_bool["should"] == [{"match_phrase": {"job_title": "full stack engineer"}}]
    # PDL rejects an explicit minimum_should_match clause; a should-only bool requires ≥1 by default.
    assert "minimum_should_match" not in title_bool


def test_skills_are_optional_should_not_anded_musts():
    q = PdlProvider._build_es_query(_q(titles=["Engineer"], skills=["JavaScript", "React", "Node"]))
    # Skills live under top-level `should` (boost), never as hard `must` filters.
    assert {"match": {"skills": "javascript"}} in q["bool"]["should"]
    assert all("skills" not in str(m) for m in q["bool"]["must"])


def test_unmappable_seniority_is_dropped_not_filtered():
    # "mid" has no PDL job_title_levels equivalent, so it must not add a filter (which would
    # exclude everyone); "senior" maps through.
    assert all("job_title_levels" not in str(c) for c in PdlProvider._build_es_query(_q(seniorities=["mid"]))["bool"].get("must", []))
    q = PdlProvider._build_es_query(_q(seniorities=["senior"]))
    assert {"terms": {"job_title_levels": ["senior"]}} in q["bool"]["must"]
