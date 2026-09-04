"""Local rule-based filtering — keep this cheap and explainable."""

from smartapply.filtering.filters import (
    FilterResult,
    JobFilter,
    ruleset_from_preferences,
)
from smartapply.filtering.relevance import (
    RoleRelevanceAssessment,
    RoleRelevanceDisposition,
    assess_role_relevance,
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
from smartapply.filtering.types import FilterDisposition

__all__ = [
    "DEFAULT_NEGATIVE_DESC_TOKENS",
    "DEFAULT_NEGATIVE_TITLE_KEYWORDS",
    "DEFAULT_POSITIVE_TITLE_KEYWORDS",
    "DEFAULT_SENIORITY_BLOCK_TERMS",
    "DEFAULT_TITLE_HARD_REJECT_KEYWORDS",
    "FilterFacts",
    "FilterDisposition",
    "FilterResult",
    "JobFilter",
    "RoleRelevanceAssessment",
    "RoleRelevanceDisposition",
    "RuleSet",
    "build_filter_facts",
    "build_francetravail_filter_facts",
    "build_serpapi_filter_facts",
    "build_wttj_filter_facts",
    "assess_role_relevance",
    "ruleset_from_preferences",
]
