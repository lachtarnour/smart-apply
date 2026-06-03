"""Tests for the CV module — selector, adapter, validator, docx renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from smartapply.cv import (
    CvAdapter,
    CvBlockSelector,
    CvDocxRenderer,
    HtmlApplicationRenderer,
    CvValidator,
)
from smartapply.cv.html_renderer import pdf_page_count
from smartapply.llm import (
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    ApplicationDraft,
    EmailDraft,
    JobAnalysis,
    MockLLMProvider,
    SkillSelectionBlock,
)
from smartapply.llm.prompts import application_draft
from smartapply.profile import get_profile
from smartapply.ranking import MockEmbeddingsProvider


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import reset_engine_cache
    reset_engine_cache()
    from smartapply.database.session import init_db
    init_db()
    yield


def _sample_analysis() -> JobAnalysis:
    return JobAnalysis(
        role_type="Data Scientist NLP",
        seniority="mid",
        domain="HealthTech",
        main_tasks=[
            "Build RAG pipelines",
            "Fine-tune transformer models",
            "Productionize ML services",
        ],
        required_skills=["PyTorch", "RAG", "Python"],
        nice_to_have=["Docker"],
        match_reasons=["Strong NLP background", "Multimodal AI experience"],
        risks=["No prior healthtech experience"],
        cv_keywords_to_include=["PyTorch", "RAG", "Whisper", "FAISS"],
    )


def _valid_adapted_cv() -> AdaptedCV:
    return AdaptedCV(
        cv_title="Data Scientist – NLP & Multimodal AI",
        professional_summary=(
            "Data Scientist with 2 years applied R&D in multimodal AI and clinical "
            "digital biomarkers. Strong NLP/RAG and speech pipelines."
        ),
        selected_experiences=[
            AdaptedExperience(
                source_id="exp_emobot_ds_2024",
                bullets=[
                    AdaptedBullet(
                        source_id="blt_emobot_ds_multimodal",
                        text="Built multimodal pipelines reaching 0.67 correlation with clinical scores.",
                    ),
                    AdaptedBullet(
                        source_id="blt_emobot_ds_speech_face",
                        text="Developed speech/NLP and face-recognition pipelines using Whisper and Pyannote.",
                    ),
                ],
            )
        ],
        selected_project_ids=["proj_scifact_rag", "proj_ner_camembert"],
        skills_order=["ml_ai", "data_infra", "stats_signal"],
        warnings=[],
    )


# ---------------- Selector ----------------


def test_selector_returns_top_k_relevant_blocks() -> None:
    profile = get_profile()
    selector = CvBlockSelector(MockEmbeddingsProvider())
    res = selector.select(profile, _sample_analysis(), top_k_experiences=2, top_k_projects=2)
    assert 1 <= len(res.experiences) <= 2
    assert len(res.projects) <= 2


def test_selector_always_keeps_most_recent_experience() -> None:
    profile = get_profile()
    selector = CvBlockSelector(MockEmbeddingsProvider())
    res = selector.select(profile, _sample_analysis(), top_k_experiences=1)
    assert res.experiences[0].id == profile.experiences[0].id


# ---------------- Adapter ----------------


def test_adapter_uses_llm_to_produce_cv() -> None:
    MockLLMProvider.clear()
    MockLLMProvider.register("cv_adaptation", _valid_adapted_cv())
    adapter = CvAdapter(get_profile(), embeddings=MockEmbeddingsProvider())
    adapted, selection = adapter.adapt(
        _sample_analysis(), job_title="Data Scientist NLP", job_company="Acme"
    )
    assert isinstance(adapted, AdaptedCV)
    assert adapted.cv_title.startswith("Data Scientist")
    assert len(selection.experiences) >= 1


def test_adapter_can_produce_cv_and_email_in_one_call() -> None:
    MockLLMProvider.clear()
    cv = _valid_adapted_cv()
    MockLLMProvider.register(
        "application_draft",
        ApplicationDraft(
            cv_title=cv.cv_title,
            professional_summary=cv.professional_summary,
            selected_experiences=cv.selected_experiences,
            selected_project_ids=cv.selected_project_ids,
            skills_order=cv.skills_order,
            warnings=cv.warnings,
            email_subject="Application: Data Scientist NLP",
            email_body="Hello,\n\nI am writing about this role." + " word" * 25,
        ),
    )
    adapter = CvAdapter(get_profile(), embeddings=MockEmbeddingsProvider())
    adapted, email, selection = adapter.adapt_application(
        _sample_analysis(), job_title="Data Scientist NLP", job_company="Acme"
    )
    assert adapted.cv_title.startswith("Data Scientist")
    assert email.subject.startswith("Application")
    assert len(selection.experiences) >= 1


def test_adapter_adds_supported_required_skills_to_llm_selection() -> None:
    MockLLMProvider.clear()
    cv = _valid_adapted_cv().model_copy(
        update={
            "selected_skills": [
                SkillSelectionBlock(category_id="data_infra", skills=["Docker"])
            ],
            "skills_order": ["data_infra"],
        }
    )
    MockLLMProvider.register(
        "application_draft",
        ApplicationDraft(
            cv_title=cv.cv_title,
            professional_summary=cv.professional_summary,
            selected_experiences=cv.selected_experiences,
            selected_project_ids=cv.selected_project_ids,
            selected_skills=cv.selected_skills,
            skills_order=cv.skills_order,
            warnings=cv.warnings,
            email_subject="Application: AI Engineer",
            email_body="Hello,\n\nI am writing about this role." + " word" * 25,
        ),
    )
    analysis = _sample_analysis().model_copy(
        update={
            "required_skills": ["Python programming", "Experience with PyTorch", "Kubernetes"],
            "cv_keywords_to_include": ["GCP", "CI/CD"],
        }
    )
    adapter = CvAdapter(get_profile(), embeddings=MockEmbeddingsProvider())
    adapted, _email, _selection = adapter.adapt_application(
        analysis, job_title="AI Engineer", job_company="Acme"
    )
    selected = {
        skill
        for block in adapted.selected_skills
        for skill in block.skills
    }
    assert {"Docker", "Python", "PyTorch", "CI/CD"}.issubset(selected)
    assert "Kubernetes" not in selected
    assert "GCP" not in selected


# ---------------- Validator ----------------


def test_validator_accepts_clean_cv() -> None:
    v = CvValidator(get_profile())
    result = v.validate(_valid_adapted_cv())
    assert result.ok
    assert not result.errors


def test_validator_rejects_unknown_bullet_id() -> None:
    cv = _valid_adapted_cv()
    cv.selected_experiences[0].bullets[0] = AdaptedBullet(
        source_id="blt_does_not_exist",
        text="Did something cool.",
    )
    v = CvValidator(get_profile())
    result = v.validate(cv)
    assert not result.ok
    assert any("unknown_bullet_id" in e for e in result.errors)


def test_validator_warns_on_hallucinated_number() -> None:
    cv = _valid_adapted_cv()
    cv.selected_experiences[0].bullets[0] = AdaptedBullet(
        source_id="blt_emobot_ds_multimodal",
        text="Built multimodal pipelines reaching 0.99 correlation with clinical scores.",
    )
    v = CvValidator(get_profile())
    result = v.validate(cv)
    assert result.ok  # numbers are warnings, not errors
    assert any("hallucinated_number" in w for w in result.warnings)


def test_validator_rejects_misplaced_bullet() -> None:
    cv = _valid_adapted_cv()
    # Bullet belongs to exp_emobot_ds_2024 but we put it under another experience
    cv.selected_experiences[0] = AdaptedExperience(
        source_id="exp_vds_intern_2022",
        bullets=[
            AdaptedBullet(
                source_id="blt_emobot_ds_multimodal",
                text="text",
            )
        ],
    )
    v = CvValidator(get_profile())
    result = v.validate(cv)
    assert not result.ok
    assert any("bullet_wrong_parent" in e for e in result.errors)


def test_validator_rejects_unknown_project() -> None:
    cv = _valid_adapted_cv()
    cv.selected_project_ids.append("proj_made_up")
    v = CvValidator(get_profile())
    result = v.validate(cv)
    assert not result.ok
    assert any("unknown_project_id" in e for e in result.errors)


def test_validator_flags_and_removes_unknown_selected_skill() -> None:
    cv = _valid_adapted_cv().model_copy(
        update={
            "selected_skills": [
                SkillSelectionBlock(category_id="data_infra", skills=["Spark", "Kubernetes"])
            ]
        }
    )
    validator = CvValidator(get_profile())
    result = validator.validate(cv)
    assert "unknown_selected_skill:Kubernetes" in result.warnings
    fixed, removed = validator.auto_fix(cv)
    assert "selected_skill:Kubernetes" in removed
    assert fixed.selected_skills == [
        SkillSelectionBlock(category_id="data_infra", skills=["Spark"])
    ]


def test_validator_warns_when_text_diverges_from_allowed_claims() -> None:
    cv = _valid_adapted_cv()
    cv.selected_experiences[0].bullets[0] = AdaptedBullet(
        source_id="blt_emobot_ds_multimodal",
        text="Designed an end-to-end MLOps platform on Kubernetes serving 10M users.",
    )
    v = CvValidator(get_profile())
    result = v.validate(cv)
    assert any("off_allowed_claims" in w for w in result.warnings)


def test_validator_stricter_threshold_for_inferred_evidence() -> None:
    """Bullets marked self_reported / inferred need stronger overlap."""
    profile = get_profile()
    # patent bullet was marked self_reported in the data
    cv = _valid_adapted_cv()
    cv.selected_experiences[0].bullets.append(
        AdaptedBullet(
            source_id="blt_emobot_ds_patent",
            text="Filed multiple patents and published peer-reviewed papers on mood detection.",
        )
    )
    v = CvValidator(profile)
    result = v.validate(cv)
    assert any(
        "off_allowed_claims" in w and "blt_emobot_ds_patent" in w
        for w in result.warnings
    )


def test_validator_accepts_project_bullet_source_id() -> None:
    """Bullets from project sources are now valid source_ids too."""
    cv = _valid_adapted_cv()
    # Replace an experience bullet with a project bullet source_id — should not error
    # NOTE: the bullet still must logically belong to the experience it's nested
    # under. The validator catches that via bullet_wrong_parent for experiences.
    # For projects, source_id is exposed via the project-selection path; here we
    # just confirm the bullet index resolves project bullets.
    profile = get_profile()
    proj_bullet_id = "blt_proj_scifact_main"
    assert proj_bullet_id in profile.bullet_index()


def test_validator_auto_fix_strips_invalid() -> None:
    cv = _valid_adapted_cv()
    cv.selected_project_ids = ["proj_scifact_rag", "proj_nonsense"]
    cv.selected_experiences[0].bullets.append(
        AdaptedBullet(source_id="blt_fake", text="x")
    )
    v = CvValidator(get_profile())
    fixed, removed = v.auto_fix(cv)
    assert "proj_nonsense" not in fixed.selected_project_ids
    assert all(b.source_id != "blt_fake" for b in fixed.selected_experiences[0].bullets)
    assert removed  # something was stripped


# ---------------- DOCX renderer ----------------


def test_docx_renderer_produces_valid_file(tmp_path: Path) -> None:
    profile = get_profile()
    cv = _valid_adapted_cv()
    out = tmp_path / "cv.docx"
    renderer = CvDocxRenderer(profile)
    renderer.save(cv, out)
    assert out.exists()
    # File starts with the ZIP magic bytes (DOCX is a ZIP)
    assert out.read_bytes()[:2] == b"PK"
    # Re-open to confirm validity
    from docx import Document

    doc = Document(str(out))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert "Lachtar Nour" in full_text
    assert "Data Scientist" in full_text


def test_html_renderer_matches_reference_cv_architecture() -> None:
    profile = get_profile()
    html = HtmlApplicationRenderer(profile).render_cv_html(_valid_adapted_cv())
    assert "Professional Experience" in html
    assert "Education" in html
    assert "Skills" in html
    assert "Projects" in html
    assert "Languages" in html
    assert "Certificates" in html
    assert "section-title" in html
    assert "grid-template-columns: 38mm 1fr" in html
    assert 'class="project-link"' in html
    assert 'aria-label="Project repository"' in html
    assert "Completed" not in html


def test_html_renderer_uses_clickable_profile_links() -> None:
    html = HtmlApplicationRenderer(get_profile()).render_cv_html(_valid_adapted_cv())
    assert 'href="mailto:nour.lachtar@dauphine.eu"' in html
    assert 'href="https://github.com/lachtarnour"' in html
    assert ">GitHub</a>" in html
    assert 'href="https://emobothealth.com/"' in html
    assert 'aria-label="Emobot website"' in html
    assert (
        'href="https://dauphine.psl.eu/formations/masters/informatique/'
        'm2-intelligence-artificielle-systemes-donnees"'
    ) in html
    assert (
        'href="https://dauphine.psl.eu/formations/licences/mathematiques/'
        'l3-mathematiques-appliquees"'
    ) in html
    assert 'aria-label="Degree page"' in html


def test_html_renderer_always_renders_at_least_three_projects() -> None:
    cv = _valid_adapted_cv().model_copy(update={"selected_project_ids": ["proj_scifact_rag"]})
    html = HtmlApplicationRenderer(get_profile()).render_cv_html(cv)
    project_rows = html.count('class="project-row"')
    assert project_rows >= 3
    assert "SciFact RAG Verifier" in html


@pytest.mark.real_pdf
def test_html_renderer_can_write_pdf_when_renderer_available(tmp_path: Path) -> None:
    profile = get_profile()
    renderer = HtmlApplicationRenderer(profile)
    if not renderer.pdf_available:
        pytest.skip("No HTML PDF renderer available")
    out = tmp_path / "cv.pdf"
    renderer.save_cv_pdf(_valid_adapted_cv(), out)
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF")
    assert pdf_page_count(out) == 1


def test_html_renderer_uses_selected_skill_profile() -> None:
    cv = _valid_adapted_cv().model_copy(update={"skills_profile_id": "data_analyst"})
    html = HtmlApplicationRenderer(get_profile()).render_cv_html(cv)
    assert "Data Analysis" in html
    assert "Data visualization" in html
    assert "Streamlit" in html
    assert "Panel" in html


def test_html_renderer_uses_llm_selected_skills_without_cap() -> None:
    cv = _valid_adapted_cv().model_copy(
        update={
            "skills_order": ["data_infra"],
            "selected_skills": [
                SkillSelectionBlock(
                    category_id="data_infra",
                    skills=[
                        "Git",
                        "Docker",
                        "FastAPI",
                        "Flask",
                        "REST APIs",
                        "Spark",
                        "Data pipelines",
                        "CI/CD",
                        "Model monitoring",
                        "ONNX",
                        "Model quantization",
                        "Weights & Biases",
                    ],
                )
            ],
        }
    )
    html = HtmlApplicationRenderer(get_profile()).render_cv_html(cv)
    assert "Spark" in html
    assert "ONNX" in html
    assert "Model quantization" in html
    assert "Weights &amp; Biases" in html
    assert "Model monitoring" in html


def test_html_renderer_keeps_fixed_project_descriptions() -> None:
    cv = _valid_adapted_cv().model_copy(
        update={
            "selected_project_ids": [
                "proj_svc",
                "proj_scifact_rag",
                "proj_gpt2",
                "proj_ner_camembert",
                "proj_rl_gym",
            ]
        }
    )
    html = HtmlApplicationRenderer(get_profile()).render_cv_html(cv)
    assert "Singing Voice Conversion" in html
    assert "Ongoing Project" in html
    assert "Built a PyTorch SVC pipeline extending SoftVC-style acoustic modeling" in html
    assert "Built a claim-verification RAG pipeline with BM25, FAISS" in html
    assert "Implemented a decoder-only Transformer from scratch for language modeling." in html
    assert "Fine-tuned CamemBERT for named entity recognition on domain-specific corpora." in html
    assert "Implemented and trained reinforcement learning agents on OpenAI Gym environments" in html


def test_application_draft_prompt_separates_matching_keywords_from_display_skills() -> None:
    profile = get_profile()
    analysis = _sample_analysis().model_copy(
        update={
            "required_skills": [
                "Python",
                "Machine learning",
                "Computer vision",
                "MLOps",
                "Kubernetes",
                "Experience with PyTorch",
            ],
            "cv_keywords_to_include": ["PyTorch", "GCP"],
        }
    )
    prompt = application_draft.build_user_prompt(
        profile=profile,
        analysis=analysis,
        job_title="Clinical AI Engineer",
        job_company="Acme Health",
        selected_experiences=profile.experiences[:1],
        selected_projects=profile.projects[:2],
        language="en",
    )
    assert "allowed_skills_by_category" in prompt
    assert "core_skills_by_category" in prompt
    assert "matching_keywords_for_profile_selection_not_display" in prompt
    assert "genai" in prompt
    assert "do not copy those keywords into selected_skills" in prompt
    assert "unsupported_offer_terms_not_to_claim" in prompt
    assert "- MLOps" in prompt
    assert "- Kubernetes" in prompt
    assert "- GCP" in prompt
    assert "- Machine learning" not in prompt
    assert "- Computer vision" not in prompt
    assert "The subject and body must both use the requested email language" in prompt
    assert "selected_project_ids must include at least 3 projects" in prompt


def test_letter_renderer_uses_offer_language_labels() -> None:
    renderer = HtmlApplicationRenderer(get_profile())
    html = renderer.render_letter_html(
        email_draft=EmailDraft(subject="Application: Data Analyst", body="Hello,\n\nI am interested."),
        job_title="Data Analyst",
        job_company="Acme",
        language="en",
    )
    assert "Motivation Letter" in html
    assert "Role: Data Analyst" in html
    assert "Subject: Application: Data Analyst" in html
