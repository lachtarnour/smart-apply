"""Integration tests for the end-to-end pipeline.

Every external dependency is mocked: scrapers, LLM and embeddings. The
pipeline is exercised against real profile data so the
anti-hallucination contract is validated too.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from smartapply.llm import (
    AdaptedBullet,
    AdaptedCV,
    AdaptedExperience,
    ApplicationDraft,
    JobAnalysis,
    MockLLMProvider,
)
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
            extracted_location="Paris",
            company_context=(
                "Acme AI builds HealthTech tools for clinical NLP workflows."
            ),
            offer_interest_points=[
                "Build RAG pipelines for healthcare teams",
                "Productionize ML services in a HealthTech context",
            ],
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
        "application_draft",
        ApplicationDraft(
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
            motivation_letter_subject="Candidature - Data Scientist NLP - Lachtar Nour",
            motivation_letter_body=(
                "Bonjour,\n\n"
                "Je vous adresse ma candidature pour le poste de Data Scientist NLP. "
                "Mon expérience chez Emobot en biomarqueurs cliniques et NLP, ainsi que mon "
                "projet RAG SciFact, correspondent bien aux pipelines que vous décrivez. "
                "Je serai ravi d'échanger sur la suite.\n\n"
                "Cordialement,\n"
                "Lachtar Nour"
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
        Ingestor,
        expand_query_for_source,
        split_or_query,
    )

    assert split_or_query("Data Scientist OR Machine Learning Engineer OR AI Engineer") == [
        "Data Scientist",
        "Machine Learning Engineer",
        "AI Engineer",
    ]
    assert expand_query_for_source("serpapi", "Machine Learning Engineer CDI") == [
        "Machine Learning Engineer",
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ]
    assert expand_query_for_source("serpapi", "Data Analyst") == [
        "Data Analyst",
        "Analyste Data",
    ]
    assert expand_query_for_source("francetravail", "machine learning ing") == [
        "machine learning ing",
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
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
        max_results=11,
    )

    assert [query for query, _ in calls] == [
        "Data Scientist",
        "Data Science",
        "Scientifique des données",
        "Machine Learning Engineer",
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
        "AI Engineer",
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ]
    # Each scraper call now gets a generous raw budget (``max_results`` × 10)
    # so the round-robin can paginate past already-known offers without
    # blowing the global cap. The collector itself still enforces the
    # real cap of 11 new offers — see ``_collect_round_robin``.
    assert [max_results for _, max_results in calls] == [110] * 11
    assert report.fetched == 11
    assert report.persisted == 11
    from smartapply.database import session_scope
    from smartapply.database.models import Job

    with session_scope() as s:
        titles = [
            job.title
            for job in s.query(Job)
            .filter(Job.id.in_(report.job_ids))
            .order_by(Job.id.asc())
            .all()
        ]
    assert Counter(titles) == {
        "Data Scientist": 1,
        "Data Science": 1,
        "Scientifique des données": 1,
        "Machine Learning Engineer": 1,
        "Machine Learning": 1,
        "ML Engineer": 1,
        "Ingénieur Machine Learning": 1,
        "AI Engineer": 1,
        "Ingénieur IA": 1,
        "Ingénieur Intelligence Artificielle": 1,
        "AI ML Engineer": 1,
    }


# ---- max_results semantics: "new offers", not "raw fetched" -----------------
# Regression guard for the bug where re-running a France Travail search
# returned ``0 nouvelle(s)`` because the most recent offers in the API were
# already in the DB and consumed the whole ``max_results`` quota before any
# new offer could surface.


def _yielding_scraper(yields: list[RawJob]) -> type:
    """Build a deterministic scraper class that yields the same list each call."""

    class _FakeScraper:
        name = "fake"

        def is_available(self) -> bool:  # noqa: D401
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            limit = max_results if max_results is not None else len(yields)
            yield from yields[:limit]

    return _FakeScraper


def _fake_raw_jobs(n: int) -> list[RawJob]:
    return [
        RawJob(
            external_id=f"fake:{i:03d}",
            title=f"Data Scientist {i}",
            company=f"Acme {i}",
            location="Paris",
            description="Build ML pipelines.",
            source="fake",
        )
        for i in range(n)
    ]


def test_collect_skips_known_external_ids_and_finds_genuinely_new(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas 1 : les 5 premières offres FT sont déjà en DB, les 5 suivantes
    sont nouvelles. ``max_results=5`` doit retourner les 5 nouvelles."""
    from smartapply.pipeline.ingestor import Ingestor

    yields = _fake_raw_jobs(20)
    monkeypatch.setattr(
        "smartapply.pipeline.ingestor.get_scraper",
        lambda source: _yielding_scraper(yields)(),
    )
    ing = Ingestor()
    first = ing.from_source("fake", "Data Scientist", max_results=5, split_or=False)
    assert first.inserted == 5
    assert first.skipped_known_during_collect == 0

    second = ing.from_source("fake", "Data Scientist", max_results=5, split_or=False)
    assert second.inserted == 5, (
        f"second run should find the next 5 new offers, got "
        f"inserted={second.inserted} skipped_known={second.skipped_known_during_collect}"
    )
    assert second.skipped_known_during_collect == 5
    # The pre-filter caught every duplicate before persist, so the per-row
    # ``skipped_processed`` / ``updated_pending`` paths stay quiet.
    assert second.skipped_processed == 0
    assert second.updated_pending == 0
    assert second.hit_raw_seen_cap is False


