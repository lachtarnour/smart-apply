"""Email agent: contact discovery, deterministic email template, .eml and Gmail draft."""

from smartapply.email_agent.contact_providers import (
    AnymailFinderContactProvider,
    ContactCandidate,
    ContactProvider,
    ContactProviderChain,
    contact_lookup_key,
    default_contact_chain,
    domain_from_url,
    is_company_domain,
    is_job_board_domain,
    is_recruitment_generic_email,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
    score_email,
)
from smartapply.email_agent.eml_export import export_eml
from smartapply.email_agent.gmail_draft import GmailDraftError, create_draft
from smartapply.email_agent.template import build_application_email

__all__ = [
    "AnymailFinderContactProvider",
    "ContactCandidate",
    "ContactProvider",
    "ContactProviderChain",
    "GmailDraftError",
    "build_application_email",
    "contact_lookup_key",
    "create_draft",
    "default_contact_chain",
    "domain_from_url",
    "export_eml",
    "is_company_domain",
    "is_job_board_domain",
    "is_reliable_company_domain",
    "is_recruitment_generic_email",
    "is_suspicious_contact_domain",
    "score_email",
]
