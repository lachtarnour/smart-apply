"""Manual offer input and adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from smartapply.offers.canonical import RawJob, make_external_id


@dataclass(frozen=True, slots=True)
class ManualOfferInput:
    """Structured manual form payload before conversion to a canonical offer."""

    entreprise: str
    offre: str
    description_offre: str
    description_entreprise: str | None = None
    url_entreprise: str | None = None
    recruteur: str | None = None
    localisation: str | None = None
    url_candidature: str | None = None


class ManualOfferAdapter:
    """Translate manual user input into canonical and analyzer-ready shapes."""

    source = "manual"

    def to_canonical(self, offer: ManualOfferInput) -> RawJob:
        return self.from_text(
            offer.description_offre,
            title=offer.offre,
            company=offer.entreprise,
            location=offer.localisation,
            application_url=offer.url_candidature,
            company_description=offer.description_entreprise,
            company_url=offer.url_entreprise,
            recruiter=offer.recruteur,
            structured=True,
        )

    def from_text(
        self,
        text: str,
        *,
        title: str,
        company: str,
        location: str | None = None,
        application_url: str | None = None,
        company_description: str | None = None,
        company_url: str | None = None,
        recruiter: str | None = None,
        structured: bool = False,
    ) -> RawJob:
        clean_job_text = text.strip()
        clean_company_description = (company_description or "").strip()
        clean_company_url = (company_url or "").strip()
        clean_recruiter = (recruiter or "").strip()
        if not clean_job_text:
            raise ValueError("Empty job text")
        is_structured = structured or any(
            [
                clean_company_description,
                clean_company_url,
                clean_recruiter,
            ]
        )
        description = manual_description_body(
            job_text=clean_job_text,
            company_description=clean_company_description,
            structured=is_structured,
        )
        return RawJob(
            external_id=make_external_id(
                self.source,
                company,
                title,
                application_url or clean_job_text[:200],
            ),
            title=title.strip(),
            company=company.strip(),
            location=location,
            description=description,
            application_url=application_url,
            source=self.source,
            source_data={
                "input": "structured_manual" if is_structured else "text",
                "job_description": clean_job_text,
                "company_description": clean_company_description or None,
                "company_url": clean_company_url or None,
                "recruiter": clean_recruiter or None,
            },
        )

    def build_offer_body(
        self,
        base_body: str,
        source_data: dict[str, Any] | None,
    ) -> str:
        if not isinstance(source_data, dict):
            return base_body
        if source_data.get("input") != "structured_manual":
            return base_body

        job_text = str(source_data.get("job_description") or "").strip()
        company_description = str(source_data.get("company_description") or "").strip()
        if not job_text:
            return base_body
        if _contains_text(base_body, job_text) and (
            not company_description or _contains_text(base_body, company_description)
        ):
            return base_body

        return manual_description_body(
            job_text=job_text,
            company_description=company_description,
            structured=True,
        )

    def build_filter_facts(self, source_data: dict[str, Any] | None):
        from smartapply.filtering.facts import FilterFacts

        return FilterFacts(source=self.source)

    def build_analyzer_metadata(self, source_data: dict[str, Any] | None) -> str:
        from smartapply.offers.source_metadata_builders import build_manual_source_metadata

        return build_manual_source_metadata(source_data)


def manual_description_body(
    *,
    job_text: str,
    company_description: str,
    structured: bool = False,
) -> str:
    if not structured:
        return job_text
    sections = ["=== DESCRIPTION DE L'OFFRE ===", job_text]
    if company_description:
        sections.extend(["", "=== DESCRIPTION DE L'ENTREPRISE ===", company_description])
    return "\n".join(sections)


def _contains_text(haystack: str, needle: str) -> bool:
    normalized_haystack = _normalize_for_match(haystack)
    normalized_needle = _normalize_for_match(needle)
    if not normalized_haystack or not normalized_needle:
        return False
    if normalized_needle in normalized_haystack:
        return True
    prefix = normalized_needle[:160]
    return len(prefix) >= 80 and prefix in normalized_haystack


def _normalize_for_match(value: str) -> str:
    return " ".join(str(value or "").lower().split())
