"""Tests for the local filtering module."""

from __future__ import annotations

from dataclasses import dataclass

from smartapply.filtering import JobFilter, RuleSet, ruleset_from_preferences
from smartapply.profile import get_profile
from smartapply.utils.location import is_foreign_location


@dataclass
class FakeJob:
    title: str
    company: str
    description: str
    location: str | None = None
    contract_type: str | None = None
    remote_policy: str | None = None


def _real_rules() -> RuleSet:
    return ruleset_from_preferences(get_profile().preferences)


def test_target_role_in_paris_kept_high_score() -> None:
    rules = _real_rules()
    f = JobFilter(rules)
    job = FakeJob(
        title="Data Scientist NLP",
        company="Acme",
        description="Build RAG pipelines with PyTorch, Hugging Face. CDI.",
        location="Paris, France",
        contract_type="CDI",
        remote_policy="hybrid",
    )
    res = f.evaluate(job)
    assert res.kept
    assert res.score >= 0.7
    assert "target_role:data scientist" in res.reasons
    assert "location_preferred" in res.reasons
    assert "location_mismatch" not in res.reasons


def test_sales_role_rejected_by_negative_title() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Sales Manager",
        company="Acme",
        description="Hit quotas.",
        location="Paris, France",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept
    # Either matches a deal_breaker, a negative keyword, or a hard off-target family.
    assert any(
        ("deal_breaker" in r or "negative_title" in r or "title_hard_reject" in r)
        for r in res.reasons
    )


def test_internship_rejected_by_deal_breaker() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist Stage",
        company="Acme",
        description="6 month internship.",
        location="Paris",
        contract_type="Stage",
    )
    res = f.evaluate(job)
    assert not res.kept


def test_senior_only_role_blocked_by_seniority_term() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Looking for 15+ years of experience in ML.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept


def test_foreign_location_is_hard_rejected_even_when_remote() -> None:
    """Foreign-country location => hard reject, even with remote_policy=remote.

    The candidate only targets the French market (legal/tax reasons), so a
    Berlin-based role with remote work is still out of scope.
    """
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build ML pipelines.",
        location="Berlin, Germany",
        contract_type="CDI",
        remote_policy="remote",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("location_rejected_foreign" in r for r in res.reasons)


def test_remote_eu_is_kept() -> None:
    """A job tagged 'Remote (EU)' is acceptable for a French candidate."""
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build ML pipelines.",
        location="Remote (EU)",
        contract_type="CDI",
        remote_policy="remote",
    )
    res = f.evaluate(job)
    assert res.kept
    assert "location_remote_accepted" in res.reasons


def test_remote_us_is_foreign_and_rejected() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build ML pipelines.",
        location="Remote US",
        contract_type="Full-time",
        remote_policy="remote",
    )
    res = f.evaluate(job)

    assert not res.kept
    assert any("location_rejected_foreign" in reason for reason in res.reasons)


def test_remote_france_has_specific_location_reason() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build ML pipelines.",
        location="Remote (France)",
        contract_type="CDI",
        remote_policy="remote",
    )
    res = f.evaluate(job)
    assert res.kept
    assert "location_remote_france" in res.reasons
    assert "location_mismatch" not in res.reasons


def test_filter_rejects_5plus_years_required() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Looking for 5+ years of experience in machine learning.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("experience_required_too_high" in r for r in res.reasons)


def test_filter_rejects_french_phrasing_5_ans() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Minimum 5 ans d'expérience en data science.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("5" in r and "experience" in r for r in res.reasons)


def test_filter_keeps_3_ans_required() -> None:
    """3 ans is well within the candidate's reach — must be kept."""
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="3 ans d'expérience souhaitée en data science et Python.",
        location="Paris",
        contract_type="CDI",
    )
    assert f.evaluate(job).kept


def test_filter_rejects_freelance_visible_in_title_without_contract_field() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Analytics Engineer - Freelance H/F",
        company="Acme",
        description="Build dashboards and data models.",
        location="Paris",
        contract_type=None,
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("blocked_contract_visible_text:freelance" in r for r in res.reasons)


def test_filter_rejects_reporting_bi_without_analytical_ownership() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Automation & Reporting Analyst",
        company="Acme",
        description="Power BI, Power Query, dashboards, KPI reporting and documentation.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert "reporting_bi_without_analytical_ownership" in res.reasons


