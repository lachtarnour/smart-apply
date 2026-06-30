"""LLM provider factory."""

from __future__ import annotations

from smartapply.config import get_settings
from smartapply.llm.provider import LLMProvider


def get_llm_provider(name: str | None = None) -> LLMProvider:
    from smartapply.llm.mock_provider import MockLLMProvider
    from smartapply.llm.openai_provider import OpenAIProvider

    chosen = (name or get_settings().llm_provider).lower()
    if chosen == "openai":
        return OpenAIProvider()
    if chosen == "mock":
        return MockLLMProvider()
    raise ValueError(f"Unknown LLM provider {chosen!r}")
