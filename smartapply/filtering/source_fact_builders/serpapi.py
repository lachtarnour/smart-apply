"""SerpApi / Google Jobs structured facts for local filtering."""

from __future__ import annotations

from typing import Any

from smartapply.filtering.facts import FilterFacts
from smartapply.filtering.source_fact_builders.common import (
    _clean_text,
    _coerce_bool,
)
from smartapply.filtering.text import norm
from smartapply.utils.contracts import normalize_source_contract_type

_SERPAPI_PRESTATAIRE_MARKERS = ("prestataire",)
_SERPAPI_REMOTE_LOCATION_MARKERS = (
    "remote",
    "anywhere",
    "a distance",
    "teletravail",
    "teletravail possible",
)
_SERPAPI_HYBRID_LOCATION_MARKERS = ("hybrid", "hybride")


def build_serpapi_filter_facts(source_data: dict[str, Any]) -> FilterFacts:
    """Extract conservative SerpApi / Google Jobs facts for local filtering."""

    facts = FilterFacts(source="serpapi")
    _extract_serpapi_contract(facts, source_data)
    _extract_serpapi_location(facts, source_data)
    _extract_serpapi_remote_policy(facts, source_data)
    _extract_serpapi_search_context(facts, source_data)
    return facts


def _extract_serpapi_contract(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    extensions = source_data.get("detected_extensions")
    if not isinstance(extensions, dict):
        return

    schedule_type = _clean_text(extensions.get("schedule_type"))
    if not schedule_type:
        return

    facts.structured_contract_type = _normalize_serpapi_schedule_type(schedule_type)
    facts.structured_contract_source = "serpapi:detected_extensions.schedule_type"
    facts.facts_used.append(f"structured_contract_type:{facts.structured_contract_type}")


def _extract_serpapi_location(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    location = _clean_text(source_data.get("location"))
    if not location:
        return
    facts.structured_location = location
    facts.structured_location_source = "serpapi:location"
    facts.facts_used.append("structured_location:location")


def _extract_serpapi_remote_policy(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    extensions = source_data.get("detected_extensions")
    extensions = extensions if isinstance(extensions, dict) else {}
    if _coerce_bool(extensions.get("work_from_home")) is True:
        facts.structured_remote_policy = "remote"
        facts.structured_remote_source = "serpapi:detected_extensions.work_from_home"
        facts.facts_used.append("structured_remote_policy:remote")
        return

    location = norm(source_data.get("location"))
    if any(marker in location for marker in _SERPAPI_REMOTE_LOCATION_MARKERS):
        facts.structured_remote_policy = "remote"
        facts.structured_remote_source = "serpapi:location"
        facts.facts_used.append("structured_remote_policy:remote")
    elif any(marker in location for marker in _SERPAPI_HYBRID_LOCATION_MARKERS):
        facts.structured_remote_policy = "hybrid"
        facts.structured_remote_source = "serpapi:location"
        facts.facts_used.append("structured_remote_policy:hybrid")


def _extract_serpapi_search_context(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    search = source_data.get("_smartapply_search")
    if not isinstance(search, dict):
        return

    origin = _clean_text(search.get("result_origin"))
    chips = _clean_text(search.get("strict_chips"))
    if origin:
        facts.structured_search_origin = origin
        facts.facts_used.append(f"structured_search_origin:{origin}")
    if chips:
        facts.structured_search_chips = chips
        facts.facts_used.append(f"structured_search_chips:{chips}")


def _normalize_serpapi_schedule_type(value: str) -> str:
    normalized = norm(value)
    if any(marker in normalized for marker in _SERPAPI_PRESTATAIRE_MARKERS):
        return "Prestataire"
    return normalize_source_contract_type(value) or value
