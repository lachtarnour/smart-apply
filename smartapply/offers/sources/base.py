"""Common interfaces for source-specific offer adapters."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from smartapply.filtering.facts import FilterFacts


class OfferSourceAdapter(Protocol):
    """Source adapter used by the canonical/analyzer input layer."""

    source: str

    def build_offer_body(
        self,
        base_body: str,
        source_data: dict[str, Any] | None,
    ) -> str:
        """Return the offer body the analyzer should see for this source."""
        ...

    def build_filter_facts(self, source_data: dict[str, Any] | None) -> FilterFacts:
        """Return normalized deterministic facts for local filtering."""
        ...

    def build_analyzer_metadata(self, source_data: dict[str, Any] | None) -> str:
        """Return source-specific metadata for the analyzer prompt."""
        ...
