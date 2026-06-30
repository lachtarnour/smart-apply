"""Shared WTTJ scraper contracts and constants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from smartapply.scrapers.base import ScraperError

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

JOB_PATH_RE = re.compile(r"/(?:fr|en)/companies/[^/]+/jobs/[^/?#]+")
CONTRACT_LABELS = (
    "CDI",
    "CDD",
    "Stage",
    "Alternance",
    "Freelance",
    "VIE",
    "Temps partiel",
)
IGNORED_SECTION_TEXTS = {
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
