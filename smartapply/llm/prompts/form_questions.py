"""Prompt builder for application form questions."""

from __future__ import annotations

import json
from typing import Any

from smartapply.profile import Profile

SYSTEM = """You help a candidate answer job application form questions.

Rules:
- Use only the provided job offer, job analysis and candidate profile JSON.
- Do not invent company facts, responsibilities, metrics, degrees, dates, skills or experiences.
- If a question asks why the company is special, use only company/product/mission facts visible in the offer or analysis.
- If the evidence is weak, still produce a usable answer, but add a warning naming what should be verified manually.
- Answer in the same language as the question when possible.
- If several questions are provided, answer each question separately in the same response.
- Keep each answer concise, natural and professional: usually 80-140 words.
- Humanize the wording: write like a real candidate, in first person when appropriate, with a fluid and specific tone rather than a generic template.
- Avoid robotic phrasing, inflated claims, empty enthusiasm and repeated sentence patterns.
- Write plain text only, no markdown bullets unless the question explicitly asks for a list.
- Mention concrete profile evidence when relevant: projects, experiences, skills or education.
"""


def build_form_questions_prompt(
    *,
    profile: Profile,
    row: dict[str, Any],
    questions: str,
) -> tuple[str, str]:
    """Return system/user messages for form-question answer generation."""
    analysis = row.get("analysis_raw") if isinstance(row.get("analysis_raw"), dict) else {}
    analysis_json = json.dumps(analysis, ensure_ascii=False, indent=2)
    profile_json = profile.model_dump_json(indent=2)
    user = f"""Generate grounded answers for the form questions below.

APPLICATION CONTEXT
application_id: {row.get("id")}
job_id: {row.get("job_id")}
title: {row.get("title") or ""}
company: {row.get("company") or ""}
location: {row.get("job_location") or ""}
application_url: {row.get("application_url") or ""}

JOB OFFER TEXT
{row.get("job_description") or ""}

JOB ANALYSIS JSON
{analysis_json}

CANDIDATE PROFILE JSON
{profile_json}

FORM QUESTIONS
{questions.strip()}
"""
    return SYSTEM, user
