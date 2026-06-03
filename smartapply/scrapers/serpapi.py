"""SerpApi Google Jobs scraper.

Documentation: https://serpapi.com/google-jobs-api

Pagination uses ``next_page_token`` returned in ``serpapi_pagination``.
Each page returns up to 10 results; we cap pages via ``SERPAPI_MAX_PAGES``.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger
from smartapply.scrapers.base import RawJob, Scraper, ScraperConfigError, make_external_id

logger = get_logger(__name__)

SERPAPI_URL = "https://serpapi.com/search.json"
SERPAPI_DATE_POSTED_OPTIONS = {
    "any": "",
    "today": "since yesterday",
    "3days": "in the last 3 days",
    "week": "in the last week",
    "month": "in the last month",
}
SERPAPI_DATE_POSTED_LABELS = {
    "any": "Toutes dates",
    "today": "Aujourd'hui",
    "3days": "3 derniers jours",
    "week": "7 derniers jours",
    "month": "30 derniers jours",
}


def split_localization_values(value: str | None, *, fallback: str) -> list[str]:
    raw = value if value is not None else fallback
    parts = [
        part.strip()
        for chunk in (raw or fallback).split("|")
        for part in chunk.split(",")
    ]
    return [part for part in parts if part] or [fallback]


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


def query_with_date_posted(query: str, date_posted: str | None) -> str:
    """Append the Google Jobs date phrase used by SerpApi date filters."""
    normalized = normalize_date_posted(date_posted)
    suffix = SERPAPI_DATE_POSTED_OPTIONS[normalized]
    if not suffix:
        return query
    q = query.strip()
    if suffix.lower() in q.lower():
        return q
    return f"{q} {suffix}"


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
    ):
        settings = get_settings()
        self.api_key = api_key or settings.serpapi_api_key
        self.max_pages = max_pages or settings.serpapi_max_pages
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
        uds: str | None = None,
        date_posted: str | None = None,
        hl: str | None = None,
        gl: str | None = None,
        google_domain: str | None = None,
        **kwargs: Any,
    ) -> Iterator[RawJob]:
        if not self.api_key:
            raise ScraperConfigError("SERPAPI_API_KEY is not set")

        freshness = (
            self.date_posted
            if date_posted is None
            else normalize_date_posted(date_posted)
        )
        search_query = query_with_date_posted(query, freshness)
        search_uds = (uds if uds is not None else self.uds).strip()
        languages = split_localization_values(hl, fallback=self.hl)
        countries = split_localization_values(gl, fallback=self.gl)
        domains = split_localization_values(google_domain, fallback=self.google_domain)
        locale_count = max(1, len(languages) * len(countries) * len(domains))
        per_locale_max = (
            max(1, math.ceil(max_results / locale_count))
            if max_results and locale_count > 1
            else max_results
        )

        collected: list[RawJob] = []
        seen_external_ids: set[str] = set()
        for domain in domains:
            for country in countries:
                for language in languages:
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
                    if search_uds:
                        params["uds"] = search_uds

                    for job in self._search_pages(params, max_results=per_locale_max):
                        if job.external_id in seen_external_ids:
                            continue
                        seen_external_ids.add(job.external_id)
                        collected.append(job)

        for job in collected[:max_results] if max_results else collected:
            yield job

    def _search_pages(
        self,
        params: dict[str, Any],
        *,
        max_results: int | None,
    ) -> Iterator[RawJob]:
        pages_limit = max(1, math.ceil(max_results / 10)) if max_results else self.max_pages
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
                break

            pages_fetched += 1
            jobs = payload.get("jobs_results") or []
            if not jobs:
                logger.info(
                    "SerpApi pagination exhausted at page %d for hl=%s gl=%s q=%r",
                    pages_fetched,
                    params.get("hl"),
                    params.get("gl"),
                    params.get("q"),
                )
                break

            for raw in jobs:
                job = self._to_raw_job(raw)
                if job is None:
                    continue
                yield job
                results_yielded += 1
                if max_results and results_yielded >= max_results:
                    return

            pagination = payload.get("serpapi_pagination") or {}
            next_token = pagination.get("next_page_token")
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
        if not value:
            return None
        v = value.lower()
        mapping = {
            "full-time": "Full-time",
            "full time": "Full-time",
            "part-time": "Part-time",
            "part time": "Part-time",
            "contract": "Contract",
            "contractor": "Contract",
            "internship": "Internship",
            "intern": "Internship",
            "temporary": "Temporary",
        }
        for key, normalized in mapping.items():
            if key in v:
                return normalized
        return value

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
