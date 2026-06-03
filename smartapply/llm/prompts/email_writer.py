"""Prompt builder for the application email."""

from __future__ import annotations

from smartapply.llm.schemas import JobAnalysis
from smartapply.profile import Profile


SYSTEM = """You write short application emails in the candidate's voice.

Hard rules:
1. 120-170 words for the body. Not shorter, not longer.
2. Plain, human tone. No buzzwords like "synergy", "rockstar", "passionate".
3. NO bullet lists. NO emojis.
4. Do NOT promise things not in the profile.
5. One reason this candidate matches THIS role, made specific (cite a concrete project or stack).
6. Close with a polite, low-pressure call to action.
7. The body is also used as a motivation letter body, so write complete, fluent, professional paragraphs.
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
    return f"""Write an email from {profile.identity.full_name} applying for:

Job: {job_title} at {job_company}
Why a match (analysis): {', '.join(analysis.match_reasons)}
Risks to soft-acknowledge if relevant: {', '.join(analysis.risks)}

Candidate identity:
- Title: {profile.identity.title}
- Summary: {profile.identity.summary}
- Top skills: {', '.join(list(profile.skills.allowed_skills)[:10])}

{proj_hint}

Email / motivation letter language: {"French" if language == "fr" else "English"}

Subject: concise, mentions the role and the candidate name. Avoid generic "Application".
Body: natural, professional, specific to the offer, and suitable both as a recruiter email and as a short motivation letter.
"""
