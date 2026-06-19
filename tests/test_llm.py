"""Tests for the LLM module — schemas, mock provider, cache key, usage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from smartapply.llm import (
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    ApplicationDraft,
    EmailDraft,
    JobAnalysis,
    LLMError,
    MockLLMProvider,
    estimate_cost_usd,
    get_llm_provider,
    make_cache_key,
)
from smartapply.llm.analyzer_input import AnalyzerInput, build_analyzer_input
from smartapply.llm.prompts import job_analysis
from smartapply.llm.source_metadata import (
    build_analyzer_source_metadata,
    build_francetravail_source_metadata,
    build_serpapi_source_metadata,
    build_wttj_source_metadata,
    register_source_metadata_builder,
)

# ---------------- Schemas ----------------


def test_job_analysis_schema_round_trip() -> None:
    a = JobAnalysis(
        role_type="Data Scientist NLP",
        seniority="mid",
        domain="HealthTech",
        main_tasks=["Build pipelines"],
        required_skills=["Python", "PyTorch"],
        nice_to_have=["AWS"],
        match_reasons=["Strong NLP background"],
        risks=["No prod deploy experience"],
        cv_keywords_to_include=["PyTorch", "RAG"],
        extracted_location="Paris",
        company_context="Acme builds clinical AI products for hospital teams.",
        offer_interest_points=[
            "Improve medical knowledge access with RAG",
            "Work with product and clinical stakeholders",
        ],
    )
    raw = a.model_dump_json()
    assert "Data Scientist" in raw
    assert "clinical AI products" in raw
    assert "Paris" in raw
    b = JobAnalysis.model_validate_json(raw)
    assert b == a


def test_job_analysis_prompt_includes_structured_location() -> None:
    from smartapply.profile import get_profile

    prompt = job_analysis.build_user_prompt(
        profile=get_profile(),
        job_title="Data Scientist",
        job_company="Acme",
        job_location="France",
        application_url="https://acme.ai/jobs/42",
        job_description="Poste base a Paris, rythme hybride.",
    )

    assert "Structured location (metadata only; do not copy into extracted_location): France" in prompt
    assert "Poste base a Paris" in prompt
    assert "extracted_location" in job_analysis.SYSTEM


def _metadata_line(metadata: str, source_field: str) -> str:
    for line in metadata.splitlines():
        if f"source_field={source_field}" in line:
            return line
    raise AssertionError(f"Missing metadata URL line for {source_field}")


def test_francetravail_source_metadata_classifies_contact_and_application_urls() -> None:
    metadata = build_francetravail_source_metadata(
        {
            "id": "206GJTL",
            "entreprise": {
                "nom": "CIRIL GROUP",
                "url": "https://www.cirilgroup.com/fr/recrutement.html",
                "description": "Long company description already included elsewhere.",
            },
            "origineOffre": {
                "origine": 1,
                "urlOrigine": "https://candidat.francetravail.fr/offres/recherche/detail/206GJTL",
                "partenaires": [
                    {"nom": "Broadbean", "url": "https://www.aplitrak.com/?adid=abc"},
                ],
            },
            "contact": {
                "nom": "Service recrutement",
                "courriel": "jobs@cirilgroup.com",
                "urlPostulation": "https://taleez.com/apply/data-engineer/applying",
                "coordonnees1": "Postuler ici: https://candidat.francetravail.fr/offres/recherche/detail/206GJTL",
            },
        }
    )

    assert "CONTACT_AND_APPLICATION_METADATA" in metadata
    assert "source: francetravail" in metadata
    assert "raw_id: 206GJTL" in metadata
    assert "entreprise.nom: CIRIL GROUP" in metadata
    assert "contact.nom: Service recrutement" in metadata
    assert "contact.courriel: jobs@cirilgroup.com" in metadata

    company = _metadata_line(metadata, "entreprise.url")
    assert "domain=cirilgroup.com" in company
    assert "url_kind=company_url" in company
    assert "company_domain_candidate=cirilgroup.com" in company

    postulation = _metadata_line(metadata, "contact.urlPostulation")
    assert "domain=taleez.com" in postulation
    assert "url_kind=ats" in postulation
    assert "company_domain_candidate" not in postulation

    coordonnees = _metadata_line(metadata, "contact.coordonnees1")
    assert "domain=francetravail.fr" in coordonnees
    assert "url_kind=francetravail" in coordonnees
    assert "company_domain_candidate" not in coordonnees

    partner = _metadata_line(metadata, "origineOffre.partenaires[0].url")
    assert "domain=aplitrak.com" in partner
    assert "url_kind=ats" in partner
    assert "company_domain_candidate" not in partner

    origin = _metadata_line(metadata, "origineOffre.urlOrigine")
    assert "url_kind=francetravail" in origin


def test_francetravail_source_metadata_includes_structured_job_facts() -> None:
    metadata = build_francetravail_source_metadata(
        {
            "experienceExige": "D",
            "experienceLibelle": "3 An(s)",
            "_smartapply_experience": {"required": True, "min_months": 36},
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "dureeTravailLibelle": "35H Travail en journée",
            "salaire": {"libelle": "Annuel de 45000 Euros à 55000 Euros"},
            "secteurActiviteLibelle": "Conseil en systèmes informatiques",
            "trancheEffectifEtab": "50 à 99 salariés",
            "nombrePostes": 1,
            "formations": [{"niveauLibelle": "Bac+5", "domaineLibelle": "Data science"}],
            "langues": [{"libelle": "Anglais", "exigence": "Exigé"}],
            "competences": [{"libelle": "Python", "exigence": "Exigé"}],
            "qualitesProfessionnelles": [{"libelle": "Rigueur", "description": "Capacité à..."}],
            "deplacementLibelle": "Ponctuels Zone nationale",
            "contexteTravail": {"horaires": "Hybride", "conditions": "Open space"},
        }
    )

    assert "STRUCTURED_JOB_FACTS" in metadata
    assert "experienceExige: D" in metadata
    assert "experienceLibelle: 3 An(s)" in metadata
    assert "_smartapply_experience:" in metadata
    assert "typeContratLibelle: CDI" in metadata
    assert "salaire:" in metadata
    assert "formations: Bac+5 / Data science" in metadata
    assert "langues: Anglais / Exigé" in metadata
    assert "competences: Python / Exigé" in metadata
    assert "qualitesProfessionnelles: Rigueur / Capacité à..." in metadata
    assert "contexteTravail:" in metadata


def test_francetravail_source_metadata_extracts_visible_company_url_from_description_only() -> None:
    metadata = build_francetravail_source_metadata(
        {
            "id": "3176602",
            "entreprise": {"nom": "IPPON Technologies"},
            "description": "Actualités techniques visibles sur https://blog.ippon.fr/data-ai.",
            "origineOffre": {
                "urlOrigine": "https://candidat.francetravail.fr/offres/recherche/detail/3176602",
            },
        }
    )

    line = _metadata_line(metadata, "description")
    assert "domain=ippon.fr" in line
    assert "url_kind=company_url" in line
    assert "company_domain_candidate=ippon.fr" in line


def test_wttj_source_metadata_includes_contact_and_company_facts() -> None:
    metadata = build_wttj_source_metadata(
        {
            "company_website": "https://www.phagos.org",
            "company_domain": "phagos.org",
            "company_profile_url": "https://www.welcometothejungle.com/fr/companies/phagos-1",
            "company_summary": "Phagos développe des thérapies contre les infections bactériennes.",
            "workplace": "Suresnes, France",
            "skills": ["Python", "SQL", "Machine Learning"],
            "employment_type": "FULL_TIME",
            "remote_text": "Télétravail fréquent",
            "valid_through": "2026-08-25T22:01:01.000Z",
            "experience_level": "3_TO_4_YEARS",
            "profession": {
                "category_name": {"fr": "Technologie et ingénierie", "en": "Tech & Engineering"},
                "sub_category_name": {"fr": "Données/Business Intelligence", "en": "Data / Business Intelligence"},
            },
            "salary": {"min": 45000, "max": 50000, "currency": "EUR", "period": "yearly"},
            "detail_api": {
                "apply_url": "https://phagos.welcomekit.co/jobs/business-data",
                "ats": "wkit",
                "skills": [
                    {
                        "name": {
                            "fr": "Communication",
                            "en": "Communication skills",
                        }
                    }
                ],
                "tools": [{"name": "Python"}, {"name": "SQL"}],
            },
            "matches_api": {
                "contract_type": "full_time",
                "remote": "partial",
                "published_at": "2026-06-01T10:00:00Z",
                "experience_min": 3.0,
                "experience_max": 4.0,
            },
            "company_profile": {
                "sectors": "Intelligence artificielle / Machine Learning, Santé",
                "offices": "Paris",
                "stats": {"employees": "50", "founded": "2021"},
                "presentation": "Phagos travaille sur les phages.",
            },
        }
    )

    assert "CONTACT_AND_APPLICATION_METADATA" in metadata
    assert "source: welcometothejungle" in metadata
    assert "company_domain: phagos.org" in metadata
    assert "detail_api.ats: wkit" in metadata
    assert "source_field=company_website" in metadata
    assert "domain=phagos.org" in metadata
    assert "url_kind=company_url" in metadata
    assert "source_field=detail_api.apply_url" in metadata
    assert "domain=welcomekit.co" in metadata
    assert "STRUCTURED_JOB_FACTS" in metadata
    assert "matches_api.contract_type: full_time" in metadata
    assert "matches_api.remote: partial" in metadata
    assert "experience_level: 3_TO_4_YEARS" in metadata
    assert "matches_api.experience_min: 3.0" in metadata
    assert "matches_api.experience_max: 4.0" in metadata
    assert "salary: currency=EUR; max=50000; min=45000; period=yearly" in metadata
    assert "workplace: Suresnes, France" in metadata
    assert "skills: Communication" in metadata
    assert "tools: Python; SQL" in metadata
    assert "profession: Technologie et ingénierie / Données/Business Intelligence" in metadata
    assert "company_profile.sectors: Intelligence artificielle / Machine Learning, Santé" in metadata
    assert "company_profile.stats: employees=50; founded=2021" in metadata
    assert '"matches_api"' not in metadata


def test_wttj_source_metadata_normalizes_localized_skill_dicts() -> None:
    metadata = build_wttj_source_metadata(
        {
            "skills": [
                "{'cs': 'Komunikační dovednosti', 'en': 'Communication skills', 'fr': 'Communication'}",
                "Python",
            ],
        },
        fields={"skills"},
    )

    assert "skills: Communication; Python" in metadata
    assert "{'cs':" not in metadata


def test_wttj_source_metadata_fields_are_configurable() -> None:
    metadata = build_wttj_source_metadata(
        {
            "company_website": "https://www.phagos.org",
            "company_domain": "phagos.org",
            "skills": ["Python"],
            "company_profile": {"presentation": "Do not include this."},
        },
        fields={"company_domain", "skills"},
    )

    assert "company_domain: phagos.org" in metadata
    assert "skills: Python" in metadata
    assert "company_website" not in metadata
    assert "Do not include this." not in metadata


def test_serpapi_source_metadata_includes_compact_source_signals() -> None:
    metadata = build_serpapi_source_metadata(
        {
            "title": "Data Scientist Expert IA & Machine Learning H/F",
            "company_name": "StarClay",
            "location": "Paris, France",
            "share_link": "https://www.google.com/search?q=jobs",
            "apply_options": [
                {"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/123"},
                {"title": "Company site", "link": "https://jobs.starclay.fr/apply"},
            ],
            "detected_extensions": {
                "schedule_type": "Full-time",
                "work_from_home": True,
                "posted_at": "3 days ago",
            },
            "_smartapply_search": {
                "result_origin": "fallback",
                "strict_chips": "date_posted:week",
                "fallback_reason": "low_result_strict_filters",
            },
            "job_highlights": [
                {
                    "title": "Responsibilities",
                    "items": [
                        "Build NLP and computer vision models.",
                        "Monitor and retrain machine-learning systems.",
                    ],
                },
                {
                    "title": "Qualifications",
                    "items": ["Python", "SQL", "MLOps"],
                },
            ],
        }
    )

    assert "CONTACT_AND_APPLICATION_METADATA" in metadata
    assert "source: serpapi" in metadata
    assert "company_name: StarClay" in metadata
    assert "apply_options: LinkedIn; Company site" in metadata
    assert "source_field=apply_options[0].link" in metadata
    assert "domain=linkedin.com" in metadata
    assert "url_kind=partner_job_board" in metadata
    assert "source_field=apply_options[1].link" in metadata
    assert "company_domain_candidate=starclay.fr" in metadata
    assert "search.result_origin: fallback" in metadata
    assert "STRUCTURED_JOB_FACTS" in metadata
    assert "detected_extensions.schedule_type: Full-time" in metadata
    assert "detected_extensions.work_from_home: True" in metadata
    assert "job_highlights.Responsibilities: Build NLP and computer vision models." in metadata
    assert "MOTIVATION_ANCHORS" in metadata
    assert '"job_highlights"' not in metadata
    assert "{'title'" not in metadata


def test_serpapi_source_metadata_empty_when_no_useful_fields() -> None:
    assert build_serpapi_source_metadata({"url": "https://example.com"}) == ""


def test_analyzer_source_metadata_uses_wttj_builder() -> None:
    job = SimpleNamespace(
        source="welcometothejungle",
        source_data={
            "company_domain": "okeiro.com",
            "skills": ["Python"],
            "company_profile": {"sectors": "SaaS / Cloud Services, Santé"},
        },
    )

    metadata = build_analyzer_source_metadata(job)

    assert "source: welcometothejungle" in metadata
    assert "company_domain: okeiro.com" in metadata
    assert "company_profile.sectors: SaaS / Cloud Services, Santé" in metadata


def test_analyzer_source_metadata_uses_serpapi_builder() -> None:
    job = SimpleNamespace(
        source="serpapi",
        source_data={
            "company_name": "StarClay",
            "detected_extensions": {"schedule_type": "Full-time"},
        },
    )

    metadata = build_analyzer_source_metadata(job)

    assert "source: serpapi" in metadata
    assert "company_name: StarClay" in metadata
    assert "detected_extensions.schedule_type: Full-time" in metadata


def test_analyzer_source_metadata_unknown_source_returns_empty() -> None:
    job = SimpleNamespace(source="unknown_api", source_data={"url": "https://example.com"})

    assert build_analyzer_source_metadata(job) == ""


def test_build_analyzer_input_normalizes_common_job_fields() -> None:
    job = SimpleNamespace(
        title="Data Scientist",
        company="Acme",
        location="France",
        application_url="https://acme.ai/jobs/42",
        cleaned_description="Clean offer body.",
        description="Raw offer body.",
        source="serpapi",
        source_data={"url": "https://example.com"},
    )

    analyzer_input = build_analyzer_input(job)

    assert analyzer_input == AnalyzerInput(
        title="Data Scientist",
        company="Acme",
        location="France",
        application_url="https://acme.ai/jobs/42",
        offer_body="Clean offer body.",
        source="serpapi",
        source_metadata="",
    )


def test_build_analyzer_input_adds_wttj_company_context_to_offer_body() -> None:
    job = SimpleNamespace(
        title="Senior Data Scientist",
        company="Bureau des Talents",
        location="Puteaux",
        application_url="https://www.welcometothejungle.com/fr/companies/acme/jobs/senior-ds",
        cleaned_description="Description\nBuild RAG and LLM systems.",
        description="Raw body.",
        source="welcometothejungle",
        source_data={
            "detail_api": {
                "company_description": (
                    "<p>Le Bureau des Talents accompagne des scale-ups.</p>"
                    "<p>Le poste est basé proche de la Défense dans le 92.</p>"
                )
            }
        },
    )

    analyzer_input = build_analyzer_input(job)

    assert analyzer_input.offer_body.startswith("Description\nBuild RAG and LLM systems.")
    assert "Company context" in analyzer_input.offer_body
    assert "Le Bureau des Talents accompagne des scale-ups." in analyzer_input.offer_body
    assert "Le poste est basé proche de la Défense dans le 92." in analyzer_input.offer_body
    assert "<p>" not in analyzer_input.offer_body


def test_build_analyzer_input_does_not_duplicate_wttj_company_context() -> None:
    company_context = "Le Bureau des Talents accompagne des scale-ups."
    job = SimpleNamespace(
        title="Senior Data Scientist",
        company="Bureau des Talents",
        location="Puteaux",
        application_url=None,
        cleaned_description=f"Description\nBuild RAG systems.\n\n{company_context}",
        description="Raw body.",
        source="welcometothejungle",
        source_data={"detail_api": {"company_description": f"<p>{company_context}</p>"}},
    )

    analyzer_input = build_analyzer_input(job)

    assert analyzer_input.offer_body.count(company_context) == 1
    assert "Company context" not in analyzer_input.offer_body


def test_build_analyzer_input_uses_registered_source_metadata_builder() -> None:
    def custom_builder(source_data):
        assert source_data == {"contract": "CDI"}
        return "STRUCTURED_JOB_FACTS:\ncontract: CDI"

    register_source_metadata_builder("custom_api", custom_builder)
    job = SimpleNamespace(
        title="ML Engineer",
        company="Acme",
        location=None,
        application_url=None,
        cleaned_description=None,
        description="Offer body.",
        source="custom_api",
        source_data={"contract": "CDI"},
    )

    analyzer_input = build_analyzer_input(job)

    assert analyzer_input.source_metadata == "STRUCTURED_JOB_FACTS:\ncontract: CDI"


def test_source_metadata_does_not_include_raw_json_or_long_descriptions() -> None:
    metadata = build_francetravail_source_metadata(
        {
            "id": "1",
            "description": "Main offer body without URL.",
            "entreprise": {
                "description": "Very long company description that should not be copied into metadata.",
            },
            "competences": [{"libelle": "Python", "exigence": "Exigé", "extra": "ignored"}],
        }
    )

    assert "Very long company description" not in metadata
    assert "Main offer body without URL" not in metadata
    assert '"competences"' not in metadata
    assert "{'libelle'" not in metadata
    assert "Python / Exigé" in metadata


def test_job_analysis_prompt_includes_source_metadata_rules_when_provided() -> None:
    from smartapply.profile import get_profile

    prompt = job_analysis.build_user_prompt(
        profile=get_profile(),
        job_title="Data Engineer",
        job_company="CIRIL GROUP",
        job_location="Lyon",
        application_url="https://candidat.francetravail.fr/offres/recherche/detail/206GJTL",
        source_metadata="CONTACT_AND_APPLICATION_METADATA:\nsource: francetravail",
        job_description="Offer body.",
    )

    assert "=== SOURCE-SPECIFIC STRUCTURED METADATA ===" in prompt
    assert "Do not use this block to invent required_skills or cv_keywords_to_include" in prompt
    assert "Structured metadata complements the offer body" in prompt
    assert "Keep concrete offer-body use cases in cv_keywords_to_include" in prompt
    assert "business rules, reports, and data quality" in prompt
    assert "a recruiting agency with an anonymous client" in prompt
    assert "Do not infer or synthesize company domains" in prompt
    assert "CONTACT_AND_APPLICATION_METADATA" in prompt


def test_job_analysis_prompt_unchanged_without_source_metadata() -> None:
    from smartapply.profile import get_profile

    kwargs = {
        "profile": get_profile(),
        "job_title": "Data Scientist",
        "job_company": "Acme",
        "job_location": "France",
        "application_url": "https://acme.ai/jobs/42",
        "job_description": "Poste base a Paris.",
    }
    without = job_analysis.build_user_prompt(**kwargs)
    empty = job_analysis.build_user_prompt(**kwargs, source_metadata="")

    assert without == empty
    assert "SOURCE-SPECIFIC STRUCTURED METADATA" not in without


def test_job_analysis_prompt_from_analyzer_input_matches_legacy_builder() -> None:
    from smartapply.profile import get_profile

    profile = get_profile()
    analyzer_input = AnalyzerInput(
        title="Data Scientist",
        company="Acme",
        location="France",
        application_url="https://acme.ai/jobs/42",
        offer_body="Poste base a Paris.",
        source="serpapi",
        source_metadata="",
    )

    legacy = job_analysis.build_user_prompt(
        profile=profile,
        job_title="Data Scientist",
        job_company="Acme",
        job_location="France",
        application_url="https://acme.ai/jobs/42",
        job_description="Poste base a Paris.",
    )
    canonical = job_analysis.build_user_prompt_from_input(
        profile=profile,
        analyzer_input=analyzer_input,
    )

    assert canonical == legacy


def test_adapted_cv_schema_requires_source_ids() -> None:
    cv = AdaptedCV(
        cv_title="Data Scientist NLP",
        professional_summary="Short summary.",
        selected_experiences=[
            AdaptedExperience(
                source_id="exp_emobot_ds_2024",
                bullets=[
                    AdaptedBullet(
                        source_id="blt_emobot_ds_multimodal",
                        text="Built multimodal pipelines reaching 0.67 correlation.",
                    )
                ],
            )
        ],
        selected_project_ids=["proj_scifact_rag"],
        skills_order=["ml_ai", "data_infra"],
        warnings=[],
    )
    assert cv.selected_experiences[0].bullets[0].source_id == "blt_emobot_ds_multimodal"


def test_email_draft_schema() -> None:
    d = EmailDraft(subject="Application: Data Scientist", body="Hello,\n...")
    assert d.subject and d.body


def test_application_draft_maps_to_cv_and_email() -> None:
    draft = ApplicationDraft(
        cv_title="Data Scientist NLP",
        professional_summary="Short summary.",
        selected_experiences=[
            AdaptedExperience(
                source_id="exp_emobot_ds_2024",
                bullets=[
                    AdaptedBullet(
                        source_id="blt_emobot_ds_multimodal",
                        text="Built multimodal pipelines reaching 0.67 correlation.",
                    )
                ],
            )
        ],
        selected_project_ids=["proj_scifact_rag"],
        skills_order=["ml_ai"],
        warnings=[],
        motivation_letter_subject="Application: Data Scientist",
        motivation_letter_body="Hello,\n...",
    )
    assert draft.to_cv().cv_title == "Data Scientist NLP"
    assert draft.to_motivation_letter().subject == "Application: Data Scientist"


# ---------------- Cache key ----------------


def test_cache_key_is_deterministic_and_collision_resistant() -> None:
    k1 = make_cache_key(
        model="gpt-4o-mini",
        system="s",
        user="u",
        schema_name="JobAnalysis",
        extra={"temperature": 0.2},
    )
    k2 = make_cache_key(
        model="gpt-4o-mini",
        system="s",
        user="u",
        schema_name="JobAnalysis",
        extra={"temperature": 0.2},
    )
    k3 = make_cache_key(
        model="gpt-4o-mini",
        system="s",
        user="u DIFFERENT",
        schema_name="JobAnalysis",
        extra={"temperature": 0.2},
    )
    assert k1 == k2
    assert k1 != k3
    assert len(k1) == 64  # sha256 hex


# ---------------- Usage / pricing ----------------


def test_estimate_cost_known_model() -> None:
    cost = estimate_cost_usd("gpt-4o-mini", 1_000_000, 500_000)
    # 0.15$ in + 0.30$ out
    assert abs(cost - 0.45) < 1e-9


def test_estimate_cost_unknown_falls_back() -> None:
    assert estimate_cost_usd("totally-unknown", 1000, 1000) > 0.0


# ---------------- Mock provider ----------------


def test_mock_provider_returns_registered_response() -> None:
    MockLLMProvider.clear()
    expected = JobAnalysis(
        role_type="X",
        seniority="mid",
        domain="d",
        main_tasks=["a"],
        required_skills=["Python"],
        nice_to_have=[],
        match_reasons=["m"],
        risks=[],
        cv_keywords_to_include=["Python"],
    )
    MockLLMProvider.register("job_analysis", expected)
    p = MockLLMProvider()
    got = p.complete_json(
        system="s",
        user="u",
        schema=JobAnalysis,
        purpose="job_analysis",
    )
    assert got is expected


def test_mock_provider_missing_purpose_raises() -> None:
    MockLLMProvider.clear()
    p = MockLLMProvider()
    with pytest.raises(LLMError):
        p.complete_json(system="s", user="u", schema=JobAnalysis, purpose="missing")


def test_mock_provider_wrong_schema_raises() -> None:
    MockLLMProvider.clear()
    MockLLMProvider.register(
        "bad",
        EmailDraft(subject="s", body="b"),
    )
    p = MockLLMProvider()
    with pytest.raises(LLMError):
        p.complete_json(system="s", user="u", schema=JobAnalysis, purpose="bad")


def test_mock_provider_instances_snapshot_registered_responses() -> None:
    MockLLMProvider.clear()
    p = MockLLMProvider()
    MockLLMProvider.register("late", EmailDraft(subject="s", body="b"))

    with pytest.raises(LLMError):
        p.complete_json(system="s", user="u", schema=EmailDraft, purpose="late")

    assert MockLLMProvider().complete_json(
        system="s",
        user="u",
        schema=EmailDraft,
        purpose="late",
    ).subject == "s"


# ---------------- Factory ----------------


def test_factory_returns_mock_by_default() -> None:
    p = get_llm_provider()
    assert isinstance(p, MockLLMProvider)
    assert p.smart_model.startswith("mock") and p.cheap_model.startswith("mock")


def test_factory_unknown_provider_raises() -> None:
    with pytest.raises(ValueError):
        get_llm_provider("not-a-provider")
