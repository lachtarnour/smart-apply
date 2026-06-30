"""Canonical offer contracts shared across scrapers, storage and pipeline code."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RawJob(BaseModel):
    """Canonical representation of a freshly collected job offer.

    Scrapers and source adapters translate source-specific payloads into this
    shape before persistence. It intentionally mirrors the persisted Job fields
    without database ids.
    """

    model_config = ConfigDict(extra="ignore")

    external_id: str
    title: str
    company: str
    location: str | None = None
    contract_type: str | None = None
    remote_policy: str | None = None
    description: str
    experience: dict[str, Any] | None = None
    application_url: str | None = None
    apply_options: list[dict[str, Any]] | None = None
    published_date: datetime | None = None
    source: str
    source_data: dict[str, Any] | None = None


def make_external_id(source: str, *parts: str) -> str:
    """Build a stable external id namespaced by the source."""
    raw = "|".join(p.strip().lower() for p in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{source}:{digest}"
