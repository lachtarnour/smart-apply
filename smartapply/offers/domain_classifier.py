"""Domain normalization and classification for offer URLs."""

from __future__ import annotations

from urllib.parse import urlparse

from smartapply.offers.domain_rules import (
    APPLICATION_REDIRECT_DOMAINS,
    ATS_DOMAINS,
    NON_COMPANY_DOMAINS,
    PARTNER_JOB_BOARD_DOMAINS,
    SUSPECT_PLATFORM_DOMAIN_MARKERS,
)


def domain_from_url(url: str | None) -> str | None:
    """Return a normalized root-ish domain from an http(s) URL."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.split("@")[-1].split(":")[0].lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    multi_part_suffixes = {
        ("co", "uk"),
        ("com", "au"),
        ("com", "br"),
        ("com", "tr"),
        ("com", "fr"),
        ("co", "jp"),
        ("asso", "fr"),
    }
    if len(parts) >= 3 and tuple(parts[-2:]) in multi_part_suffixes:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_domain(domain: str | None) -> str:
    return str(domain or "").lower().strip().removeprefix("www.")


def is_known_domain(domain: str | None, known_domains: set[str]) -> bool:
    normalized = normalize_domain(domain)
    if not normalized:
        return False
    return any(normalized == known or normalized.endswith(f".{known}") for known in known_domains)


def classify_application_domain(domain: str | None) -> str:
    normalized = normalize_domain(domain)
    if is_known_domain(normalized, ATS_DOMAINS):
        return "ats"
    if is_known_domain(normalized, PARTNER_JOB_BOARD_DOMAINS):
        return "partner_job_board"
    if is_known_domain(normalized, APPLICATION_REDIRECT_DOMAINS):
        return "application_redirect"
    return "unknown"


def is_company_domain(domain: str | None) -> bool:
    if not domain:
        return False
    domain = domain.lower().removeprefix("www.")
    return not is_job_board_domain(domain)


def is_job_board_domain(domain: str | None) -> bool:
    return is_known_domain(domain, NON_COMPANY_DOMAINS)


def is_suspicious_platform_domain(domain: str | None) -> bool:
    """Return True for domains that look like recruitment platforms."""
    if not domain:
        return False
    labels = [label for label in domain.lower().removeprefix("www.").split(".") if label]
    searchable = labels[:-1] if len(labels) > 1 else labels
    return any(
        marker in label for label in searchable for marker in SUSPECT_PLATFORM_DOMAIN_MARKERS
    )


def is_reliable_company_domain(domain: str | None) -> bool:
    return is_company_domain(domain) and not is_suspicious_platform_domain(domain)
