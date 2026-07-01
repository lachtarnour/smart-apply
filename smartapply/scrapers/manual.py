"""Manual ingestion — paste a URL or raw text and produce a RawJob.

This is the most flexible source: it lets the user add a job from any career
page that isn't covered by an automated scraper. The URL flow fetches the
page and extracts the visible text with BeautifulSoup. The user can refine
title/company before persisting if the heuristics aren't precise enough.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from smartapply.offers import RawJob, make_external_id
from smartapply.offers.sources.manual import ManualOfferAdapter, ManualOfferInput

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 CandiPilot/0.1"
    )
}


class ManualScraper:
    """Single-job source: paste text or fetch a URL."""

    name = "manual"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout
        self.adapter = ManualOfferAdapter()

    # -------------------- from text --------------------

    def from_structured(self, offer: ManualOfferInput) -> RawJob:
        return self.adapter.to_canonical(offer)

    def from_text(
        self,
        text: str,
        *,
        title: str,
        company: str,
        location: str | None = None,
        application_url: str | None = None,
        company_description: str | None = None,
        company_url: str | None = None,
        recruiter: str | None = None,
        structured: bool = False,
    ) -> RawJob:
        return self.adapter.from_text(
            text,
            title=title,
            company=company,
            location=location,
            application_url=application_url,
            company_description=company_description,
            company_url=company_url,
            recruiter=recruiter,
            structured=structured,
        )

    # -------------------- from url --------------------

    def from_url(
        self,
        url: str,
        *,
        title: str | None = None,
        company: str | None = None,
        location: str | None = None,
    ) -> RawJob:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme: {url!r}")
        if _is_private_or_local_host(parsed.hostname):
            raise ValueError(f"Refusing to fetch local/private URL: {url!r}")
        response = requests.get(url, headers=_DEFAULT_HEADERS, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        extracted_title = title or self._extract_title(soup)
        extracted_company = company or self._extract_company(soup, parsed.netloc)
        description = self._extract_text(soup)
        return RawJob(
            external_id=make_external_id("manual", extracted_company, extracted_title, url),
            title=extracted_title,
            company=extracted_company,
            location=location,
            description=description,
            application_url=url,
            source=self.name,
            source_data={"input": "url", "host": parsed.netloc},
        )

    # -------------------- helpers --------------------

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str:
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        h1 = soup.find("h1")
        if h1 and h1.text:
            return h1.text.strip()
        return "Untitled job"

    @staticmethod
    def _extract_company(soup: BeautifulSoup, fallback: str) -> str:
        for selector in [
            'meta[property="og:site_name"]',
            'meta[name="application-name"]',
        ]:
            tag = soup.select_one(selector)
            if tag and tag.get("content"):
                return tag["content"].strip()
        # Strip subdomains: jobs.acme.com -> acme.com -> Acme
        host = fallback.removeprefix("www.")
        return host.split(".")[0].capitalize() or host

    @staticmethod
    def _extract_text(soup: BeautifulSoup) -> str:
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def _is_private_or_local_host(hostname: str | None) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return True
    if host == "localhost" or host.endswith(".localhost"):
        return True

    def blocked_ip(value: str) -> bool:
        try:
            ip = ipaddress.ip_address(value)
        except ValueError:
            return False
        return any(
            (
                ip.is_loopback,
                ip.is_private,
                ip.is_link_local,
                ip.is_multicast,
                ip.is_reserved,
                ip.is_unspecified,
            )
        )

    if blocked_ip(host):
        return True

    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    return any(blocked_ip(info[4][0]) for info in infos)
