"""Registry for source-specific offer adapters."""

from __future__ import annotations

from smartapply.offers.sources.base import OfferSourceAdapter
from smartapply.offers.sources.francetravail import FranceTravailOfferAdapter
from smartapply.offers.sources.linkedin import LinkedInOfferAdapter
from smartapply.offers.sources.manual import ManualOfferAdapter
from smartapply.offers.sources.serpapi import SerpApiOfferAdapter
from smartapply.offers.sources.wttj import WttjOfferAdapter

_ADAPTERS: dict[str, OfferSourceAdapter] = {}


def register_offer_source_adapter(adapter: OfferSourceAdapter) -> None:
    source = adapter.source.strip().lower()
    if not source:
        raise ValueError("adapter source must not be empty")
    _ADAPTERS[source] = adapter


def get_offer_source_adapter(source: str) -> OfferSourceAdapter | None:
    return _ADAPTERS.get(source.strip().lower())


register_offer_source_adapter(ManualOfferAdapter())
register_offer_source_adapter(WttjOfferAdapter())
register_offer_source_adapter(FranceTravailOfferAdapter())
register_offer_source_adapter(SerpApiOfferAdapter())
register_offer_source_adapter(LinkedInOfferAdapter())
