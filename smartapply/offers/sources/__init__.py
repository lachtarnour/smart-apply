"""Source-specific offer inputs and adapters."""

from smartapply.offers.sources.base import OfferSourceAdapter
from smartapply.offers.sources.francetravail import FranceTravailOfferAdapter
from smartapply.offers.sources.manual import ManualOfferAdapter, ManualOfferInput
from smartapply.offers.sources.registry import (
    get_offer_source_adapter,
    register_offer_source_adapter,
)
from smartapply.offers.sources.serpapi import SerpApiOfferAdapter
from smartapply.offers.sources.wttj import WttjOfferAdapter

__all__ = [
    "FranceTravailOfferAdapter",
    "ManualOfferAdapter",
    "ManualOfferInput",
    "OfferSourceAdapter",
    "SerpApiOfferAdapter",
    "WttjOfferAdapter",
    "get_offer_source_adapter",
    "register_offer_source_adapter",
]
