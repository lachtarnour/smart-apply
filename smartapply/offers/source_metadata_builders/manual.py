"""Manual-offer metadata blocks for analyzer prompts."""

from __future__ import annotations

from typing import Any

from smartapply.offers.source_metadata_builders.common import (
    _add_url,
    _add_urls_from_text,
    _append_scalar,
    _append_url_metadata_lines,
)


def build_manual_source_metadata(source_data: dict[str, Any] | None) -> str:
    """Build compact metadata for structured manual offers."""
    if not isinstance(source_data, dict):
        return ""

    contact_lines = _manual_contact_lines(source_data)
    fact_lines = _manual_fact_lines(source_data)
    if not contact_lines and not fact_lines:
        return ""

    sections: list[str] = []
    if contact_lines:
        sections.append("CONTACT_AND_APPLICATION_METADATA:\n" + "\n".join(contact_lines))
    if fact_lines:
        sections.append("STRUCTURED_JOB_FACTS:\n" + "\n".join(fact_lines))
    return "\n\n".join(sections)


def _manual_contact_lines(source_data: dict[str, Any]) -> list[str]:
    lines = ["source: manual"]
    _append_scalar(lines, "company_url", source_data.get("company_url"))
    _append_scalar(lines, "recruiter", source_data.get("recruiter"))

    urls: list[dict[str, str]] = []
    _add_url(urls, source_data.get("company_url"), "company_url")
    _add_urls_from_text(urls, source_data.get("recruiter"), "recruiter")
    _append_url_metadata_lines(lines, urls)
    return lines if len(lines) > 1 else []


def _manual_fact_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    _append_scalar(lines, "input", source_data.get("input"))
    return lines


