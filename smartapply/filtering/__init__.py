"""Local rule-based filtering — keep this cheap and explainable."""

from smartapply.filtering.filters import (
    FilterResult,
    JobFilter,
    ruleset_from_preferences,
)
from smartapply.filtering.rules import (
    DEFAULT_NEGATIVE_DESC_TOKENS,
    DEFAULT_NEGATIVE_TITLE_KEYWORDS,
    DEFAULT_POSITIVE_TITLE_KEYWORDS,
    DEFAULT_SENIORITY_BLOCK_TERMS,
    DEFAULT_TITLE_HARD_REJECT_KEYWORDS,
    RuleSet,
)

__all__ = [
    "DEFAULT_NEGATIVE_DESC_TOKENS",
    "DEFAULT_NEGATIVE_TITLE_KEYWORDS",
    "DEFAULT_POSITIVE_TITLE_KEYWORDS",
    "DEFAULT_SENIORITY_BLOCK_TERMS",
    "DEFAULT_TITLE_HARD_REJECT_KEYWORDS",
    "FilterResult",
    "JobFilter",
    "RuleSet",
    "ruleset_from_preferences",
]
