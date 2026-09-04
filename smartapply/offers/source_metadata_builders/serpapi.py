"""SerpApi / Google Jobs metadata blocks for analyzer prompts."""

from __future__ import annotations

from typing import Any

from smartapply.offers.source_metadata_builders.common import (
    _MAX_LIST_ITEMS,
    _add_url,
    _append_scalar,
    _append_url_metadata_lines,
    _dict,
    _short,
)


def build_serpapi_source_metadata(source_data: dict[str, Any] | None) -> str:
    """Build compact SerpApi metadata for analyzer prompts.

    SerpApi/Google Jobs already injects ``job_highlights`` into the offer body,
    so this builder avoids repeating the full description. It exposes only
    source-level signals that were previously invisible to the analyzer:
    application options, search fallback audit, detected extensions and short
    highlight summaries useful for motivation anchors, tasks and risks.
    """
    if not isinstance(source_data, dict):
        return ""

    url_lines = _serpapi_application_url_lines(source_data)
    fact_lines = _serpapi_fact_lines(source_data)
    motivation_lines = _serpapi_motivation_anchor_lines(source_data)
    if not url_lines and not fact_lines and not motivation_lines:
        return ""

    sections: list[str] = []
    if url_lines:
        sections.append("APPLICATION_URL_METADATA:\n" + "\n".join(url_lines))
    if fact_lines:
        sections.append("STRUCTURED_JOB_FACTS:\n" + "\n".join(fact_lines))
    if motivation_lines:
        sections.append("MOTIVATION_ANCHORS:\n" + "\n".join(motivation_lines))
    return "\n\n".join(sections)


def _serpapi_application_url_lines(source_data: dict[str, Any]) -> list[str]:
    lines = ["source: serpapi"]
    _append_scalar(lines, "company_name", source_data.get("company_name"))
    _append_serpapi_apply_options(lines, source_data.get("apply_options"))
    _append_serpapi_url(lines, source_data.get("share_link"), "share_link")

    search = _dict(source_data.get("_smartapply_search"))
    _append_scalar(lines, "search.result_origin", search.get("result_origin"))
    _append_scalar(lines, "search.strict_chips", search.get("strict_chips"))
    _append_scalar(lines, "search.fallback_reason", search.get("fallback_reason"))
    _append_scalar(lines, "search.fallback_chips", search.get("fallback_chips"))
    return lines if len(lines) > 1 else []


def _serpapi_fact_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    detected = _dict(source_data.get("detected_extensions"))
    for key in (
        "schedule_type",
        "work_from_home",
        "posted_at",
        "salary",
        "detected_salary",
    ):
        _append_scalar(lines, f"detected_extensions.{key}", detected.get(key))
    _append_scalar(lines, "location", source_data.get("location"))
    _append_serpapi_highlight_summaries(lines, source_data.get("job_highlights"))
    return lines


def _serpapi_motivation_anchor_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    _append_scalar(lines, "title", source_data.get("title"))
    _append_scalar(lines, "company_name", source_data.get("company_name"))
    for section in _serpapi_highlight_sections(source_data.get("job_highlights"))[:_MAX_LIST_ITEMS]:
        title = section["title"]
        items = "; ".join(section["items"][:4])
        if items:
            _append_scalar(lines, f"job_highlights.{title}", items)
    return lines


def _append_serpapi_apply_options(lines: list[str], value: Any) -> None:
    if not isinstance(value, list) or not value:
        return
    urls: list[dict[str, str]] = []
    labels: list[str] = []
    for index, item in enumerate(value[:_MAX_LIST_ITEMS]):
        if not isinstance(item, dict):
            continue
        title = _short(item.get("title") or item.get("name") or f"option_{index}")
        if title:
            labels.append(title)
        _add_url(urls, item.get("link"), f"apply_options[{index}].link")
    if labels:
        _append_scalar(lines, "apply_options", "; ".join(labels))
    _append_url_metadata_lines(lines, urls)


def _append_serpapi_url(lines: list[str], value: Any, source_field: str) -> None:
    urls: list[dict[str, str]] = []
    _add_url(urls, value, source_field)
    _append_url_metadata_lines(lines, urls)


def _append_serpapi_highlight_summaries(lines: list[str], value: Any) -> None:
    for section in _serpapi_highlight_sections(value)[:_MAX_LIST_ITEMS]:
        if section["items"]:
            _append_scalar(
                lines,
                f"job_highlights.{section['title']}",
                "; ".join(section["items"][:_MAX_LIST_ITEMS]),
            )


def _serpapi_highlight_sections(value: Any) -> list[dict[str, list[str]]]:
    if not isinstance(value, list):
        return []
    sections: list[dict[str, list[str]]] = []
    for index, section in enumerate(value):
        if not isinstance(section, dict):
            continue
        title = _short(section.get("title") or f"section_{index}", 80)
        items: list[str] = []
        for item in section.get("items") or []:
            text = _short(item, 160)
            if text and text not in items:
                items.append(text)
        if title or items:
            sections.append({"title": title or f"section_{index}", "items": items})
    return sections