def test_collect_safety_cap_stops_when_every_offer_is_known(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas 2 : toutes les offres yieldées sont déjà connues — le collecteur
    s'arrête grâce à la limite de sécurité (``max_results × 10``), pas par
    boucle infinie."""
    from smartapply.pipeline.ingestor import Ingestor

    yields = _fake_raw_jobs(200)  # supply far above the cap
    monkeypatch.setattr(
        "smartapply.pipeline.ingestor.get_scraper",
        lambda source: _yielding_scraper(yields)(),
    )
    ing = Ingestor()
    # Pre-seed the DB with all 200 external_ids.
    first = ing.from_source("fake", "q", max_results=200, split_or=False)
    assert first.inserted == 200

    # max_results=5 → raw cap = max(50, 5*10) = 50. The collector should
    # scan 50 known offers then bail out.
    second = ing.from_source("fake", "q", max_results=5, split_or=False)
    assert second.inserted == 0
    assert second.skipped_known_during_collect == 50
    assert second.hit_raw_seen_cap is True


def test_collect_preserves_intra_call_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas 3 : la dédup intra-call (même offre yieldée deux fois dans la
    même recherche) reste silencieuse — pas comptée dans
    ``skipped_known_during_collect`` ni dans ``inserted``."""
    from smartapply.pipeline.ingestor import Ingestor

    duplicated = _fake_raw_jobs(3)
    yields = duplicated + duplicated  # each ID surfaces twice
    monkeypatch.setattr(
        "smartapply.pipeline.ingestor.get_scraper",
        lambda source: _yielding_scraper(yields)(),
    )
    ing = Ingestor()
    report = ing.from_source("fake", "q", max_results=10, split_or=False)
    assert report.inserted == 3, f"expected 3 unique, got {report.inserted}"
    assert report.skipped_known_during_collect == 0


def test_collect_caps_new_offers_at_max_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cas 4 : ``max_results=5`` retourne au maximum 5 **nouvelles** offres,
    même si le scraper continue de yielder plus loin."""
    from smartapply.pipeline.ingestor import Ingestor

    yields = _fake_raw_jobs(100)
    monkeypatch.setattr(
        "smartapply.pipeline.ingestor.get_scraper",
        lambda source: _yielding_scraper(yields)(),
    )
    ing = Ingestor()
    report = ing.from_source("fake", "q", max_results=5, split_or=False)
    assert report.inserted == 5
    assert report.fetched == 5
    assert report.skipped_known_during_collect == 0


def test_ingestor_reports_serpapi_fallback_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    from smartapply.pipeline.ingestor import Ingestor

    class FakeScraper:
        name = "serpapi"

        def is_available(self) -> bool:
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            strict_meta = {
                "_smartapply_search": {
                    "query": query,
                    "location": location,
                    "google_domain": "google.com",
                    "hl": "fr",
                    "gl": "fr",
                    "result_origin": "strict",
                    "strict_chips": "employment_type:FULLTIME,date_posted:week",
                    "fallback_reason": None,
                    "fallback_chips": None,
                    "fallback_query": None,
                }
            }
            fallback_meta = {
                "_smartapply_search": {
                    "query": query,
                    "location": location,
                    "google_domain": "google.com",
                    "hl": "fr",
                    "gl": "fr",
                    "result_origin": "fallback",
                    "strict_chips": "employment_type:FULLTIME,date_posted:week",
                    "fallback_reason": "low_result_strict_filters",
                    "fallback_chips": "employment_type:FULLTIME,date_posted:month",
                    "fallback_query": query,
                }
            }
            for i in range(2):
                yield RawJob(
                    external_id=f"serpapi:strict:{i}",
                    title=f"Strict {i}",
                    company="Acme",
                    location=location,
                    description="Build ML systems.",
                    source="serpapi",
                    source_data=strict_meta,
                )
            for i in range(8):
                yield RawJob(
                    external_id=f"serpapi:fallback:{i}",
                    title=f"Fallback {i}",
                    company="Beta",
                    location=location,
                    description="Build data products.",
                    source="serpapi",
                    source_data=fallback_meta,
                )

    monkeypatch.setattr("smartapply.pipeline.ingestor.get_scraper", lambda source: FakeScraper())

    report = Ingestor().from_source(
        "serpapi",
        "Applied Scientist",
        location="Paris, France",
        max_results=10,
        split_or=False,
    )

    assert report.fetched == 10
    assert report.search_audit == [
        {
            "query": "Applied Scientist",
            "location": "Paris, France",
            "google_domain": "google.com",
            "hl": "fr",
            "gl": "fr",
            "strict_results": 2,
            "fallback_added": 8,
            "final_results": 10,
            "fallback_reason": "low_result_strict_filters",
            "strict_chips": "employment_type:FULLTIME,date_posted:week",
            "fallback_chips": "employment_type:FULLTIME,date_posted:month",
            "fallback_query": "Applied Scientist",
        }
    ]


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
        "Data Science",
        "Scientifique des données",
        "Machine Learning Engineer",
    ]
    assert all(chips == "employment_type:FULLTIME" for chips in chips_seen)


def test_francetravail_permanent_preferences_use_cdi_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from smartapply.pipeline import Pipeline

    type_contrats_seen: list[str | None] = []

    class FakeScraper:
        name = "francetravail"

        def is_available(self) -> bool:
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            type_contrats_seen.append(kwargs.get("type_contrat"))
            yield RawJob(
                external_id="ft:1",
                title=query,
                company="Acme",
                location="Paris",
                description="Build ML systems.",
                source="francetravail",
                contract_type="CDI",
            )

    monkeypatch.setattr("smartapply.pipeline.ingestor.get_scraper", lambda source: FakeScraper())

    pipeline = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    pipeline.ingest("francetravail", "Data Scientist", max_results=1)

    assert type_contrats_seen == ["CDI"]


def test_francetravail_does_not_force_cdi_when_cdd_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from smartapply.pipeline import Pipeline

    type_contrats_seen: list[str | None] = []

    class FakeScraper:
        name = "francetravail"

        def is_available(self) -> bool:
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            type_contrats_seen.append(kwargs.get("type_contrat"))
            yield RawJob(
                external_id="ft:2",
                title=query,
                company="Acme",
                location="Paris",
                description="Build ML systems.",
                source="francetravail",
                contract_type="CDD",
            )

    monkeypatch.setattr("smartapply.pipeline.ingestor.get_scraper", lambda source: FakeScraper())

    pipeline = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    pipeline.profile = pipeline.profile.model_copy(deep=True)
    pipeline.profile.preferences.accepted_contract_types = ["CDI", "CDD"]
    pipeline.ingest("francetravail", "Data Scientist", max_results=1)

    assert type_contrats_seen == [None]


def test_freshness_kwargs_propagates_date_posted_to_both_sources() -> None:
    from smartapply.pipeline.pipeline import freshness_kwargs

    assert freshness_kwargs("serpapi", date_posted="week", serpapi_hl="en,fr") == {
        "date_posted": "week",
        "hl": "en,fr",
    }
    assert freshness_kwargs("francetravail", date_posted="week", serpapi_hl="en,fr") == {
        "date_posted": "week",
    }
    assert freshness_kwargs("manual", date_posted="week", serpapi_hl="en,fr") == {}
    assert freshness_kwargs("serpapi", date_posted=None, serpapi_hl=None) == {}


def test_pipeline_ingest_passes_date_posted_to_francetravail(monkeypatch: pytest.MonkeyPatch) -> None:
    from smartapply.pipeline import Pipeline

    seen_kwargs: list[dict] = []

    class FakeScraper:
        name = "francetravail"

        def is_available(self) -> bool:
            return True

        def search(self, query, location=None, *, max_results=None, **kwargs):  # noqa: ANN001, ARG002
            seen_kwargs.append(kwargs)
            for i in range(max_results or 1):
                yield RawJob(
                    external_id=f"francetravail:{query}:{i}",
                    title=query,
                    company=f"Company {i}",
                    location="Paris",
                    description="Construire des pipelines.",
                    source="francetravail",
                )

    monkeypatch.setattr("smartapply.pipeline.ingestor.get_scraper", lambda source: FakeScraper())

    pipeline = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    pipeline.ingest("francetravail", "Data Scientist", max_results=2, date_posted="week")

    assert seen_kwargs, "scraper.search was never called"
    assert all(kw.get("date_posted") == "week" for kw in seen_kwargs)
    # ``hl`` is SerpApi-only — it must NOT leak to FT
    assert all("hl" not in kw for kw in seen_kwargs)


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


def test_rank_pending_scores_without_llm_analysis() -> None:
    from smartapply.database import session_scope
    from smartapply.database.models import Job, JobStatus
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    first = p.ingest_text(
        text="Construire des modèles Machine Learning avec Python, SQL et PyTorch. CDI Paris.",
        title="Data Scientist",
        company="ScoreCo",
        location="Paris",
    )
    second = p.ingest_text(
        text="Analyser des données produit avec Python, SQL et expérimentation. CDI Lyon.",
        title="Product Data Analyst",
        company="RankCo",
        location="Lyon",
    )

    report = p.rank_pending(
        top_k_ranked=1,
        job_ids=[first.job_ids[0], second.job_ids[0]],
    )

    assert report.total == 2
    assert report.ranked == 2
    assert report.shortlisted == 1
    with session_scope() as s:
        jobs = s.query(Job).filter(Job.id.in_(report.ranked_ids)).all()
        assert all(job.score and job.score.final_score is not None for job in jobs)
        assert all(job.analyzed_at is None for job in jobs)
        assert sum(job.status == JobStatus.SHORTLISTED for job in jobs) == 1
        assert sum(job.status == JobStatus.FILTERED for job in jobs) == 1
        assert all(job.archived_at is None for job in jobs)


def test_analyze_jobs_only_selected_ranked_jobs() -> None:
    _register_llm_responses()
    from smartapply.database import session_scope
    from smartapply.database.models import Job, JobStatus
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    first = p.ingest_text(
        text="Construire des modèles Machine Learning avec Python, SQL et PyTorch. CDI Paris.",
        title="Data Scientist",
        company="AnalyzeCo",
        location="Paris",
    )
    second = p.ingest_text(
        text="Analyser des données produit avec Python, SQL et expérimentation. CDI Lyon.",
        title="Product Data Analyst",
        company="LaterRankCo",
        location="Lyon",
    )
    p.rank_pending(
        top_k_ranked=2,
        job_ids=[first.job_ids[0], second.job_ids[0]],
    )

    report = p.analyze_jobs([first.job_ids[0]])

    assert report.requested == 1
    assert report.analyzed == 1
    with session_scope() as s:
        selected = s.get(Job, first.job_ids[0])
        later = s.get(Job, second.job_ids[0])
        assert selected.status == JobStatus.ANALYZED
        assert later.status == JobStatus.SHORTLISTED
        assert later.analyzed_at is None


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
        assert stage_job.score.components["rejection_stage"] == "local_filter"
        assert any(
            "blocked_contract_visible_text:stage" in reason
            for reason in stage_job.score.components["rejection_reasons"]
        )
        assert cdi_job.status == JobStatus.SCRAPED


def test_filter_pending_records_duplicate_archive_reason() -> None:
    from smartapply.database import session_scope
    from smartapply.database.models import Job, JobStatus
    from smartapply.database.repository import upsert_job
    from smartapply.pipeline import Pipeline

    with session_scope() as s:
        first = upsert_job(
            s,
            external_id="manual:duplicate-a",
            title="Data Scientist",
            company="Acme",
            description="Build ML models with Python and PyTorch.",
            location="Paris",
            contract_type="CDI",
            source="manual",
        )
        second = upsert_job(
            s,
            external_id="manual:duplicate-b",
            title="Data Scientist H/F",
            company="Acme SAS",
            description="Build ML models with Python and PyTorch.",
            location="Paris",
            contract_type="CDI",
            source="manual",
        )
        first_id = first.id
        second_id = second.id

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    report = p.filter_pending(job_ids=[first_id, second_id])

    assert report.duplicates_removed == 1
    with session_scope() as s:
        archived = (
            s.query(Job)
            .filter(Job.id.in_([first_id, second_id]))
            .filter(Job.status == JobStatus.ARCHIVED)
            .one()
        )
        assert archived.score.components["rejection_stage"] == "deduplication"
        assert any(
            reason.startswith("duplicate_of:")
            for reason in archived.score.components["rejection_reasons"]
        )


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
        assert top[0].analysis is not None
        raw = top[0].analysis.raw_response
        assert raw["company_context"] == (
            "Acme AI builds HealthTech tools for clinical NLP workflows."
        )
        assert raw["extracted_location"] == "Paris"
        assert "Build RAG pipelines for healthcare teams" in raw["offer_interest_points"]
    top_id = top[0].id

    report = p.apply_to(top_id, create_gmail_draft=False)
    assert report.application_id is not None
    assert report.docx_path and Path(report.docx_path).exists()
    assert report.cv_pdf_path and Path(report.cv_pdf_path).exists()
    assert report.letter_pdf_path and Path(report.letter_pdf_path).exists()
    assert report.eml_path and Path(report.eml_path).exists()
    assert not report.validation_errors


def test_process_pending_replaces_generic_location_with_extracted_location() -> None:
    _register_llm_responses()
    from smartapply.database import session_scope
    from smartapply.database.models import Job
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    ingested = p.ingest_text(
        text="Build RAG pipelines with Python. Poste base a Paris.",
        title="Data Scientist NLP",
        company="Acme AI",
        location="France",
        application_url="https://acme.ai/jobs/42",
    )

    p.process_pending(job_ids=ingested.job_ids)

    with session_scope() as s:
        job = s.get(Job, ingested.job_ids[0])
        assert job is not None
        assert job.location == "Paris"


def test_apply_to_uses_manual_contact_email() -> None:
    _register_llm_responses()
    from smartapply.database import session_scope
    from smartapply.database.models import Application
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    ingested = p.ingest_text(
        text="Build RAG pipelines with Python.",
        title="Data Scientist NLP",
        company="ManualContactCo",
        location="Paris",
        application_url="https://manual.example/jobs/1",
    )
    p.process_pending(top_k_analyze=1, job_ids=ingested.job_ids)

    report = p.apply_to(
        ingested.job_ids[0],
        contact_email="Recruitment@Manual.Example",
        create_gmail_draft=False,
    )

    assert report.contact_email == "recruitment@manual.example"
    assert report.contact_source == "manual"
    assert report.status == "email_generated"
    with session_scope() as s:
        app = s.get(Application, report.application_id)
        assert app is not None
        assert app.contact is not None
        assert app.contact.email == "recruitment@manual.example"
        assert app.contact.source_url == "manual"


def test_apply_to_rejects_manual_contact_when_optional_verification_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_llm_responses()
    monkeypatch.setenv("ANYMAILFINDER_VERIFY_MANUAL_CONTACTS", "true")
    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.email_agent.contact_providers import (
        ContactCandidate,
        ContactProvider,
        ContactProviderChain,
    )
    from smartapply.pipeline import Pipeline

    class RejectingVerifier(ContactProvider):
        name = "rejecting_verifier"

        def find(
            self,
            *,
            company: str,
            application_url: str | None,
            job_location: str | None = None,
        ) -> list[ContactCandidate]:
            return []

        def verify_email(self, email: str) -> bool | None:
            return False

    p = Pipeline(
        embeddings=MockEmbeddingsProvider(),
        llm=MockLLMProvider(),
        contact_chain=ContactProviderChain([RejectingVerifier()]),
    )
    ingested = p.ingest_text(
        text="Build RAG pipelines with Python.",
        title="Data Scientist NLP",
        company="Acme",
        location="Paris",
        application_url="https://acme.ai/jobs/42",
    )
    p.process_pending(job_ids=ingested.job_ids)

    report = p.apply_to(
        ingested.job_ids[0],
        create_gmail_draft=False,
        contact_email="manual@acme.ai",
    )

    assert report.contact_email is None
    assert "manual_contact_email_not_verified" in report.validation_warnings

    get_settings.cache_clear()


def test_pipeline_invalid_source_raises() -> None:
    from smartapply.pipeline import Pipeline

    p = Pipeline(embeddings=MockEmbeddingsProvider(), llm=MockLLMProvider())
    with pytest.raises(RuntimeError):
        p.ingest("serpapi", "data scientist")  # no API key in tests


def test_offer_language_detection_fr_and_en() -> None:
    from smartapply.pipeline.language import detect_offer_language

    assert detect_offer_language("Vos missions: analyser des donnees. CDI Paris.") == "fr"
    assert detect_offer_language("Poste en télétravail avec CDI et profil recherché data.") == "fr"
    assert detect_offer_language("Responsibilities: build ML models. English required.") == "en"


def test_next_action_for_sent_application() -> None:
    from datetime import datetime, timezone

    from smartapply.jobsearch import next_action_for

    action = next_action_for("sent", datetime(2026, 5, 1, tzinfo=timezone.utc))
    assert "08/05/2026" in action
