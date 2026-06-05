"""Tests for the LLM module — schemas, mock provider, cache key, usage."""

from __future__ import annotations

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
from smartapply.llm.prompts import job_analysis


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
