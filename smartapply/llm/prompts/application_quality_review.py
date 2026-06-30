"""Prompt builder for the autopilot quality gate."""

from __future__ import annotations

from typing import Any

from smartapply.llm import AdaptedCV, EmailDraft, JobAnalysis, MotivationLetter
from smartapply.llm.prompts.loader import load_prompt, render_prompt
from smartapply.profile import Profile

SYSTEM = load_prompt("application_quality_review/system.j2")


def build_user_prompt(
    *,
    profile: Profile,
    job_title: str,
    job_company: str,
    job_description: str,
    score_components: dict[str, Any] | None,
    analysis: JobAnalysis,
    adapted_cv: AdaptedCV,
    motivation_letter: MotivationLetter,
    email_draft: EmailDraft,
    validation_warnings: list[str],
    validation_errors: list[str],
) -> str:
    return render_prompt(
        "application_quality_review/user.j2",
        candidate_title=profile.identity.title,
        target_roles=", ".join(profile.preferences.target_roles),
        seniority=profile.preferences.seniority or "unspecified",
        preferred_locations=", ".join(profile.preferences.preferred_locations),
        deal_breakers=", ".join(profile.preferences.deal_breakers),
        job_title=job_title,
        job_company=job_company,
        job_description=job_description[:5000],
        score_components=score_components or {},
        analysis_json=analysis.model_dump_json(),
        adapted_cv_json=adapted_cv.model_dump_json(),
        motivation_letter_subject=motivation_letter.subject,
        motivation_letter_body=motivation_letter.body,
        email_draft_subject=email_draft.subject,
        email_draft_body=email_draft.body,
        validation_warnings=validation_warnings,
        validation_errors=validation_errors,
    )
