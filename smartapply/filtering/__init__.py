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
from smartapply.filtering.source_facts import (
    FilterFacts,
    build_filter_facts,
    build_francetravail_filter_facts,
    build_serpapi_filter_facts,
    build_wttj_filter_facts,
)

__all__ = [
    "DEFAULT_NEGATIVE_DESC_TOKENS",
    "DEFAULT_NEGATIVE_TITLE_KEYWORDS",
    "DEFAULT_POSITIVE_TITLE_KEYWORDS",
    "DEFAULT_SENIORITY_BLOCK_TERMS",
    "DEFAULT_TITLE_HARD_REJECT_KEYWORDS",
    "FilterFacts",
    "FilterResult",
    "JobFilter",
    "RuleSet",
    "build_filter_facts",
    "build_francetravail_filter_facts",
    "build_serpapi_filter_facts",
    "build_wttj_filter_facts",
    "ruleset_from_preferences",
]
