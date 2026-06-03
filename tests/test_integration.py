"""End-to-end integration test on a realistic sample of jobs.

Drives the entire pipeline with mocked LLM and mocked HTTP — no API keys,
no network. Verifies anti-hallucination, persistence, and artifact files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smartapply.llm import (
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    EmailDraft,
    JobAnalysis,
    MockLLMProvider,
)
from smartapply.ranking import MockEmbeddingsProvider


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "smartapply.db"
    output_dir = tmp_path / "output"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))

    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import reset_engine_cache
    reset_engine_cache()
    from smartapply.database.session import init_db
    init_db()
    yield


SAMPLE_JOBS = [
    {
        "title": "Data Scientist NLP",
        "company": "Doctolib",
        "location": "Paris, France",
        "contract_type": "CDI",
        "remote_policy": "hybrid",
        "application_url": "https://careers.doctolib.com/jobs/42",
        "description": (
            "Vos missions\n"
            "Concevoir des pipelines RAG (BM25, FAISS, reranking) sur des données "
            "médicales. Fine-tuner des modèles Hugging Face. Déployer en production "
            "via Docker et AWS. Travailler avec PyTorch et Whisper pour la voix.\n\n"
            "Profil recherché\n"
            "2-4 ans d'expérience en ML. Maîtrise Python, PyTorch. NLP solide. "
            "Connaissance des outils LLM (Hugging Face, LangChain). Anglais courant."
        ),
    },
    {
        "title": "Senior ML Engineer",
        "company": "Mistral AI",
        "location": "Paris, France",
        "contract_type": "CDI",
        "remote_policy": "onsite",
        "application_url": "https://jobs.mistral.ai/ml-engineer",
        "description": (
            "Build distributed training infrastructure for foundation models. "
            "5+ years of experience required. PyTorch, JAX, CUDA expert. "
            "PhD preferred."
        ),
    },
    {
        "title": "Data Analyst BI",
        "company": "Carrefour",
        "location": "Massy, France",
        "contract_type": "CDI",
        "remote_policy": "hybrid",
        "application_url": "https://careers.carrefour.com/analyst",
        "description": (
            "Création de dashboards Power BI. Reporting financier mensuel. "
            "SQL avancé requis. Pas de développement Python."
        ),
    },
    {
        "title": "Sales Director Europe",
        "company": "Salesforce",
        "location": "Paris, France",
        "contract_type": "CDI",
        "remote_policy": "hybrid",
        "application_url": "https://salesforce.com/careers",
        "description": (
            "Lead the European B2B sales organization. 10+ years of experience "
            "managing enterprise sales teams. Hit aggressive growth targets."
        ),
    },
    {
        "title": "AI Research Engineer",
        "company": "Hugging Face",
        "location": "Remote (EU)",
        "contract_type": "CDI",
        "remote_policy": "remote",
        "application_url": "https://huggingface.co/jobs/ai-researcher",
        "description": (
            "Research engineer to push the state of the art in multimodal AI. "
            "Strong publications and engineering skills. PyTorch, Transformers, "
            "Diffusion models. 2-5 years experience."
        ),
    },
]


def _register_llm_fixtures() -> None:
    MockLLMProvider.clear()
    MockLLMProvider.register(
        "job_analysis",
        JobAnalysis(
            role_type="Data Scientist NLP",
            seniority="mid",
            domain="HealthTech",
            main_tasks=[
                "Concevoir des pipelines RAG",
                "Fine-tuner des modèles transformers",
                "Déployer en production",
            ],
            required_skills=["Python", "PyTorch", "RAG", "FAISS"],
            nice_to_have=["AWS", "Docker"],
            match_reasons=[
                "Forte expérience NLP/RAG",
                "Projet SciFact RAG",
                "Pipelines speech via Whisper",
            ],
            risks=["Pas d'expérience prod cloud à grande échelle"],
            cv_keywords_to_include=[
                "PyTorch",
                "Hugging Face",
                "FAISS",
                "BM25",
                "Whisper",
                "RAG",
            ],
        ),
    )
    MockLLMProvider.register(
        "cv_adaptation",
        AdaptedCV(
            cv_title="Data Scientist – NLP & Multimodal AI",
            professional_summary=(
                "Data Scientist with 2 years applied R&D in NLP, multimodal AI and "
                "clinical digital biomarkers. Built RAG pipelines, speech/NLP "
                "stacks (Whisper, Pyannote) and multimodal models reaching 0.67 "
                "correlation with clinical scores."
            ),
            selected_experiences=[
                AdaptedExperience(
                    source_id="exp_emobot_ds_2024",
                    bullets=[
                        AdaptedBullet(
                            source_id="blt_emobot_ds_multimodal",
                            text=(
                                "Built multimodal digital biomarker pipelines from facial, "
                                "mobility and smartphone data, reaching 0.67 correlation "
                                "with validated clinical scores."
                            ),
                        ),
                        AdaptedBullet(
                            source_id="blt_emobot_ds_speech_face",
                            text=(
                                "Developed speech/NLP and face-recognition pipelines using "
                                "Whisper, Pyannote, RetinaFace, FaceNet and Flask APIs."
                            ),
                        ),
                        AdaptedBullet(
                            source_id="blt_emobot_ds_patent",
                            text=(
                                "Contributed to a patent-pending AI monitoring system and "
                                "clinical preprint on passive mood markers."
                            ),
                        ),
                    ],
                ),
                AdaptedExperience(
                    source_id="exp_emobot_intern_2023",
                    bullets=[
                        AdaptedBullet(
                            source_id="blt_emobot_intern_anomaly",
                            text=(
                                "Built an anomaly detection pipeline for identifying "
                                "behavioral disruptions in mood tracking data."
                            ),
                        ),
                    ],
                ),
            ],
            selected_project_ids=[
                "proj_scifact_rag",
                "proj_ner_camembert",
                "proj_gpt2",
            ],
            skills_order=["ml_ai", "data_infra", "stats_signal"],
            warnings=[],
        ),
    )
    MockLLMProvider.register(
        "email_writer",
        EmailDraft(
            subject="Candidature : Data Scientist NLP – Lachtar Nour",
            body=(
                "Bonjour,\n\n"
                "Je me permets de vous adresser ma candidature pour le poste de "
                "Data Scientist NLP. Mes deux années chez Emobot m'ont permis de "
                "construire des pipelines NLP/speech (Whisper, Pyannote) et des "
                "biomarqueurs cliniques multimodaux. Mon projet SciFact RAG "
                "(BM25, FAISS, reranking) correspond particulièrement aux missions "
                "que vous décrivez. Je serais ravi d'en discuter avec vous.\n\n"
                "Bien cordialement,\nLachtar Nour"
            ),
        ),
    )


def test_full_pipeline_on_realistic_sample(tmp_path: Path) -> None:
    """Ingest 5 jobs → process → apply to top 2. Verify everything."""
    _register_llm_fixtures()

    from smartapply.database import session_scope
    from smartapply.database.repository import top_jobs_by_score
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())

    # ---- Step 1: Ingest the 5 sample jobs ----
    for job_data in SAMPLE_JOBS:
        p.ingest_text(
            text=job_data["description"],
            title=job_data["title"],
            company=job_data["company"],
            location=job_data["location"],
            application_url=job_data["application_url"],
        )

    # ---- Step 2: Process ----
    process_report = p.process_pending()
    assert process_report.total == 5
    # Sales Director should be filtered out by the rules engine.
    # Data Scientist NLP + AI Research Engineer must be analyzed.
    assert process_report.kept_after_filter >= 2
    assert process_report.kept_after_filter <= 4
    assert process_report.analyzed >= 2

    # ---- Step 3: Apply to top-scoring jobs ----
    p.contact_finder.find = MagicMock(return_value=[])

    with session_scope() as s:
        top = list(top_jobs_by_score(s, 2))
        top_ids = [j.id for j in top]
        top_companies = [j.company for j in top]

    assert top_ids
    # The Sales Director should NOT be in the top
    assert "Salesforce" not in top_companies
    # The BI role should NOT be in the top
    assert "Carrefour" not in top_companies

    reports = []
    for jid in top_ids:
        report = p.apply_to(jid, create_gmail_draft=False)
        reports.append(report)
        assert report.application_id is not None
        assert report.docx_path and Path(report.docx_path).exists()
        assert report.cv_pdf_path and Path(report.cv_pdf_path).exists()
        assert report.letter_pdf_path and Path(report.letter_pdf_path).exists()
        assert report.eml_path and Path(report.eml_path).exists()
        # Anti-hallucination: no validation errors after auto-fix
        assert not report.validation_errors

    # ---- Step 4: Verify generated CV contains real profile facts ----
    from docx import Document

    docx_path = reports[0].docx_path
    doc = Document(docx_path)
    text = "\n".join(p.text for p in doc.paragraphs)
    # Extract text from tables too
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                text += "\n" + cell.text

    # Real facts from the profile must appear
    assert "Lachtar Nour" in text
    assert "Emobot" in text
    assert "0.67" in text  # the validated quantified metric
    assert "Whisper" in text  # real tech from profile
    # Allowed skills should appear
    assert "PyTorch" in text

    # ---- Step 5: Verify .eml is a valid message ----
    from email import message_from_bytes, policy

    eml_bytes = Path(reports[0].eml_path).read_bytes()
    msg = message_from_bytes(eml_bytes, policy=policy.default)
    assert "Lachtar Nour" in str(msg["Subject"]) or "Data Scientist" in str(msg["Subject"])
    assert str(msg["From"]) == "nour.lachtar@dauphine.eu"
    attachments = list(msg.iter_attachments())
    filenames = [attachment.get_filename() for attachment in attachments]
    assert any(name.endswith(".pdf") and name.startswith("CV_") for name in filenames)
    assert any(name.endswith(".pdf") and name.startswith("Lettre_motivation_") for name in filenames)

    # ---- Step 6: Application persisted with full audit trail ----
    from smartapply.database.models import Application

    with session_scope() as s:
        app = s.get(Application, reports[0].application_id)
        assert app is not None
        assert app.email_subject
        assert app.email_body
        assert app.cv_json  # full structured CV is persisted
        # READY_FOR_FORM_SUBMISSION is the unified-Applier outcome when no
        # contact email was discovered. EMAIL_GENERATED / DRAFT_CREATED are
        # the outcomes when one was found. All three indicate a successful
        # manual apply — the difference is the recipient resolution.
        assert app.status in (
            "email_generated",
            "draft_created",
            "ready_for_form_submission",
        )
        assert app.cv_pdf_path and Path(app.cv_pdf_path).exists()
        assert len(app.documents) >= 8  # cv docs, letter docs, cv_json, email, eml
