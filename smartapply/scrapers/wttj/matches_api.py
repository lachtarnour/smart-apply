"""WTTJ personalized matches API pagination and scraping."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from smartapply.logging_setup import get_logger
from smartapply.offers import RawJob
from smartapply.scrapers.wttj.company_hydration import (
    _attach_company_profile,
    _merge_company_profile_from_matches_api,
)
from smartapply.scrapers.wttj.contracts import (
    WTTJ_BASE_URL,
    WTTJ_HEADERS,
    WTTJ_MATCHES_API_URL,
    WTTJ_MATCHES_URL,
    WTTJAuthenticationError,
    WTTJJobLink,
    WTTJScraperError,
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
ProgressCallback = Callable[[dict[str, Any]], None]


def _emit_progress(callback: ProgressCallback | None, **event: Any) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception as exc:
        logger.debug("Ignoring WTTJ progress callback error: %s", exc)


def _should_stop(stop_requested: Callable[[], bool] | None) -> bool:
    return bool(stop_requested and stop_requested())


def matches_page_url(page: int, *, published_since: str | None = None) -> str:
    """Build the personalized matches URL for a 1-indexed page number."""
    if page < 1:
        raise ValueError("page must be >= 1")
    params: dict[str, Any] = {}
    if published_since:
        params["published_since"] = published_since
    if page > 1:
        params["page"] = page
    query = urlencode(params)
    return f"{WTTJ_MATCHES_URL}?{query}" if query else WTTJ_MATCHES_URL


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
    published_since: str | None = None,
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
        raise WTTJAuthenticationError(
            "A logged-in WTTJ Cookie header is required for jobs-matches."
        )

    params: dict[str, Any] = {"page": page}
    if per_page is not None:
        params["per_page"] = per_page
    if published_since:
        params["published_since"] = published_since

    headers = _api_headers(
        cookie_header,
        published_since=published_since,
        extra_headers=extra_headers,
    )
    response = requests.get(WTTJ_MATCHES_API_URL, headers=headers, params=params, timeout=timeout)
    if response.status_code in {401, 403}:
        raise WTTJAuthenticationError(
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
    if payload.get("error"):
        detail = payload.get("error")
        raise WTTJScraperError(f"WTTJ jobs-matches API returned an error: {str(detail)[:500]}")
    if not isinstance(payload.get("data"), list):
        raise WTTJScraperError("WTTJ jobs-matches API response has no data list.")
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


def _is_missing_matches_page_error(exc: requests.RequestException) -> bool:
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None) in {404, 410}


def _public_scrape_error(exc: Exception) -> str:
    """Return a short reason safe for UI display (never headers or cookies)."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return f"HTTP {status}"
    if isinstance(exc, requests.Timeout):
        return "délai dépassé"
    if isinstance(exc, requests.ConnectionError):
        return "connexion impossible"
    return type(exc).__name__


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
    progress_target: int | None = None,
    per_page: int | None = None,
    published_since: str | None = None,
    include_company_profile: bool = True,
    skip_failed_jobs: bool = True,
    timeout: int = 30,
    delay_seconds: float = 0.5,
    extra_headers: dict[str, str] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    progress_callback: ProgressCallback | None = None,
    fetch_matches_api_page_fn: Callable[..., dict[str, Any]] | None = None,
    fetch_detail_api_job_fn: Callable[..., dict[str, Any]] | None = None,
) -> Iterator[RawJob]:
    """Scrape personalized WTTJ matches with requests.

    Only the matches API needs the logged-in Cookie header. Job detail pages
    are public, so they are fetched without cookies.
    """
    if not cookie_header.strip():
        raise WTTJAuthenticationError(
            "A logged-in WTTJ Cookie header is required for jobs-matches."
        )
    if _should_stop(stop_requested):
        _emit_progress(progress_callback, event="cancelled", yielded=0)
        return

    seen: set[str] = set()
    company_cache: dict[str, dict[str, Any]] = {}
    yielded = 0
    first_detail_error: WTTJScraperError | None = None
    page_count: int | None = None
    pages_total = len(pages)
    for page_number in pages:
        if _should_stop(stop_requested):
            _emit_progress(
                progress_callback,
                event="cancelled",
                pages_total=pages_total,
                page_count=page_count,
                max_jobs=max_jobs,
                progress_target=progress_target,
                yielded=yielded,
            )
            return
        if page_count is not None and page_number > page_count:
            break
        _emit_progress(
            progress_callback,
            event="page_fetch_start",
            page=page_number,
            pages_total=pages_total,
            page_count=page_count,
            max_jobs=max_jobs,
            progress_target=progress_target,
            yielded=yielded,
        )
        try:
            payload = (fetch_matches_api_page_fn or fetch_matches_api_page)(
                page=page_number,
                cookie_header=cookie_header,
                per_page=per_page,
                published_since=published_since,
                timeout=timeout,
                extra_headers=extra_headers,
            )
        except WTTJAuthenticationError:
            raise
        except requests.RequestException as exc:
            if _is_missing_matches_page_error(exc):
                logger.info("Stopping WTTJ pagination at missing page %s: %s", page_number, exc)
                _emit_progress(
                    progress_callback,
                    event="page_missing",
                    page=page_number,
                    pages_total=pages_total,
                    page_count=page_count,
                    max_jobs=max_jobs,
                    progress_target=progress_target,
                    yielded=yielded,
                )
                break
            if not skip_failed_jobs or yielded == 0:
                raise
            logger.warning("Skipping WTTJ matches page %s: %s", page_number, exc)
            _emit_progress(
                progress_callback,
                event="warning",
                code="page_fetch_failed",
                message=(f"WTTJ : page {page_number} ignorée ({_public_scrape_error(exc)})."),
                page=page_number,
                yielded=yielded,
            )
            continue
        except WTTJScraperError as exc:
            if not skip_failed_jobs or yielded == 0:
                raise
            logger.warning("Skipping WTTJ matches page %s: %s", page_number, exc)
            _emit_progress(
                progress_callback,
                event="warning",
                code="page_parse_failed",
                message=(f"WTTJ : page {page_number} illisible ({_public_scrape_error(exc)})."),
                page=page_number,
                yielded=yielded,
            )
            continue

        page_count = _matches_api_page_count(payload) or page_count
        if page_count is not None and page_number > page_count:
            logger.info(
                "Stopping WTTJ pagination at page %s beyond page_count=%s",
                page_number,
                page_count,
            )
            _emit_progress(
                progress_callback,
                event="page_missing",
                page=page_number,
                pages_total=pages_total,
                page_count=page_count,
                max_jobs=max_jobs,
                progress_target=progress_target,
                yielded=yielded,
            )
            break
        links = parse_matches_api_links(payload)
        _emit_progress(
            progress_callback,
            event="page_links",
            page=page_number,
            pages_total=pages_total,
            page_count=page_count,
            links=len(links),
            max_jobs=max_jobs,
            progress_target=progress_target,
            yielded=yielded,
        )
        if not links:
            _emit_progress(
                progress_callback,
                event="page_empty",
                page=page_number,
                pages_total=pages_total,
                page_count=page_count,
                max_jobs=max_jobs,
                progress_target=progress_target,
                yielded=yielded,
            )
            break

        page_has_new_link = False
        for page_job_index, link in enumerate(links, start=1):
            if _should_stop(stop_requested):
                _emit_progress(
                    progress_callback,
                    event="cancelled",
                    page=page_number,
                    pages_total=pages_total,
                    page_count=page_count,
                    max_jobs=max_jobs,
                    progress_target=progress_target,
                    yielded=yielded,
                )
                return
            if link.url in seen:
                continue
            page_has_new_link = True
            seen.add(link.url)
            _emit_progress(
                progress_callback,
                event="job_detail_start",
                page=page_number,
                pages_total=pages_total,
                page_count=page_count,
                page_job_index=page_job_index,
                page_jobs=len(links),
                max_jobs=max_jobs,
                progress_target=progress_target,
                yielded=yielded,
                title_hint=link.title_hint,
            )
            try:
                detail_response = requests.get(link.url, headers=WTTJ_HEADERS, timeout=timeout)
                detail_response.raise_for_status()
                job = parse_detail_html(detail_response.text, url=link.url)
            except (requests.RequestException, WTTJScraperError) as html_exc:
                try:
                    api_job = (fetch_detail_api_job_fn or fetch_detail_api_job)(
                        link.url, timeout=timeout
                    )
                    job = parse_detail_api_job(api_job, url=link.url)
                except (requests.RequestException, WTTJScraperError) as api_exc:
                    detail_error = WTTJScraperError(
                        f"Failed to parse WTTJ job from HTML ({html_exc}) and API ({api_exc})"
                    )
                    if not skip_failed_jobs:
                        raise detail_error from api_exc
                    first_detail_error = first_detail_error or detail_error
                    logger.warning(
                        "Skipping WTTJ job %s: HTML failed (%s); API failed (%s)",
                        link.url,
                        html_exc,
                        api_exc,
                    )
                    _emit_progress(
                        progress_callback,
                        event="warning",
                        code="job_detail_failed",
                        message=(
                            f"WTTJ : offre {page_job_index} de la page {page_number} "
                            "ignorée car sa fiche était "
                            f"illisible ({_public_scrape_error(api_exc)})."
                        ),
                        page=page_number,
                        yielded=yielded,
                        title_hint=link.title_hint,
                    )
                    continue
            except Exception as exc:
                if not skip_failed_jobs:
                    raise
                first_detail_error = first_detail_error or WTTJScraperError(str(exc))
                logger.warning("Skipping WTTJ job %s: %s", link.url, exc)
                _emit_progress(
                    progress_callback,
                    event="warning",
                    code="job_detail_failed",
                    message=(
                        f"WTTJ : offre {page_job_index} de la page {page_number} "
                        "ignorée car sa fiche était "
                        f"illisible ({_public_scrape_error(exc)})."
                    ),
                    page=page_number,
                    yielded=yielded,
                    title_hint=link.title_hint,
                )
                continue
            source_data = dict(job.source_data or {})
            if link.api_data:
                source_data["matches_api"] = link.api_data
                _merge_company_profile_from_matches_api(source_data, link.api_data)
            job.source_data = source_data
            if include_company_profile:
                if _should_stop(stop_requested):
                    _emit_progress(
                        progress_callback,
                        event="cancelled",
                        page=page_number,
                        pages_total=pages_total,
                        page_count=page_count,
                        max_jobs=max_jobs,
                        progress_target=progress_target,
                        yielded=yielded,
                    )
                    return
                _emit_progress(
                    progress_callback,
                    event="company_profile_start",
                    page=page_number,
                    pages_total=pages_total,
                    page_count=page_count,
                    max_jobs=max_jobs,
                    progress_target=progress_target,
                    yielded=yielded,
                    title=job.title,
                    company=job.company,
                )
                _attach_company_profile(job, company_cache=company_cache, timeout=timeout)
            yielded += 1
            _emit_progress(
                progress_callback,
                event="job_yielded",
                page=page_number,
                pages_total=pages_total,
                page_count=page_count,
                max_jobs=max_jobs,
                progress_target=progress_target,
                yielded=yielded,
                title=job.title,
                company=job.company,
            )
            yield job
            if _should_stop(stop_requested):
                _emit_progress(
                    progress_callback,
                    event="cancelled",
                    page=page_number,
                    pages_total=pages_total,
                    page_count=page_count,
                    max_jobs=max_jobs,
                    progress_target=progress_target,
                    yielded=yielded,
                )
                return
            if max_jobs is not None and yielded >= max_jobs:
                _emit_progress(
                    progress_callback,
                    event="done",
                    page=page_number,
                    pages_total=pages_total,
                    page_count=page_count,
                    max_jobs=max_jobs,
                    progress_target=progress_target,
                    yielded=yielded,
                )
                return
            if delay_seconds > 0:
                sleep(delay_seconds)
        if not page_has_new_link:
            _emit_progress(
                progress_callback,
                event="page_duplicate",
                page=page_number,
                pages_total=pages_total,
                page_count=page_count,
                max_jobs=max_jobs,
                progress_target=progress_target,
                yielded=yielded,
            )
            break
    if yielded == 0 and first_detail_error is not None:
        raise first_detail_error
    _emit_progress(
        progress_callback,
        event="done",
        pages_total=pages_total,
        page_count=page_count,
        max_jobs=max_jobs,
        progress_target=progress_target,
        yielded=yielded,
    )


