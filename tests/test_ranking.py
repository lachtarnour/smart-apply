"""Tests for the ranking module — embeddings, scoring, rank."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from smartapply.profile import get_profile
from smartapply.ranking import (
    WEIGHTS,
    EmbeddingsProvider,
    JobScorer,
    MockEmbeddingsProvider,
    ScoreComponents,
    cosine_similarity,
    get_embeddings_provider,
)
from smartapply.ranking.embeddings import OpenAIEmbeddingsProvider


@dataclass
class FakeJob:
    title: str
    description: str
    location: str | None = None


# ----------------- Embeddings -----------------


def test_mock_provider_returns_normalized_vectors() -> None:
    p = MockEmbeddingsProvider()
    vecs = p.embed(["hello world", "data scientist pytorch"])
    assert len(vecs) == 2
    for v in vecs:
        assert len(v) == p.DIM
        # mock vectors are normalized
        norm = sum(x * x for x in v) ** 0.5
        assert abs(norm - 1.0) < 1e-6 or norm == 0.0


def test_mock_provider_similar_texts_have_higher_cosine() -> None:
    p = MockEmbeddingsProvider()
    a, b, c = p.embed(["data scientist pytorch", "data scientist", "barista coffee"])
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_factory_resolves_mock_by_default() -> None:
    # conftest sets EMBEDDINGS_PROVIDER=mock
    provider = get_embeddings_provider()
    assert isinstance(provider, MockEmbeddingsProvider)


def test_factory_rejects_unknown_provider() -> None:
    import pytest

    with pytest.raises(ValueError):
        get_embeddings_provider("nonsense")


def test_openai_embeddings_retries_transient_errors() -> None:
    import httpx
    from openai import APITimeoutError
    from tenacity import wait_none

    calls = {"count": 0}

    class FakeEmbeddings:
        def create(self, **kwargs):  # noqa: ANN003
            calls["count"] += 1
            if calls["count"] == 1:
                raise APITimeoutError(
                    request=httpx.Request("POST", "https://api.openai.test/embed")
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[1.0, 0.0]),
                    SimpleNamespace(embedding=[0.0, 1.0]),
                ]
            )

    provider = OpenAIEmbeddingsProvider(model="test-embedding", batch_size=10)
    provider._client = SimpleNamespace(embeddings=FakeEmbeddings())
    retrying = provider._create_embeddings.retry_with(wait=wait_none())
    provider._create_embeddings = retrying.__get__(provider, OpenAIEmbeddingsProvider)

    assert provider.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert calls["count"] == 2


# ----------------- Scoring -----------------


def test_score_components_final_uses_documented_weights() -> None:
    comp = ScoreComponents(
        semantic=1.0,
        skills=1.0,
        title=1.0,
        seniority=1.0,
        location=1.0,
        domain=1.0,
    )
    assert abs(comp.final - sum(WEIGHTS.values())) < 1e-9
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_scorer_prefers_target_role_in_preferred_location() -> None:
    profile = get_profile()
    provider = MockEmbeddingsProvider()
    scorer = JobScorer(profile, embeddings=provider)

    great = FakeJob(
        title="Data Scientist NLP",
        description=(
            "Build RAG pipelines with PyTorch, Hugging Face and FAISS. "
            "Work on multimodal AI for HealthTech. Junior welcome."
        ),
        location="Paris, France",
    )
    bad = FakeJob(
        title="Sales Manager",
        description="Hit revenue quotas. 10 years of B2B experience required.",
        location="Berlin, Germany",
    )

    s_great = scorer.score(great)
    s_bad = scorer.score(bad)
    assert s_great.final > s_bad.final
    assert s_great.title > s_bad.title
    assert s_great.skills > s_bad.skills
    assert s_great.location > s_bad.location


def test_scorer_rank_orders_top_k() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    jobs = [
        FakeJob("Sales Manager", "Quotas, B2B", "Berlin"),
        FakeJob("Data Scientist", "PyTorch RAG FAISS multimodal AI", "Paris"),
        FakeJob("ML Engineer", "MLOps on AWS with Docker", "Lyon"),
        FakeJob("Receptionist", "Greet visitors", "Paris"),
    ]
    ranked = scorer.rank(jobs, top_k=2)
    assert len(ranked) == 2
    titles = [j.title for j, _ in ranked]
    assert "Data Scientist" in titles
    assert "Sales Manager" not in titles


def test_scorer_rank_batches_job_embeddings() -> None:
    class CountingEmbeddings(EmbeddingsProvider):
        name = "counting"

        def __init__(self):
            self.calls: list[int] = []

        @property
        def model_name(self) -> str:
            return "counting"

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.calls.append(len(texts))
            return [[1.0, 0.0] for _ in texts]

    provider = CountingEmbeddings()
    scorer = JobScorer(get_profile(), embeddings=provider)
    jobs = [
        FakeJob("Data Scientist", "Python ML", "Paris"),
        FakeJob("ML Engineer", "PyTorch", "Lyon"),
        FakeJob("Data Analyst", "SQL", "Paris"),
    ]

    scorer.rank(jobs)

    assert provider.calls == [1, 3]


def test_scorer_seniority_penalizes_15_years() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    senior_only = FakeJob(
        title="Data Scientist",
        description="15+ years of experience required.",
        location="Paris",
    )
    s = scorer.score(senior_only)
    # seniority component should be small
    assert s.seniority < 0.3


def test_scorer_penalizes_bi_analyst_without_python() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    serious = FakeJob(
        title="Data Analyst",
        description="Analyze product data with SQL, Python, Pandas, forecasting and dashboards.",
        location="Paris",
    )
    bi_only = FakeJob(
        title="Data Analyst BI",
        description="Power BI dashboards, SQL requis. Pas de développement Python.",
        location="Paris",
    )
    assert scorer.score(serious).final > scorer.score(bi_only).final
    assert scorer.score(bi_only).skills == 0.0


def test_scorer_penalizes_senior_in_title() -> None:
    """Senior roles must be pushed down hard regardless of other signals."""
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    senior = FakeJob(
        title="Senior Data Scientist",
        description="Build ML pipelines with PyTorch in Paris.",
        location="Paris",
    )
    assert scorer.score(senior).seniority <= 0.15


def test_scorer_penalizes_4plus_years_requirement() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    job = FakeJob(
        title="Data Scientist",
        description="We are looking for 4+ years of experience in data science.",
        location="Paris",
    )
    assert scorer.score(job).seniority <= 0.45


def test_scorer_treats_any_france_location_as_acceptable() -> None:
    """France-wide cities (not in preferred_locations) score ~0.85, not 0.2."""
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    chateaufort = FakeJob("Data Scientist", "ML role", location="Châteaufort")
    saint_herblain = FakeJob("Data Scientist", "ML role", location="Saint-Herblain")
    massy = FakeJob("Data Scientist", "ML role", location="Massy")
    for job in (chateaufort, saint_herblain, massy):
        assert scorer.score(job).location >= 0.8, job.location


def test_scorer_still_penalizes_foreign_location() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    foreign = FakeJob("Data Scientist", "ML role", location="Berlin, Germany")
    assert scorer.score(foreign).location <= 0.25


def test_scorer_caps_foreign_location_final_score() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    foreign = FakeJob(
        "Data Scientist",
        "Python, PyTorch, NLP, machine learning, SQL and strong profile match.",
        location="Berlin, Germany",
    )
    score = scorer.score(foreign)
    assert score.final <= 0.35
    assert score.cap == 0.35


def test_scorer_paris_still_gets_top_location() -> None:
    profile = get_profile()
    scorer = JobScorer(profile, embeddings=MockEmbeddingsProvider())
    paris = FakeJob("Data Scientist", "ML role", location="Paris")
    assert scorer.score(paris).location == 1.0


def test_scorer_caches_profile_vector() -> None:
    profile = get_profile()
    provider = MockEmbeddingsProvider()
    scorer = JobScorer(profile, embeddings=provider)
    # Call score twice — profile embedding should be reused
    scorer.score(FakeJob("Data Scientist", "PyTorch", "Paris"))
    assert scorer._profile_vector is not None  # noqa: SLF001
    first_vec = scorer._profile_vector  # noqa: SLF001
    scorer.score(FakeJob("ML Engineer", "AWS", "Paris"))
    assert scorer._profile_vector is first_vec  # noqa: SLF001
