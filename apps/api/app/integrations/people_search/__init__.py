"""People-search integration: provider-agnostic boundary + registry."""

from .base import (
    ExternalCandidate,
    PeopleSearchProvider,
    PeopleSearchQuery,
    PeopleSearchResult,
)
from .registry import KNOWN_PROVIDERS, get_people_search_provider

__all__ = [
    "ExternalCandidate",
    "PeopleSearchProvider",
    "PeopleSearchQuery",
    "PeopleSearchResult",
    "KNOWN_PROVIDERS",
    "get_people_search_provider",
]
