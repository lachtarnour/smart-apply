"""Contact lookup strategy and candidate quality scoring."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from smartapply.email_agent import (
    ContactCandidate,
    domain_from_url,
    is_job_board_domain,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
)

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
    "jobinlive",
    "linkedin",
    "michael page",
    "michael page france",
    "non communique",
    "non communiquée",
    "unknown",
    "groupe talents handicap",
    "talent-r",
    "talents handicap",
    "welcome to the jungle",
    "welcometothejungle",
    "wttj",
}

GENERIC_COMPANY_TOKENS = {
    "and",
    "assurances",
    "batiment",
    "company",
    "conseil",
    "consulting",
    "data",
    "de",
    "des",
    "digital",
    "distribution",
    "du",
    "et",
    "franc",
    "france",
    "group",
    "groupe",
    "inc",
    "ingenierie",
    "international",
    "la",
    "le",
    "les",
    "limited",
    "ltd",
    "of",
    "recrutement",
    "recruitment",
    "reseaux",
    "sa",
    "sarl",
    "sas",
    "solutions",
    "systemes",
    "technologies",
    "technology",
    "the",
}


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
    """Extract strong email/URL signals visible in the offer body.

    Bare tokens such as ``draw.io`` or French inclusive writing like
    ``client.es`` are intentionally ignored. They are too noisy to prove a
    company domain.
    """
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
    return _unique_domains(domains)


def _email_domain(email: str | None) -> str:
    value = (email or "").strip().lower()
    if "@" not in value:
        return ""
    return value.rsplit("@", 1)[-1]


def _domain_terms(domain: str | None) -> set[str]:
    normalized = domain_from_url(f"https://{domain}") if domain else None
    normalized = normalized or normalize_domain_like(domain)
    parts = [part for part in normalized.split(".") if part]
    labels = parts[:-1] if len(parts) > 1 else parts
    if len(labels) > 1 and labels[-1] in {"asso", "co", "com"}:
        labels = labels[:-1]
    terms: set[str] = set()
    for label in labels:
        terms.update(part for part in re.split(r"[-_]+", label) if part)
        terms.add(re.sub(r"[^a-z0-9]+", "", label))
    return {term for term in terms if term}


def normalize_domain_like(domain: str | None) -> str:
    return str(domain or "").lower().strip().removeprefix("www.")


def _company_tokens(company: str | None) -> list[str]:
    normalized = _ascii_lower(company)
    tokens = [
        token
        for token in re.split(r"[^a-z0-9]+", normalized)
        if len(token) >= 2 and token not in GENERIC_COMPANY_TOKENS
    ]
    return tokens


def _same_company_domain(left: str | None, right: str | None) -> bool:
    left_norm = normalize_domain_like(domain_from_url(f"https://{left}") or left)
    right_norm = normalize_domain_like(domain_from_url(f"https://{right}") or right)
    if not left_norm or not right_norm:
        return False
    if left_norm == right_norm:
        return True
    if left_norm.endswith(f".{right_norm}") or right_norm.endswith(f".{left_norm}"):
        return True
    left_terms = _domain_terms(left_norm)
    right_terms = _domain_terms(right_norm)
    return bool(left_terms and right_terms and left_terms & right_terms)


def _email_domain_matches_company(email_domain: str, company: str | None) -> bool:
    tokens = _company_tokens(company)
    if not tokens:
        return True
    terms = _domain_terms(email_domain)
    joined_terms = "".join(sorted(terms))
    compact_domain = re.sub(r"[^a-z0-9]+", "", normalize_domain_like(email_domain))
    if any(
        token in terms
        or token in joined_terms
        or token in compact_domain
        or any(token in term for term in terms if len(token) >= 4)
        for token in tokens
    ):
        return True
    acronym = "".join(token[0] for token in tokens if token)
    return len(acronym) >= 3 and (
        acronym in terms or acronym in joined_terms or acronym in compact_domain
    )


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


def _external_contact_quality_issue(
    contact: ContactCandidate,
    *,
    lookup_company: str | None,
    lookup_domain: str | None,
) -> str | None:
    """Return a rejection reason for low-quality Anymail-style contacts."""
    source = (contact.source_url or "").lower()
    provider = (contact.provider or "").lower()
    if "anymailfinder" not in source and "anymailfinder" not in provider:
        return None

    email_domain = _email_domain(contact.email)
    if not email_domain:
        return "email_invalid"
    normalized_domain = domain_from_url(f"https://{email_domain}") or email_domain
    if is_job_board_domain(normalized_domain):
        return "email_domain_is_job_board"
    if is_suspicious_contact_domain(normalized_domain):
        return "email_domain_is_suspicious"
    if lookup_domain and not _same_company_domain(normalized_domain, lookup_domain):
        return "email_domain_not_matching_lookup_domain"
    if (
        not lookup_domain
        and lookup_company
        and not _email_domain_matches_company(normalized_domain, lookup_company)
    ):
        return "email_domain_not_related_to_company"
    return None


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
