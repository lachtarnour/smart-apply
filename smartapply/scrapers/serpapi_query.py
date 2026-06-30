"""SerpApi query chips, localization and fallback helpers."""

from __future__ import annotations

from typing import Any

from smartapply.offers import RawJob
from smartapply.scrapers.base import ScraperConfigError

SERPAPI_DATE_POSTED_OPTIONS = {
    "any": "",
    "today": "date_posted:today",
    "3days": "date_posted:3days",
    "week": "date_posted:week",
    "month": "date_posted:month",
}
SERPAPI_DATE_POSTED_LABELS = {
    "any": "Toutes dates",
    "today": "Aujourd'hui",
    "3days": "3 derniers jours",
    "week": "7 derniers jours",
    "month": "30 derniers jours",
}
LOW_RESULT_FALLBACK_TARGET = 10

def split_localization_values(value: str | None, *, fallback: str) -> list[str]:
    raw = value if value is not None else fallback
    parts = [
        part.strip()
        for chunk in (raw or fallback).split("|")
        for part in chunk.split(",")
    ]
    return [part for part in parts if part] or [fallback]


def _is_france_market(country: str | None, location: str | None) -> bool:
    country_norm = (country or "").strip().lower()
    location_norm = (location or "").strip().lower()
    return country_norm == "fr" or any(
        marker in location_norm
        for marker in ("france", "paris", "ile-de-france", "île-de-france")
    )


def market_languages(
    languages: list[str],
    *,
    country: str | None,
    location: str | None,
) -> list[str]:
    """Return Google Jobs UI languages for the target market.

    ``hl`` controls Google's interface language, not the language of the job
    descriptions. For the French job market, Google Jobs returns both English
    and French-titled offers much more reliably with ``hl=fr``; ``hl=en`` often
    returns zero even for English role titles.
    """
    if _is_france_market(country, location):
        return ["fr"]
    deduped: list[str] = []
    seen: set[str] = set()
    for language in languages:
        key = language.strip().lower()
        if not key or key in seen:
            continue
        deduped.append(language)
        seen.add(key)
    return deduped or ["en"]


def normalize_date_posted(value: str | None) -> str:
    normalized = (value or "any").strip().lower().replace("_", "").replace("-", "")
    aliases = {
        "": "any",
        "none": "any",
        "all": "any",
        "lastday": "today",
        "day": "today",
        "1day": "today",
        "last3days": "3days",
        "3day": "3days",
        "lastweek": "week",
        "7days": "week",
        "last7days": "week",
        "lastmonth": "month",
        "30days": "month",
        "last30days": "month",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in SERPAPI_DATE_POSTED_OPTIONS:
        allowed = ", ".join(SERPAPI_DATE_POSTED_OPTIONS)
        raise ScraperConfigError(
            f"Invalid SERPAPI_DATE_POSTED={value!r}. Allowed values: {allowed}."
        )
    return normalized


def date_posted_chip(date_posted: str | None) -> str:
    """Return the static Google Jobs chip for a freshness filter."""
    normalized = normalize_date_posted(date_posted)
    return SERPAPI_DATE_POSTED_OPTIONS[normalized]


def combine_chips(*values: str | None) -> str:
    """Combine comma-separated chip values while preserving order."""
    chips: list[str] = []
    seen: set[str] = set()
    for value in values:
        for part in (value or "").split(","):
            chip = part.strip()
            if not chip:
                continue
            key = chip.lower()
            if key in seen:
                continue
            chips.append(chip)
            seen.add(key)
    return ",".join(chips)


def _chip_parts(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _replace_date_chip(chips: str | None, replacement: str | None) -> str:
    parts = [
        part
        for part in _chip_parts(chips)
        if not part.lower().startswith("date_posted:")
    ]
    if replacement:
        parts.append(replacement)
    return ",".join(parts)


def _remove_chip_prefix(chips: str | None, prefix: str) -> str:
    prefix = prefix.lower()
    return ",".join(
        part for part in _chip_parts(chips) if not part.lower().startswith(prefix)
    )


def zero_result_fallback_params(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Return progressively wider SerpApi attempts for empty Google Jobs pages.

    Google Jobs can return zero for exact role titles with strict chips even
    when nearby results exist. Widening only after a zero-result attempt keeps
    the default search precise while avoiding false negatives at ingestion time.
    """
    attempts: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None]] = {
        (params.get("q", ""), params.get("chips") or "")
    }

    def add(candidate: dict[str, Any]) -> None:
        chips = candidate.get("chips") or ""
        key = (candidate.get("q", ""), chips)
        if key in seen:
            return
        seen.add(key)
        if chips:
            candidate["chips"] = chips
        else:
            candidate.pop("chips", None)
        attempts.append(candidate)

    chips = params.get("chips") or ""
    has_date = any(part.lower().startswith("date_posted:") for part in _chip_parts(chips))
    has_employment = any(
        part.lower().startswith("employment_type:") for part in _chip_parts(chips)
    )
    if has_date:
        add({**params, "chips": _replace_date_chip(chips, "date_posted:month")})
        add({**params, "chips": _replace_date_chip(chips, None)})
    if has_employment:
        without_employment = _remove_chip_prefix(chips, "employment_type:")
        add({**params, "chips": without_employment})
        if has_date:
            add(
                {
                    **params,
                    "chips": _replace_date_chip(
                        without_employment,
                        "date_posted:month",
                    ),
                }
            )
            add({**params, "chips": _replace_date_chip(without_employment, None)})
    return attempts


def _low_result_target(
    max_results: int | None,
    fallback_target: int = LOW_RESULT_FALLBACK_TARGET,
) -> int:
    """Aim to fill at least one Google Jobs page when strict chips underperform."""
    if max_results is None or fallback_target <= 0:
        return 0
    return min(max_results, fallback_target)


def _should_widen_low_result(
    params: dict[str, Any],
    yielded: int,
    max_results: int | None,
    fallback_target: int = LOW_RESULT_FALLBACK_TARGET,
) -> bool:
    target = _low_result_target(max_results, fallback_target)
    if yielded <= 0 or target <= 0 or yielded >= target:
        return False
    chips = params.get("chips") or ""
    return any(
        part.lower().startswith(("date_posted:", "employment_type:"))
        for part in _chip_parts(chips)
    )


def _with_search_audit(
    job: RawJob,
    *,
    params: dict[str, Any],
    result_origin: str,
    fallback_reason: str | None = None,
    fallback_params: dict[str, Any] | None = None,
) -> RawJob:
    source_data = dict(job.source_data or {})
    source_data["_smartapply_search"] = {
        "query": params.get("q"),
        "location": params.get("location"),
        "google_domain": params.get("google_domain"),
        "hl": params.get("hl"),
        "gl": params.get("gl"),
        "result_origin": result_origin,
        "strict_chips": params.get("chips"),
        "fallback_reason": fallback_reason,
        "fallback_chips": fallback_params.get("chips") if fallback_params else None,
        "fallback_query": fallback_params.get("q") if fallback_params else None,
    }
    return job.model_copy(update={"source_data": source_data})


