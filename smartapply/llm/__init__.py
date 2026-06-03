"""LLM provider abstraction + schemas + prompts."""

from smartapply.llm.cache import make_cache_key
from smartapply.llm.mock_provider import MockLLMProvider
from smartapply.llm.openai_provider import OpenAIProvider
from smartapply.llm.provider import (
    LLMError,
    LLMProvider,
    LLMValidationError,
    get_llm_provider,
)
from smartapply.llm.schemas import (
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    ApplicationDraft,
    ApplicationQualityReview,
    EmailDraft,
    JobAnalysis,
    SkillSelectionBlock,
)
from smartapply.llm.usage import OPENAI_PRICING, estimate_cost_usd

__all__ = [
    "AdaptedBullet",
    "AdaptedCV",
    "AdaptedExperience",
    "ApplicationDraft",
    "ApplicationQualityReview",
    "EmailDraft",
    "JobAnalysis",
    "SkillSelectionBlock",
    "LLMError",
    "LLMProvider",
    "LLMValidationError",
    "MockLLMProvider",
    "OPENAI_PRICING",
    "OpenAIProvider",
    "estimate_cost_usd",
    "get_llm_provider",
    "make_cache_key",
]
