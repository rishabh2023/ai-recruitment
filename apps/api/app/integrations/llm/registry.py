"""LLM provider selection.

Returns the platform LLM provider. When `PLATFORM_LLM_API_KEY` is configured the Anthropic
(Claude Haiku) provider is used for JD understanding; otherwise the deterministic offline stub
is used so the product flow works and tests stay stable.
"""

from __future__ import annotations

import logging

from app.config import settings

from .base import LLMProvider
from .stub import StubLLMProvider

logger = logging.getLogger(__name__)


def get_llm_provider() -> LLMProvider:
    api_key = settings.platform_llm_api_key
    if api_key:
        try:
            from .anthropic_provider import AnthropicLLMProvider

            return AnthropicLLMProvider(api_key=api_key, model=settings.platform_llm_model)
        except Exception as exc:  # never let provider wiring break the flow
            logger.warning("Falling back to stub LLM provider (%s).", exc)
    return StubLLMProvider()
