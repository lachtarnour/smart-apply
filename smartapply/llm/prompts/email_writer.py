"""Prompt builder for the legacy motivation-letter call."""

from __future__ import annotations

from smartapply.llm.schemas import JobAnalysis
from smartapply.profile import Profile


SYSTEM = """You write a concise motivation letter in the candidate's voice.

Hard rules:
1. 180-280 words for the body. Not shorter, not longer.
2. Plain, human tone. No buzzwords like "synergy", "rockstar", "passionate".
3. NO bullet lists. NO emojis.
4. Do NOT promise things not in the profile.
5. Cite one concrete project, stack or experience from the profile.
6. Close with a polite, low-pressure call to action.
7. This is NOT the recruiter email. The sending email is generated later by a deterministic template.
8. Return ONLY the JSON {subject, body}.
"""


def build_user_prompt(
    *,
    profile: Profile,
    analysis: JobAnalysis,
    job_title: str,
    job_company: str,
    language: str = "fr",
) -> str:
    proj_hint = ""
    if profile.projects:
        proj_hint = "Reference candidate projects: " + ", ".join(
            f"{p.name} ({p.description[:80]}...)" for p in profile.projects[:3]
        )
    return f"""Write a motivation letter from {profile.identity.full_name} applying for:

Job: {job_title} at {job_company}
Why a match (analysis): {', '.join(analysis.match_reasons)}
Risks to soft-acknowledge if relevant: {', '.join(analysis.risks)}

Candidate identity:
- Title: {profile.identity.title}
- Summary: {profile.identity.summary}
- Top skills: {', '.join(list(profile.skills.allowed_skills)[:10])}

{proj_hint}

Motivation letter language: {"French" if language == "fr" else "English"}

Subject: concise, mentions the role and the candidate name. For French, use "Candidature - ...".
Body: 180-280 words, natural, professional, specific to the offer, no bullet list.
"""
