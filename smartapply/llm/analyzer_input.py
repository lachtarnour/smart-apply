"""Canonical input object for the job-analysis LLM call.

Different job sources expose different raw fields. This module keeps the
analyzer prompt isolated from those source-specific shapes by converting a
persisted ``Job`` into one stable payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from smartapply.llm.source_metadata import build_analyzer_source_metadata


@dataclass(frozen=True, slots=True)
class AnalyzerInput:
    """Stable payload consumed by the job-analysis prompt builder."""

    title: str
    company: str
    location: str | None
    application_url: str | None
    offer_body: str
    source: str
    source_metadata: str = ""


def build_analyzer_input(job: Any) -> AnalyzerInput:
    """Normalize a persisted job into the LLM analyzer input contract."""
    return AnalyzerInput(
        title=str(getattr(job, "title", "") or ""),
        company=str(getattr(job, "company", "") or ""),
        location=getattr(job, "location", None),
        application_url=getattr(job, "application_url", None),
        offer_body=str(
            getattr(job, "cleaned_description", None)
            or getattr(job, "description", "")
            or ""
        ),
        source=str(getattr(job, "source", "") or ""),
        source_metadata=build_analyzer_source_metadata(job),
    )
