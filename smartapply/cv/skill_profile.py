"""Shared skill-profile inference for CV renderers."""

from __future__ import annotations

from smartapply.profile import Profile

PROFILE_PRIORITY = (
    "medical_ai",
    "reinforcement_learning",
    "computer_vision",
    "speech_audio",
    "llm",
    "time_series",
    "data_analyst",
    "machine_learning",
)


def infer_skill_profile_id(
    profile: Profile,
    context: str,
    *,
    default: str | None = None,
) -> str | None:
    """Infer the best profile family from adapted CV context."""
    normalized = (context or "").lower()
    for profile_id in PROFILE_PRIORITY:
        if profile_id in profile.skills.profile_ids and any(
            keyword.lower() in normalized
            for keyword in profile.skills.matching_keywords.get(profile_id, [])
        ):
            return profile_id

    fallback_rules = (
        (
            "reinforcement_learning",
            ("reinforcement", "agent training", "game-based task"),
        ),
        (
            "medical_ai",
            ("clinical", "medical", "digital health", "biomarker", "healthtech", "medtech"),
        ),
        (
            "computer_vision",
            (
                "computer vision",
                "image classification",
                "object detection",
                "segmentation",
                "face recognition",
            ),
        ),
        ("llm", ("llm", "rag", "nlp", "language model", "transformer", "embedding model", "retrieval")),
        ("time_series", ("forecasting", "time series", "time-series", "anomaly detection", "arima", "kalman")),
        ("data_analyst", ("data analyst", "analytics", "dashboard", "kpi", "reporting", "product analyst")),
        ("machine_learning", ("ml engineer", "deployment", "production", "mlops", "model serving", "data pipeline")),
    )
    for profile_id, tokens in fallback_rules:
        if profile_id in profile.skills.profile_ids and any(token in normalized for token in tokens):
            return profile_id
    return default
