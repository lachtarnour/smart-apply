"""Shared helpers for source metadata prompt blocks."""

from __future__ import annotations

import re
from typing import Any

from smartapply.contacts.domain_classifier import (
    classify_application_domain,
    domain_from_url,
    is_reliable_company_domain,
)

_URL_RE = re.compile(r"https?://[^\s\"'<>),;]+|www\.[^\s\"'<>),;]+", re.IGNORECASE)

_MAX_LINE = 220
_MAX_URLS = 14
_MAX_LIST_ITEMS = 8

def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _append_scalar(lines: list[str], key: str, value: Any) -> None:
    text = _short(value)
    if text:
        lines.append(f"{key}: {text}")


def _append_list_summary(
    lines: list[str],
    key: str,
    value: Any,
    fields: tuple[str, ...],
) -> None:
    if not isinstance(value, list) or not value:
        return
    parts: list[str] = []
    for item in value[:_MAX_LIST_ITEMS]:
        if isinstance(item, dict):
            text = " / ".join(_short(item.get(field)) for field in fields if _short(item.get(field)))
        else:
            text = _short(item)
        if text:
            parts.append(text)
    if parts:
        _append_scalar(lines, key, "; ".join(parts))


def _append_context_summary(lines: list[str], value: Any) -> None:
    if not isinstance(value, dict) or not value:
        return
    parts = [f"{key}={_short(val)}" for key, val in sorted(value.items()) if _short(val)]
    if parts:
        _append_scalar(lines, "contexteTravail", "; ".join(parts))


def _compact_mapping(value: Any) -> str:
    if not isinstance(value, dict):
        return _short(value)
    parts = [f"{key}={_short(val)}" for key, val in sorted(value.items()) if _short(val)]
    return "; ".join(parts)


def _short(value: Any, limit: int = _MAX_LINE) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _add_urls_from_text(
    urls: list[dict[str, str]],
    value: Any,
    source_field: str,
) -> None:
    for match in _URL_RE.finditer(str(value or "")):
        _add_url(urls, match.group(0), source_field)


def _add_url(urls: list[dict[str, str]], value: Any, source_field: str) -> None:
    url = _normalize_url(value)
    if not url:
        return
    domain = domain_from_url(url)
    if not domain:
        return
    if any(item["url"] == url and item["source_field"] == source_field for item in urls):
        return
    url_kind = _classify_url(domain, source_field)
    item = {
        "url": url,
        "domain": domain,
        "source_field": source_field,
        "url_kind": url_kind,
    }
    if url_kind == "company_url":
        item["company_domain_candidate"] = domain
    urls.append(item)


def _normalize_url(value: Any) -> str:
    text = str(value or "").strip().rstrip(".,;")
    if not text:
        return ""
    if text.startswith("www."):
        return f"https://{text}"
    if not text.startswith(("http://", "https://")):
        return ""
    return text


def _classify_url(domain: str, source_field: str) -> str:
    if domain == "francetravail.fr":
        return "francetravail"
    if source_field in {"entreprise.url", "company_url"} and _can_be_company_domain(domain):
        return "company_url"
    domain_kind = classify_application_domain(domain)
    if domain_kind != "unknown":
        return domain_kind
    if source_field.startswith("origineOffre.partenaires"):
        return "partner_job_board"
    if source_field.startswith("contact."):
        return "application_url"
    if _can_be_company_domain(domain):
        return "company_url"
    return "unknown"


def _can_be_company_domain(domain: str) -> bool:
    return is_reliable_company_domain(domain) and classify_application_domain(domain) == "unknown"


def _append_url_metadata_lines(lines: list[str], urls: list[dict[str, str]]) -> None:
    for item in urls[:_MAX_URLS]:
        line = (
            f"url: source_field={item['source_field']} | url={item['url']} | "
            f"domain={item['domain']} | url_kind={item['url_kind']}"
        )
        if item.get("company_domain_candidate"):
            line += f" | company_domain_candidate={item['company_domain_candidate']}"
        lines.append(line)


