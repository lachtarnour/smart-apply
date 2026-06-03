"""Autopilot runner for high-volume application drafting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.models import Job, JobScore, JobStatus
from smartapply.logging_setup import get_logger
from smartapply.pipeline import ApplyReport, IngestReport, Pipeline, ProcessReport

logger = get_logger(__name__)


@dataclass
class AutopilotReport:
    query: str
    location: str | None
    target_drafts: int
    ingest: list[dict[str, Any]] = field(default_factory=list)
    process: dict[str, Any] | None = None
    attempted: int = 0
    draft_created: int = 0
    ready_for_form_submission: int = 0
    email_generated: int = 0
    quality_rejected: int = 0
    failed: int = 0
    applications: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def productive_outputs(self) -> int:
        return self.draft_created + self.ready_for_form_submission + self.email_generated

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "location": self.location,
            "target_drafts": self.target_drafts,
            "ingest": self.ingest,
            "process": self.process,
            "attempted": self.attempted,
            "draft_created": self.draft_created,
            "ready_for_form_submission": self.ready_for_form_submission,
            "email_generated": self.email_generated,
            "quality_rejected": self.quality_rejected,
            "failed": self.failed,
            "productive_outputs": self.productive_outputs,
            "applications": self.applications,
            "errors": self.errors,
        }


class AutopilotRunner:
    """Run a full daily search/apply loop until enough outputs are produced."""

    def __init__(self, pipeline: Pipeline | None = None):
        self.pipeline = pipeline or Pipeline()
        self.settings = get_settings()

    def run(
        self,
        *,
        query: str,
        location: str | None = None,
        sources: list[str] | None = None,
        max_per_source: int | None = None,
        target_drafts: int | None = None,
        create_gmail_drafts: bool = True,
        require_quality_gate: bool | None = None,
        date_posted: str | None = None,
        serpapi_hl: str | None = None,
    ) -> AutopilotReport:
        sources = sources or ["serpapi", "francetravail", "manual"]
        target = target_drafts or self.settings.autopilot_target_drafts
        max_results = max_per_source or max(target, 25)
        report = AutopilotReport(query=query, location=location, target_drafts=target)

        for source in sources:
            if source == "manual":
                continue
            try:
                kwargs = (
                    {"date_posted": date_posted, "hl": serpapi_hl}
                    if source == "serpapi"
                    else {}
                )
                ingest = self.pipeline.ingest(
                    source,
                    query,
                    location,
                    max_results=max_results,
                    **kwargs,
                )
                report.ingest.append(ingest.__dict__)
            except Exception as e:
                message = f"{source}: {e}"
                logger.warning("Autopilot ingest skipped: %s", message)
                report.errors.append(message)

        analyze_limit = max(int(target * self.settings.autopilot_analyze_multiplier), target, 15)
        process = self.pipeline.process_pending(top_k_analyze=analyze_limit)
        report.process = process.__dict__

        candidate_limit = max(int(target * self.settings.autopilot_candidate_multiplier), target)
        candidate_ids = self._candidate_ids(limit=candidate_limit)
        for job_id in candidate_ids:
            if report.productive_outputs >= target:
                break
            try:
                application = self.pipeline.apply_to_autopilot(
                    job_id,
                    create_gmail_draft=create_gmail_drafts,
                    require_quality_gate=require_quality_gate,
                )
                report.attempted += 1
                self._record_application(report, application)
            except Exception as e:
                logger.exception("Autopilot apply failed for job %s: %s", job_id, e)
                report.failed += 1
                report.errors.append(f"job {job_id}: {e}")

        return report

    def _candidate_ids(self, *, limit: int) -> list[int]:
        with session_scope() as s:
            stmt = (
                select(Job)
                .join(JobScore)
                .where(Job.status == JobStatus.ANALYZED)
                .where(JobScore.final_score.is_not(None))
                .where(JobScore.final_score >= self.settings.autopilot_min_score)
                .order_by(JobScore.final_score.desc())
                .limit(limit)
            )
            return [job.id for job in s.execute(stmt).scalars().all()]

    @staticmethod
    def _record_application(report: AutopilotReport, application: ApplyReport) -> None:
        if application.status == JobStatus.DRAFT_CREATED:
            report.draft_created += 1
        elif application.status == JobStatus.READY_FOR_FORM_SUBMISSION:
            report.ready_for_form_submission += 1
        elif application.status == JobStatus.EMAIL_GENERATED:
            report.email_generated += 1
        elif application.status == JobStatus.QUALITY_REJECTED:
            report.quality_rejected += 1

        report.applications.append(
            {
                "job_id": application.job_id,
                "application_id": application.application_id,
                "status": application.status,
                "contact_email": application.contact_email,
                "contact_source": application.contact_source,
                "contact_form_url": application.contact_form_url,
                "gmail_draft_id": application.gmail_draft_id,
                "docx_path": application.docx_path,
                "eml_path": application.eml_path,
                "quality_review": application.quality_review,
                "validation_warnings": application.validation_warnings,
                "validation_errors": application.validation_errors,
            }
        )