def test_filter_rejects_finance_reporting_bi_without_core_data_tech() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Automation & Reporting Analyst",
        company="Acme",
        description=(
            "Rattaché à la direction administrative et financière. "
            "Concevoir des tableaux de bord Power BI, automatiser les reportings "
            "Power Query, documenter les règles de gestion et le contrôle de gestion."
        ),
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert "finance_reporting_bi_without_core_data_tech" in res.reasons


def test_filter_keeps_data_analyst_bi_with_python_or_sql_ownership() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Analyst BI",
        company="Acme",
        description="Power BI dashboards with SQL, Python, statistical analysis and forecasting.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert res.kept


def test_filter_rejects_web_analytics_tracking_focus() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Digital Analytics Engineer",
        company="Acme",
        description="Own GA4, GTM, data layer, tagging plan and tracking implementation.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert "web_analytics_tracking_focus" in res.reasons


def test_filter_rejects_mep_data_center_roles() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Ingénieur MEP Data Center",
        company="Acme",
        description="Coordination lots MEP, HVAC, electrical and plumbing for data centers.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept


def test_filter_rejects_hidden_senior_or_director_role_in_description() -> None:
    f = JobFilter(_real_rules())
    jobs = [
        FakeJob(
            title="Analyste développeur Big Data",
            company="Acme",
            description="Nous recherchons un Senior Analytics Engineer pour LookML.",
            location="Paris",
            contract_type="CDI",
        ),
        FakeJob(
            title="Analyste développeur Big Data",
            company="Acme",
            description="Director Automation & Data Engineering. Vous pilotez une équipe data.",
            location="Paris",
            contract_type="CDI",
        ),
    ]
    for job in jobs:
        res = f.evaluate(job)
        assert not res.kept
        assert "seniority_or_leadership_in_description" in res.reasons


def test_filter_rejects_english_internship_in_title() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist Internship",
        company="Acme",
        description="6 months internship program.",
        location="Paris",
        contract_type="Internship",
    )
    res = f.evaluate(job)
    assert not res.kept


def test_filter_rejects_intern_dash_pattern_in_title() -> None:
    """'Data Scientist Intern - Paris' must hit the 'intern -' deal-breaker.

    The dash variant covers postings that don't use the word 'Internship'
    while keeping 'International' / 'Internal' safe from false positives.
    """
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist Intern - Paris",
        company="Acme",
        description="6 month role",
        location="Paris",
        contract_type="CDD",
    )
    assert not f.evaluate(job).kept


def test_filter_does_not_reject_international_in_title() -> None:
    """'Intern -' must NOT match 'International' (avoid false positives)."""
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="International Data Scientist",
        company="Acme",
        description="Global team building ML pipelines.",
        location="Paris",
        contract_type="CDI",
    )
    assert f.evaluate(job).kept


def test_filter_rejects_apprentice_in_title() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Apprentice Engineer",
        company="Acme",
        description="Learn on the job.",
        location="Paris",
        contract_type="Apprenticeship",
    )
    assert not f.evaluate(job).kept


def test_filter_rejects_internship_contract_type_even_with_clean_title() -> None:
    """blocked_contract_types catches offers where the title is generic but
    the contract column says Internship."""
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Join our team to build ML pipelines.",
        location="Paris",
        contract_type="Internship",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("blocked_contract_type" in r for r in res.reasons)


def test_filter_rejects_french_stage_contract_type() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Construire des pipelines ML.",
        location="Paris",
        contract_type="Stage",
    )
    assert not f.evaluate(job).kept


def test_filter_rejects_apprentissage_contract_type() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Construire des pipelines ML.",
        location="Paris",
        contract_type="Apprentissage",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("apprenti" in r for r in res.reasons)


def test_filter_rejects_alternant_visible_in_title_without_contract_field() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Alternant Analytics Engineer - Data BI & Pipelines",
        company="Acme",
        description="Python, SQL, data pipelines.",
        location="Paris",
        contract_type=None,
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any("blocked_contract_visible_text:alternant" in r for r in res.reasons)