def scrape_matches_live(
    *,
    pages: Sequence[int],
    max_jobs: int | None = None,
    published_since: str | None = None,
    stop_requested: Callable[[], bool] | None = None,
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
            profile_dir = Path(
                user_data_dir or "~/Library/Application Support/Elan/cache/wttj-chrome-profile"
            ).expanduser()
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
                if _should_stop(stop_requested):
                    return
                url = matches_page_url(page_number, published_since=published_since)
                list_page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                _wait_for_wttj_content(list_page, timeout_ms, PlaywrightTimeoutError)
                listing_html = list_page.content()
                if html_dir:
                    (html_dir / f"jobs-matches-page-{page_number}.html").write_text(
                        listing_html,
                        encoding="utf-8",
                    )

                for link in parse_listing_links(listing_html):
                    if _should_stop(stop_requested):
                        return
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
    published_since: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, str]:
    headers = dict(WTTJ_HEADERS)
    headers.update(
        {
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie_header.strip(),
            "Origin": WTTJ_BASE_URL,
            "Referer": matches_page_url(1, published_since=published_since),
        }
    )
    csrf_token = _cookie_value(cookie_header, "csrf-token")
    if csrf_token:
        headers["x-csrf-token"] = csrf_token
    if extra_headers:
        headers.update(extra_headers)
    return headers
