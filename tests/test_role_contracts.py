"""Tests for the role-family classifier and the post-LLM skill contract.

These tests pin the behaviour the V1 contract is meant to guarantee:
- No FAISS / Markov / OpenAI Gym on roles that don't ask for them.
- Data Scientist roles keep a minimal ML/IA baseline.
- Data Scientist offers with AI/NLP signals get NLP + Transformers + HF.
- Analytics / Software offers strip Flask/FastAPI/NLP unless explicit.
- LLM offers anchor RAG + FAISS + Vector search.
- Explicit ``required_skills`` lifts the forbidden lock for that term.
"""

from __future__ import annotations

import pytest

from smartapply.cv.role_contracts import apply_contract
from smartapply.cv.role_family import classify, has_data_scientist_ia_signal
from smartapply.llm import AdaptedCV, JobAnalysis, SkillSelectionBlock
from smartapply.profile import get_profile


def _analysis(
    *,
    role_type: str,
    main_tasks: list[str] | None = None,
    required: list[str] | None = None,
    keywords: list[str] | None = None,
    nice_to_have: list[str] | None = None,
    domain: str = "Tech",
) -> JobAnalysis:
    return JobAnalysis(
        role_type=role_type,
        seniority="mid",
        domain=domain,
        main_tasks=main_tasks or [],
        required_skills=required or [],
        nice_to_have=nice_to_have or [],
        match_reasons=[],
        risks=[],
        cv_keywords_to_include=keywords or [],
    )


def _cv(selected: dict[str, list[str]]) -> AdaptedCV:
    return AdaptedCV(
        cv_title="Adapted CV",
        professional_summary="Adapted summary.",
        selected_experiences=[],
        selected_project_ids=[],
        selected_skills=[
            SkillSelectionBlock(category_id=cid, skills=skills)
            for cid, skills in selected.items()
        ],
        skills_order=list(selected.keys()),
        warnings=[],
    )


def _apply(cv: AdaptedCV, analysis: JobAnalysis, title: str) -> tuple[AdaptedCV, str]:
    profile = get_profile()
    allowed_lower = {s.lower() for s in profile.skills.allowed_skills}
    return apply_contract(
        cv,
        analysis=analysis,
        job_title=title,
        allowed_skills_lower=allowed_lower,
    )


def _selected_map(cv: AdaptedCV) -> dict[str, list[str]]:
    return {block.category_id: list(block.skills) for block in cv.selected_skills}


# ---------------- classify() ----------------


@pytest.mark.parametrize(
    "title,role_type,tasks,expected",
    [
        ("Data Scientist", "Data Scientist", [], "data_scientist"),
        ("Senior ML Engineer", "Machine Learning Engineer", [], "ml_engineer"),
        ("Applied AI Engineer", "AI Engineer", [], "ml_engineer"),
        (
            "GenAI Engineer",
            "LLM Engineer",
            ["Build RAG pipelines"],
            "llm_engineer",
        ),
        ("Data Analyst", "Data Analyst", [], "data_analyst"),
        (
            "Analytics Engineer",
            "Analytics Engineer",
            ["Build dbt models"],
            "analytics_engineer",
        ),
        (
            "Cloud Data Engineer",
            "Cloud Data Engineer",
            ["Build BigQuery, Airflow and dbt pipelines"],
            "data_engineer",
        ),
        ("MLOps Engineer", "MLOps", [], "mlops"),
        ("C++ Software Engineer", "Software Engineer", [], "software_engineer"),
        (
            "Computer Vision Engineer",
            "Applied AI",
            ["Train object detection"],
            "computer_vision",
        ),
        (
            "Speech AI Engineer",
            "Audio",
            ["Build transcription pipelines"],
            "speech_audio",
        ),
        (
            "RL Researcher",
            "Reinforcement Learning",
            ["Train RL agents on control tasks"],
            "reinforcement_learning",
        ),
        (
            "Marketing Manager",
            "Marketing",
            ["Run campaigns"],
            "other",
        ),
        (
            "DevOps (H/F)",
            "DevOps",
            ["Maintain BI portals and CI/CD scripts"],
            "other",
        ),
        (
            "Ingénieur IAM F/H",
            "IAM Engineer",
            ["Design identity and access management policies"],
            "other",
        ),
    ],
)
def test_classify_routes_to_expected_family(title, role_type, tasks, expected):
    analysis = _analysis(role_type=role_type, main_tasks=tasks)
    assert classify(analysis, title=title) == expected


def test_data_scientist_with_power_bi_in_nice_to_have_stays_data_scientist():
    """Regression: a DS offer with Power BI as bonus must NOT become data_analyst."""
    analysis = _analysis(
        role_type="Data Scientist",
        main_tasks=["Build predictive models and ML algorithms"],
        required=["Python", "MySQL", "Flask"],
        nice_to_have=["Tableau", "Power BI"],
        keywords=["Data Science", "Machine Learning"],
    )
    assert classify(analysis, title="Data scientist (H/F)") == "data_scientist"


