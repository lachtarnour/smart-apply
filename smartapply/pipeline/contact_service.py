"""Contact lookup with persistent cache.

External contact providers (Anymail Finder, future ones) are expensive — we cache
both hits AND misses so a follow-up run on the same company doesn't burn
a quota. Local ``contacts`` table is checked first (manual entries from
the user), then the cache, finally the live provider chain.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
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
    is_job_board_domain,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
    score_email,
)
from smartapply.logging_setup import get_logger
from smartapply.utils.location import canonical_french_city, french_city_mismatch

logger = get_logger(__name__)

GENERIC_COMPANY_NAMES = {
    "",
    "anonyme",
    "apec",
    "confidentiel",
    "entreprise confidentielle",
    "entreprise non communiquee",
    "entreprise non communiquée",
    "france travail",
    "hellowork",
    "indeed",
    "linkedin",
    "non communique",
    "non communiquée",
    "unknown",
    "welcome to the jungle",
    "welcometothejungle",
    "wttj",
}

DOMAIN_TLDS_RE = (
    r"fr|com|io|ai|co|org|net|eu|dev|tech|jobs|careers|health|"
    r"consulting|cloud|app|software|digital|uk|de|es|it"
)


@dataclass(frozen=True)
class ContactLookupDecision:
    lookup_company: str | None
    lookup_application_url: str | None
    lookup_domain: str | None
    lookup_location: str | None
    strategy: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candidate_domains: list[str] = field(default_factory=list)
    rejected_domains: list[str] = field(default_factory=list)


def _ascii_lower(text: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _clean_company_name(company: str | None) -> str:
    return " ".join((company or "").strip().split())


def _is_generic_company_name(company: str | None) -> bool:
    cleaned = _clean_company_name(company)
    if not cleaned:
        return True
    norm = _ascii_lower(cleaned)
    if norm in GENERIC_COMPANY_NAMES:
        return True
    domain_like = domain_from_url(f"https://{cleaned}") if "." in cleaned else None
    return bool(domain_like and is_job_board_domain(domain_like))


def _analysis_value(analysis: Any | None, key: str) -> str:
    if analysis is None:
        return ""
    value = analysis.get(key) if isinstance(analysis, Mapping) else getattr(analysis, key, None)
    return str(value or "").strip()


def _normalize_domain_candidate(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    if not candidate:
        return None
    candidate = candidate.removeprefix("mailto:")
    if "@" in candidate and "://" not in candidate:
        candidate = candidate.rsplit("@", 1)[-1]
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9](?:/.*)?", candidate) and (
        "://" not in candidate
    ):
        return None
    url = candidate if "://" in candidate else f"https://{candidate}"
    domain = domain_from_url(url)
    if not domain or not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", domain):
        return None
    return domain


def _unique_domains(domains: list[str | None]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for domain in domains:
        normalized = _normalize_domain_candidate(domain)
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def domains_visible_in_text(text: str | None) -> list[str]:
    """Extract literal email/URL/domain signals visible in the offer body."""
    body = text or ""
    domains: list[str | None] = []
    domains.extend(re.findall(r"[\w.+-]+@([\w.-]+\.[a-zA-Z]{2,})", body))
    domains.extend(
        re.findall(
            r"\bhttps?://(?:www\.)?([\w.-]+\.[a-zA-Z]{2,})(?:[/?#:]|\b)",
            body,
        )
    )
    domains.extend(
        re.findall(r"\bwww\.([\w.-]+\.[a-zA-Z]{2,})(?:[/?#:]|\b)", body)
    )
    domains.extend(
        re.findall(
            rf"(?<![\w@.-])([a-zA-Z0-9][a-zA-Z0-9-]{{1,63}}"
            rf"(?:\.[a-zA-Z0-9-]{{2,63}})?\.(?:{DOMAIN_TLDS_RE}))(?![\w-])",
            body,
        )
    )
    return _unique_domains(domains)


def _domain_is_usable(domain: str | None) -> tuple[bool, str]:
    if not domain:
        return False, "domain_invalid"
    if is_job_board_domain(domain):
        return False, "domain_is_job_board"
    if is_suspicious_contact_domain(domain):
        return False, "domain_looks_like_recruitment_platform"
    if not is_reliable_company_domain(domain):
        return False, "domain_not_reliable_company_domain"
    return True, "domain_reliable"


def _domain_confirmed_by_sources(
    domain: str,
    *,
    body_domains: list[str],
    application_domain: str | None,
) -> bool:
    return domain in body_domains or (
        bool(application_domain)
        and domain == application_domain
        and is_reliable_company_domain(application_domain)
    )


def _best_lookup_company(
    job_company: str,
    extracted_company_name: str,
) -> tuple[str | None, str | None]:
    cleaned_job_company = _clean_company_name(job_company)
    cleaned_extracted = _clean_company_name(extracted_company_name)
    if not _is_generic_company_name(cleaned_job_company):
        return cleaned_job_company, None
    if cleaned_extracted and not _is_generic_company_name(cleaned_extracted):
        return cleaned_extracted, "company_name_from_extracted_company"
    return None, "manual_review_no_reliable_company"


def _domain_url(domain: str) -> str:
    return f"https://{domain}"


def resolve_contact_lookup_strategy(
    *,
    job_company: str,
    job_application_url: str | None,
    job_description: str | None,
    analysis: Any | None,
    job_location: str | None,
) -> ContactLookupDecision:
    """Choose the safest lookup strategy before calling a contact provider."""
    reasons: list[str] = []
    warnings: list[str] = []
    rejected_domains: list[str] = []
    body_domains = domains_visible_in_text(job_description)
    candidate_domains = list(body_domains)
    application_domain = domain_from_url(job_application_url)
    if application_domain:
        candidate_domains.append(application_domain)

    llm_hint_raw = _analysis_value(analysis, "contact_domain_hint")
    llm_hint_kind = _analysis_value(analysis, "contact_domain_kind") or "unknown"
    llm_hint_domain = _normalize_domain_candidate(llm_hint_raw)
    if llm_hint_domain:
        candidate_domains.append(llm_hint_domain)

    extracted_company = _analysis_value(analysis, "extracted_company_name")
    extracted_location = _analysis_value(analysis, "extracted_location")
    lookup_location = extracted_location or job_location
    lookup_company, company_fallback_strategy = _best_lookup_company(
        job_company,
        extracted_company,
    )

    if llm_hint_raw:
        if llm_hint_kind != "company_domain":
            warnings.append("llm_domain_hint_ignored_kind_not_company_domain")
        elif not llm_hint_domain:
            warnings.append("llm_domain_hint_invalid")
            rejected_domains.append(llm_hint_raw)
        else:
            usable, warning = _domain_is_usable(llm_hint_domain)
            if not usable:
                warnings.append(f"llm_{warning}")
                rejected_domains.append(llm_hint_domain)
            elif not _domain_confirmed_by_sources(
                llm_hint_domain,
                body_domains=body_domains,
                application_domain=application_domain,
            ):
                warnings.append("llm_domain_hint_not_visible")
                rejected_domains.append(llm_hint_domain)
            else:
                reasons.append("validated_llm_domain_hint_visible_locally")
                return ContactLookupDecision(
                    lookup_company=lookup_company or _clean_company_name(job_company) or None,
                    lookup_application_url=_domain_url(llm_hint_domain),
                    lookup_domain=llm_hint_domain,
                    lookup_location=lookup_location,
                    strategy="domain_from_llm_hint_validated",
                    confidence=0.92,
                    reasons=reasons,
                    warnings=warnings,
                    candidate_domains=_unique_domains(candidate_domains),
                    rejected_domains=_unique_domains(rejected_domains),
                )

    reliable_body_domains: list[str] = []
    for domain in body_domains:
        usable, warning = _domain_is_usable(domain)
        if usable:
            reliable_body_domains.append(domain)
        else:
            warnings.append(f"offer_body_{warning}:{domain}")
            rejected_domains.append(domain)

    if reliable_body_domains:
        body_domain = reliable_body_domains[0]
        if (
            application_domain
            and application_domain != body_domain
            and is_reliable_company_domain(application_domain)
        ):
            warnings.append("application_domain_conflicts_with_offer_body_domain")
            return ContactLookupDecision(
                lookup_company=lookup_company,
                lookup_application_url=None,
                lookup_domain=None,
                lookup_location=lookup_location,
                strategy="manual_review_domain_conflict",
                confidence=0.2,
                reasons=["conflicting_reliable_domains"],
                warnings=warnings,
                candidate_domains=_unique_domains(candidate_domains),
                rejected_domains=_unique_domains(rejected_domains),
            )
        reasons.append("company_domain_visible_in_offer_body")
        return ContactLookupDecision(
            lookup_company=lookup_company or _clean_company_name(job_company) or None,
            lookup_application_url=_domain_url(body_domain),
            lookup_domain=body_domain,
            lookup_location=lookup_location,
            strategy="domain_from_offer_body",
            confidence=0.9,
            reasons=reasons,
            warnings=warnings,
            candidate_domains=_unique_domains(candidate_domains),
            rejected_domains=_unique_domains(rejected_domains),
        )

    if application_domain:
        usable, warning = _domain_is_usable(application_domain)
        if usable:
            if llm_hint_domain and llm_hint_domain != application_domain:
                warnings.append("llm_domain_hint_conflicts_with_application_domain")
                rejected_domains.append(llm_hint_domain)
            reasons.append("application_url_host_is_reliable_company_domain")
            return ContactLookupDecision(
                lookup_company=lookup_company or _clean_company_name(job_company) or None,
                lookup_application_url=job_application_url,
                lookup_domain=application_domain,
                lookup_location=lookup_location,
                strategy="domain_from_company_url",
                confidence=0.82,
                reasons=reasons,
                warnings=warnings,
                candidate_domains=_unique_domains(candidate_domains),
                rejected_domains=_unique_domains(rejected_domains),
            )
        warnings.append(f"application_{warning}:{application_domain}")
        rejected_domains.append(application_domain)

    if lookup_company:
        strategy = company_fallback_strategy or "company_name_fallback"
        reasons.append("no_reliable_domain_using_company_name")
        return ContactLookupDecision(
            lookup_company=lookup_company,
            lookup_application_url=None,
            lookup_domain=None,
            lookup_location=lookup_location,
            strategy=strategy,
            confidence=0.62 if strategy == "company_name_fallback" else 0.68,
            reasons=reasons,
            warnings=warnings,
            candidate_domains=_unique_domains(candidate_domains),
            rejected_domains=_unique_domains(rejected_domains),
        )

    warnings.append("no_reliable_company_name_for_contact_lookup")
    return ContactLookupDecision(
        lookup_company=None,
        lookup_application_url=None,
        lookup_domain=None,
        lookup_location=lookup_location,
        strategy="manual_review_no_reliable_company",
        confidence=0.0,
        reasons=["no_reliable_domain_or_company_name"],
        warnings=warnings,
        candidate_domains=_unique_domains(candidate_domains),
        rejected_domains=_unique_domains(rejected_domains),
    )


class ContactService:
    """Encapsulates contact discovery with multi-level caching."""

    def __init__(self, chain: ContactProviderChain):
        self.chain = chain
        self.settings = get_settings()
        self.last_lookup_decision: ContactLookupDecision | None = None

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
                    return self._from_cache_payload(cached.contacts)

        contacts = self.chain.find(
            company=lookup_company,
            application_url=contact_url,
            job_location=lookup_location,
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
        job_description: str | None = None,
        company: str = "",
    ) -> str | None:
        """Pick the best URL to pass to the contact provider.

        Kept for compatibility with older call sites/tests. The actual service
        now uses ``resolve_contact_lookup_strategy`` so LLM hints are never used
        unless locally validated.
        """
        decision = resolve_contact_lookup_strategy(
            job_company=company,
            job_application_url=application_url,
            job_description=job_description,
            analysis={
                "contact_domain_hint": contact_domain_hint,
                "contact_domain_kind": contact_domain_kind,
            },
            job_location=None,
        )
        return decision.lookup_application_url

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
