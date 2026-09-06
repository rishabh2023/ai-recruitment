"""People Data Labs (PDL) people-search provider.

Second real provider behind the PeopleSearchProvider interface. Contract from PDL docs:

- Search:     POST https://api.peopledatalabs.com/v5/person/search
- Auth:       `X-Api-Key` header
- Body:       Elasticsearch-style {"query": {...}, "size": N, "from": offset} OR {"sql": "..."}
- Response:   {"status":200, "data":[<person>...], "total": N}
- Enrich:     GET  https://api.peopledatalabs.com/v5/person/enrich  (by linkedin/name+company)
              returns emails/phone_numbers when the plan/record allows.

PDL returns real profiles on its free tier (limited monthly credits). Contact fields
(emails, phone) are plan-gated; when absent the platform surfaces that (progressive profile),
never fabricates them. stdlib-only HTTP so the adapter has no extra runtime dependency.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import (
    EnrichmentResult,
    ExternalCandidate,
    PeopleSearchQuery,
    PeopleSearchResult,
)

DEFAULT_BASE_URL = "https://api.peopledatalabs.com/v5"
SEARCH_PATH = "/person/search"
ENRICH_PATH = "/person/enrich"
MAX_SIZE = 100


class PdlError(RuntimeError):
    """Raised when PDL returns a non-2xx response or an unreadable body."""


class PdlProvider:
    key = "pdl"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout_seconds: float = 20.0) -> None:
        if not api_key:
            raise ValueError("PDL_API_KEY is required for the PDL provider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    # --- Public API -------------------------------------------------------------
    def search(self, query: PeopleSearchQuery) -> PeopleSearchResult:
        size = min(max(1, query.page_size), MAX_SIZE)
        body = {
            "query": self._build_es_query(query),
            "size": size,
            "from": (max(1, query.page) - 1) * size,
        }
        payload = self._post(SEARCH_PATH, body)
        return self._build_result(payload, page=query.page, size=size)

    def enrich(self, source_id: str, *, full_name: str | None = None) -> EnrichmentResult:
        """Enrich by PDL id (source_id). Reveals email/phone when the plan/record allows."""
        params = {"pdl_id": source_id, "pretty": "false"}
        payload = self._get(ENRICH_PATH, params)
        person = payload.get("data") or {}
        return EnrichmentResult(
            source="pdl",
            source_id=source_id,
            phone=_first(person.get("phone_numbers")) or person.get("mobile_phone"),
            email=_first(person.get("emails"), key="address") or person.get("work_email"),
            raw=person,
        )

    # --- request/response mapping ----------------------------------------------
    @staticmethod
    def _build_es_query(query: PeopleSearchQuery) -> dict[str, Any]:
        """Map the normalized query to a PDL Elasticsearch bool query.

        Titles/locations are OR-ed within their field; keywords/skills match job title or
        skills. Only documented PDL fields are referenced; unknown filters are omitted.
        """
        must: list[dict[str, Any]] = []
        if query.titles:
            must.append({"terms": {"job_title": [t.lower() for t in query.titles]}})
        if query.locations:
            must.append(
                {"bool": {"should": [{"match": {"location_name": loc.lower()}} for loc in query.locations]}}
            )
        for skill in query.skills:
            must.append({"match": {"skills": skill.lower()}})
        for kw in query.keywords:
            must.append(
                {"bool": {"should": [{"match": {"job_title": kw.lower()}}, {"match": {"skills": kw.lower()}}]}}
            )
        if query.seniorities:
            must.append({"terms": {"job_title_levels": [s.lower() for s in query.seniorities]}})
        return {"bool": {"must": must}} if must else {"bool": {"must": [{"exists": {"field": "linkedin_url"}}]}}

    @staticmethod
    def _to_candidate(person: dict[str, Any]) -> ExternalCandidate:
        location = person.get("location_name") or person.get("job_company_location_name")
        return ExternalCandidate(
            source="pdl",
            source_id=str(person.get("id") or person.get("pdl_id") or ""),
            full_name=person.get("full_name") or None,
            title=person.get("job_title"),
            company=person.get("job_company_name"),
            location=location,
            phone=_first(person.get("phone_numbers")) or person.get("mobile_phone"),
            email=_first(person.get("emails"), key="address") or person.get("work_email"),
            linkedin_url=person.get("linkedin_url"),
            raw=person,
        )

    @staticmethod
    def _build_result(payload: dict[str, Any], page: int, size: int) -> PeopleSearchResult:
        people = payload.get("data") or []
        total = payload.get("total")
        return PeopleSearchResult(
            candidates=[PdlProvider._to_candidate(p) for p in people],
            total=total,
            page=page,
            has_more=bool(total is not None and page * size < total),
            provider="pdl",
        )

    # --- HTTP (stdlib) ----------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url=self._base_url + path, data=data, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json", "X-Api-Key": self._api_key},
        )
        return self._send(req, path)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = self._base_url + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url=url, method="GET", headers={"Accept": "application/json", "X-Api-Key": self._api_key})
        return self._send(req, path)

    def _send(self, req: urllib.request.Request, path: str) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise PdlError(f"PDL {path} HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            raise PdlError(f"PDL {path} request failed: {exc}") from exc


def _first(items: Any, key: str | None = None) -> str | None:
    """First value from a PDL list field (list of strings, or list of dicts with `key`)."""
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if key and isinstance(first, dict):
        return first.get(key)
    return first if isinstance(first, str) else None
