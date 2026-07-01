"""Registry of available scrapers.

Other modules should always go through ``get_scraper(name)`` rather than
instantiating concrete scrapers directly. This keeps the pipeline decoupled
from concrete sources.
"""

from __future__ import annotations

from collections.abc import Callable

from smartapply.scrapers.base import Scraper
from smartapply.scrapers.francetravail import FranceTravailScraper
from smartapply.scrapers.linkedin import LinkedInJobsScraper
from smartapply.scrapers.serpapi import SerpApiGoogleJobsScraper
from smartapply.scrapers.welcometothejungle import WelcomeToTheJungleScraper

_BUILDERS: dict[str, Callable[[], Scraper]] = {
    "serpapi": SerpApiGoogleJobsScraper,
    "francetravail": FranceTravailScraper,
    "linkedin": LinkedInJobsScraper,
    "welcometothejungle": WelcomeToTheJungleScraper,
}


def available_scrapers() -> list[str]:
    return list(_BUILDERS.keys())


def get_scraper(name: str) -> Scraper:
    """Return a fresh scraper instance for the given source name."""
    if name not in _BUILDERS:
        raise KeyError(
            f"Unknown scraper {name!r}. Available: {', '.join(available_scrapers())}"
        )
    return _BUILDERS[name]()
