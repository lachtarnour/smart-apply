"""WTTJ company profile parsing and hydration."""

from __future__ import annotations

import re
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from smartapply.offers import RawJob
from smartapply.scrapers.wttj.contracts import (
    IGNORED_SECTION_TEXTS,
    WTTJ_API_BASE_URL,
    WTTJ_BASE_URL,
    WTTJ_HEADERS,
    WTTJScraperError,
)
from smartapply.scrapers.wttj.normalizers import (
    _api_company_summary,
    _as_text,
    _block_after_heading,
    _canonical_company_url,
    _clean_text,
    _company_canonical_url,
    _dict,
    _domain_from_url,
    _external_company_website,
    _faq_answers,
    _format_api_offices,
    _format_api_sectors,
    _href_for_selector,
    _is_external_url,
    _leaf_texts,
    _localized_text,
    _strip_heading,
    _text_for_selector,
    _video_titles,
)


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
        source_data["company_domain"] = _domain_from_url(
            _as_text(source_data.get("company_website"))
        )
        job.source_data = source_data
        return

    existing_profile = _dict(source_data.get("company_profile"))
    company_profile = company_cache.get(profile_url)
    if company_profile is None:
        company_profile = dict(existing_profile)
        try:
            html = _fetch_company_profile_html(profile_url, timeout=timeout)
            company_profile = _merge_company_profiles(
                company_profile,
                parse_company_html(html, url=profile_url),
            )
            company_profile.pop("scrape_error", None)
        except (requests.RequestException, WTTJScraperError) as exc:
            try:
                company_profile = _merge_company_profiles(
                    company_profile,
                    _fetch_company_profile_api(profile_url, timeout=timeout),
                )
                company_profile.pop("scrape_error", None)
            except (requests.RequestException, WTTJScraperError):
                company_profile = _merge_company_profiles(
                    company_profile,
                    {"url": profile_url, "scrape_error": str(exc)},
                )
        company_cache[profile_url] = company_profile

    website = _as_text(company_profile.get("website")) or _as_text(
        source_data.get("company_website")
    )
    source_data["company_profile_url"] = profile_url
    source_data["company_profile"] = company_profile
    source_data["company_website"] = website
    source_data["company_domain"] = _domain_from_url(website)
    job.source_data = source_data


def _fetch_company_profile_html(
    profile_url: str,
    *,
    timeout: int,
    attempts: int = 4,
    retry_delay_seconds: float = 0.5,
) -> str:
    last_error: requests.RequestException | None = None
    max_attempts = max(1, attempts)
    for attempt in range(max_attempts):
        response = requests.get(profile_url, headers=WTTJ_HEADERS, timeout=timeout)
        if response.status_code == 202 and not response.text.strip():
            last_error = requests.RequestException("WTTJ returned an empty 202 company page")
            if attempt < max_attempts - 1 and retry_delay_seconds > 0:
                sleep(retry_delay_seconds)
            continue
        response.raise_for_status()
        return response.text
    raise last_error or requests.RequestException("WTTJ company page did not return HTML")


def _fetch_company_profile_api(profile_url: str, *, timeout: int) -> dict[str, Any]:
    slug = _company_slug_from_profile_url(profile_url)
    if not slug:
        raise WTTJScraperError(f"Cannot build WTTJ organization API URL for {profile_url}")
    headers = dict(WTTJ_HEADERS)
    headers["Accept"] = "application/json, text/plain, */*"
    response = requests.get(
        f"{WTTJ_API_BASE_URL}/api/v1/organizations/{slug}",
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise WTTJScraperError("WTTJ organization API did not return JSON.") from exc
    organization = payload.get("organization") if isinstance(payload, dict) else None
    if not isinstance(organization, dict):
        raise WTTJScraperError("Unexpected WTTJ organization API payload.")
    return _company_profile_from_public_api(organization, profile_url)


def _company_profile_from_public_api(
    organization: dict[str, Any],
    profile_url: str,
) -> dict[str, Any]:
    website = _company_website_from_public_api(organization.get("media_website_url"))
    stats = {
        "employees": organization.get("nb_employees"),
    }
    stats = {key: value for key, value in stats.items() if value is not None}
    return {
        "name": _as_text(organization.get("name")),
        "url": profile_url,
        "website": website,
        "domain": _domain_from_url(website),
        "sectors": _format_api_sectors(organization.get("sectors")),
        "offices": _format_api_offices(organization.get("offices")),
        "stats": stats,
        "source": "organization_api",
    }


def _company_slug_from_profile_url(profile_url: str) -> str | None:
    match = re.search(r"/companies/([^/?#]+)", profile_url)
    return match.group(1) if match else None


def _company_website_from_public_api(value: Any) -> str | None:
    text = _as_text(value)
    if not text:
        return None
    if _is_external_url(text):
        return text
    if "." not in text or text.startswith(("/", "#")):
        return None
    candidate = f"https://{text}"
    return candidate if _is_external_url(candidate) else None


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
        if text.lower() not in IGNORED_SECTION_TEXTS
    ]
    return _clean_text("\n".join(paragraphs)) or None


def _company_tags(soup: BeautifulSoup) -> list[str]:
    tags = [
        _clean_text(tag.get_text(" ", strip=True))
        for tag in soup.select('[data-testid="job-company-tag"]')
    ]
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
    candidates = [
        text for text in _leaf_texts(block, tags=("a", "span", "p")) if text != "Le lieu de travail"
    ]
    return (
        candidates[-1]
        if candidates
        else _strip_heading(_clean_text(block.get_text(" ", strip=True)), "Le lieu de travail")
    )


def _section_items_by_heading(soup: BeautifulSoup, heading: str) -> list[str]:
    block = _block_after_heading(soup, heading, parent_steps=2)
    if not block:
        return []
    items: list[str] = []
    for text in _leaf_texts(block):
        if text == heading:
            continue
        normalized = text.lower()
        if normalized in IGNORED_SECTION_TEXTS or re.fullmatch(r"\d+", text):
            continue
        if len(text) > 120:
            continue
        if text not in items:
            items.append(text)
    return items


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
