"""Prompt builder for a combined CV adaptation + email draft call."""

from __future__ import annotations

from smartapply.llm.schemas import JobAnalysis
from smartapply.llm.prompts.cv_adaptation import (
    _format_core_skills,
    _format_experiences,
    _format_matching_keywords,
    _format_projects,
    _format_skill_catalog,
    _format_unsupported_offer_terms,
)
from smartapply.profile import Experience, Profile, Project


SYSTEM = """You adapt a candidate's CV and write the application email in one structured output.

Hard rules:
1. Every CV bullet MUST reference a real source_id from the provided list.
2. Every CV claim MUST come from the bullet's allowed_claims list.
3. Respect each bullet's evidence_level; be conservative for inferred claims.
4. Do NOT invent skills outside allowed_skills.
5. Do NOT change quantified results, dates, company names or project names.
6. The CV is ALWAYS in English, even when the job offer is in French.
7. Density rule (very important): default to the source bullet's exact phrasing — it is already dense and intentional. Only paraphrase when you can naturally surface an offer keyword without adding fluff. If the rewrite would be longer, heavier, or less natural than the source, keep the source bullet verbatim. Surfacing keywords is OPTIONAL.
8. When you do rephrase, you may only recombine/paraphrase the provided allowed_claims.
9. CV bullets must be concise (<= 220 chars) and relevant to this offer.
10. If a source bullet declares ``links``, keep each ``anchor`` token verbatim in your output bullet — the renderer wraps it as a hyperlink. Do not embed any markdown link or HTML tag yourself.
11. The professional_summary may be adapted to the offer, but must only use facts from the source profile.
12. The professional_summary must fit in 2 lines maximum and stay within the profile style length limit.
13. Choose exactly one skills_profile_id from the provided skill profile choices. Use matching_keywords only to understand the role family; they are NOT display skills.
14. The email body is also used as the motivation letter body; write complete, fluent, professional paragraphs.
15. The email/motivation letter body must be 120-170 words, plain and human, with no bullet list.
16. The email must cite one concrete project, stack or experience from the profile.
17. selected_skills is the exact Skills section to display. Build organized category blocks from allowed_skills_by_category only.
18. Skill selection strategy: include offer-required skills that exist in allowed_skills; add core/profile skills only when they strengthen the application for this offer; omit generic or unrelated skills even if the candidate has them.
19. Unsupported offer terms are a no-claim list: do not describe the candidate as having those skills in the summary, bullets, title, skills, email or warnings.
20. selected_project_ids must contain at least 3 relevant projects when available. Prefer overlap with job tasks, required skills and project evidence; avoid unrelated filler when a more relevant project exists.
21. Output ONLY the requested JSON. No prose, no commentary.
"""


def _format_skill_profiles(profile: Profile) -> str:
    if not profile.skills.profiles:
        return "- mixed: default compact skills profile"
    lines: list[str] = []
    for skill_profile in profile.skills.profiles:
        blocks = []
        for category_id, skills in skill_profile.category_skills.items():
            blocks.append(f"{category_id}: {', '.join(skills)}")
        description = f" — {skill_profile.description}" if skill_profile.description else ""
        lines.append(f"- {skill_profile.id}: {skill_profile.name}{description} ({'; '.join(blocks)})")
    return "\n".join(lines)


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
    project_hint = ", ".join(p.name for p in selected_projects[:3])
    skill_profiles = _format_skill_profiles(profile)
    skill_catalog = _format_skill_catalog(profile)
    core_skills = _format_core_skills(profile)
    matching_keywords = _format_matching_keywords(profile)
    unsupported_offer_terms = _format_unsupported_offer_terms(profile, analysis)

    return f"""Produce a complete application draft for this role.

=== JOB ===
Title: {job_title}
Company: {job_company}
Role type: {analysis.role_type}
Seniority: {analysis.seniority}
Domain: {analysis.domain}
Main tasks:
{main_tasks_block}
Required skills: {', '.join(analysis.required_skills)}
Keywords to surface: {', '.join(analysis.cv_keywords_to_include)}
Match reasons: {', '.join(analysis.match_reasons)}
Risks to avoid overclaiming: {', '.join(analysis.risks)}

=== PROFILE (source of truth — do NOT invent) ===
candidate_name: {profile.identity.full_name}
candidate_title: {profile.identity.title}
summary_source: {profile.identity.summary}
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

experiences (use bullet `id` as source_id in selected_experiences):
{_format_experiences(selected_experiences)}

projects:
{_format_projects(selected_projects)}

=== EMAIL ===
Email / motivation letter language: {"French" if language == "fr" else "English"}
Project hints for the email: {project_hint}
Subject: concise, mentions the role and the candidate name. The subject and body must both use the requested email language. For French, use "Candidature - ..." rather than "Application for ...".
Body: 120-170 words, natural, professional, no buzzwords, no bullet list, polite call to action.
Do not claim unsupported_offer_terms_not_to_claim as candidate skills in the email. If a required term is unsupported, simply emphasize adjacent allowed skills and concrete evidence.

=== STYLE ===
Tone: {style.tone}
Voice: {style.voice}
CV language: English only. Keep cv_title, professional_summary and CV bullets in English.
Professional summary: adapt it to the job, max {style.max_summary_lines} lines and max {style.max_summary_length} characters. Use only summary_source, experiences, projects and allowed_skills.
Do:
  - {do}
Don't:
  - {dont}

Return JSON conforming to ApplicationDraft:
- CV fields: cv_title, professional_summary, selected_experiences, selected_project_ids, skills_profile_id, selected_skills, skills_order, warnings.
- Email fields: email_subject, email_body.

Project output rule:
- selected_project_ids must include at least 3 projects when at least 3 candidate projects are provided.
- Rank projects by direct relevance to the job tasks, required skills and keywords.
- Do not pick a project only as filler when another provided project has stronger overlap.

Skills output rule:
- Fill selected_skills as a list of blocks: {{"category_id": "...", "skills": ["..."]}}.
- category_id must be one of the ids in allowed_skills_by_category.
- skills must be exact skill names from the matching allowed_skills_by_category block.
- Include every required or strongly requested offer skill that exists in allowed_skills.
- Use core_skills_by_category as a baseline only inside categories that are relevant to the offer.
- Use matching_keywords_for_profile_selection_not_display only for reasoning about the right skill profile/category; do not copy those keywords into selected_skills unless the exact term is also listed in allowed_skills_by_category.
- Treat unsupported_offer_terms_not_to_claim as a no-claim list. Do not put those terms in cv_title, professional_summary, selected_skills, rewritten bullets, email_subject or email_body as candidate capabilities.
- Do not cap selected_skills by number, but do not pad the section. Every displayed skill must add value for this specific application.
"""
