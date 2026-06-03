"""Contact lookup with persistent cache.

External contact providers (Snov, future ones) are expensive — we cache
both hits AND misses so a follow-up run on the same company doesn't burn
a quota. Local ``contacts`` table is checked first (manual entries from
the user), then the cache, finally the live provider chain.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.repository import (
    find_contacts_for,
    get_contact_lookup_cache,
    upsert_contact_lookup_cache,
)
from smartapply.email_agent import (
    ContactCandidate,
    ContactProviderChain,
    contact_lookup_key,
    domain_from_url,
)


class ContactService:
    """Encapsulates contact discovery with multi-level caching."""

    def __init__(self, chain: ContactProviderChain):
        self.chain = chain
        self.settings = get_settings()

    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        contact_domain_hint: str = "",
        contact_domain_kind: str = "unknown",
    ) -> ContactCandidate | None:
        """Find a contact once per company/domain and reuse cached outcomes."""
        provider_key = self.chain.provider_key
        contact_url = self._contact_lookup_url(
            application_url=application_url,
            contact_domain_hint=contact_domain_hint,
            contact_domain_kind=contact_domain_kind,
        )
        lookup_key = contact_lookup_key(company, contact_url)
        domain = domain_from_url(contact_url)

        stored = self._from_local_db(company)
        if stored is not None:
            return stored

        if provider_key == "none":
            return None

        if self.settings.contact_cache_enabled:
            with session_scope() as s:
                cached = get_contact_lookup_cache(
                    s,
                    provider_key=provider_key,
                    lookup_key=lookup_key,
                )
                if cached is not None:
                    return self._from_cache_payload(cached.contacts)

        contacts = self.chain.find(company=company, application_url=contact_url)
        best = contacts[0] if contacts else None

        if self.settings.contact_cache_enabled:
            ttl_days = (
                self.settings.contact_cache_ttl_days
                if contacts
                else self.settings.contact_cache_negative_ttl_days
            )
            expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)
            with session_scope() as s:
                upsert_contact_lookup_cache(
                    s,
                    provider_key=provider_key,
                    lookup_key=lookup_key,
                    company=company,
                    domain=domain,
                    application_url=contact_url,
                    status="hit" if contacts else "miss",
                    contacts=[self._to_cache_payload(c) for c in contacts],
                    expires_at=expires_at,
                )

        return best

    # -------------------- helpers --------------------

    @staticmethod
    def _contact_lookup_url(
        *,
        application_url: str | None,
        contact_domain_hint: str = "",
        contact_domain_kind: str = "unknown",
    ) -> str | None:
        """Pick the best URL to pass to the contact provider.

        Priority:
        1. The LLM extracted a company-owned domain from the offer text
           (``contact_domain_hint``) → use it, regardless of how the LLM
           classified the application URL.
        2. The application URL is an ATS / job board → return ``None`` so
           the provider falls back to name-based domain resolution using
           ``Job.company``. We deliberately do NOT pass the ATS URL: it
           would lead Snov to scrape Greenhouse / LinkedIn employees, not
           the hiring company's.
        3. Otherwise → use the application URL.
        """
        hint = (contact_domain_hint or "").strip().lower()
        if hint and "://" not in hint:
            hint = f"https://{hint}"
        if hint:
            return hint
        if contact_domain_kind == "ats_or_job_board":
            return None
        return application_url

    @staticmethod
    def _to_cache_payload(contact: ContactCandidate) -> dict[str, Any]:
        return {
            "email": contact.email,
            "source_url": contact.source_url,
            "confidence": contact.confidence,
            "provider": contact.provider,
            "verified": contact.verified,
            "kind": contact.kind,
            "form_url": contact.form_url,
        }

    @staticmethod
    def _from_cache_payload(payload: Any | None) -> ContactCandidate | None:
        if not payload:
            return None
        first = payload[0] if isinstance(payload, list) else payload
        if not isinstance(first, dict):
            return None
        provider = first.get("provider") or "contact"
        return ContactCandidate(
            email=first.get("email") or "",
            source_url=first.get("source_url") or "contact_cache",
            confidence=float(first.get("confidence") or 0.0),
            provider=f"{provider}_cache",
            verified=bool(first.get("verified")),
            kind=first.get("kind") or "cached",
            form_url=first.get("form_url"),
        )

    @staticmethod
    def _row_to_candidate(contact) -> ContactCandidate:
        return ContactCandidate(
            email=contact.email,
            source_url=contact.source_url or "contacts_table",
            confidence=contact.confidence,
            provider="db_cache",
            verified=True,
            kind="cached_contact",
        )

    def _from_local_db(self, company: str) -> ContactCandidate | None:
        with session_scope() as s:
            contacts = find_contacts_for(s, company)
            return self._row_to_candidate(contacts[0]) if contacts else None
