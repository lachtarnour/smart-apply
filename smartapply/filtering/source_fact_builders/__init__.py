"""Source-specific structured fact builders."""

from smartapply.filtering.source_fact_builders.francetravail import (
    build_francetravail_filter_facts,
)
from smartapply.filtering.source_fact_builders.linkedin import build_linkedin_filter_facts
from smartapply.filtering.source_fact_builders.serpapi import (
    build_serpapi_filter_facts,
)
from smartapply.filtering.source_fact_builders.wttj import build_wttj_filter_facts

__all__ = [
    "build_francetravail_filter_facts",
    "build_linkedin_filter_facts",
    "build_serpapi_filter_facts",
    "build_wttj_filter_facts",
]
