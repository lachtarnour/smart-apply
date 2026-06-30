"""Welcome to the Jungle offer adapter."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup


class WttjOfferAdapter:
    """Translate WTTJ-specific stored data into analyzer-ready offer context."""

    source = "welcometothejungle"

    def build_offer_body(
        self,
        base_body: str,
        source_data: dict[str, Any] | None,
    ) -> str:
        if not isinstance(source_data, dict):
            return base_body

        detail_api = source_data.get("detail_api")
        if not isinstance(detail_api, dict):
            return base_body

        company_description = _html_to_text(detail_api.get("company_description"))
        if not company_description or _contains_text(base_body, company_description):
            return base_body

        body = base_body.strip()
        company_block = f"Company context\n{company_description}"
        if not body:
            return company_block
        return f"{body}\n\n{company_block}"

    def build_filter_facts(self, source_data: dict[str, Any] | None):
        from smartapply.filtering.facts import FilterFacts
        from smartapply.filtering.source_fact_builders import build_wttj_filter_facts

        if not isinstance(source_data, dict):
            return FilterFacts(source=self.source)
        return build_wttj_filter_facts(source_data)

    def build_analyzer_metadata(self, source_data: dict[str, Any] | None) -> str:
        from smartapply.offers.source_metadata_builders import build_wttj_source_metadata

        return build_wttj_source_metadata(source_data)


def _html_to_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    soup = BeautifulSoup(text, "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return " ".join(soup.get_text("\n", strip=True).split())


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