def test_mlops_requires_match_in_title_or_role_type():
    """A DS offer that lists 'ML Ops workflows' as required must NOT be mlops."""
    analysis = _analysis(
        role_type="Data Scientist - IA",
        main_tasks=["Design embedded AI models", "Build end-to-end ML pipelines"],
        required=["Python", "PyTorch", "ML Ops workflows"],
    )
    assert classify(analysis, title="Data Scientist - IA (H/F)") == "data_scientist"

    # But a genuine MLOps role still matches.
    mlops = _analysis(role_type="MLOps Engineer", main_tasks=["Build ML platform"])
    assert classify(mlops, title="MLOps Engineer") == "mlops"


def test_title_family_wins_over_noisy_offer_body():
    """Regression benchmark: explicit titles should not be rerouted by skills."""
    product_analyst = _analysis(
        role_type="Product Data Analyst",
        main_tasks=["Build dashboards and analyze customer journey"],
        required=["SQL", "Snowflake", "Power BI"],
        keywords=["Machine learning", "Data visualization"],
    )
    assert (
        classify(
            product_analyst,
            title="Product Data Analyst F/H - Système, réseaux, données",
        )
        == "data_analyst"
    )

    backend = _analysis(
        role_type="Backend Software Engineer",
        main_tasks=[
            "Design backend features",
            "Collaborate with data science and product teams",
        ],
        required=["Node.js", "API development", "Software architecture"],
        keywords=["data engineering", "software architecture"],
    )
    assert classify(backend, title="Backend Software Engineer (H/F)") == "software_engineer"

    ds_llm = _analysis(
        role_type="Data Scientist",
        main_tasks=["Integrate LLMs and generative AI into support projects"],
        required=["Machine Learning", "NLP", "Databricks"],
        keywords=["NLP", "Data pipelines"],
    )
    assert classify(ds_llm, title="Data scientist (H/F)") == "data_scientist"
    assert has_data_scientist_ia_signal(ds_llm, "Data scientist (H/F)")


def test_segmentation_in_data_mining_context_does_not_trigger_cv():
    """Regression: 'sales segmentation' must NOT be classified as computer_vision."""
    analysis = _analysis(
        role_type="Data Miner / Data Analyst",
        main_tasks=[
            "Perform sales forecasting and segmentation models",
            "Build reporting analysis",
        ],
        required=["SQL", "Statistical analysis"],
    )
    assert classify(analysis, title="Data Miner / Data Analyst H/F") == "data_analyst"


def test_data_scientist_ia_signal_detection():
    base = _analysis(
        role_type="Data Scientist",
        main_tasks=["Build forecasting models"],
    )
    assert not has_data_scientist_ia_signal(base, "Data Scientist")

    nlp_offer = _analysis(
        role_type="Data Scientist",
        required=["NLP"],
        main_tasks=["Develop language models"],
    )
    assert has_data_scientist_ia_signal(nlp_offer, "Data Scientist NLP")


# ---------------- apply_contract() ----------------


def test_data_scientist_anchors_ml_baseline():
    """A DS offer that mentions no AI keyword still keeps PyTorch + Scikit-learn."""
    cv = _cv({"data_analysis": ["Python", "SQL"]})
    analysis = _analysis(
        role_type="Data Scientist",
        main_tasks=["Build predictive models on customer data"],
    )
    adapted, family = _apply(cv, analysis, "Data Scientist")
    assert family == "data_scientist"
    selected = _selected_map(adapted)
    assert "PyTorch" in selected["ml_ai"]
    assert "Scikit-learn" in selected["ml_ai"]
    assert "Python" in selected["data_analysis"]
    assert "NLP" not in selected.get("ml_ai", [])


def test_data_scientist_ia_offer_adds_nlp_transformers_hf():
    cv = _cv({"data_analysis": ["Python", "SQL"]})
    analysis = _analysis(
        role_type="Data Scientist NLP",
        main_tasks=["Train transformer models for text classification"],
        required=["NLP"],
    )
    adapted, _family = _apply(cv, analysis, "Data Scientist NLP")
    selected = _selected_map(adapted)
    assert {"PyTorch", "Scikit-learn", "NLP", "Transformers", "Hugging Face"}.issubset(
        set(selected["ml_ai"])
    )


