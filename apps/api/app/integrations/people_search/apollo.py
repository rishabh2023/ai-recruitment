"""Apollo.io people-search provider.

First concrete provider behind the PeopleSearchProvider interface. Contract VERIFIED from
Apollo developer docs (see docs/vendor-capability-matrix.md):

- Search:     POST https://api.apollo.io/api/v1/mixed_people/api_search  (key-based variant)
- Auth:       `x-api-key` header
- Pagination: `page` + `per_page` (<=100), display cap 50,000 (500 pages)
- IMPORTANT:  search returns obfuscated names and `has_email`/`has_direct_phone` flags but
              NOT emails or phone numbers. Contact details require the enrichment endpoint
              (POST /people/match with reveal_phone_number=true + an HTTPS webhook_url,
              delivered asynchronously). Outreach (Journey B) therefore needs an enrichment
              step before a Hunar call — tracked for Phase 4.

Uses only the Python standard library (urllib) so the adapter has no runtime dependency yet.
The app layer may later swap in its shared HTTP client.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import (
    ExternalCandidate,
    PeopleSearchQuery,
    PeopleSearchResult,
)

DEFAULT_BASE_URL = "https://api.apollo.io/api/v1"
SEARCH_PATH = "/mixed_people/api_search"
ENRICH_PATH = "/people/match"
MAX_PER_PAGE = 100


class ApolloError(RuntimeError):
    """Raised when Apollo returns a non-2xx response or an unreadable body."""


class ApolloProvider:
    key = "apollo"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("APOLLO_API_KEY is required for the Apollo provider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    # --- Public API -------------------------------------------------------------
    def search(self, query: PeopleSearchQuery) -> PeopleSearchResult:
        body = self._build_request(query)
        payload = self._post(SEARCH_PATH, body)
        return self._build_result(payload, page=query.page)

    def enrich(self, source_id: str, *, full_name: str | None = None):  # type: ignore[override]
        """Apollo reveals phone numbers only via `/people/match` with `reveal_phone_number=true`
        + an HTTPS `webhook_url`, delivered **asynchronously** (see vendor-capability-matrix).
        There is no synchronous phone reveal, so this raises: the platform must implement the
        webhook round-trip (Phase 4b) before Apollo enrichment can complete. Raising here lets
        the caller degrade to a clearly-flagged fallback rather than fake a synchronous result."""
        raise ApolloError(
            "Apollo phone enrichment is asynchronous (reveal via /people/match webhook) and "
            "requires a paid plan; synchronous enrichment is not available."
        )

    # --- Request/response mapping ----------------------------------------------
    @staticmethod
    def _build_request(query: PeopleSearchQuery) -> dict[str, Any]:
        """Map the normalized query to Apollo search parameters.

        Only parameters Apollo documents are sent; unsupported normalized filters are
        omitted rather than guessed at.
        """
        body: dict[str, Any] = {
            "page": max(1, query.page),
            "per_page": min(max(1, query.page_size), MAX_PER_PAGE),
        }
        if query.titles:
            body["person_titles"] = query.titles
        if query.locations:
            body["person_locations"] = query.locations
        if query.seniorities:
            body["person_seniorities"] = query.seniorities
        if query.keywords:
            body["q_keywords"] = " ".join(query.keywords)
        return body

    @staticmethod
    def _to_candidate(person: dict[str, Any]) -> ExternalCandidate:
        """Map one Apollo person to the normalized shape.

        Search does not return email/phone, so those are left None; `has_email` /
        `has_direct_phone` remain in `raw` so callers can decide whether to enrich.
        Last name is often obfuscated by Apollo, so `name` is best-effort.
        """
        first = person.get("first_name") or ""
        last = person.get("last_name") or person.get("last_name_obfuscated") or ""
        name = (person.get("name") or f"{first} {last}").strip() or None
        org = person.get("organization") or {}
        location = ", ".join(
            p for p in (person.get("city"), person.get("state"), person.get("country")) if p
        ) or None
        return ExternalCandidate(
            source="apollo",
            source_id=str(person.get("id", "")),
            full_name=name,
            title=person.get("title"),
            company=org.get("name"),
            location=location,
            phone=None,  # not returned by search — requires enrichment
            email=None,  # not returned by search — requires enrichment
            linkedin_url=person.get("linkedin_url"),
            raw=person,
        )

    @staticmethod
    def _build_result(payload: dict[str, Any], page: int) -> PeopleSearchResult:
        people = payload.get("people") or payload.get("contacts") or []
        pagination = payload.get("pagination") or {}
        total = pagination.get("total_entries")
        total_pages = pagination.get("total_pages")
        return PeopleSearchResult(
            candidates=[ApolloProvider._to_candidate(p) for p in people],
            total=total,
            page=pagination.get("page", page),
            has_more=bool(total_pages and pagination.get("page", page) < total_pages),
            provider="apollo",
        )

    # --- HTTP (stdlib) ----------------------------------------------------------
    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url=self._base_url + path,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": self._api_key,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # non-2xx
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ApolloError(f"Apollo {path} HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            raise ApolloError(f"Apollo {path} request failed: {exc}") from exc
