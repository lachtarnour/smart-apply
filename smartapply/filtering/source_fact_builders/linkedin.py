"""LinkedIn structured facts for local filtering."""

from __future__ import annotations

from typing import Any

from smartapply.filtering.facts import FilterFacts
from smartapply.filtering.source_fact_builders.common import _clean_text
from smartapply.filtering.text import norm
from smartapply.utils.contracts import normalize_source_contract_type

_REMOTE_MARKERS = ("remote", "teletravail", "télétravail")
_HYBRID_MARKERS = ("hybrid", "hybride")


def build_linkedin_filter_facts(source_data: dict[str, Any]) -> FilterFacts:
    facts = FilterFacts(source="linkedin")
    _extract_contract(facts, source_data)
    _extract_location(facts, source_data)
    _extract_remote_policy(facts, source_data)
    _extract_experience(facts, source_data)
    _extract_search_context(facts, source_data)
    return facts


def _extract_contract(facts: FilterFacts, source_data: dict[str, Any]) -> None:
    contract = _clean_text(source_data.get("contractType"))
    if not contract:
        return
    facts.structured_contract_type = normalize_source_contract_type(contract) or contract
    facts.structured_contract_source = "linkedin:contractType"
    facts.facts_used.append(f"structured_contract_type:{facts.structured_contract_type}")


def _extract_location(facts: FilterFacts, source_data: dict[str, Any]) -> None:
    location = _clean_text(source_data.get("location"))
    if not location:
        return
    facts.structured_location = location
    facts.structured_location_source = "linkedin:location"
    facts.facts_used.append("structured_location:location")


def _extract_remote_policy(facts: FilterFacts, source_data: dict[str, Any]) -> None:
    text = norm(
        " ".join(
            str(source_data.get(key) or "")
            for key in ("remote", "workType", "location")
        )
    )
    if any(marker in text for marker in _REMOTE_MARKERS):
        facts.structured_remote_policy = "remote"
        facts.structured_remote_source = "linkedin:remote/workType/location"
        facts.facts_used.append("structured_remote_policy:remote")
    elif any(marker in text for marker in _HYBRID_MARKERS):
        facts.structured_remote_policy = "hybrid"
        facts.structured_remote_source = "linkedin:remote/workType/location"
        facts.facts_used.append("structured_remote_policy:hybrid")


def _extract_experience(facts: FilterFacts, source_data: dict[str, Any]) -> None:
    experience = _clean_text(source_data.get("experienceLevel"))
    if not experience:
        return
    facts.experience_requirement = experience
    facts.experience_source = "linkedin:experienceLevel"
    facts.facts_used.append(f"experience_requirement:{experience}")


def _extract_search_context(facts: FilterFacts, source_data: dict[str, Any]) -> None:
    search = source_data.get("_smartapply_search")
    if not isinstance(search, dict):
        return

    facts.structured_search_origin = "apify_linkedin_jobs_scraper"
    chips = _search_chips(search)
    if chips:
        facts.structured_search_chips = chips
    facts.facts_used.append("structured_search_origin:apify_linkedin_jobs_scraper")


def _search_chips(search: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "datePosted",
        "contractType",
        "experienceLevel",
        "remote",
        "experience_fallback_used",
    ):
        text = _format_search_value(search.get(key))
        if text:
            parts.append(f"{key}={text}")
    return "; ".join(parts)


def _format_search_value(value: Any) -> str:
    if isinstance(value, list | tuple):
        return ",".join(str(item) for item in value if str(item).strip())
    return _clean_text(value) or ""
