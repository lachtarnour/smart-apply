"""Ingestion-time duplicate matching helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from smartapply.offers import RawJob


@dataclass(frozen=True)
class _KnownJobIndex:
    external_ids: frozenset[str]
    application_urls: frozenset[str]

    @classmethod
    def from_jobs(cls, jobs: list[Any]) -> _KnownJobIndex:
        urls: set[str] = set()
        external_ids: set[str] = set()
        for job in jobs:
            if job.external_id:
                external_ids.add(str(job.external_id))
            url_key = _normalize_application_url(job.application_url)
            if url_key:
                urls.add(url_key)
        return cls(
            external_ids=frozenset(external_ids),
            application_urls=frozenset(urls),
        )

    def matches(self, raw: RawJob) -> bool:
        if raw.external_id and raw.external_id in self.external_ids:
            return True
        url_key = _normalize_application_url(raw.application_url)
        return bool(url_key and url_key in self.application_urls)


def _normalize_application_url(url: str | None) -> str:
    value = (url or "").strip()
    if not value or value.startswith("mailto:"):
        return ""
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        return ""
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    query = _normalized_non_tracking_query(parsed.query)
    normalized = f"{host}{path}".lower()
    if query:
        normalized = f"{normalized}?{query}"
    return normalized


def _normalized_non_tracking_query(query: str) -> str:
    tracking_prefixes = ("utm_",)
    tracking_names = {
        "fbclid",
        "alternatechannel",
        "ebp",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "refid",
        "source",
        "trackingid",
        "utm",
    }
    kept = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() not in tracking_names
        and not key.lower().startswith(tracking_prefixes)
    ]
    return urlencode(sorted(kept), doseq=True)

