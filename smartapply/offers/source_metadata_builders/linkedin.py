"""LinkedIn metadata blocks for analyzer prompts."""

from __future__ import annotations

from typing import Any

from smartapply.offers.source_metadata_builders.common import (
    _add_url,
    _append_scalar,
    _append_url_metadata_lines,
    _dict,
    _short,
)


def build_linkedin_source_metadata(source_data: dict[str, Any] | None) -> str:
    if not isinstance(source_data, dict):
        return ""

    contact_lines = _contact_lines(source_data)
    fact_lines = _fact_lines(source_data)
    motivation_lines = _motivation_lines(source_data)
    if not contact_lines and not fact_lines and not motivation_lines:
        return ""

    sections: list[str] = []
    if contact_lines:
        sections.append("CONTACT_AND_APPLICATION_METADATA:\n" + "\n".join(contact_lines))
    if fact_lines:
        sections.append("STRUCTURED_JOB_FACTS:\n" + "\n".join(fact_lines))
    if motivation_lines:
        sections.append("MOTIVATION_ANCHORS:\n" + "\n".join(motivation_lines))
    return "\n\n".join(sections)


def _contact_lines(source_data: dict[str, Any]) -> list[str]:
    lines = ["source: linkedin"]
    _append_scalar(lines, "companyName", source_data.get("companyName"))
    _append_scalar(lines, "recruiterName", source_data.get("recruiterName"))
    _append_scalar(lines, "applyType", source_data.get("applyType"))
    urls: list[dict[str, str]] = []
    _add_url(urls, _source_url(source_data, "applyUrl"), "applyUrl")
    _add_url(urls, _source_url(source_data, "url"), "url")
    _add_url(urls, _source_url(source_data, "companyUrl"), "companyUrl")
    _add_url(urls, _source_url(source_data, "recruiterUrl"), "recruiterUrl")
    _append_url_metadata_lines(lines, urls)
    return lines if len(lines) > 1 else []


def _fact_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in (
        "id",
        "title",
        "location",
        "postedDate",
        "postedTimeAgo",
        "applicationsCount",
        "experienceLevel",
        "contractType",
        "workType",
        "sector",
        "salary",
        "applyType",
    ):
        _append_scalar(lines, key, source_data.get(key))
    search = _dict(source_data.get("_smartapply_search"))
    for key in (
        "title",
        "location",
        "datePosted",
        "contractType",
        "experienceLevel",
        "remote",
        "experience_pass",
        "experience_fallback_used",
    ):
        _append_scalar(lines, f"search.{key}", search.get(key))
    normalized = _dict(source_data.get("_smartapply_normalized"))
    _append_scalar(lines, "normalized.description_source", normalized.get("description_source"))
    return lines


def _motivation_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    _append_scalar(lines, "company", source_data.get("companyName"))
    _append_scalar(lines, "sector", source_data.get("sector"))
    _append_scalar(lines, "role", source_data.get("title"))
    _append_scalar(lines, "workType", source_data.get("workType"))
    summary = _role_context_summary(source_data)
    if summary:
        _append_scalar(lines, "linkedin_context", summary)
    return lines


def _role_context_summary(source_data: dict[str, Any]) -> str:
    parts = [
        _short(source_data.get("experienceLevel"), 80),
        _short(source_data.get("contractType"), 80),
        _short(source_data.get("applicationsCount"), 80),
    ]
    return " · ".join(part for part in parts if part)


def _source_url(source_data: dict[str, Any], key: str) -> str:
    normalized = _dict(source_data.get("_smartapply_normalized"))
    return str(normalized.get(key) or source_data.get(key) or "")