def test_data_scientist_strips_forbidden_prestige_skills():
    """FAISS / Markov / OpenAI Gym must disappear even if the LLM picked them."""
    cv = _cv(
        {
            "data_analysis": ["Python", "SQL"],
            "rag_retrieval": ["FAISS", "Vector search"],
            "stats_signal": ["Markov chains", "ARIMA/SARIMA"],
            "rl": ["OpenAI Gym"],
        }
    )
    analysis = _analysis(role_type="Data Scientist")
    adapted, _family = _apply(cv, analysis, "Data Scientist")
    selected = _selected_map(adapted)
    assert "rag_retrieval" not in selected
    assert "rl" not in selected
    assert "Markov chains" not in selected.get("stats_signal", [])
    # ARIMA/SARIMA is allowed for DS; only the explicitly-forbidden Markov goes.
    assert "ARIMA/SARIMA" in selected.get("stats_signal", [])


def test_analytics_engineer_strips_fastapi_and_nlp_keeps_global_baseline():
    """Analytics keeps the global baseline, while stripping noisy AI extras."""
    cv = _cv(
        {
            "data_analysis": ["SQL", "Python", "Data visualization"],
            "data_infra": ["Git", "Data pipelines", "FastAPI", "Flask"],
            "ml_ai": ["NLP", "Transformers"],
        }
    )
    analysis = _analysis(
        role_type="Analytics Engineer",
        main_tasks=["Build dbt models on Snowflake"],
    )
    adapted, family = _apply(cv, analysis, "Analytics Engineer")
    assert family == "analytics_engineer"
    selected = _selected_map(adapted)
    assert "FastAPI" not in selected["data_infra"]
    assert "Flask" not in selected["data_infra"]
    assert {"Docker", "Git", "AWS"}.issubset(set(selected["data_infra"]))
    assert {"PyTorch", "TensorFlow", "Scikit-learn"}.issubset(set(selected["ml_ai"]))
    # But forbidden NLP/Transformers are stripped.
    assert "NLP" not in selected["ml_ai"]
    assert "Transformers" not in selected["ml_ai"]


def test_data_engineer_keeps_global_ml_and_pipeline_stack():
    cv = _cv(
        {
            "ml_ai": ["PyTorch", "Scikit-learn", "NLP"],
            "data_analysis": ["SQL"],
            "data_infra": ["Data pipelines", "Docker"],
        }
    )
    analysis = _analysis(
        role_type="Cloud Data Engineer",
        main_tasks=["Build BigQuery, Airflow and dbt pipelines"],
        required=["SQL", "CI/CD", "Terraform"],
    )
    adapted, family = _apply(cv, analysis, "Cloud Data Engineer")
    assert family == "data_engineer"
    selected = _selected_map(adapted)
    assert {"PyTorch", "TensorFlow", "Scikit-learn"}.issubset(set(selected["ml_ai"]))
    assert "Python" in selected["data_analysis"]
    assert {"Data pipelines", "Spark", "Docker", "Git", "CI/CD"}.issubset(
        set(selected["data_infra"])
    )


def test_llm_engineer_anchors_rag_block():
    cv = _cv({"ml_ai": ["PyTorch"]})
    analysis = _analysis(
        role_type="LLM Engineer",
        main_tasks=["Build RAG pipelines"],
        required=["LLMs"],
    )
    adapted, family = _apply(cv, analysis, "GenAI Engineer")
    assert family == "llm_engineer"
    selected = _selected_map(adapted)
    assert {"RAG", "Vector search", "FAISS"}.issubset(set(selected["rag_retrieval"]))
    assert {"NLP", "LLMs", "Transformers", "Hugging Face"}.issubset(set(selected["ml_ai"]))


def test_software_engineer_strips_nlp_when_not_explicitly_required():
    cv = _cv(
        {
            "data_analysis": ["Python"],
            "data_infra": ["Git", "Docker", "CI/CD", "FastAPI", "Flask"],
            "ml_ai": ["NLP", "Transformers"],
        }
    )
    analysis = _analysis(
        role_type="C++ Software Engineer",
        main_tasks=["Develop Qt-based desktop application"],
    )
    adapted, family = _apply(cv, analysis, "C++ Software Engineer")
    assert family == "software_engineer"
    selected = _selected_map(adapted)
    assert {"PyTorch", "TensorFlow", "Scikit-learn"}.issubset(set(selected["ml_ai"]))
    assert "FastAPI" not in selected["data_infra"]
    assert {"Git", "Docker", "CI/CD", "AWS"}.issubset(
        set(selected["data_infra"])
    )
    assert "REST APIs" not in selected["data_infra"]


def test_explicit_required_skill_lifts_forbidden_lock():
    """If an Analytics offer explicitly requires NLP, NLP survives."""
    cv = _cv(
        {
            "data_analysis": ["SQL", "Python"],
            "ml_ai": ["NLP"],
        }
    )
    analysis = _analysis(
        role_type="Analytics Engineer",
        required=["NLP"],
    )
    adapted, _family = _apply(cv, analysis, "Analytics Engineer")
    selected = _selected_map(adapted)
    assert "NLP" in selected.get("ml_ai", [])