def test_filter_hard_rejects_off_target_title_families() -> None:
    f = JobFilter(_real_rules())
    blocked_titles = [
        "Enseignant Data Science",
        "Technicien Support Data",
        "Chef de projet Data",
        "Formateur Python IA",
        "Audit DevOps Engineer",
        "Senior Responsable Data",
        "Product Owner IA",
        "Architecte Solution Java",
        "DevOps Engineer AWS Terraform",
        "Manager Data & AI",
        "IDE infirmier en clinique",
        "Full Stack Java Angular",
        "Expert IA Cybersécurité",
        "Consultant Dataiku DSS",
        "MLOps Engineer",
        "AI Engineer / MLOps",
        "VIE HPC - Ingénieur Développeur F/H",
    ]
    for title in blocked_titles:
        job = FakeJob(
            title=title,
            company="Acme",
            description="Python, data, machine learning.",
            location="Paris",
            contract_type="CDI",
        )
        res = f.evaluate(job)
        assert not res.kept, title
        assert any(reason.startswith("title_hard_reject:") for reason in res.reasons)


def test_filter_keeps_mlops_when_only_required_skill_not_job_title() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Machine Learning Engineer",
        company="Acme",
        description=(
            "Build ML models with Python and PyTorch. Required skills include "
            "CI/CD, Docker and MLOps practices for production collaboration."
        ),
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert res.kept
    assert not any(reason.startswith("title_hard_reject:") for reason in res.reasons)


def test_filter_keeps_devops_when_only_required_skill_not_job_title() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description=(
            "Build machine learning models with Python and PyTorch. Required "
            "skills include Docker, CI/CD and DevOps collaboration for deployment."
        ),
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert res.kept
    assert not any(reason.startswith("title_hard_reject:") for reason in res.reasons)


def test_filter_keeps_cdi_contract_type() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build pipelines with Python.",
        location="Paris",
        contract_type="CDI",
    )
    assert f.evaluate(job).kept


def test_filter_accepts_multilingual_permanent_fulltime_contract_synonyms() -> None:
    f = JobFilter(_real_rules())
    contracts = (
        "CDI",
        "Contrat à durée indéterminée",
        "Permanent",
        "Permanent contract",
        "Full-time",
        "Full time",
        "Fulltime",
        "Temps plein",
        "À temps plein",
        "A plein temps",
    )
    for contract in contracts:
        job = FakeJob(
            title="Data Scientist",
            company="Acme",
            description="Build pipelines with Python.",
            location="Paris",
            contract_type=contract,
        )
        res = f.evaluate(job)
        assert res.kept, contract
        assert any(reason.startswith("contract_ok:") for reason in res.reasons), contract


def test_filter_rejects_cdd_even_when_fulltime_is_visible() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build pipelines with Python.",
        location="Paris",
        contract_type="CDD temps plein",
    )
    res = f.evaluate(job)

    assert not res.kept
    assert any("blocked_contract_type" in reason for reason in res.reasons)


def test_filter_rejects_contractor_contract_type() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="AI Engineer",
        company="Acme",
        description="Build LLM products with Python.",
        location="Paris",
        contract_type="Contract",
    )
    res = f.evaluate(job)

    assert not res.kept
    assert any("blocked_contract_type" in reason for reason in res.reasons)


def test_filter_blocked_contract_types_is_configurable() -> None:
    """Canonical incompatible contract tags still protect the current profile."""
    rules = _real_rules()
    rules.blocked_contract_types = ("stage",)  # only block stages
    f = JobFilter(rules)
    intern_job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="OK",
        location="Paris",
        contract_type="Internship",
    )
    assert not f.evaluate(intern_job).kept
    # Title still has 'internship' via deal_breakers too — adjust title to verify
    # the canonical contract tag remains protective by itself.
    rules.deal_breakers = [d for d in rules.deal_breakers if "intern" not in d and "apprentice" not in d]
    f2 = JobFilter(rules)
    assert not f2.evaluate(intern_job).kept


def test_filter_keeps_no_experience_mention() -> None:
    """A job without any explicit years requirement must not be rejected by
    the experience filter — it can still pass other gates."""
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Looking for a strong Python and PyTorch profile.",
        location="Paris",
        contract_type="CDI",
    )
    assert f.evaluate(job).kept


def test_filter_threshold_is_configurable() -> None:
    """Lowering max_required_years to 3 should reject a '4 ans' offer."""
    rules = _real_rules()
    rules.max_required_years = 3
    f = JobFilter(rules)
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="4 ans d'expérience minimum.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)
    assert not res.kept


