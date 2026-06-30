"""Contact lookup with persistent cache."""

from __future__ import annotations

from smartapply.config import get_settings
from smartapply.contacts.cache import ContactCacheMixin
from smartapply.contacts.company import normalize_domain_like
from smartapply.contacts.domain_candidates import domains_visible_in_text
from smartapply.contacts.lookup_strategy import resolve_contact_lookup_strategy
from smartapply.contacts.models import ContactLookupDecision
from smartapply.contacts.providers import ContactProviderChain
from smartapply.contacts.search import ContactSearchMixin


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
