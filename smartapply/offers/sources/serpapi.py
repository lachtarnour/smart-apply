"""SerpApi / Google Jobs offer adapter."""

from __future__ import annotations

from typing import Any


class SerpApiOfferAdapter:
    """Translate SerpApi source payloads into shared offer contracts."""

    source = "serpapi"

    def build_offer_body(
        self,
        base_body: str,
        source_data: dict[str, Any] | None,
    ) -> str:
        return base_body

    def build_filter_facts(self, source_data: dict[str, Any] | None):
        from smartapply.filtering.facts import FilterFacts
        from smartapply.filtering.source_fact_builders import (
            build_serpapi_filter_facts,
        )

        if not isinstance(source_data, dict):
            return FilterFacts(source=self.source)
        return build_serpapi_filter_facts(source_data)

    def build_analyzer_metadata(self, source_data: dict[str, Any] | None) -> str:
        from smartapply.offers.source_metadata_builders import build_serpapi_source_metadata

        return build_serpapi_source_metadata(source_data)
