"""Provider selection for people search.

Chooses the active provider from configuration (PEOPLE_SEARCH_PROVIDER) and constructs it
with the matching API key. Only Apollo is implemented today; PDL, Proxycurl, and
Coresignal are registered as known keys so they can be added without touching callers.
"""

from __future__ import annotations

import os

from .apollo import ApolloProvider
from .base import PeopleSearchProvider
from .sample import SampleProvider

# Known provider keys from the assignment. Value is the env var holding that provider's key
# (None for providers that need no key). `sample` is an offline, no-key provider used as the
# demonstrable fallback while a paid Apollo key is unavailable (see sample.py).
KNOWN_PROVIDERS: dict[str, str | None] = {
    "sample": None,
    "apollo": "APOLLO_API_KEY",
    "pdl": "PDL_API_KEY",
    "proxycurl": "PROXYCURL_API_KEY",
    "coresignal": "CORESIGNAL_API_KEY",
}


def get_people_search_provider(
    provider_key: str | None = None,
    env: dict[str, str] | None = None,
) -> PeopleSearchProvider:
    """Return the configured people-search provider instance.

    Raises ValueError for an unknown provider, a not-yet-implemented provider, or a
    missing API key — failing loudly at startup rather than at call time.
    """
    env = env or dict(os.environ)
    key = (provider_key or env.get("PEOPLE_SEARCH_PROVIDER") or "apollo").lower()

    if key not in KNOWN_PROVIDERS:
        raise ValueError(
            f"Unknown people-search provider '{key}'. "
            f"Known: {', '.join(sorted(KNOWN_PROVIDERS))}."
        )

    if key == "sample":
        return SampleProvider()

    api_key = env.get(KNOWN_PROVIDERS[key] or "", "")

    if key == "apollo":
        return ApolloProvider(api_key=api_key)

    # PDL / Proxycurl / Coresignal: known and pluggable, not yet implemented.
    raise ValueError(
        f"People-search provider '{key}' is not implemented yet. "
        f"Add a provider class implementing PeopleSearchProvider and wire it here."
    )
