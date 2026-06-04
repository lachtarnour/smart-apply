"""Contact lookup with persistent cache.

External contact providers (Anymail Finder, future ones) are expensive — we cache
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
    is_company_domain,
    score_email,
)
from smartapply.utils.location import canonical_french_city, french_city_mismatch


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
        job_location: str | None = None,
    ) -> ContactCandidate | None:
        """Find a contact once per company/domain and reuse cached outcomes."""
        provider_key = self.chain.provider_key
        contact_url = self._contact_lookup_url(
            application_url=application_url,
            contact_domain_hint=contact_domain_hint,
            contact_domain_kind=contact_domain_kind,
        )
        lookup_key = self._location_scoped_lookup_key(
            contact_lookup_key(company, contact_url),
            job_location,
        )
        domain = domain_from_url(contact_url)

        stored = self._from_local_db(company, job_location=job_location)
        if stored is not None:
            if not self._stored_contact_passes_optional_verification(stored):
                return None
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

        contacts = self.chain.find(
            company=company,
            application_url=contact_url,
            job_location=job_location,
        )
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

    def verify_email(self, email: str) -> bool | None:
        """Verify an already-known address when configured.

        Returns True/False when a provider can answer, or None when no verifier
        is available. We keep this explicit because Anymail verification spends
        credits and should never happen accidentally.
        """
        return self.chain.verify_email(email)

    def _stored_contact_passes_optional_verification(self, contact: ContactCandidate) -> bool:
        source = (contact.source_url or "").lower()
        if source == "manual":
            enabled = self.settings.anymailfinder_verify_manual_contacts
        elif "anymailfinder:" in source:
            return True
        else:
            enabled = self.settings.anymailfinder_verify_cached_external_contacts
        if not enabled:
            return True
        verified = self.verify_email(contact.email)
        return verified is not False

    @staticmethod
    def _location_scoped_lookup_key(lookup_key: str, job_location: str | None) -> str:
        city = canonical_french_city(job_location)
        return f"{lookup_key}|loc:{city}" if city else lookup_key

    @staticmethod
    def _contact_lookup_url(
        *,
        application_url: str | None,
        contact_domain_hint: str = "",
        contact_domain_kind: str = "unknown",
    ) -> str | None:
        """Pick the best URL to pass to the contact provider.

        Priority:
        1. The LLM extracted a company-owned domain from the offer text and
           classified it as such (``contact_domain_kind=company_domain``) → use it.
        2. The application URL is an ATS / job board → return ``None`` so
           the provider falls back to name-based domain resolution using
           ``Job.company``. We deliberately do NOT pass the ATS URL: it
           would lead the provider to search Greenhouse / LinkedIn employees,
           not the hiring company's.
        3. Otherwise → use the application URL.
        """
        hint = (contact_domain_hint or "").strip().lower()
        if hint and "://" not in hint:
            hint = f"https://{hint}"
        hint_domain = domain_from_url(hint)
        if (
            hint
            and contact_domain_kind == "company_domain"
            and is_company_domain(hint_domain)
        ):
            return hint
        application_domain = domain_from_url(application_url)
        if application_domain and not is_company_domain(application_domain):
            return None
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
            "full_name": contact.full_name,
            "job_title": contact.job_title,
            "location_hint": contact.location_hint,
            "decision_reason": contact.decision_reason,
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
            full_name=first.get("full_name"),
            job_title=first.get("job_title"),
            location_hint=first.get("location_hint"),
            decision_reason=first.get("decision_reason"),
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
            full_name=contact.full_name,
            job_title=getattr(contact, "job_title", None),
            location_hint=getattr(contact, "location_hint", None),
            decision_reason=getattr(contact, "decision_reason", None),
        )

    @staticmethod
    def _can_reuse_local_contact(contact, job_location: str | None) -> bool:
        source = (contact.source_url or "").lower()
        if source == "manual":
            return True
        if ContactService._external_contact_uses_blocked_domain(contact):
            return False
        if "anymailfinder:company" in source:
            return score_email(contact.email) >= 0.6

        observed = " ".join(
            str(part)
            for part in (
                getattr(contact, "location_hint", None),
                getattr(contact, "job_title", None),
                contact.full_name,
            )
            if part
        )
        if observed and french_city_mismatch(job_location, observed):
            return False
        # Personal decision-maker contacts are location-sensitive. If the
        # previous row has no reusable location context, prefer the scoped
        # provider cache/live lookup instead of blindly reusing it.
        if "anymailfinder:decision-maker" in source and job_location:
            return bool(canonical_french_city(observed))
        return True

    @staticmethod
    def _external_contact_uses_blocked_domain(contact) -> bool:
        source = (contact.source_url or "").lower()
        if "anymailfinder:" not in source:
            return False
        domains: list[str] = []
        email = (contact.email or "").lower()
        if "@" in email:
            domains.append(email.rsplit("@", 1)[1])
        source_value = source.rsplit(":", 1)[-1]
        if "." in source_value and " " not in source_value:
            domains.append(source_value)
        for domain in domains:
            normalized = domain_from_url(f"https://{domain}") or domain
            if not is_company_domain(domain) or not is_company_domain(normalized):
                return True
        return False

    def _from_local_db(
        self,
        company: str,
        *,
        job_location: str | None = None,
    ) -> ContactCandidate | None:
        with session_scope() as s:
            contacts = find_contacts_for(s, company)
            for contact in contacts:
                if self._can_reuse_local_contact(contact, job_location):
                    return self._row_to_candidate(contact)
            return None
