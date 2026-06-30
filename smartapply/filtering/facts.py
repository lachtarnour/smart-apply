"""Canonical structured facts consumed by local filtering."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FilterFacts:
    source: str | None = None

    experience_min_years: float | None = None
    experience_required: bool | None = None
    experience_requirement: str | None = None
    experience_source: str | None = None

    structured_contract_type: str | None = None
    structured_contract_source: str | None = None

    structured_location: str | None = None
    structured_location_source: str | None = None

    structured_remote_policy: str | None = None
    structured_remote_source: str | None = None

    structured_search_origin: str | None = None
    structured_search_chips: str | None = None

    structured_alternance: bool | None = None

    structured_work_time: str | None = None
    structured_work_time_source: str | None = None

    structured_rome_code: str | None = None
    structured_rome_label: str | None = None
    structured_appellation_label: str | None = None

    facts_used: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
