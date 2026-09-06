"""Provider selection for people search.

Multi-provider by design (ADR-0001): Apollo, People Data Labs (PDL), Proxycurl, and
Coresignal are all wired as real providers, each constructed with its own API key. The active
provider is chosen per request (recruiter picks one) or from configuration
(PEOPLE_SEARCH_PROVIDER). A provider is only offered when its API key is present.

`sample` is an offline, no-key provider kept for tests and local development only. It is NOT a
real people-search source and is never used as an automatic fallback; it is constructed solely
when explicitly requested.
"""

from __future__ import annotations

import os

from .apollo import ApolloProvider
from .base import PeopleSearchProvider
from .coresignal import CoresignalProvider
from .pdl import PdlProvider
from .proxycurl import ProxycurlProvider
from .sample import SampleProvider

# Real provider key -> env var holding that provider's API key.
KNOWN_PROVIDERS: dict[str, str] = {
    "apollo": "APOLLO_API_KEY",
    "pdl": "PDL_API_KEY",
    "proxycurl": "PROXYCURL_API_KEY",
    "coresignal": "CORESIGNAL_API_KEY",
}

# Recruiter-facing labels (never expose env var names or vendor internals in the UI).
PROVIDER_LABELS: dict[str, str] = {
    "apollo": "Apollo.io",
    "pdl": "People Data Labs",
    "proxycurl": "Proxycurl",
    "coresignal": "Coresignal",
    "sample": "Sample (offline demo)",
}

_CONSTRUCTORS = {
    "apollo": ApolloProvider,
    "pdl": PdlProvider,
    "proxycurl": ProxycurlProvider,
    "coresignal": CoresignalProvider,
}


def configured_providers(env: dict[str, str] | None = None) -> list[str]:
    """Real providers that have an API key set, in a stable order."""
    env = env or dict(os.environ)
    return [key for key, var in KNOWN_PROVIDERS.items() if (env.get(var) or "").strip()]


def get_people_search_provider(
    provider_key: str | None = None,
    env: dict[str, str] | None = None,
) -> PeopleSearchProvider:
    """Return a people-search provider instance.

    Raises ValueError for an unknown provider or a missing API key — failing loudly rather
    than silently returning fake data.
    """
    env = env or dict(os.environ)
    key = (provider_key or env.get("PEOPLE_SEARCH_PROVIDER") or "apollo").lower()

    if key == "sample":
        return SampleProvider()

    if key not in _CONSTRUCTORS:
        raise ValueError(
            f"Unknown people-search provider '{key}'. Known: {', '.join(sorted(KNOWN_PROVIDERS))}."
        )

    api_key = (env.get(KNOWN_PROVIDERS[key]) or "").strip()
    if not api_key:
        raise ValueError(
            f"{PROVIDER_LABELS.get(key, key)} is not configured — add its API key in Settings."
        )
    return _CONSTRUCTORS[key](api_key=api_key)
