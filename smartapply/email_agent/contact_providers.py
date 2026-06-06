"""Anymail Finder contact lookup for autopilot.

The production path is intentionally small:
- extract a company-owned domain when the job URL has one;
- skip known ATS/job-board domains unless an upstream analysis supplied a hint;
- return only observed provider results, never guessed aliases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger
from smartapply.utils.location import canonical_french_city, french_city_mismatch

logger = get_logger(__name__)


ATS_DOMAINS = {
    # Greenhouse / Lever / Ashby
    "greenhouse.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    # Workday / Oracle / SAP / UKG
    "myworkdayjobs.com",
    "oraclecloud.com",
    "successfactors.com",
    "successfactors.eu",
    "taleo.com",
    "taleo.net",
    "ukg.com",
    "ultipro.com",
    "workdayjobs.com",
    # SmartRecruiters / Workable / Recruitee / Teamtailor
    "smartrecruiters.com",
    "smartrecruiters.eu",
    "workable.com",
    "recruitee.com",
    "teamtailor.com",
    # Jobvite / JazzHR / ApplyToJob / iCIMS
    "applytojob.com",
    "icims.com",
    "jazz.co",
    "jazzhr.com",
    "jobvite.com",
    # Common SMB / Europe ATS
    "bamboohr.com",
    "altays-progiciels.com",
    "adequasys.com",
    "beetween.com",
    "breezy.hr",
    "contactrh.com",
    "comeet.co",
    "flatchr.io",
    "gestmax.fr",
    "homerun.co",
    "intervieweb.it",
    "jobaffinity.fr",
    "jobylon.com",
    "jometer.com",
    "join.com",
    "mstaff.co",
    "mytalentplug.com",
    "odoo.com",
    "personio.com",
    "pinpointhq.com",
    "recruitmentplatform.com",
    "skeeled.com",
    "softy.pro",
    "taleez.com",
    "talent-soft.com",
    "talentview.io",
    "werecruit.io",
    "welcomekit.co",
    "wink-lab.com",
    "zoho.com",
    "zohorecruit.com",
    # Other ATS / apply platforms observed in data
    "aplitrak.com",
    "easyapply.jobs",
    "nicoka.com",
    "smrtr.io",
    "trakstar.com",
    "aio-jobs.com",
    "xtramile.io",
}

PARTNER_JOB_BOARD_DOMAINS = {
    # France Travail / public
    "candidat.francetravail.fr",
    "francetravail.fr",
    "gouv.fr",
    "pole-emploi.fr",
    # France major job boards
    "adzuna.com",
    "adzuna.fr",
    "apec.fr",
    "cadremploi.fr",
    "cadreo.com",
    "glassdoor.com",
    "hellowork.com",
    "indeed.com",
    "indeed.fr",
    "jobijoba.com",
    "keljob.com",
    "linkedin.com",
    "meteojob.com",
    "monster.com",
    "monster.fr",
    "ouestjob.com",
    "pacajob.com",
    "parisjob.com",
    "regionsjob.com",
    "rhonealpesjob.com",
    "sudouestjob.com",
    "talent.com",
    "welcometothejungle.com",
    # Tech / specialist boards
    "chooseyourboss.com",
    "aerocontact.com",
    "dogfinance.com",
    "emploi-pro.fr",
    "free-work.com",
    "moovijob.com",
    "lesjeudis.com",
    "linkfinance.fr",
    # Inclusion / handicap / sector partners
    "agefiph.asso.fr",
    "agefiph.fr",
    "apecita.com",
    "clicandsport.fr",
    "clicandearth.fr",
    "handicap-job.com",
    "handicap.fr",
    "jobinlive.com",
    "lindustrie-recrute.fr",
    "missionhandicap.com",
    "talents-handicap.com",
    # Aggregators / partner posting
    "batiactu.com",
    "bebee.com",
    "carriereonline.com",
    "careerjet.com",
    "directemploi.com",
    "emploi-collectivites.fr",
    "equest.com",
    "google.com",
    "jobposting.pro",
    "jobtransport.com",
    "jobvitae.fr",
    "jooble.org",
    "optioncarriere.com",
    "ouest-france.fr",
    "pmejob.fr",
}

APPLICATION_REDIRECT_DOMAINS = {
    "app.link",
    "bit.ly",
    "lnkd.in",
    "t.co",
    "tinyurl.com",
    "urlr.me",
}

NON_COMPANY_CONTACT_DOMAINS = (
    ATS_DOMAINS | PARTNER_JOB_BOARD_DOMAINS | APPLICATION_REDIRECT_DOMAINS
)

SUSPECT_CONTACT_DOMAIN_MARKERS = {
    "applicant",
    "apply",
    "ashby",
    "ats",
    "career",
    "careers",
    "candidate",
    "emploi",
    "greenhouse",
    "hiring",
    "icims",
    "job",
    "jobs",
    "lever",
    "recruit",
    "recrut",
    "smartrecruit",
    "taleo",
    "talent",
    "teamtailor",
    "workable",
    "workday",
}

# Higher score = more likely to be a real recruitment contact.
PREFIX_SCORES: list[tuple[str, float]] = [
    ("recrutement", 0.99),
    ("recruit", 0.99),
    ("jobs", 0.98),
    ("careers", 0.98),
    ("carrieres", 0.98),
    ("talent", 0.97),
    ("hiring", 0.97),
    ("hr", 0.97),
    ("rh", 0.97),
    ("contact", 0.6),
    ("hello", 0.5),
    ("info", 0.4),
    ("support", 0.2),
    ("press", 0.1),
]

BLOCKED_PREFIXES = {
    "noreply",
    "no-reply",
    "donotreply",
    "postmaster",
    "abuse",
    "mailer-daemon",
    "webmaster",
}


@dataclass(frozen=True)
class ContactCandidate:
    email: str
    source_url: str
    confidence: float
    provider: str
    verified: bool = False
    kind: str = "contact"
    form_url: str | None = None
    full_name: str | None = None
    job_title: str | None = None
    location_hint: str | None = None
    decision_reason: str | None = None


def score_email(email: str) -> float:
    prefix = email.split("@", 1)[0].lower()
    if prefix in BLOCKED_PREFIXES:
        return 0.0
    for keyword, score in PREFIX_SCORES:
        if prefix.startswith(keyword) or keyword in prefix:
            return score
    # Generic person-like prefix (firstname.lastname@) — neutral.
    return 0.5


def is_recruitment_generic_email(email: str) -> bool:
    """True for role-based recruitment/RH addresses we prefer as primary To."""
    return score_email(email) >= 0.97


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
    multi_part_suffixes = {
        ("co", "uk"),
        ("com", "au"),
        ("com", "br"),
        ("com", "tr"),
        ("com", "fr"),
        ("co", "jp"),
        ("asso", "fr"),
    }
    if len(parts) >= 3 and tuple(parts[-2:]) in multi_part_suffixes:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def normalize_domain(domain: str | None) -> str:
    return str(domain or "").lower().strip().removeprefix("www.")


def is_known_domain(domain: str | None, known_domains: set[str]) -> bool:
    normalized = normalize_domain(domain)
    if not normalized:
        return False
    return any(
        normalized == known or normalized.endswith(f".{known}")
        for known in known_domains
    )


def classify_application_domain(domain: str | None) -> str:
    normalized = normalize_domain(domain)
    if is_known_domain(normalized, ATS_DOMAINS):
        return "ats"
    if is_known_domain(normalized, PARTNER_JOB_BOARD_DOMAINS):
        return "partner_job_board"
    if is_known_domain(normalized, APPLICATION_REDIRECT_DOMAINS):
        return "application_redirect"
    return "unknown"


def is_company_domain(domain: str | None) -> bool:
    if not domain:
        return False
    domain = domain.lower().removeprefix("www.")
    return not is_job_board_domain(domain)


def is_job_board_domain(domain: str | None) -> bool:
    return is_known_domain(domain, NON_COMPANY_CONTACT_DOMAINS)


def is_suspicious_contact_domain(domain: str | None) -> bool:
    """Return True for domains that look like recruitment platforms."""
    if not domain:
        return False
    labels = [
        label
        for label in domain.lower().removeprefix("www.").split(".")
        if label
    ]
    searchable = labels[:-1] if len(labels) > 1 else labels
    return any(
        marker in label
        for label in searchable
        for marker in SUSPECT_CONTACT_DOMAIN_MARKERS
    )


def is_reliable_company_domain(domain: str | None) -> bool:
    return is_company_domain(domain) and not is_suspicious_contact_domain(domain)


def normalize_company_name(company: str) -> str:
    return " ".join((company or "").strip().lower().split())


def contact_lookup_key(company: str, application_url: str | None) -> str:
    domain = domain_from_url(application_url)
    if is_reliable_company_domain(domain):
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
    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        """Return ranked contact candidates."""


class AnymailFinderContactProvider(ContactProvider):
    name = "anymailfinder"

    DECISION_MAKER_URL = "https://api.anymailfinder.com/v5.1/find-email/decision-maker"
    COMPANY_URL = "https://api.anymailfinder.com/v5.1/find-email/company"
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

        candidates.extend(
            self._decision_maker_contacts(lookup, job_location=job_location)
        )

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
    ) -> list[ContactCandidate]:
        if not self.decision_maker_categories:
            return []

        payload = {
            **lookup,
            "decision_maker_category": self.decision_maker_categories,
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
