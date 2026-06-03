"""Tests for the local filtering module."""

from __future__ import annotations

from dataclasses import dataclass

from smartapply.filtering import JobFilter, RuleSet, ruleset_from_preferences
from smartapply.profile import get_profile


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
    # Either matches a deal_breaker or a negative_title keyword
    assert any(("deal_breaker" in r or "negative_title" in r) for r in res.reasons)


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
    assert any("foreign_location" in r for r in res.reasons)


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


def test_filter_hard_rejects_off_target_title_families() -> None:
    f = JobFilter(_real_rules())
    blocked_titles = [
        "Enseignant Data Science",
        "Technicien Support Data",
        "Chef de projet Data",
        "Formateur Python IA",
        "Audit DevOps Engineer",
        "Senior Responsable Data",
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


def test_filter_blocked_contract_types_is_configurable() -> None:
    """Project-specific override: relax for a user who DOES accept freelance."""
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
    # With the relaxed rules, internship is no longer hard-rejected by contract
    res = f.evaluate(intern_job)
    # Title still has 'internship' via deal_breakers though — adjust title to verify only contract path
    rules.deal_breakers = [d for d in rules.deal_breakers if "intern" not in d and "apprentice" not in d]
    f2 = JobFilter(rules)
    assert f2.evaluate(intern_job).kept


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
        assert f.evaluate(job).kept, city


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
    assert "analytics_without_python" in res.reasons
    assert res.score < 0.7


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
