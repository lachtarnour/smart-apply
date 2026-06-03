"""Registry of available scrapers.

Other modules should always go through ``get_scraper(name)`` rather than
instantiating concrete scrapers directly. This keeps the pipeline decoupled
from concrete sources.
"""

from __future__ import annotations

from collections.abc import Callable

from smartapply.config import get_settings
from smartapply.scrapers.base import Scraper
from smartapply.scrapers.francetravail import FranceTravailScraper
from smartapply.scrapers.serpapi import SerpApiGoogleJobsScraper

_BUILDERS: dict[str, Callable[[], Scraper]] = {
    "serpapi": SerpApiGoogleJobsScraper,
    "francetravail": FranceTravailScraper,
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


def get_active_scrapers() -> list[Scraper]:
    """Return scraper instances enabled in JOB_SOURCES *and* configured."""
    settings = get_settings()
    active: list[Scraper] = []
    for name in settings.enabled_sources:
        if name == "manual":
            # manual is a pull-based source, not a Scraper instance
            continue
        if name not in _BUILDERS:
            continue
        scraper = _BUILDERS[name]()
        if scraper.is_available():
            active.append(scraper)
    return active
