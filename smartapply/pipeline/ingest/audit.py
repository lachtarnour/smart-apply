"""Search contribution audit helpers for ingestion reports."""

from __future__ import annotations

from typing import Any

from smartapply.offers import RawJob


def _audit_base_key(meta: dict[str, Any]) -> tuple:
    return (
        meta.get("query"),
        meta.get("location"),
        meta.get("google_domain"),
        meta.get("hl"),
        meta.get("gl"),
        meta.get("strict_chips"),
    )


def _build_search_audit(raws: list[RawJob]) -> list[dict[str, Any]]:
    """Summarize SerpApi strict-vs-fallback contribution for ingest reports."""
    strict_counts: dict[tuple, int] = {}
    fallback_counts: dict[tuple, int] = {}
    fallback_meta: dict[tuple, dict[str, Any]] = {}

    for raw in raws:
        meta = (raw.source_data or {}).get("_smartapply_search")
        if not isinstance(meta, dict):
            continue
        base_key = _audit_base_key(meta)
        origin = meta.get("result_origin")
        if origin == "strict":
            strict_counts[base_key] = strict_counts.get(base_key, 0) + 1
        elif origin == "fallback":
            fallback_key = (
                *base_key,
                meta.get("fallback_reason"),
                meta.get("fallback_chips"),
                meta.get("fallback_query"),
            )
            fallback_counts[fallback_key] = fallback_counts.get(fallback_key, 0) + 1
            fallback_meta[fallback_key] = meta

    audit: list[dict[str, Any]] = []
    for fallback_key, fallback_added in fallback_counts.items():
        base_key = fallback_key[:6]
        meta = fallback_meta[fallback_key]
        strict_results = strict_counts.get(base_key, 0)
        audit.append(
            {
                "query": meta.get("query"),
                "location": meta.get("location"),
                "google_domain": meta.get("google_domain"),
                "hl": meta.get("hl"),
                "gl": meta.get("gl"),
                "strict_results": strict_results,
                "fallback_added": fallback_added,
                "final_results": strict_results + fallback_added,
                "fallback_reason": meta.get("fallback_reason"),
                "strict_chips": meta.get("strict_chips"),
                "fallback_chips": meta.get("fallback_chips"),
                "fallback_query": meta.get("fallback_query"),
            }
        )
    return audit
