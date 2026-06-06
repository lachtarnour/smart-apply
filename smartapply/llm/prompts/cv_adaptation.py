"""Prompt builder for CV adaptation — strictly grounded in the profile.

Each bullet exposes:
- ``allowed_claims``: the exhaustive list of claims you may make about it.
  Any sentence that goes beyond these claims is treated as a hallucination.
- ``evidence_level``: how strong the underlying evidence is.
  - ``verified``: reformulate freely while staying faithful.
  - ``self_reported``: keep the claim narrow, don't generalize.
  - ``inferred``: be conservative; avoid asserting it strongly.
"""

from __future__ import annotations

import re

from smartapply.cv.constants import NON_DISPLAY_DOMAIN_TERMS
from smartapply.llm.prompts.skill_profiles import format_skill_profiles
from smartapply.llm.schemas import JobAnalysis
from smartapply.profile import Bullet, Experience, Profile, Project

SYSTEM = """You adapt a candidate's CV to a job offer WITHOUT inventing anything.

Hard rules:
1. Every output bullet MUST reference a real source_id from the provided list. The validator will reject any bullet without a valid source_id.
2. Every claim you make about a bullet MUST come from its ``allowed_claims`` list. You may combine, paraphrase or shorten claims, but never add new ones.
3. Respect each bullet's ``evidence_level``:
   - ``verified``: rephrase freely while staying faithful.
   - ``self_reported``: keep the claim narrow, don't generalize.
   - ``inferred``: be conservative; soften the wording rather than assert.
4. You MUST NOT invent skills outside of ``allowed_skills``.
5. You MUST NOT change quantified results (numbers, percentages, dates, company names).
6. The CV is ALWAYS in English, even when the job offer is in French.
7. Density rule (very important): default to the source bullet's exact phrasing — it is already dense and intentional. Only paraphrase when you can naturally surface an offer keyword without adding fluff. If the rewrite would be longer, heavier, or less natural than the source, keep the source bullet verbatim. Surfacing keywords is OPTIONAL: skip it whenever it would weigh the bullet down.
8. When you do rephrase, you may only recombine/paraphrase the provided allowed_claims.
9. Keep bullets concise (<= 220 chars). Lead with action verbs.
10. selected_experiences MUST include every provided source experience and every provided source bullet. Do not remove bullets to optimize relevance. If a bullet cannot be naturally adapted to the offer, keep the source text verbatim.
11. If a source bullet declares ``links``, keep each ``anchor`` token verbatim in your output bullet — the renderer wraps it as a hyperlink. Do not embed any markdown link or HTML tag yourself; just preserve the anchor word.
12. The cv_title MUST be adapted to this role and MUST contain at least one specific role anchor from the job title, role_type or main_tasks. Generic default titles are forbidden.
13. The professional_summary MUST be adapted to this role, cite at least one concrete offer anchor, fit in 2 lines maximum, and use only facts from the source profile.
14. Generic default summaries are forbidden. Do not reuse broad phrases such as "applied AI, NLP and multimodal learning" unless those exact areas are directly relevant to the offer.
15. Choose exactly one skills_profile_id from the provided skill profile choices. Use matching_keywords only to understand the role family; they are NOT display skills.
16. selected_skills is the exact Skills section to display. Build organized category blocks from allowed_skills_by_category only.
17. Skill selection strategy: include offer-required skills that exist in allowed_skills; add core/profile skills only when they strengthen the application for this offer; omit generic or unrelated skills even if the candidate has them.
18. Unsupported offer terms are a no-claim list: do not describe the candidate as having those skills in the summary, bullets, title, skills or warnings.
19. selected_project_ids must contain 2 to 4 projects. Include at least 3 only when 3 genuinely relevant projects are available. Do not select a project only as filler.
20. Output ONLY the JSON. No prose, no commentary.
"""


def _format_bullet(bullet: Bullet) -> str:
    claims = "\n".join(f"      * {c}" for c in bullet.effective_allowed_claims)
    numbers = f" numbers={bullet.numbers}" if bullet.numbers else ""
    link_line = ""
    if bullet.links:
        anchors = ", ".join(f'"{link.anchor}"' for link in bullet.links)
        link_line = f"    keep_anchors_verbatim: {anchors}\n"
    return (
        f"  - id={bullet.id} (evidence={bullet.evidence_level}){numbers}\n"
        f"    source_text: {bullet.text}\n"
        f"{link_line}"
        f"    allowed_claims:\n{claims}"
    )


def _format_experiences(experiences: list[Experience]) -> str:
    out = []
    for exp in experiences:
        header = f"- id={exp.id} :: {exp.title} @ {exp.company} ({exp.start_date} → {exp.end_date})"
        out.append(header)
        for b in exp.bullets:
            out.append(_format_bullet(b))
    return "\n".join(out)


def _format_projects(projects: list[Project]) -> str:
    out = []
    for proj in projects:
        header = f"- id={proj.id} :: {proj.name}" + (f" ({proj.status})" if proj.status else "")
        out.append(header)
        if proj.keywords:
            out.append(f"  keywords: {', '.join(proj.keywords)}")
        for b in proj.bullets:
            out.append(_format_bullet(b))
    return "\n".join(out)


def _format_skill_catalog(profile: Profile) -> str:
    lines: list[str] = []
    for category in profile.skills.categories:
        lines.append(f"- {category.id} ({category.name}): {', '.join(category.skills)}")
    return "\n".join(lines)


def _format_core_skills(profile: Profile) -> str:
    if not profile.skills.core:
        return "- none"
    return "\n".join(
        f"- {category_id}: {', '.join(skills)}"
        for category_id, skills in profile.skills.core.items()
    )


