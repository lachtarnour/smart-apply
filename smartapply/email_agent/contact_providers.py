"""Snov.io contact lookup for autopilot.

The production path is intentionally small:
- extract a company-owned domain when the job URL has one;
- skip known ATS/job-board domains unless an upstream analysis supplied a hint;
- preflight Snov's free email-count endpoint before paid lookup;
- return only observed provider results, never guessed aliases.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from smartapply.config import get_settings
from smartapply.email_agent.contact_finder import score_email
from smartapply.logging_setup import get_logger

logger = get_logger(__name__)


NON_COMPANY_CONTACT_DOMAINS = {
    "apec.fr",
    "ashbyhq.com",
    "bamboohr.com",
    "francetravail.fr",
    "glassdoor.com",
    "greenhouse.io",
    "hellowork.com",
    "icims.com",
    "indeed.com",
    "jobs.lever.co",
    "lever.co",
    "linkedin.com",
    "monster.com",
    "myworkdayjobs.com",
    "recruitee.com",
    "smartrecruiters.com",
    "taleo.net",
    "teamtailor.com",
    "welcometothejungle.com",
    "workable.com",
    "workdayjobs.com",
}


@dataclass(frozen=True)
class ContactCandidate:
    email: str
    source_url: str
    confidence: float
    provider: str
    verified: bool = False
    kind: str = "snov"
    form_url: str | None = None


def domain_from_url(url: str | None) -> str | None:
    """Return a normalized root-ish domain from an http(s) URL."""
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    host = parsed.netloc.split("@")[-1].split(":")[0].lower().removeprefix("www.")
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def is_company_domain(domain: str | None) -> bool:
    return bool(domain and domain not in NON_COMPANY_CONTACT_DOMAINS)


def normalize_company_name(company: str) -> str:
    return " ".join((company or "").strip().lower().split())


def contact_lookup_key(company: str, application_url: str | None) -> str:
    domain = domain_from_url(application_url)
    if is_company_domain(domain):
        return f"domain:{domain}"
    normalized = normalize_company_name(company)
    return f"company:{normalized}" if normalized else "company:unknown"


def _dedupe_rank(candidates: list[ContactCandidate]) -> list[ContactCandidate]:
    best: dict[str, ContactCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.email)
        if current is None or candidate.confidence > current.confidence:
            best[candidate.email] = candidate
    return sorted(best.values(), key=lambda c: c.confidence, reverse=True)


class ContactProvider(ABC):
    name: str = ""

    def is_available(self) -> bool:
        return True

    @abstractmethod
    def find(self, *, company: str, application_url: str | None) -> list[ContactCandidate]:
        """Return ranked contact candidates."""


class SnovContactProvider(ContactProvider):
    name = "snov"

    TOKEN_URL = "https://api.snov.io/v1/oauth/access_token"
    EMAIL_COUNT_URL = "https://api.snov.io/v1/get-domain-emails-count"
    START_URL = "https://api.snov.io/v2/domain-search/generic-contacts/start"
    RESULT_URL = "https://api.snov.io/v2/domain-search/generic-contacts/result/{task_hash}"
    COMPANY_DOMAIN_START_URL = "https://api.snov.io/v2/company-domain-by-name/start"
    COMPANY_DOMAIN_RESULT_URL = "https://api.snov.io/v2/company-domain-by-name/result"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        timeout: int = 20,
    ):
        settings = get_settings()
        self.client_id = client_id if client_id is not None else settings.snov_client_id
        self.client_secret = (
            client_secret if client_secret is not None else settings.snov_client_secret
        )
        self.use_email_count_preflight = settings.snov_preflight_email_count
        self.resolve_company_domain = settings.snov_resolve_company_domain
        self.max_contacts = settings.snov_max_contacts
        self.timeout = timeout
        self._token: str | None = None
        self._expires_at = 0.0

    def is_available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def find(self, *, company: str, application_url: str | None) -> list[ContactCandidate]:
        if not self.is_available():
            return []
        domain = self._domain_for_lookup(company=company, application_url=application_url)
        if not domain:
            return []

        try:
            token = self._token_lazy()
            if self.use_email_count_preflight and not self._has_available_emails(
                token=token,
                domain=domain,
            ):
                return []
            payload = self._generic_contacts_payload(token=token, domain=domain)
        except requests.RequestException as e:
            logger.warning("Snov contact lookup failed for %s: %s", domain, e)
            return []

        candidates = [
            self._candidate_from_item(item, domain=domain)
            for item in payload.get("data") or []
        ]
        return _dedupe_rank([c for c in candidates if c is not None])[: self.max_contacts]

    def _token_lazy(self) -> str:
        if self._token and time.time() < self._expires_at - 30:
            return self._token
        response = requests.post(
            self.TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._expires_at = time.time() + payload.get("expires_in", 3600)
        return self._token

    def _domain_for_lookup(self, *, company: str, application_url: str | None) -> str | None:
        domain = domain_from_url(application_url)
        if is_company_domain(domain):
            return domain
        if self.resolve_company_domain and company:
            return self._resolve_company_domain(company)
        return None

    def _has_available_emails(self, *, token: str, domain: str) -> bool:
        try:
            response = requests.post(
                self.EMAIL_COUNT_URL,
                data={"access_token": token, "domain": domain},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("webmail"):
                return False
            return int(payload.get("result") or 0) > 0
        except (requests.RequestException, TypeError, ValueError) as e:
            logger.warning("Snov email-count preflight failed for %s: %s", domain, e)
            return True

    def _generic_contacts_payload(self, *, token: str, domain: str) -> dict:
        headers = {"Authorization": f"Bearer {token}"}
        start = requests.post(
            self.START_URL,
            data={"domain": domain},
            headers=headers,
            timeout=self.timeout,
        )
        start.raise_for_status()
        start_payload = start.json()
        task_hash = (
            start_payload.get("task_hash")
            or (start_payload.get("data") or {}).get("task_hash")
            or (start_payload.get("meta") or {}).get("task_hash")
        )
        if not task_hash:
            return {}

        result = requests.get(
            self.RESULT_URL.format(task_hash=task_hash),
            headers=headers,
            timeout=self.timeout,
        )
        result.raise_for_status()
        return result.json()

    def _resolve_company_domain(self, company: str) -> str | None:
        try:
            token = self._token_lazy()
            headers = {"Authorization": f"Bearer {token}"}
            start = requests.post(
                self.COMPANY_DOMAIN_START_URL,
                params={"names[]": [company]},
                headers=headers,
                timeout=self.timeout,
            )
            start.raise_for_status()
            task_hash = (start.json().get("data") or {}).get("task_hash")
            if not task_hash:
                return None

            result = requests.get(
                self.COMPANY_DOMAIN_RESULT_URL,
                params={"task_hash": task_hash},
                headers=headers,
                timeout=self.timeout,
            )
            result.raise_for_status()
        except requests.RequestException as e:
            logger.warning("Snov company-domain lookup failed for %s: %s", company, e)
            return None

        for item in result.json().get("data") or []:
            domain = ((item.get("result") or {}).get("domain") or "").lower()
            if is_company_domain(domain):
                return domain
        return None

    @staticmethod
    def _candidate_from_item(item: dict, *, domain: str) -> ContactCandidate | None:
        email = (item.get("email") or item.get("value") or "").lower()
        if not email:
            return None
        role_score = score_email(email)
        if role_score <= 0:
            return None
        return ContactCandidate(
            email=email,
            source_url=f"snov:{domain}",
            confidence=max(0.55, role_score),
            provider=SnovContactProvider.name,
            verified=False,
            kind="snov_generic",
        )


class ContactProviderChain:
    def __init__(self, providers: list[ContactProvider], min_confidence: float = 0.60):
        self.providers = providers
        self.min_confidence = min_confidence

    def find(self, *, company: str, application_url: str | None) -> list[ContactCandidate]:
        candidates: list[ContactCandidate] = []
        for provider in self.providers:
            if provider.is_available():
                candidates.extend(provider.find(company=company, application_url=application_url))
        return [c for c in _dedupe_rank(candidates) if c.confidence >= self.min_confidence]

    def best(self, *, company: str, application_url: str | None) -> ContactCandidate | None:
        contacts = self.find(company=company, application_url=application_url)
        return contacts[0] if contacts else None

    @property
    def provider_key(self) -> str:
        return ",".join(provider.name for provider in self.providers) or "none"


def default_contact_chain() -> ContactProviderChain:
    settings = get_settings()
    providers: list[ContactProvider] = []
    snov = SnovContactProvider()
    if snov.is_available():
        providers.append(snov)
    return ContactProviderChain(
        providers=providers,
        min_confidence=settings.autopilot_contact_min_confidence,
    )
