"""Persistent and local contact cache helpers."""

from __future__ import annotations

from typing import Any

from smartapply.contacts.domain_classifier import domain_from_url, is_company_domain
from smartapply.contacts.models import ContactCandidate
from smartapply.contacts.quality import _external_contact_quality_issue
from smartapply.contacts.validation import score_email
from smartapply.database import session_scope
from smartapply.database.repository import find_contacts_for
from smartapply.utils.location import canonical_french_city, french_city_mismatch


class ContactCacheMixin:
    """Reuse local contacts and provider lookup cache entries safely."""

    @staticmethod
    def _location_scoped_lookup_key(lookup_key: str, job_location: str | None) -> str:
        city = canonical_french_city(job_location)
        return f"{lookup_key}|loc:{city}" if city else lookup_key

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
    def _can_reuse_local_contact(
        contact,
        company: str | None,
        job_location: str | None,
    ) -> bool:
        source = (contact.source_url or "").lower()
        if source == "manual":
            return True
        if ContactCacheMixin._external_contact_uses_blocked_domain(contact):
            return False
        candidate = ContactCacheMixin._row_to_candidate(contact)
        if _external_contact_quality_issue(
            candidate,
            lookup_company=company,
            lookup_domain=None,
        ):
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
                if self._can_reuse_local_contact(contact, company, job_location):
                    return self._row_to_candidate(contact)
            return None
