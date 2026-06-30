"""Prompt builder for a combined CV adaptation + motivation-letter call."""

from __future__ import annotations

import re

from smartapply.llm.prompts.cv_adaptation import (
    _format_core_skills,
    _format_experiences,
    _format_matching_keywords,
    _format_projects,
    _format_skill_catalog,
    _format_unsupported_offer_terms,
)
from smartapply.llm.prompts.loader import load_prompt, render_prompt
from smartapply.llm.prompts.skill_profiles import format_skill_profiles
from smartapply.llm.schemas import JobAnalysis
from smartapply.profile import Experience, Profile, Project

SYSTEM = load_prompt("application_draft/system.j2")


def _format_offer_interest_anchors(analysis: JobAnalysis) -> str:
    lines: list[str] = []
    if analysis.company_context.strip():
        lines.append(f"Company/context: {analysis.company_context.strip()}")
    for point in analysis.offer_interest_points:
        point = " ".join((point or "").split())
        if point:
            lines.append(f"- {point}")
    if lines:
        return "\n".join(lines)
    return (
        "No reliable company/about-us anchor extracted. Use only the visible "
        "domain, missions, responsibilities and required skills; do not invent "
        "company facts."
    )


def _format_langchain_langgraph_letter_instruction(analysis: JobAnalysis) -> str:
    fields = [
        analysis.role_type,
        analysis.domain,
        analysis.company_context,
        *analysis.main_tasks,
        *analysis.required_skills,
        *analysis.cv_keywords_to_include,
        *analysis.offer_interest_points,
        *analysis.match_reasons,
        *analysis.risks,
    ]
    text = " ".join(field for field in fields if field)
    if not re.search(r"\blang\s*(?:chain|graph)\b", text, flags=re.IGNORECASE):
        return ""
    # This note is letter-only. LangChain remains a CV skill only through the
    # whitelist; LangGraph is not a display skill.
    return (
        "LangChain/LangGraph note (motivation letter only): include exactly one short, "
        "positive sentence in paragraph 2 or 3 saying the candidate has started "
        "actively exploring LangChain/LangGraph, is still deepening them, and plans "
        "to build a concrete Text-to-SQL assistant project soon; do not present "
        "these tools as mastered in the letter. In CV fields, mention LangChain "
        "only if it is selected from allowed_skills; do not mention LangGraph."
    )


def build_user_prompt(
    *,
    profile: Profile,
    analysis: JobAnalysis,
    job_title: str,
    job_company: str,
    selected_experiences: list[Experience],
    selected_projects: list[Project],
    language: str = "fr",
) -> str:
    allowed = ", ".join(sorted(profile.skills.allowed_skills))
    style = profile.style_guide
    dont = "\n  - ".join(style.dont)
    do = "\n  - ".join(style.do)
    main_tasks_block = "\n".join(f"- {t}" for t in analysis.main_tasks)
    project_hint = ", ".join(p.name for p in selected_projects[:4])
    skill_profiles = format_skill_profiles(profile)
    skill_catalog = _format_skill_catalog(profile)
    core_skills = _format_core_skills(profile)
    matching_keywords = _format_matching_keywords(profile)
    unsupported_offer_terms = _format_unsupported_offer_terms(profile, analysis)
    offer_interest_anchors = _format_offer_interest_anchors(analysis)
    langchain_langgraph_letter_instruction = (
        _format_langchain_langgraph_letter_instruction(analysis)
    )

    return render_prompt(
        "application_draft/user.j2",
        job_title=job_title,
        job_company=job_company,
        role_type=analysis.role_type,
        seniority=analysis.seniority,
        domain=analysis.domain,
        offer_interest_anchors=offer_interest_anchors,
        main_tasks_block=main_tasks_block,
        required_skills=", ".join(analysis.required_skills),
        keywords_to_surface=", ".join(analysis.cv_keywords_to_include),
        match_reasons=", ".join(analysis.match_reasons),
        risks_to_avoid=", ".join(analysis.risks),
        candidate_name=profile.identity.full_name,
        candidate_title=profile.identity.title,
        summary_source=profile.identity.summary,
        allowed_skills=allowed,
        skill_catalog=skill_catalog,
        core_skills=core_skills,
        skill_profiles=skill_profiles,
        matching_keywords=matching_keywords,
        unsupported_offer_terms=unsupported_offer_terms,
        experiences_block=_format_experiences(selected_experiences),
        projects_block=_format_projects(selected_projects),
        letter_language="French" if language == "fr" else "English",
        project_hint=project_hint,
        langchain_langgraph_letter_instruction=langchain_langgraph_letter_instruction,
        tone=style.tone,
        voice=style.voice,
        max_summary_lines=style.max_summary_lines,
        max_summary_length=style.max_summary_length,
        do=do,
        dont=dont,
    )
