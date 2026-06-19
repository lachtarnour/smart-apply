"""Canonical input object for the job-analysis LLM call.

Different job sources expose different raw fields. This module keeps the
analyzer prompt isolated from those source-specific shapes by converting a
persisted ``Job`` into one stable payload.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

from smartapply.llm.source_metadata import build_analyzer_source_metadata

SourceOfferBodyBuilder = Callable[[str, dict[str, Any] | None], str]

_SOURCE_OFFER_BODY_BUILDERS: dict[str, SourceOfferBodyBuilder] = {}


@dataclass(frozen=True, slots=True)
class AnalyzerInput:
    """Stable payload consumed by the job-analysis prompt builder."""

    title: str
    company: str
    location: str | None
    application_url: str | None
    offer_body: str
    source: str
    source_metadata: str = ""


def register_source_offer_body_builder(
    source: str,
    builder: SourceOfferBodyBuilder,
) -> None:
    """Register a source-specific offer body enhancer for analyzer inputs."""
    normalized = source.strip().lower()
    if not normalized:
        raise ValueError("source must not be empty")
    _SOURCE_OFFER_BODY_BUILDERS[normalized] = builder


def build_analyzer_input(job: Any) -> AnalyzerInput:
    """Normalize a persisted job into the LLM analyzer input contract."""
    source = str(getattr(job, "source", "") or "")
    offer_body = _build_offer_body(job, source)
    return AnalyzerInput(
        title=str(getattr(job, "title", "") or ""),
        company=str(getattr(job, "company", "") or ""),
        location=getattr(job, "location", None),
        application_url=getattr(job, "application_url", None),
        offer_body=offer_body,
        source=source,
        source_metadata=build_analyzer_source_metadata(job),
    )


def _build_offer_body(job: Any, source: str) -> str:
    base_body = str(
        getattr(job, "cleaned_description", None)
        or getattr(job, "description", "")
        or ""
    )
    builder = _SOURCE_OFFER_BODY_BUILDERS.get(source.strip().lower())
    if builder is None:
        return base_body
    return builder(base_body, getattr(job, "source_data", None))


def _wttj_offer_body(base_body: str, source_data: dict[str, Any] | None) -> str:
    if not isinstance(source_data, dict):
        return base_body

    detail_api = source_data.get("detail_api")
    if not isinstance(detail_api, dict):
        return base_body

    company_description = _html_to_text(detail_api.get("company_description"))
    if not company_description or _contains_text(base_body, company_description):
        return base_body

    body = base_body.strip()
    company_block = f"Company context\n{company_description}"
    if not body:
        return company_block
    return f"{body}\n\n{company_block}"


def _html_to_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return " ".join(soup.get_text("\n", strip=True).split())


def _contains_text(haystack: str, needle: str) -> bool:
    normalized_haystack = _normalize_for_match(haystack)
    normalized_needle = _normalize_for_match(needle)
    if not normalized_haystack or not normalized_needle:
        return False
    if normalized_needle in normalized_haystack:
        return True
    prefix = normalized_needle[:160]
    return len(prefix) >= 80 and prefix in normalized_haystack


def _normalize_for_match(value: str) -> str:
    return " ".join(str(value or "").lower().split())


register_source_offer_body_builder("welcometothejungle", _wttj_offer_body)
