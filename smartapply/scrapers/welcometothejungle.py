"""Welcome to the Jungle personalized matches scraper prototype.

This module is intentionally independent from the main scraper registry for
now: it can parse saved HTML fixtures offline, query the personalized WTTJ API
with a browser Cookie header, and parse public job/company detail pages.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger
from smartapply.scrapers.base import (
    RawJob,
    Scraper,
    ScraperConfigError,
    ScraperError,
    make_external_id,
)
from smartapply.utils.contracts import normalize_source_contract_type

logger = get_logger(__name__)

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


def matches_page_url(page: int) -> str:
    """Build the personalized matches URL for a 1-indexed page number."""
    if page < 1:
        raise ValueError("page must be >= 1")
    return f"{WTTJ_MATCHES_URL}?page={page}"


def parse_listing_links(html: str, *, base_url: str = WTTJ_BASE_URL) -> list[WTTJJobLink]:
    """Extract unique WTTJ job links from a jobs-matches HTML page."""
    soup = BeautifulSoup(html, "lxml")
    seen: set[str] = set()
    links: list[WTTJJobLink] = []
    for anchor in soup.find_all("a", href=True):
        url = _canonical_job_url(urljoin(base_url, anchor["href"]))
        if not url or url in seen:
            continue
        seen.add(url)
        title_hint = _clean_text(anchor.get_text(" ", strip=True)) or None
        links.append(WTTJJobLink(url=url, title_hint=title_hint))
    return links


def fetch_matches_api_page(
    *,
    page: int,
    cookie_header: str,
    per_page: int | None = None,
    timeout: int = 30,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch one personalized jobs-matches API page.

    The rendered ``/fr/jobs-matches?page=N`` document only contains skeleton
    cards in its initial HTML. The actual personalized jobs are loaded from
    WTTJ's API, authenticated by the same browser Cookie header.
    """
    if page < 1:
        raise ValueError("page must be >= 1")
    if not cookie_header.strip():
        raise WTTJScraperError("A logged-in WTTJ Cookie header is required for jobs-matches.")

    params: dict[str, int] = {"page": page}
    if per_page is not None:
        params["per_page"] = per_page

    headers = _api_headers(cookie_header, extra_headers=extra_headers)
    response = requests.get(WTTJ_MATCHES_API_URL, headers=headers, params=params, timeout=timeout)
    if response.status_code in {401, 403}:
        raise WTTJScraperError(
            "WTTJ API rejected the Cookie header. Copy the Cookie from a logged-in "
            "jobs-matches browser request and retry."
        )
    response.raise_for_status()
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise WTTJScraperError("WTTJ API did not return JSON for jobs-matches.") from exc
    if not isinstance(payload, dict):
        raise WTTJScraperError("Unexpected WTTJ jobs-matches API payload.")
    return payload


def parse_matches_api_links(payload: dict[str, Any]) -> list[WTTJJobLink]:
    """Build public job detail URLs from a WTTJ ``/api/v3/search/jobs`` payload."""
    jobs = payload.get("data")
    if not isinstance(jobs, list):
        return []

    links: list[WTTJJobLink] = []
    seen: set[str] = set()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        url = _job_url_from_api_item(job)
        if not url or url in seen:
            continue
        seen.add(url)
        links.append(
            WTTJJobLink(
                url=url,
                title_hint=_as_text(job.get("name")),
                api_data=job,
            )
        )
    return links


def _matches_api_page_count(payload: dict[str, Any]) -> int | None:
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("page_count")
    if isinstance(value, int) and value >= 1:
        return value
    return None


def parse_detail_html(html: str, *, url: str | None = None) -> RawJob:
    """Parse one WTTJ job detail page into the project's canonical RawJob."""
    soup = BeautifulSoup(html, "lxml")
    job_posting = _first_json_ld(soup, "JobPosting")
    if not job_posting:
        raise WTTJScraperError("No schema.org JobPosting JSON-LD found in WTTJ detail page")

    faq = _faq_answers(soup)
    metadata = _metadata_text(soup)
    organization = job_posting.get("hiringOrganization") or {}
    company_profile_url = _company_profile_url(soup)

    title = _as_text(job_posting.get("title")) or _meta_content(soup, "og:title") or "Untitled job"
    company = _as_text(organization.get("name")) or _company_from_title_tag(soup) or "Unknown company"
    description = _description_to_text(_as_text(job_posting.get("description")))
    location = _format_locations(job_posting.get("jobLocation"))
    contract_type = _contract_type(metadata, faq, job_posting)
    remote_text = _remote_text(metadata, faq)
    remote_policy = _normalize_remote_policy(remote_text)
    application_url = _canonical_job_url(url) if url else _detail_canonical_url(soup)
    published_date = _parse_datetime(_as_text(job_posting.get("datePosted")))

    if not description:
        description = _clean_text(soup.get_text("\n", strip=True))

    source_data: dict[str, Any] = {
        "url": application_url,
        "industry": job_posting.get("industry"),
        "valid_through": job_posting.get("validThrough"),
        "employment_type": job_posting.get("employmentType"),
        "remote_text": remote_text,
        "metadata_text": metadata,
        "hiring_organization": organization,
        "company_profile_url": company_profile_url,
        "company_website": _company_website(soup, organization),
        "company_social_links": _social_links(soup),
        "company_summary": _company_summary_from_job_page(soup),
        "company_tags": _company_tags(soup),
        "company_stats": _company_stats_from_job_page(soup),
        "skills": _skills(soup),
        "skills_more_count": _skills_more_count(soup),
        "workplace": _workplace(soup),
        "perks_and_benefits": _section_items_by_heading(soup, "Les avantages salariés"),
        "certifications": _section_items_by_heading(soup, "Engagements"),
        "videos": _video_titles(soup),
        "json_ld": job_posting,
    }
    if faq:
        source_data["faq"] = faq

    external_key = application_url or f"{company}|{title}|{location or ''}"
    return RawJob(
        external_id=make_external_id(WTTJ_SOURCE, external_key),
        title=title,
        company=company,
        location=location,
        contract_type=contract_type,
        remote_policy=remote_policy,
        description=description,
        application_url=application_url,
        published_date=published_date,
        source=WTTJ_SOURCE,
        source_data=source_data,
    )


