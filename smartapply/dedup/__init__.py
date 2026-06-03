"""Cross-source job deduplication."""

from smartapply.dedup.deduplicator import (
    DedupReport,
    Deduplicator,
    JobLike,
    normalize_company,
    normalize_title,
)

__all__ = [
    "DedupReport",
    "Deduplicator",
    "JobLike",
    "normalize_company",
    "normalize_title",
]
