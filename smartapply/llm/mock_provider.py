"""Mock LLM provider — produces deterministic outputs for tests.

Tests inject responses via ``register(purpose, schema_instance)``. If no
response is registered for a purpose, the provider raises ``LLMError`` —
this surfaces missing test fixtures loudly instead of returning silent
defaults.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from smartapply.llm.provider import LLMError, LLMProvider

T = TypeVar("T", bound=BaseModel)


class MockLLMProvider(LLMProvider):
    name = "mock"

    # Class-level so tests can register globally without holding a reference.
    _registry: dict[str, BaseModel] = {}

    @property
    def smart_model(self) -> str:
        return "mock-smart"

    @property
    def cheap_model(self) -> str:
        return "mock-cheap"

    @classmethod
    def register(cls, purpose: str, response: BaseModel) -> None:
        cls._registry[purpose] = response

    @classmethod
    def clear(cls) -> None:
        cls._registry.clear()

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
    ) -> T:
        if purpose not in self._registry:
            raise LLMError(
                f"No mock response registered for purpose={purpose!r}. "
                f"Call MockLLMProvider.register({purpose!r}, <instance>) first."
            )
        response = self._registry[purpose]
        if not isinstance(response, schema):
            raise LLMError(
                f"Registered response type {type(response).__name__} does not "
                f"match expected {schema.__name__}"
            )
        return response  # type: ignore[return-value]
