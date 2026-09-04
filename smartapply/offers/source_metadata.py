"""Build source-specific metadata for job-analysis prompts."""

from __future__ import annotations

from typing import Any


def build_analyzer_source_metadata(job: Any) -> str:
    """Return a short structured source-specific metadata block for the analyzer."""
    source = str(getattr(job, "source", "") or "").strip().lower()
    from smartapply.offers.sources.registry import get_offer_source_adapter

    adapter = get_offer_source_adapter(source)
    if adapter is None:
        return ""
    return adapter.build_analyzer_metadata(getattr(job, "source_data", None))
