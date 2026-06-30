"""Company-name and domain matching helpers for contact lookup."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from smartapply.contacts.domain_classifier import domain_from_url, is_job_board_domain

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


def _mapping_value(value: Any, key: str) -> Any:
    return value.get(key) if isinstance(value, Mapping) else None


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


def _source_metadata_company_name(source_data: Any | None) -> str:
    profile = _mapping_value(source_data, "company_profile")
    organization = _mapping_value(source_data, "hiring_organization")
    source_company = _mapping_value(source_data, "company")
    for value in (
        _mapping_value(profile, "name"),
        _mapping_value(organization, "name"),
        _mapping_value(source_company, "name"),
        _mapping_value(source_company, "nom"),
        _mapping_value(source_data, "company_name"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    return ""


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