def test_french_city_outside_paris_is_kept() -> None:
    """Anywhere in France passes the filter (the user's stated policy)."""
    f = JobFilter(_real_rules())
    for city in ("Châteaufort", "Saint-Herblain", "Massy", "Lyon", "Toulouse"):
        job = FakeJob(
            title="Data Scientist",
            company="Acme",
            description="Build ML pipelines with PyTorch.",
            location=city,
            contract_type="CDI",
            remote_policy="hybrid",
        )
        res = f.evaluate(job)
        assert res.kept, city
        assert "location_accepted_france" in res.reasons
        assert "location_mismatch" not in res.reasons


def test_french_city_from_official_commune_cache_is_accepted(monkeypatch) -> None:  # noqa: ANN001
    import smartapply.utils.location as location_utils

    monkeypatch.setattr(
        location_utils,
        "_official_french_commune_names",
        lambda: frozenset({"quimper"}),
    )

    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Scientist",
        company="Acme",
        description="Build ML pipelines with PyTorch.",
        location="Quimper",
        contract_type="CDI",
        remote_policy="hybrid",
    )
    res = f.evaluate(job)

    assert res.kept
    assert "location_accepted_france" in res.reasons
    assert "location_mismatch" not in res.reasons


def test_foreign_location_handles_strong_and_ambiguous_markers(monkeypatch) -> None:  # noqa: ANN001
    import smartapply.utils.location as location_utils

    monkeypatch.setattr(
        location_utils,
        "_official_french_commune_names",
        lambda: frozenset({"montreal"}),
    )

    not_foreign = (
        "Paris, France",
        "75 - Paris",
        "Remote France",
        "Remote Europe",
        "Montréal",
    )
    foreign = (
        "Paris, TX",
        "Paris, United States",
        "Berlin, Germany",
        "Berlin",
        "Montreal, Canada",
        "USA",
        "UK",
    )

    for location in not_foreign:
        assert not is_foreign_location(location), location
    for location in foreign:
        assert is_foreign_location(location), location


def test_data_analyst_role_is_now_in_target_scope() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Analyst",
        company="Acme",
        description="Analyze product data with SQL, Python, dashboards and forecasting.",
        location="Paris, France",
        contract_type="CDI",
        remote_policy="hybrid",
    )
    res = f.evaluate(job)
    assert res.kept
    assert "target_role:data analyst" in res.reasons


def test_bi_analyst_without_python_is_penalized() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Analyst BI",
        company="Acme",
        description="Power BI dashboards, reporting mensuel, SQL requis. Pas de développement Python.",
        location="Paris, France",
        contract_type="CDI",
        remote_policy="hybrid",
    )
    res = f.evaluate(job)
    assert not res.kept
    assert any(
        reason in res.reasons
        for reason in ("analytics_without_python", "reporting_without_core_data_tech")
    )


def test_reporting_analyst_without_python_sql_is_rejected() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Reporting Analyst",
        company="Acme",
        description="Reporting dashboards only, no Python, no SQL, no analytics ownership.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)

    assert not res.kept
    assert "reporting_without_core_data_tech" in res.reasons


def test_pure_data_engineer_platform_role_is_rejected() -> None:
    f = JobFilter(_real_rules())
    job = FakeJob(
        title="Data Engineer",
        company="Acme",
        description="Own ETL, Airflow, warehouse modeling and data platform reliability.",
        location="Paris",
        contract_type="CDI",
    )
    res = f.evaluate(job)

    assert not res.kept
    assert "pure_data_engineering_role" in res.reasons


def test_filter_many_partitions_jobs() -> None:
    f = JobFilter(_real_rules())
    jobs = [
        FakeJob("Data Scientist", "Acme", "PyTorch", "Paris", "CDI"),
        FakeJob("Sales Director", "Beta", "Quotas", "Paris", "CDI"),
        FakeJob("ML Engineer", "Gamma", "MLOps with AWS", "Lyon", "CDI"),
    ]
    kept, evaluated = f.filter_many(jobs)
    assert len(evaluated) == 3
    assert len(kept) == 2
    assert "Sales Director" not in {j.title for j in kept}


def test_below_min_score_threshold_drops_job() -> None:
    rules = _real_rules()
    rules.min_score = 0.99  # impossible to reach
    f = JobFilter(rules)
    job = FakeJob("Data Scientist", "Acme", "PyTorch", "Paris", "CDI", "hybrid")
    res = f.evaluate(job)
    assert not res.kept
    assert any(r.startswith("below_min_score") for r in res.reasons)
