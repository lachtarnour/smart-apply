"""Common types and abstract base class for job scrapers."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class RawJob(BaseModel):
    """Canonical representation of a freshly scraped job.

    Maps 1-1 to the ``Job`` SQLAlchemy model, intentionally without ids so it
    can be safely (de-)serialized.
    """

    model_config = ConfigDict(extra="ignore")

    external_id: str
    title: str
    company: str
    location: str | None = None
    contract_type: str | None = None
    remote_policy: str | None = None
    description: str
    application_url: str | None = None
    apply_options: list[dict[str, Any]] | None = None
    published_date: datetime | None = None
    source: str
    source_data: dict[str, Any] | None = None


def make_external_id(source: str, *parts: str) -> str:
    """Build a stable external id namespaced by the source.

    The hash makes it independent of accidental whitespace / casing changes
    while staying short and deterministic.
    """
    raw = "|".join(p.strip().lower() for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"


class Scraper(ABC):
    """Abstract base class for searchable job sources."""

    name: str = ""

    @abstractmethod
    def search(
        self,
        query: str,
        location: str | None = None,
        *,
        max_results: int | None = None,
        **kwargs: Any,
    ) -> Iterator[RawJob]:
        """Yield jobs matching the search query."""

    def is_available(self) -> bool:
        """Return True if the scraper has the credentials/config it needs."""
        return True


class ScraperError(RuntimeError):
    """Base exception for scrapers."""


class ScraperConfigError(ScraperError):
    """Raised when a scraper is misconfigured (missing API key, etc.)."""
