"""Source-specific structured facts for the local filter.

This module is the adapter boundary between raw source payloads and the global
rule-based filter. Source quirks stay here; ``JobFilter`` only consumes the
normalized facts below.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from smartapply.filtering.text import norm
from smartapply.utils.contracts import normalize_source_contract_type


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


_FT_EXPERIENCE_DURATION_RE = re.compile(
    r"\b(?P<amount>\d{1,3})\s*"
    r"(?P<unit>an(?:\(s\)|s)?|annee(?:\(s\)|s)?|mois|years?|months?)"
    r"(?=\W|$)",
    re.IGNORECASE,
)

_FT_EXPERIENCE_NOT_REQUIRED = {
    "d",
    "debutant accepte",
    "aucune experience",
    "non exige",
    "non exigee",
}
_FT_EXPERIENCE_PREFERRED = {"s", "souhaite", "souhaitee", "preferred"}
_FT_EXPERIENCE_REQUIRED = {"e", "exige", "exigee", "obligatoire", "required"}

_FT_APPRENTICESHIP_MARKERS = (
    "alternance",
    "apprentissage",
    "professionnalisation",
    "contrat apprentissage",
    "cont. professionnalisation",
)
_FT_INTERNSHIP_MARKERS = ("stage", "stagiaire")
_FT_NON_SALARIED_MARKERS = (
    "emploi non salarie",
    "profession liberale",
    "franchise",
    "profession commerciale",
)
_FT_TEMPORARY_MARKERS = ("interim", "mission interim")
_FT_PART_TIME_MARKERS = ("temps partiel", "mi temps", "mi-temps", "part time", "part-time")
_FT_FULL_TIME_MARKERS = ("temps plein", "plein temps", "full time", "full-time")
_FT_WEEKLY_HOURS_RE = re.compile(r"\b(?P<hours>\d{1,2})(?:[,.]\d+)?\s*h\b")

_SERPAPI_PRESTATAIRE_MARKERS = ("prestataire",)
_SERPAPI_REMOTE_LOCATION_MARKERS = (
    "remote",
    "anywhere",
    "a distance",
    "teletravail",
    "teletravail possible",
)
_SERPAPI_HYBRID_LOCATION_MARKERS = ("hybrid", "hybride")


def build_filter_facts(job: Any) -> FilterFacts:
    """Build normalized structured facts for a job-like object.

    Unknown sources, missing ``source_data`` and plain manual jobs intentionally
    return an empty facts object so the global text filter remains the fallback.
    """

    source = _clean_text(getattr(job, "source", None))
    source_data = getattr(job, "source_data", None)
    if not isinstance(source_data, dict):
        return FilterFacts(source=source)

    if norm(source) == "francetravail":
        return build_francetravail_filter_facts(source_data)
    if norm(source) == "serpapi":
        return build_serpapi_filter_facts(source_data)

    return FilterFacts(source=source)


def build_francetravail_filter_facts(source_data: dict[str, Any]) -> FilterFacts:
    """Extract reliable France Travail structured fields for local filtering."""

    facts = FilterFacts(source="francetravail")
    _extract_francetravail_experience(facts, source_data)
    _extract_francetravail_contract(facts, source_data)
    _extract_francetravail_location(facts, source_data)
    _extract_francetravail_work_modalities(facts, source_data)
    _extract_francetravail_rome_context(facts, source_data)
    return facts


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
    facts.facts_used.append(
        f"structured_contract_type:{facts.structured_contract_type}"
    )


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


def _extract_francetravail_experience(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    smart = source_data.get("_smartapply_experience")
    smart_exp = smart if isinstance(smart, dict) else {}
    raw_required = source_data.get("experienceExige")
    label = _clean_text(source_data.get("experienceLibelle"))
    comment = _clean_text(source_data.get("experienceCommentaire"))

    requirement = _clean_text(smart_exp.get("requirement"))
    required = _coerce_bool(smart_exp.get("required"))
    if requirement is None:
        required, requirement = _experience_requirement(raw_required, label)
    elif required is None:
        required = _required_from_requirement(requirement)

    if requirement:
        facts.experience_requirement = requirement
        facts.experience_required = required
        facts.experience_source = "francetravail:_smartapply_experience.requirement"
        facts.facts_used.append(f"experience_requirement:{requirement}")

    if requirement in {"beginner_accepted", "preferred"} or required is False:
        years = _coerce_years(smart_exp.get("min_years"))
        if years is not None and years > 0:
            facts.warnings.append("experience_years_ignored_for_non_required_requirement")
        return

    years_source = "francetravail:_smartapply_experience.min_years"
    years = _coerce_years(smart_exp.get("min_years"))
    if years is None:
        years = _parse_ft_experience_years(label, comment)
        years_source = "francetravail:experienceLibelle"

    if years is None:
        return
    if years > 11:
        facts.warnings.append(f"experience_min_years_untrusted:{_format_years(years)}")
        return

    facts.experience_min_years = years
    facts.experience_required = True if required is None else required
    facts.experience_source = years_source
    facts.facts_used.append(f"experience_min_years:{_format_years(years)}")


def _extract_francetravail_contract(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    type_code = _clean_text(source_data.get("typeContrat"))
    type_label = _clean_text(source_data.get("typeContratLibelle"))
    nature = _clean_text(source_data.get("natureContrat"))
    values = (type_code, type_label, nature)
    text = " ".join(norm(value) for value in values if value)

    contract_type: str | None = None
    source = "francetravail:typeContratLibelle"
    if any(marker in text for marker in _FT_APPRENTICESHIP_MARKERS):
        contract_type = "Apprenticeship"
        source = "francetravail:natureContrat"
    elif any(marker in text for marker in _FT_INTERNSHIP_MARKERS):
        contract_type = "Internship"
    elif any(marker in text for marker in _FT_NON_SALARIED_MARKERS) or norm(type_code) in {
        "cce",
        "fra",
        "lib",
    }:
        contract_type = "Freelance"
        source = "francetravail:natureContrat"
    elif any(marker in text for marker in _FT_TEMPORARY_MARKERS) or norm(type_code) == "mis":
        contract_type = "Temporary"
    elif type_label or nature:
        contract_type = normalize_source_contract_type(type_label or nature)

    if not contract_type:
        return

    facts.structured_contract_type = contract_type
    facts.structured_contract_source = source
    facts.facts_used.append(f"structured_contract_type:{contract_type}")


def _extract_francetravail_location(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    lieu = source_data.get("lieuTravail")
    if not isinstance(lieu, dict):
        return
    location = _clean_text(lieu.get("libelle"))
    if not location:
        return
    facts.structured_location = location
    facts.structured_location_source = "francetravail:lieuTravail.libelle"
    facts.facts_used.append("structured_location:lieuTravail.libelle")


def _extract_francetravail_work_modalities(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    alternance = _coerce_bool(source_data.get("alternance"))
    if alternance is not None:
        facts.structured_alternance = alternance
        facts.facts_used.append(f"structured_alternance:{str(alternance).lower()}")

    converted = _clean_text(source_data.get("dureeTravailLibelleConverti"))
    if converted:
        work_time = _normalized_work_time_label(converted) or converted
        facts.structured_work_time = work_time
        facts.structured_work_time_source = "francetravail:dureeTravailLibelleConverti"
        facts.facts_used.append(f"structured_work_time:{work_time}")
        return

    raw_label = _clean_text(source_data.get("dureeTravailLibelle"))
    work_time = _work_time_from_raw_label(raw_label)
    if not work_time:
        return
    facts.structured_work_time = work_time
    facts.structured_work_time_source = "francetravail:dureeTravailLibelle"
    facts.facts_used.append(f"structured_work_time:{work_time}")


def _extract_francetravail_rome_context(
    facts: FilterFacts,
    source_data: dict[str, Any],
) -> None:
    facts.structured_rome_code = _clean_text(source_data.get("romeCode"))
    facts.structured_rome_label = _clean_text(source_data.get("romeLibelle"))
    facts.structured_appellation_label = _clean_text(source_data.get("appellationlibelle"))

    if facts.structured_rome_code or facts.structured_rome_label:
        parts = [
            part
            for part in (facts.structured_rome_code, facts.structured_rome_label)
            if part
        ]
        facts.facts_used.append(f"structured_rome:{':'.join(parts)}")
    if facts.structured_appellation_label:
        facts.facts_used.append(
            f"structured_appellation:{facts.structured_appellation_label}"
        )


def _normalized_work_time_label(value: str | None) -> str | None:
    normalized = norm(value)
    if any(marker in normalized for marker in _FT_PART_TIME_MARKERS):
        return "Temps partiel"
    if any(marker in normalized for marker in _FT_FULL_TIME_MARKERS):
        return "Temps plein"
    return None


def _work_time_from_raw_label(value: str | None) -> str | None:
    normalized_label = _normalized_work_time_label(value)
    if normalized_label:
        return normalized_label
    normalized = norm(value)
    if not normalized:
        return None
    match = _FT_WEEKLY_HOURS_RE.search(normalized)
    if not match:
        return None
    hours = int(match.group("hours"))
    if hours < 35:
        return "Temps partiel"
    return None


def _experience_requirement(
    raw_value: Any,
    label: str | None,
) -> tuple[bool | None, str | None]:
    raw_norm = norm(raw_value).strip(" .:-")
    label_norm = norm(label)
    haystack = " ".join(part for part in (raw_norm, label_norm) if part)
    if not haystack:
        return None, None

    if raw_norm in _FT_EXPERIENCE_NOT_REQUIRED or any(
        marker in haystack
        for marker in ("debutant accepte", "aucune experience", "sans experience")
    ):
        return False, "beginner_accepted"
    if raw_norm in _FT_EXPERIENCE_PREFERRED or any(
        marker in haystack for marker in ("souhaite", "apprecie", "preferred")
    ):
        return False, "preferred"
    if raw_norm in _FT_EXPERIENCE_REQUIRED or any(
        marker in haystack for marker in ("exige", "obligatoire", "required", "demandee")
    ):
        return True, "required"
    if _FT_EXPERIENCE_DURATION_RE.search(label_norm):
        return True, "required"
    return None, "unspecified"


def _required_from_requirement(requirement: str) -> bool | None:
    normalized = norm(requirement)
    if normalized in {"beginner_accepted", "preferred", "not_required"}:
        return False
    if normalized == "required":
        return True
    return None


def _parse_ft_experience_years(*values: str | None) -> float | None:
    for value in values:
        if not value:
            continue
        match = _FT_EXPERIENCE_DURATION_RE.search(norm(value))
        if not match:
            continue
        amount = int(match.group("amount"))
        unit = match.group("unit")
        if unit.startswith(("mois", "month")):
            return round(amount / 12, 2)
        return float(amount)
    return None


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = norm(value)
    if normalized in {"true", "1", "yes", "required", "exige", "exigee", "e"}:
        return True
    if normalized in {"false", "0", "no", "not_required", "debutant accepte", "d"}:
        return False
    return None


def _coerce_years(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        years = float(value)
    else:
        try:
            years = float(str(value).replace(",", "."))
        except ValueError:
            return None
    if not math.isfinite(years) or years < 0:
        return None
    return years


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_years(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)
