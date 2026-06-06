"""SerpApi Google Jobs scraper.

Documentation: https://serpapi.com/google-jobs-api

Pagination uses ``next_page_token`` returned in ``serpapi_pagination``.
Each page returns up to 10 results; we cap pages via ``SERPAPI_MAX_PAGES``.
Date filtering uses Google Jobs ``chips`` such as ``date_posted:week``.
Do not append freshness phrases to ``q``: it hurts recall for role titles.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger
from smartapply.scrapers.base import RawJob, Scraper, ScraperConfigError, make_external_id
from smartapply.utils.contracts import normalize_source_contract_type

logger = get_logger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
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


class SerpApiGoogleJobsScraper(Scraper):
    name = "serpapi"

    def __init__(
        self,
        api_key: str | None = None,
        max_pages: int | None = None,
        *,
        google_domain: str | None = None,
        hl: str | None = None,
        gl: str | None = None,
        low_result_fallback_target: int | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.serpapi_api_key
        self.max_pages = max_pages or settings.serpapi_max_pages
        self.low_result_fallback_target = (
            settings.serpapi_low_result_fallback_target
            if low_result_fallback_target is None
            else low_result_fallback_target
        )
        self.google_domain = google_domain or settings.serpapi_google_domain
        self.hl = hl or settings.serpapi_hl
        self.gl = gl or settings.serpapi_gl
        self.default_location = settings.serpapi_default_location
        self.date_posted = normalize_date_posted(settings.serpapi_date_posted)
        self.uds = settings.serpapi_uds.strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch(self, params: dict[str, Any]) -> dict[str, Any]:
        response = requests.get(SERPAPI_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def search(
        self,
        query: str,
        location: str | None = None,
        *,
        max_results: int | None = None,
        ltype: str | None = None,
        chips: str | None = None,
        uds: str | None = None,
        date_posted: str | None = None,
        hl: str | None = None,
        gl: str | None = None,
        google_domain: str | None = None,
        **kwargs: Any,
    ) -> Iterator[RawJob]:
        if not self.api_key:
            raise ScraperConfigError("SERPAPI_API_KEY is not set")
        if max_results is None:
            raise ScraperConfigError(
                "SerpApi requires max_results to avoid unbounded paid pagination."
            )
        if max_results is not None and max_results <= 0:
            return

        freshness = (
            self.date_posted
            if date_posted is None
            else normalize_date_posted(date_posted)
        )
        search_query = query.strip()
        date_chip = date_posted_chip(freshness)
        search_chips = combine_chips(chips, date_chip)
        search_uds = (uds if uds is not None else self.uds).strip()
        languages = split_localization_values(hl, fallback=self.hl)
        countries = split_localization_values(gl, fallback=self.gl)
        domains = split_localization_values(google_domain, fallback=self.google_domain)
        collected: list[RawJob] = []
        seen_external_ids: set[str] = set()
        for domain in domains:
            for country in countries:
                for language in market_languages(
                    languages,
                    country=country,
                    location=location or self.default_location,
                ):
                    remaining = (
                        max_results - len(collected)
                        if max_results is not None
                        else None
                    )
                    if remaining is not None and remaining <= 0:
                        break
                    params: dict[str, Any] = {
                        "engine": "google_jobs",
                        "q": search_query,
                        "location": location or self.default_location,
                        "google_domain": domain,
                        "hl": language,
                        "gl": country,
                        "api_key": self.api_key,
                    }
                    if ltype:
                        params["ltype"] = ltype
                    if search_chips:
                        params["chips"] = search_chips
                    if search_uds:
                        params["uds"] = search_uds

                    for job in self._search_pages_with_fallback(
                        params,
                        max_results=remaining,
                    ):
                        if job.external_id in seen_external_ids:
                            continue
                        seen_external_ids.add(job.external_id)
                        collected.append(job)
                        if max_results is not None and len(collected) >= max_results:
                            break

        for job in collected[:max_results] if max_results is not None else collected:
            yield job

    def _search_pages_with_fallback(
        self,
        params: dict[str, Any],
        *,
        max_results: int | None,
    ) -> Iterator[RawJob]:
        seen_external_ids: set[str] = set()
        yielded = 0

        for job in self._search_pages(params, max_results=max_results):
            if job.external_id in seen_external_ids:
                continue
            seen_external_ids.add(job.external_id)
            yielded += 1
            yield _with_search_audit(job, params=params, result_origin="strict")

        if yielded == 0:
            for fallback_params in zero_result_fallback_params(params):
                logger.info(
                    "SerpApi zero-result filter widening: q=%r hl=%s gl=%s chips=%r -> %r",
                    params.get("q"),
                    params.get("hl"),
                    params.get("gl"),
                    params.get("chips"),
                    fallback_params.get("chips"),
                )
                fallback_yielded = False
                for job in self._search_pages(
                    fallback_params,
                    max_results=max_results,
                ):
                    if job.external_id in seen_external_ids:
                        continue
                    seen_external_ids.add(job.external_id)
                    fallback_yielded = True
                    yield _with_search_audit(
                        job,
                        params=params,
                        result_origin="fallback",
                        fallback_reason="zero_result_strict_filters",
                        fallback_params=fallback_params,
                    )
                if fallback_yielded:
                    return

            location = (params.get("location") or "").strip()
            query = (params.get("q") or "").strip()
            if not location or not query:
                return
            fallback_params = dict(params)
            fallback_params["q"] = f"{query} jobs in {location}"
            fallback_params.pop("location", None)
            logger.info(
                "SerpApi fallback search after empty result: q=%r hl=%s gl=%s chips=%r",
                fallback_params.get("q"),
                fallback_params.get("hl"),
                fallback_params.get("gl"),
                fallback_params.get("chips"),
            )
            for job in self._search_pages(fallback_params, max_results=max_results):
                if job.external_id in seen_external_ids:
                    continue
                seen_external_ids.add(job.external_id)
                yield _with_search_audit(
                    job,
                    params=params,
                    result_origin="fallback",
                    fallback_reason="zero_result_contextual_location",
                    fallback_params=fallback_params,
                )
            return

        if not _should_widen_low_result(
            params,
            yielded,
            max_results,
            self.low_result_fallback_target,
        ):
            return

        target = _low_result_target(max_results, self.low_result_fallback_target)
        for fallback_params in zero_result_fallback_params(params):
            if yielded >= target:
                return
            remaining = target - yielded
            logger.info(
                "SerpApi low-result filter widening: q=%r hl=%s gl=%s count=%d chips=%r -> %r",
                params.get("q"),
                params.get("hl"),
                params.get("gl"),
                yielded,
                params.get("chips"),
                fallback_params.get("chips"),
            )
            for job in self._search_pages(fallback_params, max_results=remaining):
                if job.external_id in seen_external_ids:
                    continue
                seen_external_ids.add(job.external_id)
                yielded += 1
                yield _with_search_audit(
                    job,
                    params=params,
                    result_origin="fallback",
                    fallback_reason="low_result_strict_filters",
                    fallback_params=fallback_params,
                )
                if yielded >= target:
                    return

    def _search_pages(
        self,
        params: dict[str, Any],
        *,
        max_results: int | None,
    ) -> Iterator[RawJob]:
        pages_limit = self.max_pages
        pages_fetched = 0
        results_yielded = 0
        next_token: str | None = None

        while pages_fetched < pages_limit:
            page_params = dict(params)
            if next_token:
                page_params["next_page_token"] = next_token
            try:
                payload = self._fetch(page_params)
            except requests.RequestException as e:
                logger.error("SerpApi request failed: %s", e)
                return

            pages_fetched += 1
            jobs = payload.get("jobs_results") or []
            pagination = payload.get("serpapi_pagination") or {}
            next_token = pagination.get("next_page_token")
            if not jobs:
                logger.info(
                    "SerpApi page %d returned no jobs for hl=%s gl=%s q=%r chips=%r%s",
                    pages_fetched,
                    params.get("hl"),
                    params.get("gl"),
                    params.get("q"),
                    params.get("chips"),
                    " but next_page_token is present" if next_token else "",
                )
                if next_token:
                    continue
                break

            for raw in jobs:
                job = self._to_raw_job(raw)
                if job is None:
                    continue
                yield job
                results_yielded += 1
                if max_results is not None and results_yielded >= max_results:
                    return

            if not next_token:
                break

    # -------------------- mapping --------------------

    def _to_raw_job(self, raw: dict[str, Any]) -> RawJob | None:
        title = raw.get("title")
        company = raw.get("company_name")
        if not title or not company:
            return None

        apply_options = raw.get("apply_options") or []
        app_url: str | None = None
        if apply_options:
            app_url = apply_options[0].get("link")
        if not app_url:
            app_url = raw.get("share_link")

        ext_parts = [
            raw.get("job_id") or app_url or "",
            title,
            company,
            raw.get("location") or "",
        ]
        external_id = make_external_id(self.name, *ext_parts)

        extensions = raw.get("detected_extensions") or {}
        contract_type = self._normalize_contract(extensions.get("schedule_type"))
        remote_policy = self._normalize_remote(extensions, raw.get("location"))

        description = raw.get("description") or ""
        highlights = raw.get("job_highlights") or []
        if highlights:
            extra_sections: list[str] = []
            for section in highlights:
                title_h = section.get("title") or ""
                items = section.get("items") or []
                if items:
                    extra_sections.append(f"\n\n{title_h}\n- " + "\n- ".join(items))
            description = description + "".join(extra_sections)

        return RawJob(
            external_id=external_id,
            title=title.strip(),
            company=company.strip(),
            location=raw.get("location"),
            contract_type=contract_type,
            remote_policy=remote_policy,
            description=description,
            application_url=app_url,
            apply_options=apply_options or None,
            source=self.name,
            source_data=raw,
        )

    @staticmethod
    def _normalize_contract(value: str | None) -> str | None:
        return normalize_source_contract_type(value)

    @staticmethod
    def _normalize_remote(extensions: dict[str, Any], location: str | None) -> str | None:
        if extensions.get("work_from_home"):
            return "remote"
        loc = (location or "").lower()
        if "anywhere" in loc or "remote" in loc:
            return "remote"
        if "hybrid" in loc:
            return "hybrid"
        return None
