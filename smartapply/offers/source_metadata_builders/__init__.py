"""Source-specific metadata blocks for job analysis prompts."""

from smartapply.offers.source_metadata_builders.francetravail import (
    build_francetravail_source_metadata,
)
from smartapply.offers.source_metadata_builders.linkedin import (
    build_linkedin_source_metadata,
)
from smartapply.offers.source_metadata_builders.serpapi import (
    build_serpapi_source_metadata,
)
from smartapply.offers.source_metadata_builders.wttj import build_wttj_source_metadata

__all__ = [
    "build_francetravail_source_metadata",
    "build_linkedin_source_metadata",
    "build_serpapi_source_metadata",
    "build_wttj_source_metadata",
]
