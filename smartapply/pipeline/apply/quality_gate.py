"""Application quality review service."""

from __future__ import annotations

from typing import Any

from smartapply.config import Settings
from smartapply.database.models import Job
from smartapply.llm import (
    ApplicationQualityReview,
    EmailDraft,
    JobAnalysis,
    LLMProvider,
    MotivationLetter,
)
from smartapply.llm.prompts import application_quality_review as quality_prompts
from smartapply.pipeline.apply_specs import ApplySpec
from smartapply.pipeline.reports import ApplyReport
from smartapply.profile import Profile

_SEVERE_WARNING_PREFIXES = (
    "hallucinated_number",
    "off_allowed_claims",
    "low_text_overlap",
    "summary_too_long",
    "bullet_too_long",
    "letter_too_short",
    "letter_too_long",
    "letter_self_deprecation",
    "french_elision_missing_apostrophe",
    "unsupported_term_in_letter",
    "unsupported_tech_in_letter",
    "unselected_project_in_letter",
    "cv_title_not_offer_anchored",
    "summary_not_offer_anchored",
)


class QualityGateService:
    """Review generated applications before autopilot creates drafts."""

    def __init__(
        self,
        *,
        profile: Profile,
        llm: LLMProvider,
        settings: Settings,
    ) -> None:
        self.profile = profile
        self.llm = llm
        self.settings = settings

    def maybe_review(
        self,
        *,
        spec: ApplySpec,
        job: Job,
        analysis: JobAnalysis,
        adapted: Any,
        letter_draft: MotivationLetter,
        email_draft: EmailDraft,
        report: ApplyReport,
        score_components: dict[str, Any] | None,
    ) -> tuple[ApplicationQualityReview | None, bool]:
        """Skip the LLM quality review when the active apply mode disables it."""
        if not spec.quality_gate:
            return None, not report.validation_errors
        quality = self._review(
            job=job,
            analysis=analysis,
            adapted=adapted,
            letter_draft=letter_draft,
            email_draft=email_draft,
            report=report,
            score_components=score_components,
        )
        report.quality_review = quality.model_dump()
        return quality, self._approved(quality, report)

    def _review(
        self,
        *,
        job: Job,
        analysis: JobAnalysis,
        adapted: Any,
        letter_draft: MotivationLetter,
        email_draft: EmailDraft,
        report: ApplyReport,
        score_components: dict[str, Any] | None,
    ) -> ApplicationQualityReview:
        prompt = quality_prompts.build_user_prompt(
            profile=self.profile,
            job_title=job.title,
            job_company=job.company,
            job_description=job.cleaned_description or job.description,
            score_components=score_components,
            analysis=analysis,
            adapted_cv=adapted,
            motivation_letter=letter_draft,
            email_draft=email_draft,
            validation_warnings=report.validation_warnings,
            validation_errors=report.validation_errors,
        )
        return self.llm.complete_json(
            system=quality_prompts.SYSTEM,
            user=prompt,
            schema=ApplicationQualityReview,
            model=self.llm.cheap_model,
            temperature=0.1,
            purpose="application_quality_review",
            job_id=job.id,
        )

    def _approved(
        self,
        quality: ApplicationQualityReview,
        report: ApplyReport,
    ) -> bool:
        severe_warnings = [
            warning
            for warning in report.validation_warnings
            if warning.startswith(_SEVERE_WARNING_PREFIXES)
        ]
        scores_ok = min(
            quality.match_score,
            quality.cv_score,
            quality.email_score,
        ) >= self.settings.autopilot_min_score
        return (
            quality.approved
            and scores_ok
            and not report.validation_errors
            and not severe_warnings
        )
