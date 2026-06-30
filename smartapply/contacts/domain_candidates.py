"""Extract and normalize candidate company domains from offer sources."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from smartapply.contacts.domain_classifier import domain_from_url
from smartapply.contacts.models import SourceDomainCandidate


def _normalize_domain_candidate(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    if not candidate:
        return None
    candidate = candidate.removeprefix("mailto:")
    if "@" in candidate and "://" not in candidate:
        candidate = candidate.rsplit("@", 1)[-1]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9](?:/.*)?", candidate) and (
        "://" not in candidate
    ):
        return None
    url = candidate if "://" in candidate else f"https://{candidate}"
    domain = domain_from_url(url)
    if not domain or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
        return None
    return domain


def _unique_domains(domains: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for domain in domains:
        normalized = _normalize_domain_candidate(domain)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def domains_visible_in_text(text: str | None) -> list[str]:
    """Extract strong email/URL signals visible in the offer body.

    Bare tokens such as ``draw.io`` or French inclusive writing like
    ``client.es`` are intentionally ignored. They are too noisy to prove a
    company domain.
    """
    body = text or ""
    domains: list[str | None] = []
    domains.extend(re.findall(r"[\w.+-]+@([\w.-]+\.[a-zA-Z]{2,})", body))
    domains.extend(
        re.findall(
            r"\bhttps?://(?:www\.)?([\w.-]+\.[a-zA-Z]{2,})(?:[/?#:]|\b)",
            body,
        )
    )
    domains.extend(
        re.findall(r"\bwww\.([\w.-]+\.[a-zA-Z]{2,})(?:[/?#:]|\b)", body)
    )
    return _unique_domains(domains)


def _source_domain_url(raw_value: str) -> str | None:
    raw_value = raw_value.strip()
    return raw_value if "://" in raw_value else None


def _source_domain_candidate(
    value: Any,
    source_field: str,
) -> SourceDomainCandidate | None:
    raw_value = str(value or "").strip()
    domain = _normalize_domain_candidate(raw_value)
    if not domain:
        return None
    return SourceDomainCandidate(
        domain=domain,
        url=_source_domain_url(raw_value),
        source_field=source_field,
    )


def _append_source_domain_candidate(
    candidates: list[SourceDomainCandidate],
    value: Any,
    source_field: str,
) -> None:
    candidate = _source_domain_candidate(value, source_field)
    if candidate is None:
        return
    if any(existing.domain == candidate.domain for existing in candidates):
        return
    candidates.append(candidate)


def source_domain_candidates(source_data: Any | None) -> list[SourceDomainCandidate]:
    """Extract source-provided company domains without relying on source names.

    This intentionally reads only structured company/organization fields.
    Broad URLs such as application links or job-board profile URLs are left out;
    they are already handled by the application URL path.
    """
    if not isinstance(source_data, Mapping):
        return []

    candidates: list[SourceDomainCandidate] = []
    for key in (
        "company_website",
        "company_url",
        "employer_website",
        "employer_url",
        "organization_website",
        "organization_url",
        "company_domain",
        "employer_domain",
        "organization_domain",
    ):
        _append_source_domain_candidate(candidates, source_data.get(key), key)

    nested_fields = {
        "company_profile": ("website", "external_url", "domain"),
        "hiring_organization": ("sameAs", "website", "url", "domain"),
        "organization": ("sameAs", "website", "url", "domain"),
        "company": ("website", "url", "domain"),
        "employer": ("website", "url", "domain"),
    }
    for parent_key, keys in nested_fields.items():
        parent = source_data.get(parent_key)
        if not isinstance(parent, Mapping):
            continue
        for key in keys:
            _append_source_domain_candidate(
                candidates,
                parent.get(key),
                f"{parent_key}.{key}",
            )
    return candidates


