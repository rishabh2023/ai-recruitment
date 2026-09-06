"""Effective information requirement (carry-forward) — pure logic.

Before executing a candidate stage, compute what still needs to be collected
(docs/architecture.md, architecture §62):

    current stage requirements
    + unresolved required info from prior stages
    − info already known with acceptable provenance
    = effective information to collect

Kept pure and order-preserving so it is fully unit-testable and deterministic.
"""

from __future__ import annotations

from collections.abc import Iterable


def compute_effective_information(
    stage_requirements: Iterable[str],
    unresolved_prior: Iterable[str],
    known_field_keys: Iterable[str],
) -> list[str]:
    """Return the ordered, de-duplicated fields to collect this stage.

    Prior unresolved requirements come first (they were owed earlier), then this stage's own
    requirements; anything already known is removed.
    """
    known = {k for k in known_field_keys}
    out: list[str] = []
    for key in list(unresolved_prior) + list(stage_requirements):
        if key not in known and key not in out:
            out.append(key)
    return out
