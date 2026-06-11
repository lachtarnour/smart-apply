"""Contact provider search chain helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from smartapply.database import session_scope
from smartapply.database.repository import get_contact_lookup_cache, upsert_contact_lookup_cache
from smartapply.email_agent import ContactCandidate, contact_lookup_key, domain_from_url
from smartapply.logging_setup import get_logger
from smartapply.pipeline.contact.scorer import (
    _external_contact_quality_issue,
    resolve_contact_lookup_strategy,
)

logger = get_logger(__name__)


class ContactSearchMixin:
    """Run contact lookup through local cache, provider cache and live providers."""

    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        contact_domain_hint: str = "",
        contact_domain_kind: str = "unknown",
        job_description: str | None = None,
        analysis: Any | None = None,
        job_location: str | None = None,
        source_data: Any | None = None,
    ) -> ContactCandidate | None:
        """Find a contact once per company/domain and reuse cached outcomes."""
        provider_key = self.chain.provider_key
        analysis_for_decision = analysis or {
            "contact_domain_hint": contact_domain_hint,
            "contact_domain_kind": contact_domain_kind,
        }
        decision = resolve_contact_lookup_strategy(
            job_company=company,
            job_application_url=application_url,
            job_description=job_description,
            analysis=analysis_for_decision,
            job_location=job_location,
            source_data=source_data,
        )
        self.last_lookup_decision = decision
        logger.info(
            "contact_lookup_decision strategy=%s domain=%s company=%s warnings=%s",
            decision.strategy,
            decision.lookup_domain,
            decision.lookup_company,
            ",".join(decision.warnings),
        )
        if decision.strategy.startswith("manual_review"):
            return None

        lookup_company = decision.lookup_company or ""
        contact_url = decision.lookup_application_url
        lookup_location = decision.lookup_location
        lookup_key = self._location_scoped_lookup_key(
            contact_lookup_key(lookup_company, contact_url),
            lookup_location,
        )
        domain = decision.lookup_domain or domain_from_url(contact_url)

        if lookup_company:
            stored = self._from_local_db(lookup_company, job_location=lookup_location)
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
                    cached_contact = self._from_cache_payload(cached.contacts)
                    if cached_contact is None:
                        return None
                    if _external_contact_quality_issue(
                        cached_contact,
                        lookup_company=lookup_company,
                        lookup_domain=domain,
                    ):
                        return None
                    return cached_contact

        contacts = self.chain.find(
            company=lookup_company,
            application_url=contact_url,
            job_location=lookup_location,
        )
        contacts = self._filter_external_contacts(
            contacts,
            lookup_company=lookup_company,
            lookup_domain=domain,
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
                    company=lookup_company,
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

    @staticmethod
    def _filter_external_contacts(
        contacts: list[ContactCandidate],
        *,
        lookup_company: str | None,
        lookup_domain: str | None,
    ) -> list[ContactCandidate]:
        kept: list[ContactCandidate] = []
        for contact in contacts:
            issue = _external_contact_quality_issue(
                contact,
                lookup_company=lookup_company,
                lookup_domain=lookup_domain,
            )
            if issue:
                logger.info(
                    "contact_rejected_quality email=%s company=%s domain=%s issue=%s",
                    contact.email,
                    lookup_company,
                    lookup_domain,
                    issue,
                )
                continue
            kept.append(contact)
        return kept

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
