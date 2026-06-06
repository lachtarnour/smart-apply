"""Contact lookup with persistent cache."""

from __future__ import annotations

from smartapply.config import get_settings
from smartapply.email_agent import ContactProviderChain
from smartapply.pipeline.contact.cache import ContactCacheMixin
from smartapply.pipeline.contact.scorer import (
    ContactLookupDecision,
    domains_visible_in_text,
    normalize_domain_like,
    resolve_contact_lookup_strategy,
)
from smartapply.pipeline.contact.search import ContactSearchMixin


class ContactService(ContactSearchMixin, ContactCacheMixin):
    """Encapsulates contact discovery with multi-level caching."""

    def __init__(self, chain: ContactProviderChain):
        self.chain = chain
        self.settings = get_settings()
        self.last_lookup_decision: ContactLookupDecision | None = None


__all__ = [
    "ContactLookupDecision",
    "ContactService",
    "domains_visible_in_text",
    "normalize_domain_like",
    "resolve_contact_lookup_strategy",
]
