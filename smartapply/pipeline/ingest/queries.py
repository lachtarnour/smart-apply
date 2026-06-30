"""Source-aware query expansion for ingestion."""

from __future__ import annotations

import re

OR_SPLIT_RE = re.compile(r"\s+\bOR\b\s+", flags=re.IGNORECASE)
QUERY_AGNOSTIC_SOURCES = {"welcometothejungle"}
ROLE_QUERY_ALIASES_FR: dict[str, tuple[str, ...]] = {
    "data scientist": ("Data Science", "Scientifique des données"),
    "data analyst": ("Analyste Data",),
    "machine learning engineer": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "machine learning ing": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "ml engineer": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "ml ing": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "nlp engineer": ("NLP Engineer", "Ingénieur NLP"),
    "computer vision engineer": (
        "Computer Vision",
        "Ingénieur Vision par ordinateur",
    ),
    "ai engineer": (
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ),
    "ai ing": (
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ),
    "artificial intelligence engineer": (
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ),
    "research engineer": ("Ingénieur Recherche IA",),
    "research engineer ai": ("Ingénieur Recherche IA",),
    "mlops engineer": ("Ingénieur MLOps",),
    "analytics engineer": ("Analytics Engineer",),
}

def split_or_query(query: str) -> list[str]:
    """Split a user query like ``A OR B OR C`` into concrete searches.

    Job APIs do not all interpret boolean syntax consistently. Running one
    precise search per role is more predictable, then persistence de-duplicates
    the offers by external id.
    """
    parts = [part.strip() for part in OR_SPLIT_RE.split(query.strip())]
    return [part for part in parts if part] or [query.strip()]


def expand_query_for_source(source: str, query: str) -> list[str]:
    """Return source-aware search variants while preserving the user query.

    Google Jobs and France Travail can be uneven with English role titles in
    France. We keep the original wording so fully English offers are still
    found, then add a French alias when it is known to improve recall.
    """
    normalized = re.sub(r"\s+", " ", query.strip())
    if source.lower() not in {"serpapi", "francetravail"}:
        return [normalized]
    key = normalized.lower()
    suffix = ""
    if key.endswith(" cdi"):
        key = key[:-4].strip()
        if source.lower() == "serpapi":
            normalized = re.sub(r"\s+cdi$", "", normalized, flags=re.IGNORECASE).strip()
        else:
            suffix = " CDI"
    variants = [normalized]
    for alias in ROLE_QUERY_ALIASES_FR.get(key, ()):
        alias_query = f"{alias}{suffix}"
        if alias_query.lower() != normalized.lower():
            variants.append(alias_query)
    return variants


