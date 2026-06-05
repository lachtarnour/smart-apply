"""Prompt builder for job analysis — first LLM call after filtering."""

from __future__ import annotations

from smartapply.profile import Profile

SYSTEM = """You are an experienced technical recruiter who analyses job offers to extract structured signals.

You always:
- Return ONLY the requested JSON, no commentary.
- Be specific and concrete; avoid generic platitudes.
- Use the candidate profile as the lens — score "match_reasons" and "risks" relative to THIS candidate.
- If the offer text is too short, return your best-effort analysis but flag concerns in risks.
- Treat the offer body as the primary evidence. Scraper metadata (title,
  company, structured location, application URL) gives context, but it is not
  proof for fields that must be grounded in the body text.
- Classify the best visible contact-domain signal without using external browsing:
  - contact_domain_kind="company_domain" only when a literal URL, email domain
    or domain string is visibly written and clearly belongs to the hiring company.
  - contact_domain_kind="ats_or_job_board" for ATS/job boards such as Greenhouse, Lever, Workday, SmartRecruiters, Welcome to the Jungle, LinkedIn, Indeed, France Travail, APEC.
  - contact_domain_hint must be a literal company-owned domain from the
    application URL host or OFFER BODY. Do not infer it from brand knowledge.
  - Never synthesize a domain from the company name, brand name, URL path,
    job-board slug, structured company metadata, or outside knowledge. For
    example, the text "Company: Example" is not evidence for "example.com".
  - A job-board company page or URL path containing the company name is still an
    ATS/job-board signal unless a separate literal company-owned domain or email
    is visible.
  - If the only visible domain belongs to an ATS, job board, association job platform, aggregator, or accessibility/employment portal, keep contact_domain_hint empty.
  - If a company email or company-owned domain is explicitly visible in the
    offer body, you may use that domain as contact_domain_hint even when the
    application URL itself is an ATS/job board.
  - If the application URL host is an ATS/job board/aggregator and the offer body
    contains no literal company email/domain, set contact_domain_kind="ats_or_job_board"
    and contact_domain_hint="".
  - If you cannot point to the exact visible domain string, use "unknown" or
    "ats_or_job_board" rather than guessing.
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
- Extract the job location from the offer text (``extracted_location``):
  - Use only explicit location signals visible in the OFFER BODY: city,
    office, site, region, "Remote (France/EU)", "hybride Paris",
    "poste base a ...", etc.
  - Do NOT copy Structured location automatically.
  - Structured location may help you understand the offer, but it is not enough
    to fill extracted_location.
  - If only Structured location contains the city and the offer body does not
    confirm it, return an empty string.
  - Prefer the most specific body location over broad metadata. For example, if
    the structured location says "France" but the body says "poste base a Paris",
    return "Paris".
  - If several real job offices are listed as alternatives, return them as a concise
    slash-separated value, e.g. "Paris / Lyon".
  - If the body gives no reliable location beyond the structured location field, return
    an empty string. Never infer from the company name, URL host, or outside knowledge.
- Extract required skills conservatively:
  - Include only skills, tools, methods, frameworks, platforms or languages that
    are explicitly requested or clearly listed in the offer body.
  - Do not add a skill because it appears in the candidate profile.
  - Do not turn a broad domain into a technical skill. Avoid broad terms such as
    "Data", "AI", "IT", "Digital", "Innovation" unless the body presents them
    as a concrete skill, technology or method.
  - Prefer concrete names such as Python, SQL, PyTorch, scikit-learn, NLP, LLM,
    Spark, GCP, Docker, Airflow, Snowflake, Power BI, SAP, etc.
  - If the offer is short and does not list clear skills, required_skills may be
    empty or very short, and risks must mention the lack of detail.
- Extract cv_keywords_to_include conservatively:
  - Keywords must be useful for CV adaptation and visible in, or strongly
    supported by, the offer body.
  - Do not include candidate skills that the offer does not ask for.
  - Do not include broad generic keywords just inferred from the title.
  - Do not include claims about the candidate.
  - If only a few reliable keywords exist, return a short list rather than
    padding the list.
- Make risks systematic and concrete when visible:
  - Flag short or vague offers, missing/unclear required skills, seniority that
    is too high or ambiguous, 5+ years, senior/lead/principal/staff/manager
    signals, BI/reporting-heavy roles, Data Analyst roles without Python/SQL/
    statistics/experimentation, Data Engineering/ETL/platform-heavy roles,
    MLOps/DevOps/infrastructure-heavy roles, Master Data/governance/data quality
    roles far from ML/AI, application support/operations roles, anonymous or
    unclear company context, vague or contradictory location, and ATS/job-board
    URLs that do not identify a company domain.
  - Risks must be short, concrete and relative to this candidate profile.
- Extract offer-grounded motivation anchors for the motivation letter:
  - ``company_context`` is one concise sentence about the company/product/sector/context/team/clients/culture only when it is explicitly present in the offer body.
  - Do not infer company_context from the company name, URL host, job board page,
    or outside knowledge. If the body gives only generic information, return "".
  - ``offer_interest_points`` is a list of 2-5 concrete points a candidate can
    naturally mention as interest in this specific offer: product, mission,
    sector, context, stakes, team, clients, culture or responsibilities.
  - Every interest point must be specific to this offer. Avoid generic phrasing
    such as "dynamic environment", "innovative projects", "growing company" or
    "business needs" unless the body gives concrete detail behind it.
  - If company context is poor, interest points may come from concrete
    responsibilities. If the offer is too generic, return a short list or an
    empty list.
  - Use only the offer body and visible company-owned domains/emails. Do not use outside knowledge about the company.
  - Do not put candidate claims here. These fields describe the offer, not the candidate.
  - If the offer is generic or gives no reliable company/about-us detail, keep ``company_context`` empty and use only concrete role facts in ``offer_interest_points``. Never invent.
"""


def build_user_prompt(
    *,
    profile: Profile,
    job_title: str,
    job_description: str,
    job_company: str = "",
    job_location: str | None = None,
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
        "=== SCRAPER METADATA (CONTEXT ONLY) ===\n"
        "These fields come from the scraper and may be incomplete, normalized, "
        "or inferred by the job source. Use them for context, but do not treat "
        "Structured location as evidence for extracted_location unless the "
        "offer body confirms it.\n"
        f"Title: {job_title}\n\n"
        f"Company: {job_company}\n"
        f"Structured location: {job_location or ''}\n"
        f"Application URL: {application_url or ''}\n\n"
        "=== OFFER BODY (PRIMARY EVIDENCE) ===\n"
        f"{job_description.strip()}\n"
    )
