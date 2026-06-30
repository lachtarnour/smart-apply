"""Choose the safest contact lookup strategy for an offer."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from smartapply.contacts.company import (
    _best_lookup_company,
    _clean_company_name,
    _same_company_domain,
    _source_metadata_company_name,
)
from smartapply.contacts.domain_candidates import (
    _normalize_domain_candidate,
    _unique_domains,
    domains_visible_in_text,
    source_domain_candidates,
)
from smartapply.contacts.domain_classifier import domain_from_url, is_reliable_company_domain
from smartapply.contacts.models import ContactLookupDecision
from smartapply.contacts.quality import _domain_is_usable


def _analysis_value(analysis: Any | None, key: str) -> str:
    if analysis is None:
        return ""
    value = analysis.get(key) if isinstance(analysis, Mapping) else getattr(analysis, key, None)
    return str(value or "").strip()


def _domain_url(domain: str) -> str:
    return f"https://{domain}"


def _domain_confirmed_by_sources(
    domain: str,
    *,
    body_domains: list[str],
    application_domain: str | None,
    source_domains: list[str] | None = None,
) -> bool:
    return domain in body_domains or any(
        _same_company_domain(domain, source_domain)
        for source_domain in (source_domains or [])
    ) or (
        bool(application_domain)
        and domain == application_domain
        and is_reliable_company_domain(application_domain)
    )


def resolve_contact_lookup_strategy(
    *,
    job_company: str,
    job_application_url: str | None,
    job_description: str | None,
    analysis: Any | None,
    job_location: str | None,
    source_data: Any | None = None,
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
    source_candidates = source_domain_candidates(source_data)
    source_domains = [candidate.domain for candidate in source_candidates]
    trusted_source_domains = [
        candidate.domain
        for candidate in source_candidates
        if _domain_is_usable(candidate.domain)[0]
    ]
    candidate_domains.extend(source_domains)

    llm_hint_raw = _analysis_value(analysis, "contact_domain_hint")
    llm_hint_kind = _analysis_value(analysis, "contact_domain_kind") or "unknown"
    llm_hint_domain = _normalize_domain_candidate(llm_hint_raw)
    if llm_hint_domain:
        candidate_domains.append(llm_hint_domain)

    extracted_company = _analysis_value(analysis, "extracted_company_name")
    extracted_location = _analysis_value(analysis, "extracted_location")
    source_company = _source_metadata_company_name(source_data)
    lookup_location = extracted_location or job_location
    lookup_company, company_fallback_strategy = _best_lookup_company(
        job_company,
        extracted_company or source_company,
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
                source_domains=trusted_source_domains,
            ):
                warnings.append("llm_domain_hint_not_visible")
                rejected_domains.append(llm_hint_domain)
            else:
                reasons.append("validated_llm_domain_hint_confirmed_by_sources")
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
        if trusted_source_domains and not any(
            _same_company_domain(body_domain, source_domain)
            for source_domain in trusted_source_domains
        ):
            warnings.append("source_metadata_domain_conflicts_with_offer_body_domain")
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

    for source_candidate in source_candidates:
        usable, warning = _domain_is_usable(source_candidate.domain)
        if not usable:
            warnings.append(f"source_metadata_{warning}:{source_candidate.domain}")
            rejected_domains.append(source_candidate.domain)
            continue
        if (
            application_domain
            and is_reliable_company_domain(application_domain)
            and not _same_company_domain(source_candidate.domain, application_domain)
        ):
            warnings.append("source_metadata_domain_conflicts_with_application_domain")
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
        reasons.append(f"company_domain_from_source_metadata:{source_candidate.source_field}")
        return ContactLookupDecision(
            lookup_company=lookup_company or _clean_company_name(job_company) or None,
            lookup_application_url=source_candidate.url or _domain_url(source_candidate.domain),
            lookup_domain=source_candidate.domain,
            lookup_location=lookup_location,
            strategy="domain_from_source_metadata",
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

