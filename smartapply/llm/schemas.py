"""Pydantic schemas for LLM structured outputs.

These define the EXACT shape we ask the model to produce — and that we
validate after the call. Keep them small, flat, and JSON-Schema friendly
(OpenAI strict mode rejects exotic types).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

_strict = ConfigDict(extra="forbid")


class JobAnalysis(BaseModel):
    model_config = _strict

    fit_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Overall fit of this job offer for the candidate, expressed as a number "
            "between 0 and 1."
        ),
    )
    role_type: str = Field(description="Concise role label, e.g. 'Data Scientist NLP'")
    seniority: str = Field(description="One of: junior, mid, senior, lead, manager")
    domain: str = Field(description="Industry / vertical the role sits in")
    main_tasks: list[str] = Field(description="3-7 concrete responsibilities, short bullets")
    required_skills: list[str] = Field(
        description=(
            "Hard skills explicitly requested or clearly listed in the offer body only. "
            "Do not add candidate-profile skills, broad domains, generic soft skills, "
            "or inferred keywords from the title."
        )
    )
    nice_to_have: list[str] = Field(description="Bonus skills appreciated but not required")
    match_reasons: list[str] = Field(description="Why this role matches the candidate")
    risks: list[str] = Field(
        description=(
            "Concrete gaps or risks for this candidate, including visible seniority, "
            "vague/short offer text, missing skills, peripheral BI/reporting, "
            "Data Engineering/platform, MLOps/DevOps, support/operations, Master Data, "
            "location or company ambiguity."
        )
    )
    cv_keywords_to_include: list[str] = Field(
        description=(
            "Offer-grounded CV keywords visible in or strongly supported by the offer body. "
            "Return a short list when few reliable keywords exist; do not add candidate-only "
            "skills, generic filler, or title-only inferences."
        )
    )
    offer_language: str = Field(
        default="fr",
        description=(
            "ISO 639-1 code of the language the offer is written in "
            "('fr', 'en', 'de', 'es', ...). Drives the motivation-letter language."
        ),
    )
    extracted_company_name: str = Field(
        default="",
        description=(
            "If the structured company field is missing, generic, or names a "
            "job board / recruitment intermediary instead of the real employer "
            "(e.g. 'Entreprise non communiquée', 'Confidentiel', 'Forums "
            "Talents Handicap', empty), extract the real hiring company name "
            "from the description text. Look for "
            'patterns like "L\'entreprise X recherche", "Notre client X", '
            '"Rejoignez X", "Nous sommes X", or a \'company-name - tagline\' '
            "header. Return only the company's name, no description. "
            "Return an empty string when no real name can be confidently "
            "extracted — never invent."
        ),
    )
    extracted_location: str = Field(
        default="",
        description=(
            "Most specific job location explicitly visible in the offer body, "
            "for example 'Paris', 'Massy', 'Remote (France)' or "
            "'Paris / Lyon'. Do not copy the structured scraper location unless "
            "the body confirms it. Return an empty string when the body gives no "
            "reliable location. Never infer or use external knowledge."
        ),
    )
    company_context: str = Field(
        default="",
        description=(
            "One concise, offer-body-grounded sentence about the company, product, "
            "sector, clients, team, culture or business context. Do not infer from "
            "company name, URL host or outside knowledge. Empty string when the body "
            "gives no reliable context."
        ),
    )
    offer_interest_points: list[str] = Field(
        default_factory=list,
        description=(
            "0-5 concrete reasons a candidate could be interested in this specific "
            "offer, extracted only from the offer body: company/about-us facts, "
            "product, mission, sector, context, stakes, team, clients, culture or "
            "responsibilities. Avoid generic filler and candidate claims. Empty list "
            "when only generic information is available."
        ),
    )


class AdaptedBullet(BaseModel):
    model_config = _strict

    source_id: str = Field(
        description=(
            "ID of the source profile bullet (must exactly match a bullet id "
            "from the candidate profile). REQUIRED — used by validator."
        )
    )
    text: str = Field(description="Rewritten bullet text, faithful to source")


class AdaptedExperience(BaseModel):
    model_config = _strict

    source_id: str = Field(description="ID of the source profile experience")
    bullets: list[AdaptedBullet]


class SkillSelectionBlock(BaseModel):
    model_config = _strict

    category_id: str = Field(description="Profile skill category id, e.g. ml_ai or data_infra")
    skills: list[str] = Field(description="Exact display skills selected from allowed_skills")


class AdaptedCV(BaseModel):
    model_config = _strict

    cv_title: str = Field(description="Headline shown under the candidate name")
    professional_summary: str = Field(
        description=(
            "Offer-adapted professional summary, max 2 lines and grounded only "
            "in the candidate profile."
        )
    )
    selected_experiences: list[AdaptedExperience] = Field(
        description="Experiences to keep, in order"
    )
    selected_project_ids: list[str] = Field(
        description=(
            "IDs of profile projects to keep. Select 2 to 4 relevant projects "
            "when at least 2 useful profile projects are available; include a "
            "third or fourth project only when it adds clear value for the role."
        )
    )
    skills_profile_id: str = Field(
        default="",
        description=(
            "ID of the skill display profile to use in the CV skills section, "
            "e.g. mixed, llm, machine_learning, reinforcement_learning, data_analyst."
        ),
    )
    selected_skills: list[SkillSelectionBlock] = Field(
        default_factory=list,
        description=(
            "Exact skills to display in the CV, grouped by profile skill category id. "
            "Each skill must come from allowed_skills. Include every offer-required "
            "skill that exists in the candidate whitelist."
        ),
    )
    skills_order: list[str] = Field(
        description="Ordered list of profile skill category ids — most relevant first"
    )
    warnings: list[str] = Field(
        description="Any concern the model wants to surface to the validator"
    )


class MotivationLetter(BaseModel):
    model_config = _strict

    subject: str = Field(description="Motivation letter subject line")
    body: str = Field(
        description=(
            "220-300 words, natural and professional. Must be grounded in the "
            "selected CV/project evidence."
        )
    )


class MotivationLetterRepair(BaseModel):
    """Targeted replacement for a motivation-letter body."""

    model_config = _strict

    body: str = Field(
        description=(
            "Repaired motivation-letter body only. Preserve the original language "
            "and facts while correcting the single requested defect."
        )
    )


class FormQuestionAnswer(BaseModel):
    model_config = _strict

    question: str = Field(description="Original form question, copied or normalized")
    answer: str = Field(description="Candidate-ready answer, plain text, no markdown")
    evidence_used: list[str] = Field(
        description="Concrete profile/job evidence used to justify this answer"
    )
    warnings: list[str] = Field(
        description="Grounding warnings, missing context or claims to verify manually"
    )


class FormQuestionAnswers(BaseModel):
    model_config = _strict

    answers: list[FormQuestionAnswer] = Field(
        description="One answer per detected form question, preserving question order"
    )
    global_warnings: list[str] = Field(
        description="Overall warnings that apply to the generated answer set"
    )


class ApplicationDraft(BaseModel):
    model_config = _strict

    cv_title: str = Field(description="Headline shown under the candidate name")
    professional_summary: str = Field(
        description=(
            "Offer-adapted professional summary, max 2 lines and grounded only "
            "in the candidate profile."
        )
    )
    selected_experiences: list[AdaptedExperience] = Field(
        description="Experiences to keep, in order"
    )
    selected_project_ids: list[str] = Field(
        description=(
            "IDs of profile projects to keep. Select 2 to 4 relevant projects "
            "when at least 2 useful profile projects are available; include a "
            "third or fourth project only when it adds clear value for the role."
        )
    )
    skills_profile_id: str = Field(
        default="",
        description=(
            "ID of the skill display profile to use in the CV skills section, "
            "e.g. mixed, llm, machine_learning, reinforcement_learning, data_analyst."
        ),
    )
    selected_skills: list[SkillSelectionBlock] = Field(
        default_factory=list,
        description=(
            "Exact skills to display in the CV, grouped by profile skill category id. "
            "Each skill must come from allowed_skills. Include every offer-required "
            "skill that exists in the candidate whitelist."
        ),
    )
    skills_order: list[str] = Field(
        description="Ordered list of profile skill category ids — most relevant first"
    )
    warnings: list[str] = Field(
        description="Any concern the model wants to surface to the validator"
    )
    motivation_letter_subject: str = Field(description="Motivation letter subject line")
    motivation_letter_body: str = Field(
        description=(
            "Natural and professional motivation letter, usually 250-350 words. "
            "Must reuse evidence from selected_experiences or selected_project_ids "
            "without going into project details."
        )
    )

    def to_cv(self) -> AdaptedCV:
        return AdaptedCV(
            cv_title=self.cv_title,
            professional_summary=self.professional_summary,
            selected_experiences=self.selected_experiences,
            selected_project_ids=self.selected_project_ids,
            skills_profile_id=self.skills_profile_id,
            selected_skills=self.selected_skills,
            skills_order=self.skills_order,
            warnings=self.warnings,
        )

    def to_motivation_letter(self) -> MotivationLetter:
        return MotivationLetter(
            subject=self.motivation_letter_subject,
            body=self.motivation_letter_body,
        )
