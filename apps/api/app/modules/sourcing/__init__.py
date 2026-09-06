"""Sourcing module — People Search & Outreach (Flow B).

Bridges the provider-agnostic people-search boundary to the platform: it suggests a search
query from a job's approved JD, runs the search against the configured provider with a safe
fallback, and adds selected external candidates into the job's pipeline (SOURCED) with
provenance. It never leaks provider internals to recruiters.
"""

from .service import SourcingService, SourcingUnavailableError

__all__ = ["SourcingService", "SourcingUnavailableError"]
