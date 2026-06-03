"""Prompt builder for the autopilot quality gate."""

from __future__ import annotations

from typing import Any

from smartapply.llm import AdaptedCV, EmailDraft, JobAnalysis, MotivationLetter
from smartapply.profile import Profile


SYSTEM = """You are a strict job-application reviewer.

Your job is to decide if an automated application is safe to turn into a Gmail draft.

Approve ONLY when:
- the role is a strong fit for this candidate;
- the CV is specific to the offer and grounded in the profile;
- the motivation letter clearly references the role/company and concrete matching proof;
- the short email is suitable as a deterministic sending note;
- there is no obvious hallucination, overclaim, weak match, or generic message.

Reject if the application is mediocre, too generic, outside target roles, too senior,
sales/BI/reporting-only, internship/alternance, or if validation warnings suggest risk.

Return ONLY the requested JSON.
"""


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
    return f"""Review this generated application.

=== CANDIDATE TARGET ===
Title: {profile.identity.title}
Target roles: {', '.join(profile.preferences.target_roles)}
Seniority: {profile.preferences.seniority or 'unspecified'}
Preferred locations: {', '.join(profile.preferences.preferred_locations)}
Deal breakers: {', '.join(profile.preferences.deal_breakers)}

=== JOB ===
Title: {job_title}
Company: {job_company}
Description:
{job_description[:5000]}

=== LOCAL SCORE ===
{score_components or {}}

=== JOB ANALYSIS ===
{analysis.model_dump_json()}

=== GENERATED CV JSON ===
{adapted_cv.model_dump_json()}

=== GENERATED MOTIVATION LETTER ===
Subject: {motivation_letter.subject}
Body:
{motivation_letter.body}

=== GENERATED EMAIL TEMPLATE ===
Subject: {email_draft.subject}
Body:
{email_draft.body}

=== VALIDATION ===
Warnings: {validation_warnings}
Errors: {validation_errors}

Decide if this is safe to create as an automated Gmail draft with CV and motivation letter attachments.
Use scores from 0.0 to 1.0. Be strict: average applications should be rejected.
"""
