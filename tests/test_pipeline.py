"""Integration tests for the end-to-end pipeline.

Every external dependency is mocked: scrapers, LLM, embeddings, contact
finder. The pipeline is exercised against real profile data so the
anti-hallucination contract is validated too.
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
from smartapply.profile import get_profile
from smartapply.ranking import MockEmbeddingsProvider
from smartapply.scrapers.base import RawJob


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
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


def _register_llm_responses() -> None:
    MockLLMProvider.clear()
    MockLLMProvider.register(
        "job_analysis",
        JobAnalysis(
            role_type="Data Scientist NLP",
            seniority="mid",
            domain="HealthTech",
            main_tasks=["Build RAG pipelines", "Productionize ML services"],
            required_skills=["Python", "PyTorch", "RAG"],
            nice_to_have=["AWS"],
            match_reasons=["Strong NLP background", "Multimodal AI experience"],
            risks=["No prior healthtech experience"],
            cv_keywords_to_include=["PyTorch", "RAG", "FAISS"],
        ),
    )
    MockLLMProvider.register(
        "cv_adaptation",
        AdaptedCV(
            cv_title="Data Scientist – NLP & Multimodal AI",
            professional_summary=(
                "Data Scientist with 2 years applied R&D in multimodal AI and "
                "clinical digital biomarkers. Strong NLP/RAG and speech pipelines."
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
        ),
    )
    MockLLMProvider.register(
        "email_writer",
        EmailDraft(
            subject="Candidature : Data Scientist NLP – Lachtar Nour",
            body=(
                "Bonjour,\n\nJe me permets de candidater au poste de Data Scientist NLP. "
                "Mon expérience chez Emobot en biomarqueurs cliniques et NLP, ainsi que mon "
                "projet RAG SciFact, correspondent bien aux pipelines que vous décrivez. "
                "Je serai ravi d'échanger sur la suite.\n\nCordialement,\nNour"
            ),
        ),
    )


def test_ingest_text_persists_job() -> None:
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    report = p.ingest_text(
        text="Build ML pipelines.",
        title="Data Scientist",
        company="Acme",
        location="Paris",
    )
    assert report.persisted == 1
    assert len(report.job_ids) == 1


def test_ingest_skips_already_processed_duplicate() -> None:
    from smartapply.database import session_scope
    from smartapply.database.models import JobStatus
    from smartapply.database.repository import update_status
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    first = p.ingest_text(
        text="Build ML pipelines with Python.",
        title="Data Scientist",
        company="Acme",
        location="Paris",
    )
    with session_scope() as s:
        update_status(s, first.job_ids[0], JobStatus.ANALYZED)

    second = p.ingest_text(
        text="Build ML pipelines with Python.",
        title="Data Scientist",
        company="Acme",
        location="Paris",
    )

    assert second.fetched == 1
    assert second.persisted == 0
    assert second.inserted == 0
    assert second.updated_pending == 0
    assert second.skipped_processed == 1
    assert second.job_ids == []


def test_ingestor_splits_or_queries_and_balances_results(monkeypatch: pytest.MonkeyPatch) -> None:
    from smartapply.pipeline.ingestor import (
        expand_query_for_source,
        Ingestor,
        split_or_query,
    )

    assert split_or_query("Data Scientist OR Machine Learning Engineer OR AI Engineer") == [
        "Data Scientist",
        "Machine Learning Engineer",
        "AI Engineer",
    ]
    assert expand_query_for_source("serpapi", "Machine Learning Engineer CDI") == [
        "Machine Learning Engineer",
        "Ingénieur Machine Learning",
    ]
    assert expand_query_for_source("serpapi", "Data Analyst") == [
        "Data Analyst",
        "Analyste Data",
    ]
    assert expand_query_for_source("francetravail", "machine learning ing") == [
        "machine learning ing",
        "Ingénieur Machine Learning"
    ]

    calls: list[tuple[str, int | None]] = []

    class FakeScraper:
        name = "fake"

        def is_available(self) -> bool:
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            calls.append((query, max_results))
            for i in range(max_results or 1):
                yield RawJob(
                    external_id=f"fake:{query}:{i}",
                    title=query,
                    company=f"Company {i}",
                    location="Paris",
                    description="Build ML systems.",
                    source="fake",
                )

    monkeypatch.setattr("smartapply.pipeline.ingestor.get_scraper", lambda source: FakeScraper())

    report = Ingestor().from_source(
        "serpapi",
        "Data Scientist OR Machine Learning Engineer OR AI Engineer",
        max_results=7,
    )

    assert [query for query, _ in calls] == [
        "Data Scientist",
        "Scientifique des données",
        "Machine Learning Engineer",
        "Ingénieur Machine Learning",
        "AI Engineer",
        "Ingénieur IA",
    ]
    assert [max_results for _, max_results in calls] == [2, 2, 2, 2, 2, 2]
    assert report.fetched == 7
    assert report.persisted == 7


def test_serpapi_cdi_uses_fulltime_chip_not_query_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    from smartapply.pipeline import Pipeline

    calls: list[str] = []
    chips_seen: list[str | None] = []

    class FakeScraper:
        name = "serpapi"

        def is_available(self) -> bool:
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            calls.append(query)
            chips_seen.append(kwargs.get("chips"))
            for i in range(max_results or 1):
                yield RawJob(
                    external_id=f"serpapi:{query}:{i}",
                    title=query,
                    company=f"Company {i}",
                    location="Paris",
                    description="Build ML systems.",
                    source="serpapi",
                )

    monkeypatch.setattr("smartapply.pipeline.ingestor.get_scraper", lambda source: FakeScraper())

    pipeline = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    pipeline.ingest(
        "serpapi",
        "Data Scientist OR Machine Learning Engineer",
        max_results=4,
    )

    assert calls == [
        "Data Scientist",
        "Scientifique des données",
        "Machine Learning Engineer",
        "Ingénieur Machine Learning",
    ]
    assert all(chips == "employment_type:FULLTIME" for chips in chips_seen)


def test_process_pending_can_analyze_only_selected_jobs() -> None:
    _register_llm_responses()
    from smartapply.database import session_scope
    from smartapply.database.models import Job, JobStatus
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    first = p.ingest_text(
        text="Build RAG pipelines with Python.",
        title="Data Scientist NLP",
        company="SelectedCo",
        location="Paris",
    )
    second = p.ingest_text(
        text="Build RAG pipelines with Python.",
        title="Data Scientist NLP",
        company="LaterCo",
        location="Paris",
    )

    report = p.process_pending(top_k_analyze=1, job_ids=first.job_ids)

    assert report.total == 1
    assert report.analyzed == 1
    with session_scope() as s:
        selected = s.get(Job, first.job_ids[0])
        later = s.get(Job, second.job_ids[0])
        assert selected.status == JobStatus.ANALYZED
        assert later.status == JobStatus.SCRAPED


def test_filter_pending_archives_internships_before_llm() -> None:
    from smartapply.database import session_scope
    from smartapply.database.models import Job, JobStatus
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    stage = p.ingest_text(
        text="Stage de six mois en data science.",
        title="Data Scientist Stage",
        company="StageCo",
        location="Paris",
    )
    cdi = p.ingest_text(
        text="Build ML pipelines with Python and PyTorch.",
        title="Data Scientist",
        company="GoodCo",
        location="Paris",
    )

    report = p.filter_pending()

    assert report.total == 2
    assert report.kept == 1
    assert report.rejected == 1
    assert cdi.job_ids[0] in report.kept_ids
    assert stage.job_ids[0] in report.rejected_ids
    with session_scope() as s:
        stage_job = s.get(Job, stage.job_ids[0])
        cdi_job = s.get(Job, cdi.job_ids[0])
        assert stage_job.status == JobStatus.ARCHIVED
        assert cdi_job.status == JobStatus.SCRAPED


def test_process_pending_respects_manual_filter_override() -> None:
    _register_llm_responses()
    from smartapply.database import session_scope
    from smartapply.database.models import Job, JobStatus
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    stage = p.ingest_text(
        text="Stage de six mois en data science avec Python et PyTorch.",
        title="Data Scientist Stage",
        company="StageCo",
        location="Paris",
    )

    report = p.process_pending(
        top_k_analyze=1,
        job_ids=stage.job_ids,
        local_filter_override_ids=stage.job_ids,
    )

    assert report.total == 1
    assert report.kept_after_filter == 1
    assert report.analyzed == 1
    with session_scope() as s:
        job = s.get(Job, stage.job_ids[0])
        assert job.status == JobStatus.ANALYZED
        assert "Manual override" in " ".join(job.score.components["reasons"])


def test_full_pipeline_with_mocked_dependencies() -> None:
    _register_llm_responses()
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())

    # Manually ingest two different jobs (skipping the scrapers HTTP layer)
    p.ingest_text(
        text=(
            "Construire des pipelines RAG avec PyTorch et Hugging Face. "
            "Travailler sur du multimodal AI pour HealthTech. CDI Paris."
        ),
        title="Data Scientist NLP",
        company="Acme AI",
        location="Paris, France",
        application_url="https://example.com/jobs/42",
    )
    p.ingest_text(
        text="Vous gérez l'équipe commerciale. Atteindre 200% des quotas.",
        title="Sales Director",
        company="BetaSales",
        location="Paris, France",
    )

    # Process — filter + rank + analyze the relevant job
    process = p.process_pending()
    assert process.total == 2
    assert process.kept_after_filter == 1  # sales should be filtered out
    assert process.analyzed == 1

    # Apply
    from smartapply.database import session_scope
    from smartapply.database.repository import top_jobs_by_score

    with session_scope() as s:
        top = list(top_jobs_by_score(s, 1))
    assert top, "Expected at least one ranked job"
    top_id = top[0].id

    # Mock contact finder so we don't hit the network
    p.contact_finder.find = MagicMock(return_value=[])

    report = p.apply_to(top_id, create_gmail_draft=False)
    assert report.application_id is not None
    assert report.docx_path and Path(report.docx_path).exists()
    assert report.cv_pdf_path and Path(report.cv_pdf_path).exists()
    assert report.letter_pdf_path and Path(report.letter_pdf_path).exists()
    assert report.eml_path and Path(report.eml_path).exists()
    assert not report.validation_errors


def test_pipeline_invalid_source_raises() -> None:
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    with pytest.raises(Exception):
        p.ingest("serpapi", "data scientist")  # no API key in tests


def test_offer_language_detection_fr_and_en() -> None:
    from smartapply.pipeline import Pipeline

    assert Pipeline._detect_offer_language("Vos missions: analyser des donnees. CDI Paris.") == "fr"
    assert Pipeline._detect_offer_language("Responsibilities: build ML models. English required.") == "en"


def test_next_action_for_sent_application() -> None:
    from datetime import datetime, timezone

    from smartapply.jobsearch import next_action_for

    action = next_action_for("sent", datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert "08/05/2026" in action
