"""Welcome to the Jungle personalized matches scraper."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import requests as _requests

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger
from smartapply.scrapers.base import RawJob, Scraper, ScraperConfigError, ScraperError

logger = get_logger(__name__)
requests = _requests

WTTJ_BASE_URL = "https://www.welcometothejungle.com"
WTTJ_API_BASE_URL = "https://api.welcometothejungle.com"
WTTJ_MATCHES_URL = f"{WTTJ_BASE_URL}/fr/jobs-matches"
WTTJ_MATCHES_API_URL = f"{WTTJ_API_BASE_URL}/api/v3/search/jobs"
WTTJ_ORGANIZATIONS_API_URL = f"{WTTJ_API_BASE_URL}/api/v3/organizations"
WTTJ_SOURCE = "welcometothejungle"
WTTJ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

_JOB_PATH_RE = re.compile(r"/(?:fr|en)/companies/[^/]+/jobs/[^/?#]+")
_CONTRACT_LABELS = (
    "CDI",
    "CDD",
    "Stage",
    "Alternance",
    "Freelance",
    "VIE",
    "Temps partiel",
)
_IGNORED_SECTION_TEXTS = {
    "voir plus",
    "view more",
    "voir le site",
    "view website",
    "voir toutes les offres",
    "view all job posts",
    "voir tous les avantages",
    "suivre",
    "follow",
}


@dataclass(frozen=True)
class WTTJJobLink:
    """A job link discovered from a personalized matches page."""

    url: str
    title_hint: str | None = None
    api_data: dict[str, Any] | None = None


class WTTJScraperError(ScraperError):
    """Raised when WTTJ scraping or parsing fails."""


from smartapply.scrapers.wttj import company_hydration as _company_hydration  # noqa: E402
from smartapply.scrapers.wttj import matches_api as _matches_api  # noqa: E402
from smartapply.scrapers.wttj import offer_parser as _offer_parser  # noqa: E402
from smartapply.scrapers.wttj.company_hydration import (  # noqa: E402
    parse_company_html,
    parse_saved_company,
)
from smartapply.scrapers.wttj.matches_api import (  # noqa: E402
    fetch_html_with_requests,
    matches_page_url,
    parse_listing_links,
    parse_matches_api_links,
    parse_saved_listing,
    scrape_matches_live,
)
from smartapply.scrapers.wttj.offer_parser import (  # noqa: E402
    parse_detail_api_job,
    parse_detail_html,
    parse_saved_detail,
)


def fetch_matches_api_page(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _matches_api.fetch_matches_api_page(*args, **kwargs)


def fetch_detail_api_job(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return _offer_parser.fetch_detail_api_job(*args, **kwargs)


def scrape_matches_requests(
    *,
    pages: Sequence[int],
    cookie_header: str,
    max_jobs: int | None = None,
    per_page: int | None = None,
    include_company_profile: bool = True,
    skip_failed_jobs: bool = True,
    timeout: int = 30,
    delay_seconds: float = 0.5,
    extra_headers: dict[str, str] | None = None,
) -> Iterator[RawJob]:
    return _matches_api.scrape_matches_requests(
        pages=pages,
        cookie_header=cookie_header,
        max_jobs=max_jobs,
        per_page=per_page,
        include_company_profile=include_company_profile,
        skip_failed_jobs=skip_failed_jobs,
        timeout=timeout,
        delay_seconds=delay_seconds,
        extra_headers=extra_headers,
        fetch_matches_api_page_fn=fetch_matches_api_page,
        fetch_detail_api_job_fn=fetch_detail_api_job,
    )


class WelcomeToTheJungleScraper(Scraper):
    """Personalized Welcome to the Jungle matches source.

    WTTJ does not expose a searchable endpoint for this workflow. The source
    reads the logged-in user's personalized matches feed, then enriches each
    public job page with the public WTTJ company profile.
    """

    name = WTTJ_SOURCE

    def __init__(
        self,
        *,
        cookie_header: str | None = None,
        max_pages: int | None = None,
        pages: int | None = None,
        per_page: int | None = None,
        include_company_profile: bool | None = None,
        skip_failed_jobs: bool | None = None,
        timeout: int | None = None,
        delay_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.cookie_header = cookie_header if cookie_header is not None else settings.wttj_cookie
        self.max_pages = max_pages if max_pages is not None else settings.wttj_max_pages
        self.pages = pages if pages is not None else settings.wttj_pages
        self.per_page = per_page if per_page is not None else settings.wttj_per_page
        self.include_company_profile = (
            include_company_profile
            if include_company_profile is not None
            else settings.wttj_include_company_profile
        )
        self.skip_failed_jobs = (
            skip_failed_jobs if skip_failed_jobs is not None else settings.wttj_skip_failed_jobs
        )
        self.timeout = timeout if timeout is not None else settings.wttj_timeout
        self.delay_seconds = (
            delay_seconds if delay_seconds is not None else settings.wttj_delay_seconds
        )

    def is_available(self) -> bool:
        return bool(self.cookie_header.strip())

    def search(
        self,
        query: str,
        location: str | None = None,
        *,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> Iterator[RawJob]:
        if not self.is_available():
            raise ScraperConfigError("WTTJ_COOKIE must be set to use the WTTJ scraper")
        if max_results is not None and max_results <= 0:
            return

        pages = min(int(kwargs.pop("pages", self.pages)), int(self.max_pages))
        per_page = kwargs.pop("per_page", self.per_page)
        include_company_profile = bool(
            kwargs.pop("include_company_profile", self.include_company_profile)
        )
        skip_failed_jobs = bool(kwargs.pop("skip_failed_jobs", self.skip_failed_jobs))
        timeout = int(kwargs.pop("timeout", self.timeout))
        delay_seconds = float(kwargs.pop("delay_seconds", self.delay_seconds))
        page_numbers = range(1, pages + 1)

        for job in scrape_matches_requests(
            pages=page_numbers,
            cookie_header=self.cookie_header,
            max_jobs=max_results,
            per_page=per_page,
            include_company_profile=include_company_profile,
            skip_failed_jobs=skip_failed_jobs,
            timeout=timeout,
            delay_seconds=delay_seconds,
        ):
            source_data = dict(job.source_data or {})
            source_data["_smartapply_search"] = {
                "source_mode": "personalized_matches",
                "query": query,
                "location": location,
                "pages": pages,
                "per_page": per_page,
                "include_company_profile": include_company_profile,
            }
            job.source_data = source_data
            yield job


for _module in (_matches_api, _offer_parser, _company_hydration):
    for _name in dir(_module):
        if _name.startswith("_") and not _name.startswith("__"):
            globals().setdefault(_name, getattr(_module, _name))

__all__ = [
    "WTTJ_SOURCE",
    "WTTJJobLink",
    "WTTJScraperError",
    "WelcomeToTheJungleScraper",
    "fetch_detail_api_job",
    "fetch_html_with_requests",
    "fetch_matches_api_page",
    "matches_page_url",
    "parse_company_html",
    "parse_detail_api_job",
    "parse_detail_html",
    "parse_listing_links",
    "parse_matches_api_links",
    "parse_saved_company",
    "parse_saved_detail",
    "parse_saved_listing",
    "scrape_matches_live",
    "scrape_matches_requests",
]