def fetch_detail_api_job(
    url: str,
    *,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetch one public WTTJ job detail from the JSON API."""
    api_url = _detail_api_url_from_job_url(url)
    if not api_url:
        raise WTTJScraperError(f"Cannot build WTTJ detail API URL for {url}")

    headers = dict(WTTJ_HEADERS)
    headers["Accept"] = "application/json, text/plain, */*"
    response = requests.get(api_url, headers=headers, timeout=timeout)
    response.raise_for_status()
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise WTTJScraperError("WTTJ detail API did not return JSON.") from exc
    job = payload.get("job") if isinstance(payload, dict) else None
    if not isinstance(job, dict):
        raise WTTJScraperError("Unexpected WTTJ detail API payload.")
    return job


def parse_detail_api_job(payload: dict[str, Any], *, url: str | None = None) -> RawJob:
    """Parse one WTTJ detail API job payload into ``RawJob``."""
    organization = _dict(payload.get("organization"))
    company_slug = _as_text(organization.get("slug"))
    application_url = _canonical_job_url(url) or (
        _canonical_job_url(
            f"{WTTJ_BASE_URL}/fr/companies/{company_slug}/jobs/{payload.get('slug')}"
        )
        if company_slug and payload.get("slug")
        else None
    )
    title = _as_text(payload.get("name")) or "Untitled job"
    company = _as_text(organization.get("name")) or "Unknown company"
    description = _api_job_description(payload)
    location = _format_api_offices(payload.get("offices"))
    contract_type = _normalize_api_contract_type(payload.get("contract_type"))
    remote_policy = _normalize_api_remote_policy(payload.get("remote"))
    published_date = _parse_datetime(_as_text(payload.get("published_at")))
    company_profile_url = (
        _canonical_company_url(f"{WTTJ_BASE_URL}/fr/companies/{company_slug}")
        if company_slug
        else None
    )
    company_profile = _company_profile_from_detail_api(payload, company_profile_url)
    company_website = _as_text(company_profile.get("website"))

    source_data: dict[str, Any] = {
        "url": application_url,
        "detail_api": payload,
        "industry": _localized_text(_dict(payload.get("profession")).get("category_name")),
        "valid_through": None,
        "employment_type": payload.get("contract_type"),
        "remote_text": payload.get("remote"),
        "metadata_text": "",
        "hiring_organization": organization,
        "company_profile_url": company_profile_url,
        "company_website": company_website,
        "company_domain": _domain_from_url(company_website),
        "company_social_links": {},
        "company_summary": _api_company_summary(payload),
        "company_tags": [],
        "company_stats": company_profile.get("stats") or {},
        "company_profile": company_profile,
        "skills": _api_skills(payload),
        "skills_more_count": None,
        "workplace": location,
        "perks_and_benefits": [],
        "certifications": [],
        "videos": [],
        "salary": _api_salary(payload),
        "experience_level": payload.get("experience_level"),
        "profession": payload.get("profession"),
    }

    external_key = application_url or f"{company}|{title}|{location or ''}"
    return RawJob(
        external_id=make_external_id(WTTJ_SOURCE, external_key),
        title=title,
        company=company,
        location=location,
        contract_type=contract_type,
        remote_policy=remote_policy,
        description=description,
        experience=_api_experience(payload),
        application_url=application_url,
        published_date=published_date,
        source=WTTJ_SOURCE,
        source_data=source_data,
    )


def parse_saved_detail(path: str | Path, *, url: str | None = None) -> RawJob:
    """Parse a saved WTTJ job detail HTML file."""
    return parse_detail_html(Path(path).read_text(encoding="utf-8", errors="replace"), url=url)


def parse_saved_listing(path: str | Path) -> list[WTTJJobLink]:
    """Parse a saved WTTJ jobs-matches HTML file."""
    return parse_listing_links(Path(path).read_text(encoding="utf-8", errors="replace"))


def parse_company_html(html: str, *, url: str | None = None) -> dict[str, Any]:
    """Parse a WTTJ company profile page for motivation/contact discovery facts."""
    soup = BeautifulSoup(html, "lxml")
    canonical_url = _company_canonical_url(soup) or _canonical_company_url(url)
    header = _text_for_selector(soup, '[data-testid="showcase-header"]')
    stats = _company_profile_stats(soup)
    text_blocks = _company_profile_text_blocks(soup)
    website = _href_for_selector(soup, '[data-testid="showcase-header-website-link"]')

    return {
        "name": _company_name_from_profile(soup),
        "url": canonical_url,
        "website": website,
        "domain": _domain_from_url(website),
        "sectors": _text_for_selector(soup, '[data-testid="showcase-header-sector"]'),
        "offices": _text_for_selector(soup, '[data-testid="showcase-header-office"]'),
        "stats": stats,
        "presentation": text_blocks.get("Presentation"),
        "what_they_are_looking_for": text_blocks.get("What they are looking for"),
        "good_to_know": text_blocks.get("Good to know"),
        "addresses": _company_profile_addresses(soup),
        "social_links": _social_links(soup),
        "videos": _video_titles(soup),
        "faq": _faq_answers(soup),
        "header_text": header,
    }


def parse_saved_company(path: str | Path, *, url: str | None = None) -> dict[str, Any]:
    """Parse a saved WTTJ company profile HTML file."""
    return parse_company_html(Path(path).read_text(encoding="utf-8", errors="replace"), url=url)


def fetch_html_with_requests(
    url: str,
    *,
    cookie_header: str | None = None,
    timeout: int = 30,
) -> str:
    """Fetch one WTTJ page with requests.

    Public job/company pages usually work without cookies. Personalized pages
    such as ``/fr/jobs-matches`` require a logged-in ``Cookie`` header copied
    from the browser.
    """
    headers = dict(WTTJ_HEADERS)
    if cookie_header:
        headers["Cookie"] = cookie_header.strip()
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


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
    """Scrape personalized WTTJ matches with requests.

    Only the matches API needs the logged-in Cookie header. Job detail pages
    are public, so they are fetched without cookies.
    """
    if not cookie_header.strip():
        raise WTTJScraperError("A logged-in WTTJ Cookie header is required for jobs-matches.")

    seen: set[str] = set()
    company_cache: dict[str, dict[str, Any]] = {}
    yielded = 0
    page_count: int | None = None
    for page_number in pages:
        if page_count is not None and page_number > page_count:
            continue
        try:
            payload = fetch_matches_api_page(
                page=page_number,
                cookie_header=cookie_header,
                per_page=per_page,
                timeout=timeout,
                extra_headers=extra_headers,
            )
        except (requests.RequestException, WTTJScraperError) as exc:
            if not skip_failed_jobs:
                raise
            logger.warning("Skipping WTTJ matches page %s: %s", page_number, exc)
            continue

        page_count = _matches_api_page_count(payload) or page_count
        for link in parse_matches_api_links(payload):
            if link.url in seen:
                continue
            seen.add(link.url)
            try:
                detail_response = requests.get(link.url, headers=WTTJ_HEADERS, timeout=timeout)
                detail_response.raise_for_status()
                job = parse_detail_html(detail_response.text, url=link.url)
            except (requests.RequestException, WTTJScraperError) as html_exc:
                try:
                    api_job = fetch_detail_api_job(link.url, timeout=timeout)
                    job = parse_detail_api_job(api_job, url=link.url)
                except (requests.RequestException, WTTJScraperError) as api_exc:
                    if not skip_failed_jobs:
                        raise WTTJScraperError(
                            f"Failed to parse WTTJ job from HTML ({html_exc}) "
                            f"and API ({api_exc})"
                        ) from api_exc
                    logger.warning(
                        "Skipping WTTJ job %s: HTML failed (%s); API failed (%s)",
                        link.url,
                        html_exc,
                        api_exc,
                    )
                    continue
            except Exception as exc:
                if not skip_failed_jobs:
                    raise
                logger.warning("Skipping WTTJ job %s: %s", link.url, exc)
                continue
            source_data = dict(job.source_data or {})
            if link.api_data:
                source_data["matches_api"] = link.api_data
                _merge_company_profile_from_matches_api(source_data, link.api_data)
            job.source_data = source_data
            if include_company_profile:
                _attach_company_profile(job, company_cache=company_cache, timeout=timeout)
            yield job
            yielded += 1
            if max_jobs is not None and yielded >= max_jobs:
                return
            if delay_seconds > 0:
                sleep(delay_seconds)


def scrape_matches_live(
    *,
    pages: Sequence[int],
    max_jobs: int | None = None,
    cdp_url: str | None = None,
    user_data_dir: str | Path | None = None,
    headless: bool = False,
    timeout_ms: int = 30_000,
    delay_seconds: float = 1.0,
    save_html_dir: str | Path | None = None,
) -> Iterator[RawJob]:
    """Scrape personalized matches by opening every offer in a browser session.

    Use ``cdp_url`` to attach to a Chrome instance started with remote debugging,
    or ``user_data_dir`` to create/reuse a dedicated Playwright Chrome profile.
    The latter is the easiest long-term workflow: log into WTTJ once in the
    opened browser, then future runs reuse the same session cookies.
    """
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised by users
        raise WTTJScraperError(
            "Playwright is required for live WTTJ scraping. "
            "Install it with: .venv/bin/pip install -e '.[wttj]'"
        ) from exc

    if not pages:
        return
    html_dir = Path(save_html_dir).expanduser() if save_html_dir else None
    if html_dir:
        html_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = None
        context = None
        if cdp_url:
            browser = playwright.chromium.connect_over_cdp(cdp_url, timeout=timeout_ms)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
        else:
            profile_dir = Path(user_data_dir or "~/.smartapply/wttj-chrome-profile").expanduser()
            profile_dir.mkdir(parents=True, exist_ok=True)
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel="chrome",
                headless=headless,
                viewport={"width": 1440, "height": 1100},
            )

        assert context is not None
        list_page = context.new_page()
        detail_page = context.new_page()
        seen: set[str] = set()
        yielded = 0

        try:
            for page_number in pages:
                url = matches_page_url(page_number)
                list_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                _wait_for_wttj_content(list_page, timeout_ms, PlaywrightTimeoutError)
                listing_html = list_page.content()
                if html_dir:
                    (html_dir / f"jobs-matches-page-{page_number}.html").write_text(
                        listing_html,
                        encoding="utf-8",
                    )

                for link in parse_listing_links(listing_html):
                    if link.url in seen:
                        continue
                    seen.add(link.url)
                    detail_page.goto(link.url, wait_until="domcontentloaded", timeout=timeout_ms)
                    _wait_for_wttj_content(detail_page, timeout_ms, PlaywrightTimeoutError)
                    detail_html = detail_page.content()
                    if html_dir:
                        filename = _safe_filename(urlparse(link.url).path.rsplit("/", 1)[-1])
                        (html_dir / f"{filename}.html").write_text(detail_html, encoding="utf-8")
                    yield parse_detail_html(detail_html, url=link.url)
                    yielded += 1
                    if max_jobs is not None and yielded >= max_jobs:
                        return
                    if delay_seconds > 0:
                        sleep(delay_seconds)
        finally:
            detail_page.close()
            list_page.close()
            if cdp_url:
                if browser is not None:
                    browser.close()
            else:
                context.close()


def _api_headers(
    cookie_header: str,
    *,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = dict(WTTJ_HEADERS)
    headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie_header.strip(),
            "Origin": WTTJ_BASE_URL,
            "Referer": matches_page_url(1),
        }
    )
    csrf_token = _cookie_value(cookie_header, "csrf-token")
    if csrf_token:
        headers["x-csrf-token"] = csrf_token
    if extra_headers:
        headers.update(extra_headers)
    return headers


def _detail_api_url_from_job_url(url: str | None) -> str | None:
    parsed = urlparse(url or "")
    match = re.fullmatch(r"/(?:fr|en)/companies/([^/]+)/jobs/([^/?#]+)", parsed.path)
    if not match:
        return None
    company_slug, job_slug = match.groups()
    return f"{WTTJ_ORGANIZATIONS_API_URL}/{company_slug}/jobs/{job_slug}"


def _api_job_description(payload: dict[str, Any]) -> str:
    sections = [
        ("Description", payload.get("description")),
        ("Missions", payload.get("key_missions")),
        ("Profil recherché", payload.get("looking_for_candidate_description")),
        ("Process de recrutement", payload.get("recruitment_process")),
    ]
    parts: list[str] = []
    for heading, value in sections:
        text = _api_rich_text(value)
        if text:
            parts.append(f"{heading}\n{text}")
    return _clean_text("\n\n".join(parts)) or _api_company_summary(payload) or ""


def _api_rich_text(value: Any) -> str:
    if isinstance(value, list):
        texts = [_api_rich_text(item) for item in value]
        return _clean_text("\n".join(text for text in texts if text))
    if isinstance(value, dict):
        for key in ("description", "content", "name", "title"):
            text = _api_rich_text(value.get(key))
            if text:
                return text
        return ""
    return _description_to_text(_as_text(value))


def _format_api_offices(value: Any) -> str | None:
    offices = value if isinstance(value, list) else [value]
    formatted: list[str] = []
    for office in offices:
        if not isinstance(office, dict):
            continue
        parts = [
            _as_text(office.get("local_city") or office.get("city")),
            _as_text(office.get("district")),
            _as_text(office.get("country_code") or office.get("country")),
        ]
        text = ", ".join(part for part in parts if part)
        if text and text not in formatted:
            formatted.append(text)
    return "; ".join(formatted) or None


def _normalize_api_contract_type(value: Any) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    return normalize_source_contract_type(text.replace("_", " ")) or text


def _normalize_api_remote_policy(value: Any) -> str | None:
    text = _clean_text(str(value or "").replace("_", " ").lower())
    if not text or text == "unknown":
        return None
    if text in {"fulltime", "full time", "full remote", "remote"}:
        return "remote"
    if text in {"partial", "partiel", "hybrid", "hybride"}:
        return "hybrid"
    if text in {"no", "none", "onsite", "not allowed"}:
        return "onsite"
    return text


def _api_skills(payload: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("skills", "tools"):
        raw_items = payload.get(key)
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            text = None
            if isinstance(item, dict):
                text = _as_text(item.get("name") or item.get("title") or item.get("label"))
            else:
                text = _as_text(item)
            if text and text not in values:
                values.append(text)
    return values


def _api_salary(payload: dict[str, Any]) -> dict[str, Any]:
    salary = {
        "min": payload.get("salary_min"),
        "max": payload.get("salary_max"),
        "currency": payload.get("salary_currency"),
        "period": payload.get("salary_period"),
    }
    return {key: value for key, value in salary.items() if value is not None}


def _api_experience(payload: dict[str, Any]) -> dict[str, Any] | None:
    level = _as_text(payload.get("experience_level"))
    if not level:
        return None
    min_years = _experience_min_years_from_api_level(level)
    result: dict[str, Any] = {"level": level}
    if min_years is not None:
        result["min_years"] = min_years
        result["required"] = min_years > 0
    return result


def _experience_min_years_from_api_level(value: str | None) -> float | None:
    normalized = (value or "").strip().upper()
    mapping = {
        "NO_EXPERIENCE": 0.0,
        "LESS_THAN_1_YEAR": 0.0,
        "1_TO_2_YEARS": 1.0,
        "3_TO_4_YEARS": 3.0,
        "5_TO_10_YEARS": 5.0,
        "MORE_THAN_10_YEARS": 10.0,
    }
    return mapping.get(normalized)


def _api_company_summary(payload: dict[str, Any]) -> str | None:
    return (
        _clean_text(_description_to_text(_as_text(payload.get("company_summary"))))
        or _clean_text(_description_to_text(_as_text(payload.get("company_description"))))
        or _clean_text(
            _description_to_text(_as_text(_dict(payload.get("organization")).get("description")))
        )
    )


def _company_profile_from_detail_api(
    payload: dict[str, Any],
    url: str | None,
) -> dict[str, Any]:
    organization = _dict(payload.get("organization"))
    website = _external_company_website(organization.get("website_organization"))
    stats = {
        "employees": organization.get("nb_employees"),
        "founded": organization.get("creation_year"),
        "women": organization.get("parity_women"),
        "men": organization.get("parity_men"),
        "average_age": organization.get("average_age"),
        "turnover": organization.get("turnover"),
    }
    stats = {key: value for key, value in stats.items() if value is not None}
    return {
        "name": _as_text(organization.get("name")),
        "url": url,
        "website": website,
        "domain": _domain_from_url(website),
        "sectors": _localized_text(_dict(payload.get("profession")).get("category_name")),
        "offices": _format_api_offices(payload.get("offices")),
        "stats": stats,
        "presentation": _api_company_summary(payload),
        "what_they_are_looking_for": None,
        "good_to_know": None,
        "addresses": [],
        "social_links": {},
        "videos": [],
        "faq": {},
        "header_text": None,
        "source": "detail_api",
    }


def _external_company_website(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("url", "website", "external_url"):
            text = _as_text(value.get(key))
            if text and _is_external_url(text):
                return text
    text = _as_text(value)
    if text and _is_external_url(text):
        return text
    return None


def _merge_company_profile_from_matches_api(
    source_data: dict[str, Any],
    matches_api: dict[str, Any],
) -> None:
    profile = dict(_dict(source_data.get("company_profile")))
    organization = _dict(matches_api.get("organization"))
    profile.setdefault("name", _as_text(organization.get("name")))
    profile.setdefault("url", source_data.get("company_profile_url"))
    sectors = _format_api_sectors(organization.get("sectors")) or _as_text(
        organization.get("industry")
    )
    if sectors:
        profile["sectors"] = sectors
    stats = dict(_dict(profile.get("stats")))
    if organization.get("nb_employees") is not None:
        stats.setdefault("employees", organization.get("nb_employees"))
    if stats:
        profile["stats"] = stats
    source_data["company_profile"] = profile
    source_data["company_stats"] = stats or source_data.get("company_stats") or {}


def _format_api_sectors(value: Any) -> str | None:
    if not isinstance(value, list):
        return None
    names = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = _localized_text(item.get("name"))
        if name and name not in names:
            names.append(name)
    return ", ".join(names) or None


def _localized_text(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("fr", "en"):
            text = _as_text(value.get(key))
            if text:
                return text
        for raw in value.values():
            text = _as_text(raw)
            if text:
                return text
        return None
    return _as_text(value)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _cookie_value(cookie_header: str, name: str) -> str | None:
    for part in cookie_header.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name and value:
            return value
    return None


def _job_url_from_api_item(job: dict[str, Any]) -> str | None:
    for key in ("url", "absolute_url", "web_url"):
        url = _canonical_job_url(_as_text(job.get(key)))
        if url:
            return url

    organization = job.get("organization")
    if not isinstance(organization, dict):
        return None
    organization_slug = _as_text(organization.get("slug"))
    job_slug = _as_text(job.get("slug"))
    if not organization_slug or not job_slug:
        return None
    return _canonical_job_url(f"{WTTJ_BASE_URL}/fr/companies/{organization_slug}/jobs/{job_slug}")


def _attach_company_profile(
    job: RawJob,
    *,
    company_cache: dict[str, dict[str, Any]],
    timeout: int,
) -> None:
    source_data = dict(job.source_data or {})
    profile_url = _as_text(source_data.get("company_profile_url"))
    if not profile_url:
        matches_api = source_data.get("matches_api")
        if isinstance(matches_api, dict):
            profile_url = _company_url_from_api_item(matches_api)
    profile_url = _canonical_company_url(profile_url)
    if not profile_url:
        source_data["company_domain"] = _domain_from_url(_as_text(source_data.get("company_website")))
        job.source_data = source_data
        return

    existing_profile = _dict(source_data.get("company_profile"))
    company_profile = company_cache.get(profile_url)
    if company_profile is None:
        company_profile = dict(existing_profile)
        try:
            response = requests.get(profile_url, headers=WTTJ_HEADERS, timeout=timeout)
            if response.status_code == 202 and not response.text:
                raise requests.RequestException("WTTJ returned an empty 202 company page")
            response.raise_for_status()
            company_profile = _merge_company_profiles(
                company_profile,
                parse_company_html(response.text, url=profile_url),
            )
        except requests.RequestException as exc:
            company_profile = _merge_company_profiles(
                company_profile,
                {"url": profile_url, "scrape_error": str(exc)},
            )
        except WTTJScraperError as exc:
            company_profile = _merge_company_profiles(
                company_profile,
                {"url": profile_url, "scrape_error": str(exc)},
            )
        company_cache[profile_url] = company_profile

    website = _as_text(company_profile.get("website")) or _as_text(source_data.get("company_website"))
    source_data["company_profile_url"] = profile_url
    source_data["company_profile"] = company_profile
    source_data["company_website"] = website
    source_data["company_domain"] = _domain_from_url(website)
    job.source_data = source_data


def _merge_company_profiles(
    base: dict[str, Any],
    update: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base)
    for key, value in update.items():
        if value in (None, "", [], {}):
            continue
        if key == "stats" and isinstance(value, dict):
            stats = dict(_dict(merged.get("stats")))
            stats.update(value)
            merged["stats"] = stats
        else:
            merged[key] = value
    return merged


def _company_url_from_api_item(job: dict[str, Any]) -> str | None:
    organization = job.get("organization")
    if not isinstance(organization, dict):
        return None
    organization_slug = _as_text(organization.get("slug"))
    if not organization_slug:
        return None
    return _canonical_company_url(f"{WTTJ_BASE_URL}/fr/companies/{organization_slug}")


def _first_json_ld(soup: BeautifulSoup, json_type: str) -> dict[str, Any] | None:
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text()
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _json_ld_items(payload):
            if item.get("@type") == json_type:
                return item
    return None


def _json_ld_items(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, dict):
        if isinstance(payload.get("@graph"), list):
            yield from (item for item in payload["@graph"] if isinstance(item, dict))
        else:
            yield payload
    elif isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, dict))


def _faq_answers(soup: BeautifulSoup) -> dict[str, str]:
    faq = _first_json_ld(soup, "FAQPage")
    if not faq:
        return {}
    answers: dict[str, str] = {}
    for entity in faq.get("mainEntity") or []:
        if not isinstance(entity, dict):
            continue
        question = _as_text(entity.get("name"))
        accepted = entity.get("acceptedAnswer")
        answer = _as_text(accepted.get("text")) if isinstance(accepted, dict) else None
        if question and answer:
            answers[question] = answer
    return answers


def _metadata_text(soup: BeautifulSoup) -> str:
    metadata = soup.select_one('[data-testid="job-metadata-block"]')
    if metadata:
        return _clean_text(metadata.get_text(" ", strip=True))
    return ""


def _skills(soup: BeautifulSoup) -> list[str]:
    block = _block_after_heading(soup, "Compétences & expertises", parent_steps=3)
    if not block:
        return []
    skills: list[str] = []
    for text in _leaf_texts(block, tags=("div", "span")):
        if (
            not text
            or text == "Compétences & expertises"
            or text.startswith("+")
            or text in skills
            or len(text) > 80
        ):
            continue
        skills.append(text)
    return skills


def _skills_more_count(soup: BeautifulSoup) -> int | None:
    block = _block_after_heading(soup, "Compétences & expertises", parent_steps=3)
    if not block:
        return None
    for text in _leaf_texts(block):
        match = re.fullmatch(r"\+(\d+)", text)
        if match:
            return int(match.group(1))
    return None


def _contract_type(
    metadata: str,
    faq: dict[str, str],
    job_posting: dict[str, Any],
) -> str | None:
    combined = " ".join([metadata, *faq.values()])
    for label in _CONTRACT_LABELS:
        if re.search(rf"\b{re.escape(label)}\b", combined, flags=re.IGNORECASE):
            return label
    employment_type = _as_text(job_posting.get("employmentType"))
    if employment_type == "FULL_TIME":
        return "FULL_TIME"
    return employment_type


def _remote_text(metadata: str, faq: dict[str, str]) -> str | None:
    match = re.search(
        r"Télétravail\s+(?:total|fréquent|frequent|occasionnel|autorisé|autorise|possible|partiel)",
        metadata,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_text(match.group(0))
    for question, answer in faq.items():
        if "télétravail" in question.lower():
            return answer
    return None


def _company_profile_url(soup: BeautifulSoup) -> str | None:
    for anchor in soup.find_all("a", href=True):
        text = _clean_text(anchor.get_text(" ", strip=True)).lower()
        href = anchor["href"]
        if "/companies/" not in href or "/jobs" in href:
            continue
        if text in {"explorer l'entreprise", "explore company", "weward"} or "companies/" in href:
            url = _canonical_company_url(urljoin(WTTJ_BASE_URL, href))
            if url:
                return url
    return None


def _company_website(soup: BeautifulSoup, organization: dict[str, Any]) -> str | None:
    for anchor in soup.find_all("a", href=True):
        text = _clean_text(anchor.get_text(" ", strip=True)).lower()
        href = anchor["href"]
        if text in {"voir le site", "view website"} and _is_external_url(href):
            return href
    same_as = _as_text(organization.get("sameAs"))
    if same_as and _is_external_url(same_as):
        return same_as
    return None


def _company_summary_from_job_page(soup: BeautifulSoup) -> str | None:
    block = _block_after_heading(soup, "Qui sont-ils ?", parent_steps=2)
    if not block:
        return None
    paragraphs = [
        text
        for text in _leaf_texts(block, tags=("p",))
        if text.lower() not in _IGNORED_SECTION_TEXTS
    ]
    return _clean_text("\n".join(paragraphs)) or None


def _company_tags(soup: BeautifulSoup) -> list[str]:
    tags = [_clean_text(tag.get_text(" ", strip=True)) for tag in soup.select('[data-testid="job-company-tag"]')]
    return [tag for tag in tags if tag]


def _company_stats_from_job_page(soup: BeautifulSoup) -> dict[str, str | None]:
    tags = _company_tags(soup)
    stats: dict[str, str | None] = {
        "employees": None,
        "founded": None,
        "average_age": None,
        "gender_breakdown": None,
    }
    percentages: list[str] = []
    for tag in tags:
        lower = tag.lower()
        if "collaborateur" in lower:
            stats["employees"] = tag
        elif "créée" in lower or "created" in lower:
            stats["founded"] = tag
        elif "âge moyen" in lower or "average age" in lower:
            stats["average_age"] = tag
        elif re.fullmatch(r"\d+%", tag):
            percentages.append(tag)
    if percentages:
        stats["gender_breakdown"] = " / ".join(percentages)
    return {key: value for key, value in stats.items() if value}


def _workplace(soup: BeautifulSoup) -> str | None:
    block = _block_after_heading(soup, "Le lieu de travail", parent_steps=2)
    if not block:
        return None
    candidates = [text for text in _leaf_texts(block, tags=("a", "span", "p")) if text != "Le lieu de travail"]
    return candidates[-1] if candidates else _strip_heading(_clean_text(block.get_text(" ", strip=True)), "Le lieu de travail")


def _section_items_by_heading(soup: BeautifulSoup, heading: str) -> list[str]:
    block = _block_after_heading(soup, heading, parent_steps=2)
    if not block:
        return []
    items: list[str] = []
    for text in _leaf_texts(block):
        if text == heading:
            continue
        normalized = text.lower()
        if normalized in _IGNORED_SECTION_TEXTS or re.fullmatch(r"\d+", text):
            continue
        if len(text) > 120:
            continue
        if text not in items:
            items.append(text)
    return items


def _video_titles(soup: BeautifulSoup) -> list[str]:
    titles: list[str] = []
    for block in soup.select('[data-testid="block-videos-item"], [data-testid="organization-content-block-video"]'):
        text = _clean_text(block.get_text(" ", strip=True))
        if text and text not in titles:
            titles.append(text)
    return titles


def _company_profile_stats(soup: BeautifulSoup) -> dict[str, str | None]:
    selectors = {
        "founded": '[data-testid="stats-creation-year"]',
        "employees": '[data-testid="stats-nb-employees"]',
        "women": '[data-testid="stats-parity-women"]',
        "men": '[data-testid="stats-parity-men"]',
        "average_age": '[data-testid="stats-average-age"]',
        "turnover": '[data-testid="stats-turnover"]',
    }
    stats = {key: _text_for_selector(soup, selector) for key, selector in selectors.items()}
    return {key: value for key, value in stats.items() if value}


def _company_profile_text_blocks(soup: BeautifulSoup) -> dict[str, str]:
    blocks: dict[str, str] = {}
    for block in soup.select('[data-testid="organization-content-block-text"]'):
        leaf_texts = _leaf_texts(block, tags=("h2", "h3", "h4", "p", "span"))
        if not leaf_texts:
            continue
        heading = leaf_texts[0]
        body = _clean_text("\n".join(text for text in leaf_texts[1:] if text != heading))
        if heading and body:
            blocks[heading] = body
    return blocks


def _company_profile_addresses(soup: BeautifulSoup) -> list[str]:
    addresses: list[str] = []
    for block in soup.select('[data-testid="organization-content-block-map"]'):
        text = _clean_text(block.get_text(" ", strip=True))
        if text and text not in addresses:
            addresses.append(text)
    return addresses


def _company_name_from_profile(soup: BeautifulSoup) -> str | None:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if ":" in title:
        return title.split(":", 1)[0].strip()
    header = _text_for_selector(soup, '[data-testid="showcase-header"]')
    if header:
        return header.split(" Follow ", 1)[0].strip() or None
    return None


def _social_links(soup: BeautifulSoup) -> dict[str, str]:
    links: dict[str, str] = {}
    social_hosts = {
        "facebook.com": "facebook",
        "instagram.com": "instagram",
        "linkedin.com": "linkedin",
        "twitter.com": "twitter",
        "x.com": "twitter",
        "youtube.com": "youtube",
    }
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "wttj" in href or "welcometothejungle" in href:
            continue
        for host, name in social_hosts.items():
            if name == "linkedin" and "/in/" in href:
                continue
            if host in href and name not in links:
                links[name] = href
    return links


def _normalize_remote_policy(remote_text: str | None) -> str | None:
    if not remote_text:
        return None
    value = remote_text.lower()
    if "total" in value:
        return "remote"
    if "fréquent" in value or "frequent" in value or "occasionnel" in value or "autorisé" in value:
        return "hybrid"
    if "pas" in value or "non" in value:
        return "onsite"
    return remote_text


def _description_to_text(description_html: str | None) -> str:
    if not description_html:
        return ""
    soup = BeautifulSoup(description_html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return _clean_text(soup.get_text("\n", strip=True))


def _format_locations(job_location: Any) -> str | None:
    locations = job_location if isinstance(job_location, list) else [job_location]
    formatted: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if not isinstance(address, dict):
            continue
        locality = _as_text(address.get("addressLocality"))
        region = _as_text(address.get("addressRegion"))
        country = _as_text(address.get("addressCountry"))
        parts = [locality]
        if region and region != locality:
            parts.append(region)
        if country:
            parts.append(country)
        text = ", ".join(part for part in parts if part)
        if text:
            formatted.append(text)
    return "; ".join(formatted) or None


def _canonical_job_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc and not parsed.netloc.endswith("welcometothejungle.com"):
        return None
    if not _JOB_PATH_RE.search(parsed.path):
        return None
    return urlunparse(("https", "www.welcometothejungle.com", parsed.path, "", "", ""))


def _canonical_company_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.netloc and not parsed.netloc.endswith("welcometothejungle.com"):
        return None
    match = re.fullmatch(r"/(?:fr|en)/companies/[^/?#]+", parsed.path)
    if not match:
        return None
    return urlunparse(("https", "www.welcometothejungle.com", parsed.path, "", "", ""))


def _detail_canonical_url(soup: BeautifulSoup) -> str | None:
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        url = _canonical_job_url(canonical["href"])
        if url:
            return url
    return _canonical_job_url(_meta_content(soup, "og:url"))


def _company_canonical_url(soup: BeautifulSoup) -> str | None:
    canonical = soup.select_one('link[rel="canonical"]')
    if canonical and canonical.get("href"):
        url = _canonical_company_url(canonical["href"])
        if url:
            return url
    return _canonical_company_url(_meta_content(soup, "og:url"))


def _href_for_selector(soup: BeautifulSoup, selector: str) -> str | None:
    element = soup.select_one(selector)
    if not element:
        return None
    href = element.get("href")
    return _as_text(href)


def _text_for_selector(soup: BeautifulSoup, selector: str) -> str | None:
    element = soup.select_one(selector)
    return _clean_text(element.get_text(" ", strip=True)) if element else None


def _block_after_heading(
    soup: BeautifulSoup,
    heading: str,
    *,
    parent_steps: int,
) -> Any | None:
    node = _visible_heading_node(soup, heading)
    if not node:
        return None
    block: Any = node.parent
    for _ in range(parent_steps):
        if block and block.parent:
            block = block.parent
    return block


def _visible_heading_node(soup: BeautifulSoup, heading: str) -> Any | None:
    for node in soup.find_all(string=lambda value: bool(value and heading in value)):
        parent = node.parent
        if not parent:
            continue
        if parent.find_parent(["script", "style", "noscript"]):
            continue
        text = _clean_text(str(node))
        if text == heading or heading in text:
            return node
    return None


def _leaf_texts(
    block: Any,
    *,
    tags: tuple[str, ...] = ("span", "p", "a", "h2", "h3", "h4", "div", "li"),
) -> list[str]:
    texts: list[str] = []
    for node in block.find_all(tags):
        if node.find([tag for tag in tags]):
            continue
        text = _clean_text(node.get_text(" ", strip=True))
        if text and text not in texts:
            texts.append(text)
    return texts


def _strip_heading(text: str, heading: str) -> str | None:
    if text.startswith(heading):
        text = text[len(heading):].strip()
    return text or None


def _is_external_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and not parsed.netloc.endswith("welcometothejungle.com")


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url if re.match(r"^https?://", url) else f"https://{url}")
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    return domain or None


def _looks_logged_out(text: str, url: str) -> bool:
    value = f"{url}\n{text}".lower()
    return any(
        marker in value
        for marker in (
            "login",
            "sign in",
            "se connecter",
            "connexion",
            "inscription",
            "/login",
            "/signin",
        )
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _meta_content(soup: BeautifulSoup, property_name: str) -> str | None:
    tag = soup.select_one(f'meta[property="{property_name}"]')
    return _as_text(tag.get("content")) if tag else None


def _company_from_title_tag(soup: BeautifulSoup) -> str | None:
    if not soup.title:
        return None
    parts = [part.strip() for part in soup.title.get_text(" ", strip=True).split(" - ")]
    if len(parts) >= 2:
        return parts[-2]
    return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_text(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_filename(value: str) -> str:
    filename = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return filename[:120] or "wttj-job"


def _wait_for_wttj_content(page: Any, timeout_ms: int, timeout_error: type[Exception]) -> None:
    with suppress(timeout_error):
        page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 10_000))
    with suppress(timeout_error):
        page.wait_for_selector(
            'a[href*="/fr/companies/"][href*="/jobs/"], '
            'script[type="application/ld+json"], '
            '[data-testid="job-section-description"]',
            timeout=timeout_ms,
        )
