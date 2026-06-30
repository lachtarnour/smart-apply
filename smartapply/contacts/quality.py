"""Quality checks for external contact candidates."""

from __future__ import annotations

from smartapply.contacts.company import (
    _email_domain_matches_company,
    _same_company_domain,
)
from smartapply.contacts.domain_classifier import (
    domain_from_url,
    is_job_board_domain,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
)
from smartapply.contacts.models import ContactCandidate


def _email_domain(email: str | None) -> str:
    value = (email or "").strip().lower()
    if "@" not in value:
        return ""
    return value.rsplit("@", 1)[-1]


def _domain_is_usable(domain: str | None) -> tuple[bool, str]:
    if not domain:
        return False, "domain_invalid"
    if is_job_board_domain(domain):
        return False, "domain_is_job_board"
    if is_suspicious_contact_domain(domain):
        return False, "domain_looks_like_recruitment_platform"
    if not is_reliable_company_domain(domain):
        return False, "domain_not_reliable_company_domain"
    return True, "domain_reliable"


def _external_contact_quality_issue(
    contact: ContactCandidate,
    *,
    lookup_company: str | None,
    lookup_domain: str | None,
) -> str | None:
    """Return a rejection reason for low-quality Anymail-style contacts."""
    source = (contact.source_url or "").lower()
    provider = (contact.provider or "").lower()
    if "anymailfinder" not in source and "anymailfinder" not in provider:
        return None

    email_domain = _email_domain(contact.email)
    if not email_domain:
        return "email_invalid"
    normalized_domain = domain_from_url(f"https://{email_domain}") or email_domain
    if is_job_board_domain(normalized_domain):
        return "email_domain_is_job_board"
    if is_suspicious_contact_domain(normalized_domain):
        return "email_domain_is_suspicious"
    if lookup_domain and not _same_company_domain(normalized_domain, lookup_domain):
        return "email_domain_not_matching_lookup_domain"
    if (
        not lookup_domain
        and lookup_company
        and not _email_domain_matches_company(normalized_domain, lookup_company)
    ):
        return "email_domain_not_related_to_company"
    return None


