"""LLM provider ABC and factory."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from smartapply.config import get_settings

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract LLM provider with a single structured-output method.

    Implementations must validate the returned object against ``schema``
    before returning it, raising ``LLMError`` otherwise.
    """

    name: str = ""

    @abstractmethod
    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        model: str | None = None,
        temperature: float = 0.2,
        purpose: str = "generic",
        job_id: int | None = None,
        use_cache: bool = True,
    ) -> T: ...

    @property
    @abstractmethod
    def smart_model(self) -> str: ...

    @property
    @abstractmethod
    def cheap_model(self) -> str: ...


class LLMError(RuntimeError):
    """Base error for LLM provider failures."""


class LLMValidationError(LLMError):
    """Raised when the model output does not match the schema."""


# -------------------- Factory --------------------


def get_llm_provider(name: str | None = None) -> LLMProvider:
    from smartapply.llm.mock_provider import MockLLMProvider
    from smartapply.llm.openai_provider import OpenAIProvider

    chosen = (name or get_settings().llm_provider).lower()
    if chosen == "openai":
        return OpenAIProvider()
    if chosen == "mock":
        return MockLLMProvider()
    # Future: anthropic, azure, etc.
    raise ValueError(f"Unknown LLM provider {chosen!r}")
