"""Anymail Finder contact lookup provider."""

from __future__ import annotations

import requests

from smartapply.config import get_settings
from smartapply.contacts.domain_classifier import (
    domain_from_url,
    is_reliable_company_domain,
    normalize_domain,
)
from smartapply.contacts.models import ContactCandidate
from smartapply.contacts.providers.base import ContactProvider
from smartapply.contacts.validation import (
    _dedupe_rank,
    is_recruitment_generic_email,
    score_email,
)
from smartapply.logging_setup import get_logger
from smartapply.utils.location import canonical_french_city, french_city_mismatch

logger = get_logger(__name__)


class AnymailFinderContactProvider(ContactProvider):
    name = "anymailfinder"

    DECISION_MAKER_URL = "https://api.anymailfinder.com/v5.1/find-email/decision-maker"
    COMPANY_URL = "https://api.anymailfinder.com/v5.1/find-email/company"
    PERSON_URL = "https://api.anymailfinder.com/v5.1/find-email/person"
    VERIFY_URL = "https://api.anymailfinder.com/v5.1/verify-email"

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int | None = None,
    ):
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.anymailfinder_api_key
        self.max_contacts = settings.anymailfinder_max_contacts
        self.company_email_type = settings.anymailfinder_company_email_type
        self.decision_maker_categories = [
            category.strip()
            for category in settings.anymailfinder_decision_maker_categories.split(",")
            if category.strip()
        ]
        self.timeout = timeout or settings.anymailfinder_timeout

    def is_available(self) -> bool:
        return bool(self.api_key)

    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        if not self.is_available():
            return []

        lookup = self._lookup_payload(company=company, application_url=application_url)
        if lookup is None:
            return []

        candidates = self._company_email_contacts(lookup)
        if any(is_recruitment_generic_email(candidate.email) for candidate in candidates):
            return _dedupe_rank(candidates)[: self.max_contacts]

        candidates.extend(self._decision_maker_contacts(lookup, job_location=job_location))

        return _dedupe_rank(candidates)[: self.max_contacts]

    def _lookup_payload(
        self,
        *,
        company: str,
        application_url: str | None,
    ) -> dict[str, str] | None:
        domain = domain_from_url(application_url)
        if is_reliable_company_domain(domain):
            return {"domain": domain}
        company = " ".join((company or "").split())
        if company:
            return {"company_name": company}
        return None

    def decision_maker_search(
        self,
        *,
        domain: str | None = None,
        company_name: str | None = None,
        categories: list[str] | None = None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        """Run an explicit Anymail Finder decision-maker lookup."""
        if not self.is_available():
            return []
        lookup = self._explicit_lookup_payload(domain=domain, company_name=company_name)
        if lookup is None:
            return []
        return _dedupe_rank(
            self._decision_maker_contacts(
                lookup,
                job_location=job_location,
                categories=categories,
            )
        )[: self.max_contacts]

    def person_search(
        self,
        *,
        full_name: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        linkedin_url: str | None = None,
        domain: str | None = None,
        company_name: str | None = None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        """Run an explicit Anymail Finder person lookup."""
        if not self.is_available():
            return []

        payload: dict[str, str] = {}
        linkedin_url = " ".join((linkedin_url or "").split())
        if linkedin_url:
            payload["linkedin_url"] = linkedin_url

        full_name = " ".join((full_name or "").split())
        first_name = " ".join((first_name or "").split())
        last_name = " ".join((last_name or "").split())
        has_person_name = bool(full_name or (first_name and last_name))
        if full_name:
            payload["full_name"] = full_name
        elif first_name and last_name:
            payload["first_name"] = first_name
            payload["last_name"] = last_name

        lookup = self._explicit_lookup_payload(
            domain=domain,
            company_name=company_name,
        )
        if lookup is not None:
            payload.update(lookup)

        if not linkedin_url and (not has_person_name or lookup is None):
            return []

        try:
            data = self._post(self.PERSON_URL, payload)
        except requests.RequestException as e:
            logger.warning("Anymail Finder person lookup failed for %s: %s", payload, e)
            return []

        email = (data.get("valid_email") or data.get("email") or "").lower()
        if not email:
            return []

        full_name = data.get("person_full_name") or payload.get("full_name") or None
        if not full_name and payload.get("first_name") and payload.get("last_name"):
            full_name = f"{payload['first_name']} {payload['last_name']}"
        job_title = data.get("person_job_title") or None
        location_hint = self._location_hint(job_location, full_name, job_title)
        confidence = 0.97 if payload.get("domain") else 0.93
        decision_reason = "person_lookup"
        if location_hint == "location_mismatch":
            confidence *= 0.45
            decision_reason = "person_lookup:location_mismatch"
        return [
            ContactCandidate(
                email=email,
                source_url=self._source_url(payload, "person"),
                confidence=confidence,
                provider=self.name,
                verified=True,
                kind="anymailfinder_person",
                full_name=full_name,
                job_title=job_title,
                location_hint=location_hint,
                decision_reason=decision_reason,
            )
        ]

    @classmethod
    def _explicit_lookup_payload(
        cls,
        *,
        domain: str | None,
        company_name: str | None,
    ) -> dict[str, str] | None:
        normalized_domain = cls._manual_domain(domain)
        if normalized_domain:
            return {"domain": normalized_domain}
        company_name = " ".join((company_name or "").split())
        if company_name:
            return {"company_name": company_name}
        return None

    @staticmethod
    def _manual_domain(domain: str | None) -> str:
        value = str(domain or "").strip()
        if not value:
            return ""
        parsed = domain_from_url(value if "://" in value else f"https://{value}")
        if parsed:
            return parsed
        return normalize_domain(value).split("/", 1)[0].split(":", 1)[0]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self.api_key,
            "Content-Type": "application/json",
        }

    def _post(self, url: str, payload: dict) -> dict:
        response = requests.post(
            url,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def verify_email(self, email: str) -> bool | None:
        """Return True/False for a verification result, None when unavailable."""
        if not self.is_available():
            return None
        try:
            data = self._post(self.VERIFY_URL, {"email": email})
        except requests.RequestException as e:
            logger.warning("Anymail Finder email verification failed for %s: %s", email, e)
            return None
        status = data.get("email_status")
        if status == "valid":
            return True
        if status in {"risky", "invalid"}:
            return False
        return None

    def _decision_maker_contacts(
        self,
        lookup: dict[str, str],
        *,
        job_location: str | None = None,
        categories: list[str] | None = None,
    ) -> list[ContactCandidate]:
        configured_categories = self.decision_maker_categories if categories is None else categories
        decision_maker_categories = self._clean_categories(configured_categories)
        if not decision_maker_categories:
            return []

        payload = {
            **lookup,
            "decision_maker_category": decision_maker_categories,
        }
        try:
            data = self._post(self.DECISION_MAKER_URL, payload)
        except requests.RequestException as e:
            logger.warning("Anymail Finder decision-maker lookup failed for %s: %s", lookup, e)
            return []
        email = (data.get("valid_email") or "").lower()
        if not email:
            return []

        category = data.get("decision_maker_category") or ""
        confidence = {
            "hr": 0.96,
            "engineering": 0.88,
            "it": 0.82,
            "operations": 0.78,
            "ceo": 0.72,
        }.get(category, 0.80)
        full_name = data.get("person_full_name") or None
        job_title = data.get("person_job_title") or None
        location_hint = self._location_hint(job_location, full_name, job_title)
        decision_reason = f"decision_maker:{category or 'unknown'}"
        if location_hint == "location_mismatch":
            confidence *= 0.45
            decision_reason = f"{decision_reason}:location_mismatch"
        return [
            ContactCandidate(
                email=email,
                source_url=self._source_url(lookup, "decision-maker"),
                confidence=confidence,
                provider=self.name,
                verified=True,
                kind="anymailfinder_decision_maker",
                full_name=full_name,
                job_title=job_title,
                location_hint=location_hint,
                decision_reason=decision_reason,
            )
        ]

    def _company_email_contacts(self, lookup: dict[str, str]) -> list[ContactCandidate]:
        payload = {
            **lookup,
            "email_type": self.company_email_type,
        }
        try:
            data = self._post(self.COMPANY_URL, payload)
        except requests.RequestException as e:
            logger.warning("Anymail Finder company lookup failed for %s: %s", lookup, e)
            return []
        emails = data.get("valid_emails") or []
        candidates: list[ContactCandidate] = []
        for email in emails:
            email = (email or "").lower()
            role_score = score_email(email)
            if not email or role_score <= 0:
                continue
            candidates.append(
                ContactCandidate(
                    email=email,
                    source_url=self._source_url(lookup, "company"),
                    confidence=max(0.55, role_score),
                    provider=self.name,
                    verified=True,
                    kind="anymailfinder_company",
                    decision_reason=(
                        "generic_recruitment_email"
                        if is_recruitment_generic_email(email)
                        else "generic_company_email"
                    ),
                )
            )
        return candidates

    @staticmethod
    def _source_url(lookup: dict[str, str], endpoint: str) -> str:
        value = lookup.get("domain") or lookup.get("company_name") or "unknown"
        return f"anymailfinder:{endpoint}:{value}"

    @staticmethod
    def _location_hint(
        job_location: str | None,
        full_name: str | None,
        job_title: str | None,
    ) -> str | None:
        observed_text = " ".join(part for part in (full_name, job_title) if part)
        if french_city_mismatch(job_location, observed_text):
            return "location_mismatch"
        return canonical_french_city(observed_text)

    @staticmethod
    def _clean_categories(categories: list[str] | None) -> list[str]:
        return [category.strip() for category in categories or [] if category.strip()]