def _format_matching_keywords(profile: Profile) -> str:
    if not profile.skills.matching_keywords:
        return "- none"
    return "\n".join(
        f"- {family}: {', '.join(keywords)}"
        for family, keywords in profile.skills.matching_keywords.items()
    )


def _term_supported_by_allowed_skill(term: str, allowed_skills: set[str]) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return True
    for skill in allowed_skills:
        skill_norm = skill.strip().lower()
        if not skill_norm:
            continue
        if len(skill_norm) <= 2:
            if normalized == skill_norm:
                return True
            continue
        if normalized == skill_norm:
            return True
        if skill_norm in normalized or normalized in skill_norm:
            return True
        if re.search(rf"(?<![a-z0-9]){re.escape(skill_norm)}(?![a-z0-9])", normalized):
            return True
    return False


def _format_unsupported_offer_terms(profile: Profile, analysis: JobAnalysis) -> str:
    """Terms from the offer that should not become candidate claims."""
    allowed = profile.skills.allowed_skills
    terms: list[str] = []
    seen: set[str] = set()
    for term in list(analysis.required_skills) + list(analysis.cv_keywords_to_include):
        clean = " ".join((term or "").split())
        key = clean.lower()
        if not clean or key in seen:
            continue
        seen.add(key)
        if key in NON_DISPLAY_DOMAIN_TERMS:
            continue
        if _term_supported_by_allowed_skill(clean, allowed):
            continue
        # Skip broad education phrases; they are not skills to claim or block.
        if "equivalent" in key or "education" in key or "degree" in key:
            continue
        terms.append(clean)
    if not terms:
        return "- none"
    return "\n".join(f"- {term}" for term in terms)


def build_user_prompt(
    *,
    profile: Profile,
    analysis: JobAnalysis,
    job_title: str,
    job_company: str,
    selected_experiences: list[Experience],
    selected_projects: list[Project],
) -> str:
    allowed = ", ".join(sorted(profile.skills.allowed_skills))
    style = profile.style_guide
    dont = "\n  - ".join(style.dont)
    do = "\n  - ".join(style.do)
    main_tasks_block = "\n".join(f"- {t}" for t in analysis.main_tasks)
    skill_profiles = format_skill_profiles(profile)
    skill_catalog = _format_skill_catalog(profile)
    core_skills = _format_core_skills(profile)
    matching_keywords = _format_matching_keywords(profile)
    unsupported_offer_terms = _format_unsupported_offer_terms(profile, analysis)

    return f"""Adapt this candidate's CV for the role below.

=== JOB ===
Title: {job_title}
Company: {job_company}
Role type: {analysis.role_type}
Seniority: {analysis.seniority}
Domain: {analysis.domain}
Main tasks (from offer):
{main_tasks_block}
Required skills (from offer): {', '.join(analysis.required_skills)}
Keywords to surface: {', '.join(analysis.cv_keywords_to_include)}

=== PROFILE (source of truth — do NOT invent) ===
allowed_skills: {allowed}
allowed_skills_by_category:
{skill_catalog}
core_skills_by_category:
{core_skills}
skill_profile_choices:
{skill_profiles}
matching_keywords_for_profile_selection_not_display:
{matching_keywords}
unsupported_offer_terms_not_to_claim:
{unsupported_offer_terms}
candidate_title: {profile.identity.title}
summary_source: {profile.identity.summary}

experiences (use the bullet `id` as source_id in your output):
{_format_experiences(selected_experiences)}

projects:
{_format_projects(selected_projects)}

=== STYLE ===
Tone: {style.tone}
Voice: {style.voice}
CV language: English only. Keep cv_title, professional_summary and CV bullets in English.
CV title: must be role-specific and contain a concrete anchor from the job title, role_type or main_tasks. Do not reuse a generic default title.
Professional summary: adapt it to the job, mention at least one concrete offer anchor, max {style.max_summary_lines} lines and max {style.max_summary_length} characters. Use only summary_source, experiences, projects and allowed_skills.
Experience output: include every provided experience and every bullet id exactly once. Rephrase only when faithful; otherwise keep the source bullet.
Do:
  - {do}
Don't:
  - {dont}

Produce a JSON conformant to the AdaptedCV schema. Keep every provided experience bullet; adapt only the wording where it remains faithful and useful. Anything you write about a bullet must be expressible by combining/paraphrasing its allowed_claims.

Project output rule:
- selected_project_ids must contain 2 to 4 projects.
- Include at least 3 only when 3 genuinely relevant projects are available.
- Rank projects by direct relevance to the job tasks, required skills and keywords.
- Do not pick a project only as filler.

Skills output rule:
- Fill selected_skills as a list of blocks: {{"category_id": "...", "skills": ["..."]}}.
- category_id must be one of the ids in allowed_skills_by_category.
- skills must be exact skill names from the matching allowed_skills_by_category block.
- Include every required or strongly requested offer skill that exists in allowed_skills.
- Use core_skills_by_category as a baseline only inside categories that are relevant to the offer.
- Use matching_keywords_for_profile_selection_not_display only for reasoning about the right skill profile/category; do not copy those keywords into selected_skills unless the exact term is also listed in allowed_skills_by_category.
- Treat unsupported_offer_terms_not_to_claim as a no-claim list. Do not put those terms in cv_title, professional_summary, selected_skills or rewritten bullets as candidate capabilities.
- Do not cap selected_skills by number, but do not pad the section. Every displayed skill must add value for this specific application.
"""
