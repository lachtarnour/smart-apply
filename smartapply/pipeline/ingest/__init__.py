"""Ingestion helpers split by responsibility."""

from smartapply.pipeline.ingest.audit import _build_search_audit
from smartapply.pipeline.ingest.collection import collect_round_robin
from smartapply.pipeline.ingest.dedupe import (
    _KnownJobIndex,
    _normalize_application_url,
)
from smartapply.pipeline.ingest.queries import (
    QUERY_AGNOSTIC_SOURCES,
    expand_query_for_source,
    split_or_query,
)
from smartapply.pipeline.ingest.reports import IngestReport

__all__ = [
    "IngestReport",
    "QUERY_AGNOSTIC_SOURCES",
    "_KnownJobIndex",
    "_build_search_audit",
    "_normalize_application_url",
    "collect_round_robin",
    "expand_query_for_source",
    "split_or_query",
]
