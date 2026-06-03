"""Semantic ranking — embeddings + composite scoring."""

from smartapply.ranking.embeddings import (
    EmbeddingsProvider,
    LocalEmbeddingsProvider,
    MockEmbeddingsProvider,
    OpenAIEmbeddingsProvider,
    cosine_similarity,
    get_embeddings_provider,
)
from smartapply.ranking.scorer import (
    WEIGHTS,
    JobScorer,
    ScoreComponents,
    build_job_text,
    build_profile_text,
)

__all__ = [
    "EmbeddingsProvider",
    "JobScorer",
    "LocalEmbeddingsProvider",
    "MockEmbeddingsProvider",
    "OpenAIEmbeddingsProvider",
    "ScoreComponents",
    "WEIGHTS",
    "build_job_text",
    "build_profile_text",
    "cosine_similarity",
    "get_embeddings_provider",
]
