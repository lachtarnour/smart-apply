"""Cross-source job deduplication."""

from smartapply.dedup.deduplicator import (
    Deduplicator,
    DedupReport,
    DuplicateCandidate,
    JobLike,
    normalize_company,
    normalize_title,
)

__all__ = [
    "DedupReport",
    "DuplicateCandidate",
    "Deduplicator",
    "JobLike",
    "normalize_company",
    "normalize_title",
]
