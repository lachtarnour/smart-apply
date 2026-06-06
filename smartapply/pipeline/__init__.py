"""End-to-end pipeline orchestration.

The public surface is intentionally identical to the previous monolithic
``pipeline.py``:

    from smartapply.pipeline import Pipeline

Internally, ``Pipeline`` is a thin facade composing focused phase modules
(``ingestor``, ``processor``, ``applier``, ``contact_service``,
``application_renderer``, ``language``).
"""

from smartapply.pipeline.application_renderer import ApplicationDocumentRenderer
from smartapply.pipeline.applier import Applier
from smartapply.pipeline.apply_specs import ApplyMode
from smartapply.pipeline.contact_service import ContactService
from smartapply.pipeline.ingestor import Ingestor, IngestReport
from smartapply.pipeline.language import detect_offer_language
from smartapply.pipeline.pipeline import Pipeline
from smartapply.pipeline.processor import Processor
from smartapply.pipeline.reports import (
    AnalyzeReport,
    ApplyReport,
    LocalFilterReport,
    ProcessReport,
    RankingReport,
)

__all__ = [
    "Applier",
    "AnalyzeReport",
    "ApplicationDocumentRenderer",
    "ApplyMode",
    "ApplyReport",
    "ContactService",
    "IngestReport",
    "Ingestor",
    "Pipeline",
    "LocalFilterReport",
    "ProcessReport",
    "Processor",
    "RankingReport",
    "detect_offer_language",
]
