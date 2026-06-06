"""Public report objects returned by pipeline phases.

Keeping these dataclasses in one small module makes the phase implementations
focus on orchestration while preserving their public return shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProcessReport:
    total: int
    kept_after_filter: int
    duplicates_removed: int
    top_ranked: int
    analyzed: int


@dataclass
class LocalFilterReport:
    total: int
    kept: int
    rejected: int
    duplicates_removed: int
    kept_ids: list[int]
    rejected_ids: list[int]


@dataclass
class RankingReport:
    total: int
    kept_after_filter: int
    duplicates_removed: int
    ranked: int
    shortlisted: int
    ranked_ids: list[int]
    shortlisted_ids: list[int]


@dataclass
class AnalyzeReport:
    requested: int
    already_analyzed: int
    analyzed: int
    skipped_missing: int


@dataclass
class ApplyReport:
    job_id: int
    application_id: int | None
    docx_path: str | None = None
    cv_html_path: str | None = None
    cv_pdf_path: str | None = None
    letter_html_path: str | None = None
    letter_pdf_path: str | None = None
    eml_path: str | None = None
    contact_email: str | None = None
    contact_cc_email: str | None = None
    contact_source: str | None = None
    contact_form_url: str | None = None
    gmail_draft_id: str | None = None
    status: str | None = None
    application_strategy: str = "email_only"
    company_size: str = "unknown"
    quality_review: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    validation_warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)
