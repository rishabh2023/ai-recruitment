"""Proxycurl (Nubela) people-search provider.

Contract from Proxycurl docs:

- Search:  GET https://nubela.co/proxycurl/api/v2/search/person
           Auth: `Authorization: Bearer <key>`. Params: country (ISO-3166 alpha-2),
           current_role_title, current_company_name, region, keyword, page_size.
           With `enrich_profile=enrich` each result includes the full LinkedIn `profile`
           (full_name, occupation, city/state/country) — otherwise only the profile URL.
- Enrich:  GET https://nubela.co/proxycurl/api/contact-api/personal-contact  (phone) and
           .../personal-email  by `linkedin_profile_url` — contact lookups are separate,
           credit-charged endpoints.

Proxycurl is paid (credit-based); this adapter is written to the documented contract. Only
documented parameters are sent. stdlib-only HTTP.
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

DEFAULT_BASE_URL = "https://nubela.co/proxycurl/api"
SEARCH_PATH = "/v2/search/person"
CONTACT_PATH = "/contact-api/personal-contact"


class ProxycurlError(RuntimeError):
    """Raised when Proxycurl returns a non-2xx response or an unreadable body."""


class ProxycurlProvider:
    key = "proxycurl"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL, timeout_seconds: float = 25.0) -> None:
        if not api_key:
            raise ValueError("PROXYCURL_API_KEY is required for the Proxycurl provider")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def search(self, query: PeopleSearchQuery) -> PeopleSearchResult:
        params: dict[str, str] = {
            "page_size": str(min(max(1, query.page_size), 100)),
            "enrich_profile": "enrich",  # include full profile so we get names/titles
        }
        if query.titles:
            params["current_role_title"] = query.titles[0]
        if query.locations:
            params["region"] = query.locations[0]
        if query.keywords or query.skills:
            params["keyword"] = " ".join([*query.keywords, *query.skills])
        payload = self._get(SEARCH_PATH, params)
        results = payload.get("results") or []
        candidates = [self._to_candidate(r) for r in results]
        return PeopleSearchResult(
            candidates=candidates,
            total=payload.get("total_result_count"),
            page=query.page,
            has_more=bool(payload.get("next_page")),
            provider="proxycurl",
        )

    def enrich(self, source_id: str, *, full_name: str | None = None) -> EnrichmentResult:
        """`source_id` is the LinkedIn profile URL. Looks up a personal contact number."""
        payload = self._get(CONTACT_PATH, {"linkedin_profile_url": source_id})
        numbers = payload.get("numbers") or []
        emails = payload.get("emails") or []
        return EnrichmentResult(
            source="proxycurl", source_id=source_id,
            phone=numbers[0] if numbers else None,
            email=emails[0] if emails else None,
            raw=payload,
        )

    @staticmethod
    def _to_candidate(result: dict[str, Any]) -> ExternalCandidate:
        url = result.get("linkedin_profile_url") or ""
        profile = result.get("profile") or {}
        location = ", ".join(
            p for p in (profile.get("city"), profile.get("state"), profile.get("country_full_name")) if p
        ) or None
        experiences = profile.get("experiences") or []
        company = experiences[0].get("company") if experiences and isinstance(experiences[0], dict) else None
        return ExternalCandidate(
            source="proxycurl",
            source_id=url,  # profile URL is the stable id + the enrich key
            full_name=profile.get("full_name") or None,
            title=profile.get("occupation"),
            company=company,
            location=location,
            phone=None,
            email=None,
            linkedin_url=url or None,
            raw=result,
        )

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = self._base_url + path + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url=url, method="GET",
            headers={"Accept": "application/json", "Authorization": f"Bearer {self._api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise ProxycurlError(f"Proxycurl {path} HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as exc:
            raise ProxycurlError(f"Proxycurl {path} request failed: {exc}") from exc
