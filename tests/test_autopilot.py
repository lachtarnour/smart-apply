"""Tests for the autopilot high-volume drafting workflow."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from smartapply.email_agent.contact_providers import ContactCandidate, ContactProvider
from smartapply.llm import (
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    ApplicationDraft,
    ApplicationQualityReview,
    JobAnalysis,
    MockLLMProvider,
)
from smartapply.ranking import MockEmbeddingsProvider


class AlternatingContactProvider(ContactProvider):
    name = "test"

    def find(self, *, company: str, application_url: str | None):
        try:
            idx = int(company.rsplit(" ", 1)[-1])
        except ValueError:
            idx = 0
        if idx % 2:
            return []
        return [
            ContactCandidate(
                email=f"jobs{idx}@example.com",
                source_url=application_url or "test",
                confidence=0.9,
                provider=self.name,
                verified=True,
            )
        ]


class EmptyCountingContactProvider(ContactProvider):
    name = "empty_counting"

    def __init__(self):
        self.calls = 0

    def find(self, *, company: str, application_url: str | None):
        self.calls += 1
        return []


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "smartapply.db"
    output_dir = tmp_path / "output"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("AUTOPILOT_MIN_SCORE", "0")
    monkeypatch.setenv("AUTOPILOT_CONTACT_MIN_CONFIDENCE", "0.6")

    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import reset_engine_cache
    reset_engine_cache()
    from smartapply.database.session import init_db
    init_db()
    yield
    reset_engine_cache()
    get_settings.cache_clear()


def _register_llm(approved: bool = True) -> None:
    MockLLMProvider.clear()
    motivation_body = (
        "Bonjour,\n\n"
        "Je vous adresse ma candidature pour le poste de Data Scientist NLP. "
        "Chez Emobot, j'ai construit des pipelines de biomarqueurs numeriques "
        "a partir de donnees faciales, de mobilite et de smartphone, avec une "
        "correlation de 0.67 avec des scores cliniques valides. Cette experience "
        "m'a donne une pratique concrete de Python, PyTorch et de la modelisation "
        "appliquee a des donnees sensibles, avec une attention forte portee a la "
        "qualite des signaux et a la validation. J'ai aussi developpe des pipelines "
        "speech et NLP autour de Whisper et Pyannote, utiles pour structurer des "
        "donnees complexes avant leur exploitation. En parallele, mon projet "
        "SciFact RAG Verifier m'a permis de construire une chaine de verification "
        "avec BM25, FAISS, reranking et generation de reponses fondees. Ces elements "
        "correspondent bien aux missions de construction de pipelines RAG, de "
        "fine-tuning et de mise en production de modeles que vous decrivez. "
        "Mon parcours combine donc experimentation, evaluation et integration "
        "logicielle, ce qui me permet d'avancer rapidement sur des cas d'usage "
        "data tout en restant attentif a la robustesse des resultats. "
        "Je serais heureux d'echanger sur la maniere dont ce profil pourrait "
        "contribuer a vos sujets data et IA.\n\n"
        "Cordialement,\n"
        "Lachtar Nour"
    )
    MockLLMProvider.register(
        "job_analysis",
        JobAnalysis(
            role_type="Data Scientist NLP",
            seniority="mid",
            domain="AI",
            main_tasks=["Build RAG pipelines", "Fine-tune models"],
            required_skills=["Python", "PyTorch", "RAG"],
            nice_to_have=["AWS"],
            match_reasons=["Strong NLP/RAG profile"],
            risks=[],
            cv_keywords_to_include=["PyTorch", "RAG", "FAISS"],
        ),
    )
    MockLLMProvider.register(
        "cv_adaptation",
        AdaptedCV(
            cv_title="Data Scientist - NLP & Multimodal AI",
            professional_summary="Data Scientist with applied R&D experience in NLP and multimodal AI.",
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
                        )
                    ],
                )
            ],
            selected_project_ids=["proj_scifact_rag", "proj_ner_camembert"],
            skills_order=["ml_ai", "data_infra", "stats_signal"],
            warnings=[],
        ),
    )
    MockLLMProvider.register(
        "application_draft",
        ApplicationDraft(
            cv_title="Data Scientist - NLP & Multimodal AI",
            professional_summary="Data Scientist with applied R&D experience in NLP and multimodal AI.",
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
                        )
                    ],
                )
            ],
            selected_project_ids=["proj_scifact_rag", "proj_ner_camembert"],
            skills_order=["ml_ai", "data_infra", "stats_signal"],
            warnings=[],
            motivation_letter_subject="Candidature - Data Scientist NLP - Lachtar Nour",
            motivation_letter_body=motivation_body,
        ),
    )
    MockLLMProvider.register(
        "application_quality_review",
        ApplicationQualityReview(
            approved=approved,
            match_score=0.9 if approved else 0.2,
            cv_score=0.88 if approved else 0.2,
            email_score=0.87 if approved else 0.2,
            risks=[] if approved else ["Weak match"],
            fixes_required=[] if approved else ["Do not apply"],
            decision_reason="Strong application" if approved else "Weak application",
        ),
    )


def test_autopilot_end_to_end_creates_drafts_and_form_queue(monkeypatch: pytest.MonkeyPatch):
    _register_llm(approved=True)
    monkeypatch.setattr(
        "smartapply.pipeline.applier.create_draft",
        lambda **kwargs: f"draft-{kwargs['recipient']}",
    )

    from smartapply.email_agent.contact_providers import ContactProviderChain
    from smartapply.jobsearch import AutopilotRunner
    from smartapply.pipeline import Pipeline

    chain = ContactProviderChain([AlternatingContactProvider()], min_confidence=0.6)
    pipeline = Pipeline(
        embeddings=MockEmbeddingsProvider(),
        llm=MockLLMProvider(),
        contact_chain=chain,
    )
    for i in range(20):
        pipeline.ingest_text(
            text="Build RAG pipelines with Python, PyTorch, FAISS and Hugging Face.",
            title="Data Scientist NLP",
            company=f"ContactCo {i}",
            location="Paris, France",
            application_url=f"https://contactco{i}.com/jobs/42",
        )

    report = AutopilotRunner(pipeline=pipeline).run(
        query="Data Scientist",
        sources=["manual"],
        target_drafts=12,
        create_gmail_drafts=True,
    )
    assert report.attempted >= 12
    assert report.draft_created > 0
    assert report.ready_for_form_submission > 0
    assert report.productive_outputs >= 12


def test_autopilot_quality_gate_blocks_application(monkeypatch: pytest.MonkeyPatch):
    _register_llm(approved=False)
    monkeypatch.setattr(
        "smartapply.pipeline.applier.create_draft",
        lambda **kwargs: "should-not-be-called",
    )

    from smartapply.email_agent.contact_providers import ContactProviderChain
    from smartapply.jobsearch import AutopilotRunner
    from smartapply.pipeline import Pipeline

    pipeline = Pipeline(
        embeddings=MockEmbeddingsProvider(),
        llm=MockLLMProvider(),
        contact_chain=ContactProviderChain([AlternatingContactProvider()]),
    )
    pipeline.ingest_text(
        text="Build RAG pipelines with Python and PyTorch.",
        title="Data Scientist NLP",
        company="ContactCo 0",
        location="Paris, France",
        application_url="https://contactco0.com/jobs/42",
    )

    report = AutopilotRunner(pipeline=pipeline).run(
        query="Data Scientist",
        sources=["manual"],
        target_drafts=1,
        create_gmail_drafts=True,
    )
    assert report.quality_rejected == 1
    assert report.draft_created == 0


def test_autopilot_caches_negative_contact_lookup(monkeypatch: pytest.MonkeyPatch):
    _register_llm(approved=True)
    monkeypatch.setattr(
        "smartapply.pipeline.applier.create_draft",
        lambda **kwargs: "should-not-be-called",
    )

    from smartapply.email_agent.contact_providers import ContactProviderChain
    from smartapply.jobsearch import AutopilotRunner
    from smartapply.pipeline import Pipeline

    provider = EmptyCountingContactProvider()
    pipeline = Pipeline(
        embeddings=MockEmbeddingsProvider(),
        llm=MockLLMProvider(),
        contact_chain=ContactProviderChain([provider], min_confidence=0.6),
    )
    for i in range(2):
        pipeline.ingest_text(
            text=(
                f"Build RAG pipelines with Python and PyTorch. Posting {i}. "
                f"Different applied AI scope {i}."
            ),
            title=f"{'Data Scientist NLP' if i == 0 else 'Machine Learning Engineer RAG'}",
            company="SameCo",
            location="Paris, France",
            application_url=f"https://sameco.com/jobs/{i}",
        )

    report = AutopilotRunner(pipeline=pipeline).run(
        query="Data Scientist",
        sources=["manual"],
        target_drafts=2,
        create_gmail_drafts=True,
    )

    assert report.ready_for_form_submission == 2
    assert provider.calls == 1


def test_autopilot_cli_returns_json_without_external_sources() -> None:
    from smartapply.cli import cli

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["autopilot", "--source", "manual", "--target-drafts", "25"],
    )
    assert result.exit_code == 0
    assert '"target_drafts": 25' in result.output
