"""LLM provider selection.

Returns the platform LLM provider. A real provider plugs in when `PLATFORM_LLM_API_KEY` is
configured; until then the deterministic offline stub is used so the product flow works and
tests stay stable.
"""

from __future__ import annotations

import os

from .base import LLMProvider
from .stub import StubLLMProvider


def get_llm_provider(env: dict[str, str] | None = None) -> LLMProvider:
    env = env or dict(os.environ)
    # A real provider would be constructed here from PLATFORM_LLM_API_KEY.
    # Intentionally not implemented yet — never invent product intelligence we can't run.
    return StubLLMProvider()
