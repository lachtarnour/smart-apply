"""Offer contracts and source adapters."""

from smartapply.offers.analyzer_input import (
    AnalyzerInput,
    build_analyzer_input,
    register_source_offer_body_builder,
)
from smartapply.offers.canonical import RawJob, make_external_id
from smartapply.offers.source_metadata import (
    build_analyzer_source_metadata,
    register_source_metadata_builder,
)
from smartapply.offers.sources import (
    FranceTravailOfferAdapter,
    ManualOfferAdapter,
    ManualOfferInput,
    OfferSourceAdapter,
    SerpApiOfferAdapter,
    WttjOfferAdapter,
    get_offer_source_adapter,
    register_offer_source_adapter,
)

__all__ = [
    "AnalyzerInput",
    "FranceTravailOfferAdapter",
    "ManualOfferAdapter",
    "ManualOfferInput",
    "OfferSourceAdapter",
    "RawJob",
    "SerpApiOfferAdapter",
    "WttjOfferAdapter",
    "build_analyzer_input",
    "build_analyzer_source_metadata",
    "get_offer_source_adapter",
    "make_external_id",
    "register_offer_source_adapter",
    "register_source_metadata_builder",
    "register_source_offer_body_builder",
]
