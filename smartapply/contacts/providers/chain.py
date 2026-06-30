"""Contact provider chain orchestration."""

from __future__ import annotations

from smartapply.config import get_settings
from smartapply.contacts.models import ContactCandidate
from smartapply.contacts.providers.anymailfinder import AnymailFinderContactProvider
from smartapply.contacts.providers.base import ContactProvider
from smartapply.contacts.validation import _dedupe_rank


class ContactProviderChain:
    def __init__(self, providers: list[ContactProvider], min_confidence: float = 0.60):
        self.providers = providers
        self.min_confidence = min_confidence

    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        candidates: list[ContactCandidate] = []
        for provider in self.providers:
            if provider.is_available():
                candidates.extend(
                    provider.find(
                        company=company,
                        application_url=application_url,
                        job_location=job_location,
                    )
                )
        return [c for c in _dedupe_rank(candidates) if c.confidence >= self.min_confidence]

    def best(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> ContactCandidate | None:
        contacts = self.find(
            company=company,
            application_url=application_url,
            job_location=job_location,
        )
        return contacts[0] if contacts else None

    def verify_email(self, email: str) -> bool | None:
        for provider in self.providers:
            verifier = getattr(provider, "verify_email", None)
            if provider.is_available() and callable(verifier):
                result = verifier(email)
                if result is not None:
                    return bool(result)
        return None

    def decision_maker_search(
        self,
        *,
        domain: str | None = None,
        company_name: str | None = None,
        categories: list[str] | None = None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        candidates: list[ContactCandidate] = []
        for provider in self.providers:
            finder = getattr(provider, "decision_maker_search", None)
            if provider.is_available() and callable(finder):
                candidates.extend(
                    finder(
                        domain=domain,
                        company_name=company_name,
                        categories=categories,
                        job_location=job_location,
                    )
                )
        return [c for c in _dedupe_rank(candidates) if c.confidence >= self.min_confidence]

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
        candidates: list[ContactCandidate] = []
        for provider in self.providers:
            finder = getattr(provider, "person_search", None)
            if provider.is_available() and callable(finder):
                candidates.extend(
                    finder(
                        full_name=full_name,
                        first_name=first_name,
                        last_name=last_name,
                        linkedin_url=linkedin_url,
                        domain=domain,
                        company_name=company_name,
                        job_location=job_location,
                    )
                )
        return [c for c in _dedupe_rank(candidates) if c.confidence >= self.min_confidence]

    @property
    def provider_key(self) -> str:
        return ",".join(provider.name for provider in self.providers) or "none"


def default_contact_chain() -> ContactProviderChain:
    settings = get_settings()
    providers: list[ContactProvider] = []
    anymailfinder = AnymailFinderContactProvider()
    if anymailfinder.is_available():
        providers.append(anymailfinder)
    return ContactProviderChain(
        providers=providers,
        min_confidence=settings.autopilot_contact_min_confidence,
    )
