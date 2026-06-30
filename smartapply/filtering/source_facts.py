"""Source-specific structured facts for the local filter."""

from __future__ import annotations

from typing import Any

from smartapply.filtering.facts import FilterFacts
from smartapply.filtering.source_fact_builders import (
    build_francetravail_filter_facts,
    build_serpapi_filter_facts,
    build_wttj_filter_facts,
)
from smartapply.filtering.text import norm


def build_filter_facts(job: Any) -> FilterFacts:
    """Build normalized structured facts for a job-like object.

    Unknown sources, missing ``source_data`` and plain manual jobs intentionally
    return an empty facts object so the global text filter remains the fallback.
    """

    source = _clean_text(getattr(job, "source", None))
    source_data = getattr(job, "source_data", None)
    from smartapply.offers.sources.registry import get_offer_source_adapter

    adapter = get_offer_source_adapter(source or "")
    if adapter is not None:
        return adapter.build_filter_facts(source_data if isinstance(source_data, dict) else None)
    if not isinstance(source_data, dict):
        return FilterFacts(source=source)

    if norm(source) == "francetravail":
        return build_francetravail_filter_facts(source_data)
    if norm(source) == "serpapi":
        return build_serpapi_filter_facts(source_data)
    if norm(source) == "welcometothejungle":
        return build_wttj_filter_facts(source_data)

    return FilterFacts(source=source)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
