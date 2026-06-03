"""Email agent: write, find contact, export .eml or Gmail draft."""

from smartapply.email_agent.contact_finder import (
    ContactFinder,
    FoundContact,
    score_email,
)
from smartapply.email_agent.contact_providers import (
    ContactCandidate,
    ContactProvider,
    ContactProviderChain,
    SnovContactProvider,
    contact_lookup_key,
    default_contact_chain,
    domain_from_url,
)
from smartapply.email_agent.eml_export import export_eml
from smartapply.email_agent.gmail_draft import GmailDraftError, create_draft
from smartapply.email_agent.template import build_application_email
from smartapply.email_agent.writer import EmailWriter

__all__ = [
    "ContactFinder",
    "ContactCandidate",
    "ContactProvider",
    "ContactProviderChain",
    "EmailWriter",
    "FoundContact",
    "GmailDraftError",
    "SnovContactProvider",
    "build_application_email",
    "contact_lookup_key",
    "create_draft",
    "default_contact_chain",
    "domain_from_url",
    "export_eml",
    "score_email",
]
