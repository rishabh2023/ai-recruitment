"""Coresignal people-search provider.

Contract from Coresignal Data API (cdapi) docs:

- Search:  POST https://api.coresignal.com/cdapi/v1/professional_network/employee/search/filter
           Auth: `apikey: <key>` header. Body: documented filters (title, location, ...).
           Returns a JSON array of integer member ids (search returns ids only).
- Collect: GET https://api.coresignal.com/cdapi/v1/professional_network/employee/collect/{id}
           Returns the full member profile (name, title, location, experience).

Because search returns ids only, this adapter collects the first N ids into full profiles
(N bounded to limit credit use). Coresignal is paid/trial; written to the documented
contract. stdlib-only HTTP.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import (
    EnrichmentResult,
    ExternalCandidate,
    PeopleSearchQuery,
    PeopleSearchResult,
)

DEFAULT_BASE_URL = "https://api.coresignal.com/cdapi/v1/professional_network/employee"
SEARCH_PATH = "/search/filter"
COLLECT_PATH = "/collect"
MAX_COLLECT = 25  # cap profiles hydrated per search to bound credit spend


class CoresignalError(RuntimeError):
    """Raised when Coresignal returns a non-2xx response or an unreadable body."""


class CoresignalProvider:
    key = "coresignal"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout_seconds: float = 25.0) -> None:
        if not api_key:
            raise ValueError("CORESIGNAL_API_KEY is required for the Coresignal provider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def search(self, query: PeopleSearchQuery) -> PeopleSearchResult:
        filters: dict[str, Any] = {}
        if query.titles:
            filters["title"] = query.titles[0]
        if query.locations:
            filters["location"] = query.locations[0]
        if query.keywords or query.skills:
            filters["keyword"] = " ".join([*query.keywords, *query.skills])
        ids = self._post(SEARCH_PATH, filters)
        if not isinstance(ids, list):
            ids = []
        size = min(max(1, query.page_size), MAX_COLLECT)
        start = (max(1, query.page) - 1) * size
        window = ids[start : start + size]
        candidates = [self._to_candidate(self._collect(mid)) for mid in window]
        return PeopleSearchResult(
            candidates=candidates,
            total=len(ids),
            page=query.page,
            has_more=start + size < len(ids),
            provider="coresignal",
        )

    def enrich(self, source_id: str, *, full_name: str | None = None) -> EnrichmentResult:
        person = self._collect(source_id)
        emails = person.get("emails") or person.get("professional_emails") or []
        return EnrichmentResult(
            source="coresignal", source_id=source_id,
            phone=_first(person.get("phone_numbers")),
            email=_first(emails) if not isinstance(_first(emails), dict) else None,
            raw=person,
        )

    @staticmethod
    def _to_candidate(person: dict[str, Any]) -> ExternalCandidate:
        return ExternalCandidate(
            source="coresignal",
            source_id=str(person.get("id", "")),
            full_name=person.get("name") or person.get("full_name") or None,
            title=person.get("title") or person.get("headline"),
            company=person.get("company_name") or person.get("experience_company_name"),
            location=person.get("location"),
            phone=None,
            email=None,
            linkedin_url=person.get("url") or person.get("canonical_url"),
            raw=person,
        )

    def _collect(self, member_id: Any) -> dict[str, Any]:
        payload = self._request("GET", f"{COLLECT_PATH}/{member_id}")
        return payload if isinstance(payload, dict) else {}

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request("POST", path, json.dumps(body).encode("utf-8"))

    def _request(self, method: str, path: str, data: bytes | None = None) -> Any:
        req = urllib.request.Request(
            url=self._base_url + path, data=data, method=method,
            headers={"Content-Type": "application/json", "Accept": "application/json", "apikey": self._api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise CoresignalError(f"Coresignal {path} HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            raise CoresignalError(f"Coresignal {path} request failed: {exc}") from exc


def _first(items: Any) -> Any:
    return items[0] if isinstance(items, list) and items else None
