"""Source-specific metadata registry for job analysis prompts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from smartapply.offers.source_metadata_builders import (
    build_francetravail_source_metadata,
    build_manual_source_metadata,
    build_serpapi_source_metadata,
    build_wttj_source_metadata,
)

SourceMetadataBuilder = Callable[[dict[str, Any] | None], str]

_SOURCE_METADATA_BUILDERS: dict[str, SourceMetadataBuilder] = {}


def register_source_metadata_builder(
    source: str,
    builder: SourceMetadataBuilder,
) -> None:
    """Register a source-specific metadata builder for analyzer inputs."""
    normalized = source.strip().lower()
    if not normalized:
        raise ValueError("source must not be empty")
    _SOURCE_METADATA_BUILDERS[normalized] = builder


def build_analyzer_source_metadata(job: Any) -> str:
    """Return a short structured source-specific metadata block for the analyzer."""
    source = str(getattr(job, "source", "") or "").strip().lower()
    from smartapply.offers.sources.registry import get_offer_source_adapter

    adapter = get_offer_source_adapter(source)
    if adapter is not None:
        return adapter.build_analyzer_metadata(getattr(job, "source_data", None))
    builder = _SOURCE_METADATA_BUILDERS.get(source)
    if builder is None:
        return ""
    return builder(getattr(job, "source_data", None))


register_source_metadata_builder("francetravail", build_francetravail_source_metadata)
register_source_metadata_builder("manual", build_manual_source_metadata)
register_source_metadata_builder("serpapi", build_serpapi_source_metadata)
register_source_metadata_builder("welcometothejungle", build_wttj_source_metadata)
