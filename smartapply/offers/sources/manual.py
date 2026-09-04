"""Manual offer input and adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from smartapply.offers.canonical import RawJob, make_external_id


@dataclass(frozen=True, slots=True)
class ManualOfferInput:
    """Native manual-offer form payload."""

    company: str
    title: str
    description: str
    location: str | None = None
    application_url: str | None = None


class ManualOfferAdapter:
    """Translate manual user input into canonical and analyzer-ready shapes."""

    source = "manual"

    def to_canonical(self, offer: ManualOfferInput) -> RawJob:
        return self.from_text(
            offer.description,
            title=offer.title,
            company=offer.company,
            location=offer.location,
            application_url=offer.application_url,
        )

    def from_text(
        self,
        text: str,
        *,
        title: str,
        company: str,
        location: str | None = None,
        application_url: str | None = None,
    ) -> RawJob:
        clean_job_text = text.strip()
        if not clean_job_text:
            raise ValueError("Empty job text")
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
            description=clean_job_text,
            application_url=application_url,
            source=self.source,
            source_data={"input": "text"},
        )

    def build_offer_body(
        self,
        base_body: str,
        source_data: dict[str, Any] | None,
    ) -> str:
        return base_body

    def build_filter_facts(self, source_data: dict[str, Any] | None):
        from smartapply.filtering.facts import FilterFacts

        return FilterFacts(source=self.source)

    def build_analyzer_metadata(self, source_data: dict[str, Any] | None) -> str:
        return ""
