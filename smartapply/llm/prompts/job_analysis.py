"""Prompt builder for job analysis — first LLM call after filtering."""

from __future__ import annotations

from smartapply.profile import Profile


SYSTEM = """You are an experienced technical recruiter who analyses job offers to extract structured signals.

You always:
- Return ONLY the requested JSON, no commentary.
- Be specific and concrete; avoid generic platitudes.
- Use the candidate profile as the lens — score "match_reasons" and "risks" relative to THIS candidate.
- If the offer text is too short, return your best-effort analysis but flag concerns in risks.
- Classify the application URL for contact search without using external browsing:
  - contact_domain_kind="company_domain" only when the URL host clearly belongs to the hiring company.
  - contact_domain_kind="ats_or_job_board" for ATS/job boards such as Greenhouse, Lever, Workday, SmartRecruiters, Welcome to the Jungle, LinkedIn, Indeed, France Travail, APEC.
  - contact_domain_hint must be a visible company-owned domain from the URL or offer text. Do not infer it from brand knowledge.
- Detect the language the offer is WRITTEN in (not the languages required from the candidate).
  Use an ISO 639-1 code: "fr" for French, "en" for English, "de" for German, "es" for Spanish, etc.
  The CV stays in English in every case — this field only drives the email/motivation letter language.
- Classify the hiring company size:
  - "large": multinational, listed group, public-sector institution, well-known brand, ~500+ employees
    (examples: Safran, BNP Paribas, L'Oréal, Doctolib, Capgemini, Société Générale, Orange).
    Large companies usually require a formal ATS application even when you have an email contact.
  - "small": startup, scale-up, SME, ESN, consultancy, or any smaller firm — an email is enough.
  - "unknown": you genuinely cannot tell from the offer text and the candidate-provided URL.
  Use only the signals visible in the offer text and URL host. Do NOT infer from brand knowledge alone.
  Add one short sentence in ``company_size_reason``.
- Resolve the real hiring entity name (``extracted_company_name``):
  - When the structured "Company:" field is empty, "Confidentiel", or "Entreprise non communiquée", scan the description for the real hiring entity. The entity can be a company, an ESN, a consultancy, a government agency, a ministry, a public institution, an NGO or a university — anything that has a real name in the text counts.
  - Look in this order:
    1. The "À propos de l'entreprise :" block at the very top of the description, if any.
    2. Explicit cues such as "L'entreprise X recherche", "Notre client X", "Rejoignez X", "Nous sommes X", "X recrute".
    3. A "Name - tagline" or "Name, tagline" header.
    4. A parenthetical acronym after a full name like "Agence ministérielle pour l'intelligence artificielle de défense (AMIAD)" — in this case the acronym (AMIAD) is the canonical short name; prefer it when it exists.
  - When the structured "Company:" field already looks like a real entity name, echo it back here unchanged (do NOT substitute it with something else found in the description).
  - When no real name can be confidently extracted from the actual text, return an empty string. Never invent and never guess from brand knowledge alone (e.g. "72000 employees in 68 countries" → do NOT output "Atos" unless the text literally names it).
  - Return only the entity name itself, no extra words ("Wavestone", not "the company Wavestone"; "AMIAD", not "Agence AMIAD").
"""


def build_user_prompt(
    *,
    profile: Profile,
    job_title: str,
    job_description: str,
    job_company: str = "",
    application_url: str | None = None,
) -> str:
    profile_block = (
        f"Candidate title: {profile.identity.title}\n"
        f"Summary: {profile.identity.summary}\n"
        f"Skills: {', '.join(sorted(profile.skills.allowed_skills))}\n"
        f"Target roles: {', '.join(profile.preferences.target_roles)}\n"
        f"Seniority: {profile.preferences.seniority or 'unspecified'}\n"
        f"Preferred locations: {', '.join(profile.preferences.preferred_locations)}\n"
    )
    return (
        "Analyze the following job offer and extract structured fields.\n\n"
        "=== CANDIDATE ===\n"
        f"{profile_block}\n"
        "=== JOB OFFER ===\n"
        f"Title: {job_title}\n\n"
        f"Company: {job_company}\n"
        f"Application URL: {application_url or ''}\n\n"
        f"{job_description.strip()}\n"
    )
