"""WTTJ personalized matches API pagination and scraping."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from smartapply.logging_setup import get_logger
from smartapply.scrapers.base import RawJob
from smartapply.scrapers.welcometothejungle import (
    WTTJ_BASE_URL,
    WTTJ_HEADERS,
    WTTJ_MATCHES_API_URL,
    WTTJ_MATCHES_URL,
    WTTJJobLink,
    WTTJScraperError,
)
from smartapply.scrapers.wttj.company_hydration import (
    _attach_company_profile,
    _merge_company_profile_from_matches_api,
)
from smartapply.scrapers.wttj.normalizers import (
    _as_text,
    _canonical_job_url,
    _clean_text,
    _cookie_value,
    _job_url_from_api_item,
    _safe_filename,
    _wait_for_wttj_content,
)
from smartapply.scrapers.wttj.offer_parser import (
    fetch_detail_api_job,
    parse_detail_api_job,
    parse_detail_html,
)

logger = get_logger(__name__)

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

def parse_saved_listing(path: str | Path) -> list[WTTJJobLink]:
    """Parse a saved WTTJ jobs-matches HTML file."""
    return parse_listing_links(Path(path).read_text(encoding="utf-8", errors="replace"))

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
    fetch_matches_api_page_fn: Callable[..., dict[str, Any]] | None = None,
    fetch_detail_api_job_fn: Callable[..., dict[str, Any]] | None = None,
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
            payload = (fetch_matches_api_page_fn or fetch_matches_api_page)(
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
                    api_job = (fetch_detail_api_job_fn or fetch_detail_api_job)(link.url, timeout=timeout)
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
