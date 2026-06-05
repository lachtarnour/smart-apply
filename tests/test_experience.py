"""Tests for the bilingual minimum-experience extractor."""

from __future__ import annotations

import pytest

from smartapply.utils.experience import required_min_years

# ============================================================
# Positive cases — extracts the minimum requirement
# ============================================================


@pytest.mark.parametrize(
    "text, expected",
    [
        # ---- French ----
        ("5+ ans d'expérience", 5),
        ("5 + ans d'expérience requis", 5),
        ("minimum 5 ans d'expérience", 5),
        ("Minimum 4 ans en data science", 4),
        ("au moins 6 ans d'expérience", 6),
        ("3 ans d'expérience minimum", 3),
        ("expérience de 7 ans requise", 7),
        ("5 ans minimum dans le domaine", 5),
        ("3 ans requis sur Python", 3),
        ("5 à 7 ans d'expérience", 5),
        ("5-7 ans d'expérience", 5),
        ("3 ans d'exp minimum en ML", 3),
        # ---- English ----
        ("5+ years of experience", 5),
        ("5+ years required", 5),
        ("minimum 5 years of experience", 5),
        ("at least 4 years of experience", 4),
        ("3 years required", 3),
        ("5 to 7 years of experience", 5),
        ("5-7 years experience", 5),
        ("experience of 8 years required", 8),
        ("3 yrs minimum", 3),
        # ---- Mixed phrasings ----
        ("Looking for someone with 7+ years experience", 7),
        ("Data Scientist Senior - 4+ years of experience", 4),
    ],
)
def test_extracts_required_years_in_both_languages(text: str, expected: int) -> None:
    assert required_min_years(text) == expected


def test_takes_minimum_when_multiple_mentions() -> None:
    """If both '3 ans minimum' and '5+ ans préféré' are stated, return 3."""
    assert (
        required_min_years("3 ans minimum d'expérience, 5+ ans préféré")
        == 3
    )


def test_handles_title_and_description_combined() -> None:
    text = (
        "Senior Data Scientist NLP\n"
        "Build RAG pipelines. Minimum 6 years of experience in ML."
    )
    assert required_min_years(text) == 6


# ============================================================
# Negative cases — must return None, not a false positive
# ============================================================


@pytest.mark.parametrize(
    "text",
    [
        "Data Scientist role with strong Python skills",
        "Build RAG pipelines with FAISS and BM25",
        "We are a fast growing startup",
        "Forte de 30 ans d'expérience, notre entreprise recrute en data.",
        "Groupe avec 30 ans d'expérience et 20 ans de savoir-faire.",
        "Depuis 30 ans, ce cabinet accompagne ses clients.",
        "Cabinet avec 25 ans d'expérience dans le recrutement data.",
        "Société créée depuis 20 ans dans le logiciel.",
        "30 ans de savoir-faire au service de nos clients.",
        "Une expérience de 5 ans serait appréciée.",
        "Idéalement 5 ans d'expérience en data.",
        "5+ ans d'expérience souhaités en data.",
        "5+ years of experience preferred.",
        "Première expérience appréciée.",
        "Expérience significative souhaitée.",
        "Moins de 30 ans requis pour ce dispositif.",
        "Vous avez moins de 30 ans à la date de démarrage.",
        "Âge limite: 30 ans.",
        "Condition d'âge : moins de 30 ans.",
        "Cabinet avec 30+ ans d'expérience dans le recrutement.",
        "Stage de 5 mois",  # months, not years
        "5 jours par semaine",  # 5 days/week, not years
        "Démarrage 5 septembre",  # 5 september, not years
        "",
        None,  # type: ignore
    ],
)
def test_no_explicit_requirement_returns_none(text) -> None:
    assert required_min_years(text) is None


# ============================================================
# Edge cases — diplomas, fuzzy phrasings, sanity bounds
# ============================================================


def test_bac_plus_5_is_not_an_experience_signal() -> None:
    """'Bac+5' is a diploma level, not 5 years of experience."""
    assert required_min_years("Bac+5 souhaité") is None


def test_bac_plus_5_with_real_required_experience_returns_only_experience() -> None:
    """Strip Bac+5, but keep the explicit experience requirement."""
    assert required_min_years("Bac+5 avec minimum 2 ans d'expérience en data") == 2


def test_ambiguous_experience_after_diploma_is_not_a_hard_requirement() -> None:
    assert required_min_years("Bac+5 avec 2 ans d'expérience en data") is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Vous justifiez de 5 ans d'expérience minimum en data science.", 5),
        ("Vous disposez de 6 ans d'expérience sur un poste similaire.", 6),
        ("Vous avez au moins 5 ans d'expérience en machine learning.", 5),
        ("At least 5 years of experience in ML.", 5),
        ("5 years in a similar role.", 5),
        ("Vous justifiez de 15 ans d'expérience.", 15),
        ("Expérience demandée: 60 mois en data science.", 5),
    ],
)
def test_candidate_experience_phrasings_are_extracted(
    text: str,
    expected: int,
) -> None:
    assert required_min_years(text) == expected


def test_master_plus_2_is_diploma_not_experience() -> None:
    assert required_min_years("Master+2 minimum") is None


def test_sanity_bound_ignores_huge_numbers() -> None:
    """Numbers above 30 likely aren't experience years (could be dataset size)."""
    assert required_min_years("Trained on 100 ans of data") is None


def test_mixed_company_and_candidate_experience_returns_candidate_requirement() -> None:
    text = (
        "Entreprise avec 30 ans d'expérience. "
        "Vous justifiez de 3 ans d'expérience en Python."
    )
    assert required_min_years(text) == 3


def test_mixed_company_and_optional_experience_returns_none() -> None:
    text = (
        "Cabinet avec 25 ans d'expérience. "
        "Une expérience de 5 ans serait appréciée."
    )
    assert required_min_years(text) is None
