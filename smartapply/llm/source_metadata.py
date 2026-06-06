"""Source-specific metadata blocks for job analysis prompts."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from smartapply.email_agent.contact_providers import (
    classify_application_domain,
    domain_from_url,
    is_reliable_company_domain,
)

_URL_RE = re.compile(r"https?://[^\s\"'<>),;]+|www\.[^\s\"'<>),;]+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_MAX_LINE = 220
_MAX_URLS = 14
_MAX_LIST_ITEMS = 8

SourceMetadataBuilder = Callable[[dict[str, Any] | None], str]

_SOURCE_METADATA_BUILDERS: dict[str, SourceMetadataBuilder] = {}


def register_source_metadata_builder(
    source: str,
    builder: SourceMetadataBuilder,
) -> None:
    """Register a source-specific metadata builder for analyzer inputs."""
    normalized = source.strip().lower()
    if not normalized:
        raise ValueError("source must not be empty")
    _SOURCE_METADATA_BUILDERS[normalized] = builder


def build_analyzer_source_metadata(job: Any) -> str:
    """Return a short structured source-specific metadata block for the analyzer."""
    source = str(getattr(job, "source", "") or "").strip().lower()
    builder = _SOURCE_METADATA_BUILDERS.get(source)
    if builder is None:
        return ""
    return builder(getattr(job, "source_data", None))


def build_francetravail_source_metadata(source_data: dict[str, Any] | None) -> str:
    """Build a compact France Travail metadata block without raw JSON."""
    if not isinstance(source_data, dict):
        return ""

    contact_lines = _contact_and_application_lines(source_data)
    fact_lines = _structured_job_fact_lines(source_data)
    if not contact_lines and not fact_lines:
        return ""

    sections: list[str] = []
    if contact_lines:
        sections.append("CONTACT_AND_APPLICATION_METADATA:\n" + "\n".join(contact_lines))
    if fact_lines:
        sections.append("STRUCTURED_JOB_FACTS:\n" + "\n".join(fact_lines))
    return "\n\n".join(sections)


def _contact_and_application_lines(source_data: dict[str, Any]) -> list[str]:
    entreprise = _dict(source_data.get("entreprise"))
    contact = _dict(source_data.get("contact"))
    origine = _dict(source_data.get("origineOffre"))
    lines = ["source: francetravail"]
    _append_scalar(lines, "raw_id", source_data.get("id"))
    _append_scalar(lines, "entreprise.nom", entreprise.get("nom"))
    _append_scalar(lines, "origineOffre.origine", origine.get("origine"))
    _append_scalar(lines, "contact.nom", contact.get("nom"))
    _append_scalar(lines, "contact.courriel", contact.get("courriel"))

    urls: list[dict[str, str]] = []
    _add_url(urls, origine.get("urlOrigine"), "origineOffre.urlOrigine")
    for index, partner in enumerate(origine.get("partenaires") or []):
        if not isinstance(partner, dict):
            continue
        _append_scalar(lines, f"origineOffre.partenaires[{index}].nom", partner.get("nom"))
        _add_url(
            urls,
            partner.get("url"),
            f"origineOffre.partenaires[{index}].url",
        )
    _add_url(urls, contact.get("urlPostulation"), "contact.urlPostulation")
    _add_urls_from_text(urls, contact.get("coordonnees1"), "contact.coordonnees1")
    _add_url(urls, entreprise.get("url"), "entreprise.url")
    _add_urls_from_text(urls, source_data.get("description"), "description")
    _add_urls_from_text(urls, entreprise.get("description"), "entreprise.description")

    for item in urls[:_MAX_URLS]:
        line = (
            f"url: source_field={item['source_field']} | url={item['url']} | "
            f"domain={item['domain']} | url_kind={item['url_kind']}"
        )
        if item.get("company_domain_candidate"):
            line += f" | company_domain_candidate={item['company_domain_candidate']}"
        lines.append(line)
    return lines


def _structured_job_fact_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in (
        "experienceExige",
        "experienceLibelle",
        "typeContratLibelle",
        "natureContrat",
        "dureeTravailLibelle",
        "salaire",
        "secteurActiviteLibelle",
        "trancheEffectifEtab",
        "nombrePostes",
        "deplacementLibelle",
    ):
        _append_scalar(lines, key, source_data.get(key))

    if source_data.get("_smartapply_experience"):
        _append_scalar(lines, "_smartapply_experience", _compact_mapping(source_data["_smartapply_experience"]))
    _append_list_summary(lines, "formations", source_data.get("formations"), ("niveauLibelle", "domaineLibelle", "commentaire"))
    _append_list_summary(lines, "langues", source_data.get("langues"), ("libelle", "exigence"))
    _append_list_summary(lines, "competences", source_data.get("competences"), ("libelle", "exigence"))
    _append_list_summary(
        lines,
        "qualitesProfessionnelles",
        source_data.get("qualitesProfessionnelles"),
        ("libelle", "description"),
    )
    _append_context_summary(lines, source_data.get("contexteTravail"))
    return lines


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


def _short(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:_MAX_LINE]


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
    if source_field == "entreprise.url" and _can_be_company_domain(domain):
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


register_source_metadata_builder("francetravail", build_francetravail_source_metadata)
