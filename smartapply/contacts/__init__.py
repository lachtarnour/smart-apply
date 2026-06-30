"""Contact discovery, validation, strategy and caching."""

from smartapply.contacts.company import normalize_domain_like
from smartapply.contacts.domain_candidates import domains_visible_in_text
from smartapply.contacts.domain_classifier import (
    classify_application_domain,
    contact_lookup_key,
    domain_from_url,
    is_company_domain,
    is_job_board_domain,
    is_known_domain,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
)
from smartapply.contacts.lookup_strategy import resolve_contact_lookup_strategy
from smartapply.contacts.models import ContactCandidate, ContactLookupDecision
from smartapply.contacts.providers import (
    AnymailFinderContactProvider,
    ContactProvider,
    ContactProviderChain,
    default_contact_chain,
    is_recruitment_generic_email,
    score_email,
)
from smartapply.contacts.service import ContactService

__all__ = [
    "AnymailFinderContactProvider",
    "ContactCandidate",
    "ContactLookupDecision",
    "ContactProvider",
    "ContactProviderChain",
    "ContactService",
    "classify_application_domain",
    "contact_lookup_key",
    "default_contact_chain",
    "domain_from_url",
    "domains_visible_in_text",
    "is_company_domain",
    "is_job_board_domain",
    "is_known_domain",
    "is_recruitment_generic_email",
    "is_reliable_company_domain",
    "is_suspicious_contact_domain",
    "normalize_domain_like",
    "resolve_contact_lookup_strategy",
    "score_email",
]