def test_other_family_uses_minimal_contract():
    cv = _cv(
        {
            "ml_ai": ["NLP", "PyTorch", "Scikit-learn"],
            "data_analysis": ["Python", "SQL"],
            "data_infra": ["AWS"],
        }
    )
    analysis = _analysis(role_type="Marketing Manager")
    adapted, family = _apply(cv, analysis, "Marketing Manager")
    assert family == "other"
    selected = _selected_map(adapted)
    assert {"PyTorch", "TensorFlow", "Scikit-learn"}.issubset(set(selected["ml_ai"]))
    assert {"Python", "SQL", "Pandas", "NumPy"}.issubset(
        set(selected["data_analysis"])
    )
    assert {"Git", "Docker", "AWS", "CI/CD"}.issubset(
        set(selected["data_infra"])
    )
    assert "REST APIs" not in selected["data_infra"]
    assert sum(len(skills) for skills in selected.values()) >= 8


def test_data_scientist_anchors_r_in_data_analysis():
    """R is in the candidate profile and must show up for any DS role."""
    cv = _cv({"data_analysis": ["Python", "SQL"]})
    analysis = _analysis(role_type="Data Scientist")
    adapted, _ = _apply(cv, analysis, "Data Scientist")
    assert "R" in _selected_map(adapted)["data_analysis"]


def test_data_scientist_keeps_global_infra_baseline():
    """The global baseline keeps core infra visible on every CV."""
    cv = _cv({"data_analysis": ["Python", "SQL"]})
    analysis = _analysis(role_type="Data Scientist")
    adapted, _ = _apply(cv, analysis, "Data Scientist")
    selected = _selected_map(adapted)
    assert {"Docker", "Git", "AWS"}.issubset(
        set(selected["data_infra"])
    )
    assert "Spark" not in selected["data_infra"]
    assert "Flask" not in selected["data_infra"]
    assert "TensorFlow" in selected["ml_ai"]


def test_data_scientist_keeps_spark_when_offer_requires_it():
    """Offer-anchored Spark survives via _ensure_supported_offer_skills logic."""
    cv = _cv({"data_analysis": ["Python", "SQL"], "data_infra": ["Spark"]})
    analysis = _analysis(role_type="Data Scientist", required=["Spark"])
    adapted, _ = _apply(cv, analysis, "Data Scientist")
    assert "Spark" in _selected_map(adapted).get("data_infra", [])


def test_ml_engineer_forces_spark():
    cv = _cv({"ml_ai": ["PyTorch"]})
    analysis = _analysis(role_type="ML Engineer")
    adapted, _ = _apply(cv, analysis, "ML Engineer")
    assert "Spark" in _selected_map(adapted)["data_infra"]


def test_mlops_forces_spark():
    cv = _cv({"data_infra": ["Docker"]})
    analysis = _analysis(role_type="MLOps Engineer")
    adapted, _ = _apply(cv, analysis, "MLOps Engineer")
    assert "Spark" in _selected_map(adapted)["data_infra"]


def test_data_analyst_keeps_r_and_global_baseline():
    cv = _cv({"data_analysis": ["SQL", "Python"]})
    analysis = _analysis(role_type="Data Analyst")
    adapted, _ = _apply(cv, analysis, "Data Analyst")
    selected = _selected_map(adapted)
    assert "R" in selected["data_analysis"]
    assert {"PyTorch", "TensorFlow", "Scikit-learn"}.issubset(set(selected["ml_ai"]))
    assert {"Docker", "Git", "AWS"}.issubset(
        set(selected["data_infra"])
    )
    assert "Spark" not in selected["data_infra"]
    assert "Flask" not in selected["data_infra"]


def test_analytics_engineer_forces_r_and_spark():
    cv = _cv({"data_analysis": ["SQL", "Python"]})
    analysis = _analysis(role_type="Analytics Engineer")
    adapted, _ = _apply(cv, analysis, "Analytics Engineer")
    selected = _selected_map(adapted)
    assert "R" in selected["data_analysis"]
    assert "Spark" in selected["data_infra"]


def test_must_show_ordered_first():
    """Global baseline and must_show categories should sit at the top."""
    cv = _cv(
        {
            "stats_signal": ["ARIMA/SARIMA"],
            "data_analysis": ["Python"],
        }
    )
    analysis = _analysis(role_type="Data Scientist")
    adapted, _family = _apply(cv, analysis, "Data Scientist")
    assert adapted.skills_order[:3] == ["ml_ai", "data_analysis", "data_infra"]
    assert adapted.skills_order[-1] == "stats_signal"
