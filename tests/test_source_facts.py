"""Tests for source-specific structured facts used by the local filter."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from smartapply.filtering import JobFilter, ruleset_from_preferences
from smartapply.filtering.source_facts import (
    build_filter_facts,
    build_francetravail_filter_facts,
    build_serpapi_filter_facts,
)
from smartapply.profile import get_profile


@dataclass
class FakeJob:
    title: str = "Data Scientist"
    company: str = "Acme"
    description: str = "Python, SQL et machine learning."
    location: str | None = "Paris"
    contract_type: str | None = "CDI"
    remote_policy: str | None = None
    application_url: str | None = None
    source: str | None = "francetravail"
    source_data: dict[str, Any] | None = field(default_factory=dict)


def _real_filter(*, use_source_facts: bool = True) -> JobFilter:
    rules = ruleset_from_preferences(get_profile().preferences)
    return JobFilter(rules, use_source_facts=use_source_facts)


def test_francetravail_smart_experience_min_years_is_used() -> None:
    facts = build_francetravail_filter_facts(
        {
            "_smartapply_experience": {
                "requirement": "required",
                "required": True,
                "min_years": 3,
            },
        }
    )

    assert facts.experience_min_years == 3
    assert facts.experience_required is True
    assert "experience_min_years:3" in facts.facts_used


def test_francetravail_beginner_accepted_skips_text_experience_rejection() -> None:
    job = FakeJob(
        description=(
            "Vous justifiez de 5 ans d'expérience minimum. "
            "Python, SQL et machine learning."
        ),
        source_data={
            "experienceExige": "D",
            "experienceLibelle": "Débutant accepté",
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    baseline = _real_filter(use_source_facts=False).evaluate(job)
    after = _real_filter().evaluate(job)

    assert not baseline.kept
    assert any("experience_required_too_high" in reason for reason in baseline.reasons)
    assert after.kept, after.reasons
    assert "experience_structured_francetravail:beginner_accepted" in after.reasons


def test_francetravail_without_structured_experience_falls_back_to_text() -> None:
    job = FakeJob(
        description=(
            "Vous justifiez de 5 ans d'expérience minimum. "
            "Python, SQL et machine learning."
        ),
        source_data={
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    result = _real_filter().evaluate(job)

    assert not result.kept
    assert any("experience_required_too_high:5+ years" in r for r in result.reasons)
    assert not any(r.startswith("experience_structured_") for r in result.reasons)


def test_francetravail_cdi_contract_is_exploitable() -> None:
    facts = build_francetravail_filter_facts(
        {
            "typeContrat": "CDI",
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
        }
    )

    assert facts.structured_contract_type == "CDI"
    assert facts.structured_contract_source == "francetravail:typeContratLibelle"


def test_francetravail_alternance_contract_rejected_from_structured_facts() -> None:
    job = FakeJob(
        contract_type=None,
        source_data={
            "typeContrat": "CDD",
            "typeContratLibelle": "Alternance",
            "natureContrat": "Contrat apprentissage",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    result = _real_filter().evaluate(job)

    assert not result.kept
    assert any(
        reason.startswith("blocked_contract_structured:apprenticeship")
        for reason in result.reasons
    )


def test_francetravail_lieu_travail_location_is_exploitable() -> None:
    facts = build_francetravail_filter_facts(
        {"lieuTravail": {"libelle": "75 - Paris"}}
    )

    assert facts.structured_location == "75 - Paris"
    assert facts.structured_location_source == "francetravail:lieuTravail.libelle"


def test_francetravail_alternance_flag_is_extracted() -> None:
    facts = build_francetravail_filter_facts({"alternance": True})

    assert facts.structured_alternance is True
    assert "structured_alternance:true" in facts.facts_used


def test_francetravail_alternance_flag_rejects_ambiguous_cdi() -> None:
    job = FakeJob(
        contract_type="CDI",
        source_data={
            "alternance": True,
            "typeContrat": "CDI",
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    result = _real_filter().evaluate(job)

    assert not result.kept
    assert any(
        reason.startswith("blocked_contract_structured:alternance")
        for reason in result.reasons
    )


def test_francetravail_converted_part_time_is_extracted() -> None:
    facts = build_francetravail_filter_facts(
        {"dureeTravailLibelleConverti": "Temps partiel"}
    )

    assert facts.structured_work_time == "Temps partiel"
    assert facts.structured_work_time_source == (
        "francetravail:dureeTravailLibelleConverti"
    )


def test_francetravail_part_time_is_rejected_when_not_accepted() -> None:
    job = FakeJob(
        contract_type="CDI",
        source_data={
            "dureeTravailLibelleConverti": "Temps partiel",
            "typeContrat": "CDI",
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    result = _real_filter().evaluate(job)

    assert not result.kept
    assert any(
        reason.startswith("blocked_work_time_structured:temps_partiel")
        for reason in result.reasons
    )


def test_francetravail_raw_20h_work_time_detects_part_time() -> None:
    facts = build_francetravail_filter_facts({"dureeTravailLibelle": "20H/semaine"})

    assert facts.structured_work_time == "Temps partiel"
    assert facts.structured_work_time_source == "francetravail:dureeTravailLibelle"


def test_francetravail_full_time_is_diagnostic_only() -> None:
    job = FakeJob(
        contract_type="CDI",
        source_data={
            "dureeTravailLibelleConverti": "Temps plein",
            "typeContrat": "CDI",
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    result = _real_filter().evaluate(job)

    assert result.kept, result.reasons
    assert "work_time_structured:temps_plein" in result.reasons


def test_francetravail_rome_and_appellation_are_diagnostic_only() -> None:
    job = FakeJob(
        source_data={
            "romeCode": "M1419",
            "romeLibelle": "Data analyst",
            "appellationlibelle": "Data analyst",
            "typeContrat": "CDI",
            "typeContratLibelle": "CDI",
            "natureContrat": "Contrat travail",
            "lieuTravail": {"libelle": "75 - Paris"},
        },
    )

    facts = build_filter_facts(job)
    result = _real_filter().evaluate(job)

    assert facts.structured_rome_code == "M1419"
    assert facts.structured_rome_label == "Data analyst"
    assert facts.structured_appellation_label == "Data analyst"
    assert result.kept, result.reasons
    assert any(reason.startswith("rome_context:m1419") for reason in result.reasons)


def test_serpapi_schedule_type_internship_is_rejected() -> None:
    job = FakeJob(
        source="serpapi",
        contract_type=None,
        source_data={"detected_extensions": {"schedule_type": "Internship"}},
    )

    facts = build_serpapi_filter_facts(job.source_data or {})
    result = _real_filter().evaluate(job)

    assert facts.structured_contract_type == "Internship"
    assert not result.kept
    assert any(
        reason.startswith("blocked_contract_structured:internship")
        for reason in result.reasons
    )


def test_serpapi_schedule_type_part_time_is_rejected_when_not_accepted() -> None:
    job = FakeJob(
        source="serpapi",
        contract_type=None,
        source_data={"detected_extensions": {"schedule_type": "Part-time"}},
    )

    result = _real_filter().evaluate(job)

    assert not result.kept
    assert any(
        reason.startswith("blocked_contract_structured:part-time")
        for reason in result.reasons
    )


def test_serpapi_schedule_type_prestataire_is_contractor_like_when_corroborated() -> None:
    job = FakeJob(
        source="serpapi",
        contract_type=None,
        application_url="https://www.free-work.com/fr/tech-it/data/job-mission/1",
        source_data={"detected_extensions": {"schedule_type": "Prestataire"}},
    )

    facts = build_filter_facts(job)
    result = _real_filter().evaluate(job)

    assert facts.structured_contract_type == "Prestataire"
    assert facts.structured_contract_source == (
        "serpapi:detected_extensions.schedule_type"
    )
    assert not result.kept
    assert any(
        reason.startswith("blocked_contract_structured:prestataire")
        and "contractor" in reason
        for reason in result.reasons
    )


def test_serpapi_uncorroborated_prestataire_is_not_a_hard_reject() -> None:
    job = FakeJob(
        title="CDI Data Analyst H/F",
        source="serpapi",
        contract_type="Full-time",
        source_data={"detected_extensions": {"schedule_type": "Prestataire"}},
    )

    facts = build_filter_facts(job)
    result = _real_filter().evaluate(job)

    assert facts.structured_contract_type == "Prestataire"
    assert result.kept, result.reasons
    assert "contract_structured_uncorroborated:prestataire" in result.reasons
    assert not any(
        reason.startswith("blocked_contract_structured:prestataire")
        for reason in result.reasons
    )


def test_serpapi_full_time_does_not_override_visible_alternance_text() -> None:
    job = FakeJob(
        title="Data Analyst en alternance",
        source="serpapi",
        contract_type=None,
        source_data={"detected_extensions": {"schedule_type": "Full-time"}},
    )

    result = _real_filter().evaluate(job)

    assert not result.kept
    assert any(
        reason.startswith("blocked_contract_visible_text:alternance")
        for reason in result.reasons
    )


def test_serpapi_work_from_home_extracts_structured_remote_policy() -> None:
    job = FakeJob(
        source="serpapi",
        remote_policy=None,
        source_data={
            "location": "Paris, France",
            "detected_extensions": {
                "schedule_type": "Full-time",
                "work_from_home": True,
            },
        },
    )

    facts = build_filter_facts(job)
    result = _real_filter().evaluate(job)

    assert facts.structured_remote_policy == "remote"
    assert facts.structured_remote_source == (
        "serpapi:detected_extensions.work_from_home"
    )
    assert result.kept, result.reasons
    assert "remote_structured:remote" in result.reasons


def test_serpapi_location_overrides_ambiguous_job_location_for_filtering() -> None:
    job = FakeJob(
        source="serpapi",
        location="Berlin, Germany",
        source_data={
            "location": "Paris, France",
            "detected_extensions": {"schedule_type": "Full-time"},
        },
    )

    facts = build_filter_facts(job)
    result = _real_filter().evaluate(job)

    assert facts.structured_location == "Paris, France"
    assert facts.structured_location_source == "serpapi:location"
    assert result.kept, result.reasons
    assert not any(reason.startswith("location_rejected_foreign") for reason in result.reasons)


def test_serpapi_search_context_is_diagnostic_only() -> None:
    job = FakeJob(
        source="serpapi",
        source_data={
            "location": "Paris, France",
            "detected_extensions": {"schedule_type": "Full-time"},
            "_smartapply_search": {
                "result_origin": "fallback",
                "strict_chips": "employment_type:FULLTIME,date_posted:month",
            },
        },
    )

    facts = build_filter_facts(job)
    result = _real_filter().evaluate(job)

    assert facts.structured_search_origin == "fallback"
    assert facts.structured_search_chips == (
        "employment_type:FULLTIME,date_posted:month"
    )
    assert result.kept, result.reasons
    assert any(reason.startswith("search_context:") for reason in result.reasons)


def test_serpapi_incomplete_source_data_does_not_crash() -> None:
    facts = build_filter_facts(FakeJob(source="serpapi", source_data={}))

    assert facts.source == "serpapi"
    assert facts.facts_used == []
    assert facts.warnings == []


def test_unknown_source_returns_empty_facts() -> None:
    facts = build_filter_facts(
        FakeJob(source="unknown", source_data={"typeContratLibelle": "CDI"})
    )

    assert facts.source == "unknown"
    assert facts.experience_min_years is None
    assert facts.structured_contract_type is None
    assert facts.structured_location is None
    assert facts.structured_remote_policy is None
    assert facts.structured_search_origin is None
    assert facts.structured_search_chips is None
    assert facts.structured_alternance is None
    assert facts.structured_work_time is None
    assert facts.structured_rome_code is None


def test_object_without_source_or_source_data_does_not_crash() -> None:
    @dataclass
    class MinimalJob:
        title: str = "Data Scientist"

    facts = build_filter_facts(MinimalJob())

    assert facts.source is None
    assert facts.facts_used == []
    assert facts.warnings == []
