"""Contact provider public API."""

from __future__ import annotations

import requests

from smartapply.contacts.domain_classifier import (
    classify_application_domain,
    contact_lookup_key,
    domain_from_url,
    is_company_domain,
    is_job_board_domain,
    is_known_domain,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
    normalize_company_name,
    normalize_domain,
)
from smartapply.contacts.domain_rules import (
    APPLICATION_REDIRECT_DOMAINS,
    ATS_DOMAINS,
    NON_COMPANY_CONTACT_DOMAINS,
    PARTNER_JOB_BOARD_DOMAINS,
    SUSPECT_CONTACT_DOMAIN_MARKERS,
)
from smartapply.contacts.models import ContactCandidate
from smartapply.contacts.providers.anymailfinder import AnymailFinderContactProvider
from smartapply.contacts.providers.base import ContactProvider
from smartapply.contacts.providers.chain import ContactProviderChain, default_contact_chain
from smartapply.contacts.validation import (
    BLOCKED_PREFIXES,
    PREFIX_SCORES,
    is_recruitment_generic_email,
    score_email,
)

__all__ = [
    "APPLICATION_REDIRECT_DOMAINS",
    "ATS_DOMAINS",
    "AnymailFinderContactProvider",
    "BLOCKED_PREFIXES",
    "ContactCandidate",
    "ContactProvider",
    "ContactProviderChain",
    "NON_COMPANY_CONTACT_DOMAINS",
    "PARTNER_JOB_BOARD_DOMAINS",
    "PREFIX_SCORES",
    "SUSPECT_CONTACT_DOMAIN_MARKERS",
    "classify_application_domain",
    "contact_lookup_key",
    "default_contact_chain",
    "domain_from_url",
    "is_company_domain",
    "is_job_board_domain",
    "is_known_domain",
    "is_recruitment_generic_email",
    "is_reliable_company_domain",
    "is_suspicious_contact_domain",
    "normalize_company_name",
    "normalize_domain",
    "requests",
    "score_email",
]
