"""Tests for the candidate profile module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from smartapply.profile import (
    ProfileLoadError,
    clear_cache,
    get_profile,
    load_profile,
)


def test_loads_default_profile_with_real_data() -> None:
    profile = load_profile()
    assert profile.identity.full_name == "Lachtar Nour"
    assert profile.identity.email.endswith("@dauphine.eu")
    assert profile.identity.location == "Paris, France"
    assert len(profile.experiences) >= 3
    assert len(profile.projects) >= 5
    assert len(profile.education) == 2


def test_identity_summary_respects_style_limits() -> None:
    profile = load_profile()
    summary_lines = [
        line for line in profile.identity.summary.splitlines() if line.strip()
    ]
    assert len(profile.identity.summary) <= profile.style_guide.max_summary_length
    assert len(summary_lines) <= profile.style_guide.max_summary_lines


# -------------------- New schema features --------------------


def test_email_validation_rejects_invalid_address(tmp_path: Path) -> None:
    """EmailStr is enforced — bogus emails fail at load time."""
    sample_profile_dir = _copy_profile(tmp_path)
    identity = json.loads((sample_profile_dir / "identity.json").read_text())
    identity["email"] = "not-an-email"
    (sample_profile_dir / "identity.json").write_text(json.dumps(identity))
    with pytest.raises(ValidationError):
        load_profile(sample_profile_dir)


def test_github_url_is_parsed_as_httpurl() -> None:
    profile = load_profile()
    # github is a HttpUrl, so str() returns the canonical form
    assert str(profile.identity.github).startswith("https://github.com/lachtarnour")


def test_invalid_date_rejected(tmp_path: Path) -> None:
    """Date format validation: MM/YYYY or Present/Current/Ongoing."""
    sample = _copy_profile(tmp_path)
    exps = json.loads((sample / "experiences.json").read_text())
    exps[0]["start_date"] = "2024-Q1"  # invalid
    (sample / "experiences.json").write_text(json.dumps(exps))
    with pytest.raises(ValidationError):
        load_profile(sample)


def test_present_is_valid_end_date(tmp_path: Path) -> None:
    sample = _copy_profile(tmp_path)
    exps = json.loads((sample / "experiences.json").read_text())
    exps[0]["end_date"] = "Present"
    (sample / "experiences.json").write_text(json.dumps(exps))
    # Should NOT raise
    profile = load_profile(sample)
    assert profile.experiences[0].end_date == "Present"


def test_job_preferences_renamed_accepted_job_languages() -> None:
    """``languages`` was renamed to ``accepted_job_languages`` to avoid clash."""
    profile = load_profile()
    assert "fr" in profile.preferences.accepted_job_languages
    assert "en" in profile.preferences.accepted_job_languages
    assert not hasattr(profile.preferences, "languages")


def test_projects_have_bullets_with_stable_ids() -> None:
    """Projects now share the Experience bullet contract (id + allowed_claims)."""
    profile = load_profile()
    proj = next(p for p in profile.projects if p.id == "proj_scifact_rag")
    assert len(proj.bullets) >= 1
    blt = proj.bullets[0]
    assert blt.id.startswith("blt_")
    assert blt.evidence_level in ("verified", "self_reported", "inferred")
    assert blt.allowed_claims  # non-empty
    # description still works as a derived view
    assert "BM25" in proj.description


def test_bot_traffic_project_is_available_for_selection() -> None:
    profile = load_profile()
    proj = next(p for p in profile.projects if p.id == "proj_bot_traffic_anomaly")
    assert proj.url is not None
    assert "anomaly detection" in [kw.lower() for kw in proj.keywords]
    assert "blt_proj_bot_traffic_main" in profile.bullet_index()


def test_aal_stock_forecasting_project_is_available_for_selection() -> None:
    profile = load_profile()
    proj = next(p for p in profile.projects if p.id == "proj_aal_stock_forecasting")
    assert "forecasting" in [kw.lower() for kw in proj.keywords]
    assert "arima" in [kw.lower() for kw in proj.keywords]
    assert "blt_proj_aal_forecasting_main" in profile.bullet_index()


def test_project_repository_links_are_available() -> None:
    profile = load_profile()
    links = {
        project.id: str(project.url).rstrip("/") if project.url else None
        for project in profile.projects
    }
    assert links["proj_svc"] == "https://github.com/lachtarnour/signing-conversion"
    assert links["proj_scifact_rag"] == "https://github.com/lachtarnour/scifact-verifier"
    assert links["proj_bot_traffic_anomaly"] == (
        "https://github.com/lachtarnour/bot-traffic-anomaly-detection"
    )
    assert links["proj_rl_gym"] == "https://github.com/lachtarnour/Reinforcement-learning"
    assert links["proj_ner_camembert"] == "https://github.com/lachtarnour/Token-classification"
    assert links["proj_aal_stock_forecasting"] == (
        "https://github.com/lachtarnour/"
        "Using-time-series-analysis-to-forecast-American-Airlines-Group-stocks"
    )
    assert links["proj_gpt2"] is None


def test_experience_and_education_links_are_available() -> None:
    profile = load_profile()
    experience_links = {
        exp.id: str(exp.url).rstrip("/") if exp.url else None
        for exp in profile.experiences
    }
    education_links = {
        degree.id: str(degree.url).rstrip("/") if degree.url else None
        for degree in profile.education
    }
    assert experience_links["exp_emobot_ds_2024"] == "https://emobothealth.com"
    assert experience_links["exp_emobot_intern_2023"] == "https://emobothealth.com"
    assert experience_links["exp_vds_intern_2022"] == "https://value.com.tn"
    assert education_links["edu_msc_iasd"] == (
        "https://dauphine.psl.eu/formations/masters/informatique/"
        "m2-intelligence-artificielle-systemes-donnees"
    )
    assert education_links["edu_bsc_mefa"] == (
        "https://dauphine.psl.eu/formations/licences/mathematiques/"
        "l3-mathematiques-appliquees"
    )


def test_bullet_index_includes_project_bullets() -> None:
    profile = load_profile()
    index = profile.bullet_index()
    # Experience bullet AND project bullet both resolvable
    assert "blt_emobot_ds_multimodal" in index
    assert "blt_proj_scifact_main" in index


def test_block_for_bullet_works_for_projects() -> None:
    profile = load_profile()
    block = profile.block_for_bullet("blt_proj_scifact_main")
    assert block is not None
    assert block.id == "proj_scifact_rag"


def test_bullet_evidence_levels_present() -> None:
    profile = load_profile()
    # The patent bullet was marked self_reported
    patent = profile.bullet_index()["blt_emobot_ds_patent"]
    assert patent.evidence_level == "self_reported"


def test_bullet_effective_allowed_claims_falls_back_to_text() -> None:
    """When ``allowed_claims`` is empty, the bullet text itself is the allowed claim."""
    from smartapply.profile.schema import Bullet

    b = Bullet(id="blt_test", text="Did stuff.")
    assert b.effective_allowed_claims == ["Did stuff."]


def test_education_end_year_must_be_after_start_year(tmp_path: Path) -> None:
    sample = _copy_profile(tmp_path)
    edu = json.loads((sample / "education.json").read_text())
    edu[0]["start_year"], edu[0]["end_year"] = 2023, 2020
    (sample / "education.json").write_text(json.dumps(edu))
    with pytest.raises(ValidationError):
        load_profile(sample)


# Helper used by several tests above
def _copy_profile(tmp_path: Path) -> Path:
    from smartapply.config import get_settings

    src = get_settings().profile_dir
    for f in src.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    return tmp_path


def test_allowed_skills_whitelist_includes_known_tech() -> None:
    profile = load_profile()
    allowed = profile.skills.allowed_skills
    assert "PyTorch" in allowed
    assert "Hugging Face" in allowed
    assert "Statistical modeling" in allowed
    assert "R" in allowed
    assert "ARIMA/SARIMA" in allowed
    assert "FAISS" in allowed
    assert "ONNX" in allowed
    assert "Weights & Biases" in allowed
    # Matching keywords are detection cues, not displayable CV skills.
    assert "genai" not in allowed
    assert "Machine learning" not in allowed
    assert "Computer vision" not in allowed
    assert "Data analysis" not in allowed
    assert "Reporting" not in allowed
    assert "Reinforcement learning" not in allowed
    assert "MLOps" not in allowed
    # Skill not in any category should NOT be allowed
    assert "Kubernetes" not in allowed


def test_profile_has_targeted_skill_profiles() -> None:
    profile = load_profile()
    assert {
        "mixed",
        "llm",
        "machine_learning",
        "reinforcement_learning",
        "data_analyst",
        "time_series",
        "computer_vision",
        "speech_audio",
        "medical_ai",
    }.issubset(profile.skills.profile_ids)
    data_analyst = profile.skills.profile_by_id("data_analyst")
    assert data_analyst is not None
    assert "SQL" in data_analyst.category_skills["data_analysis"]
    assert "Data visualization" in data_analyst.category_skills["data_analysis"]
    medical_ai = profile.skills.profile_by_id("medical_ai")
    assert medical_ai is not None
    assert "Facial analysis" in medical_ai.category_skills["computer_vision"]


def test_core_skills_baseline_is_defined() -> None:
    profile = load_profile()
    core = profile.skills.core
    assert core["ml_ai"] == ["PyTorch", "Scikit-learn", "NLP"]
    assert core["data_analysis"] == ["Python", "SQL", "Pandas", "NumPy"]
    assert core["data_infra"] == ["Git", "Docker", "FastAPI"]


def test_effective_skills_merge_core_into_every_profile() -> None:
    """Every profile's effective view contains the core baseline, with no duplicates."""
    profile = load_profile()
    for sp in profile.skills.profiles:
        merged = profile.skills.effective_category_skills(sp.id)
        for category_id, core_skills in profile.skills.core.items():
            assert category_id in merged, f"{sp.id} missing core category {category_id}"
            for skill in core_skills:
                assert skill in merged[category_id], (
                    f"{sp.id}/{category_id} missing core skill {skill}"
                )
            assert len(merged[category_id]) == len(set(merged[category_id])), (
                f"{sp.id}/{category_id} has duplicates: {merged[category_id]}"
            )


def test_effective_skills_surface_profile_specific_first() -> None:
    """Offer-specific additions come BEFORE core in each category, so a tight
    per-category cap still surfaces what makes the profile distinct."""
    profile = load_profile()
    merged = profile.skills.effective_category_skills("llm")
    # Profile-specific skills should precede the broader core baseline.
    ml_ai = merged["ml_ai"]
    assert ml_ai.index("LLMs") < ml_ai.index("PyTorch")
    assert "RAG" in merged["rag_retrieval"]


def test_matching_keywords_are_kept_separate_from_display_skills() -> None:
    profile = load_profile()
    assert "llm" in profile.skills.matching_keywords
    assert "genai" in profile.skills.matching_keywords["llm"]
    assert "machine learning" in profile.skills.matching_keywords["machine_learning"]
    assert "computer vision" in profile.skills.matching_keywords["computer_vision"]
    assert "data analysis" in profile.skills.matching_keywords["data_analyst"]
    assert "reinforcement learning" in profile.skills.matching_keywords["reinforcement_learning"]
    assert "genai" not in profile.skills.allowed_skills


def test_effective_skills_unknown_profile_returns_core_only() -> None:
    profile = load_profile()
    merged = profile.skills.effective_category_skills("does_not_exist")
    assert merged == profile.skills.core


def test_preferences_include_data_analyst_roles() -> None:
    profile = load_profile()
    assert "Data Analyst" in profile.preferences.target_roles
    assert "Analytics Engineer" in profile.preferences.target_roles


def test_bullet_ids_are_globally_unique() -> None:
    profile = load_profile()
    bullet_ids = [b.id for e in profile.experiences for b in e.bullets]
    assert len(set(bullet_ids)) == len(bullet_ids)


def test_bullet_index_resolves_ids_to_text() -> None:
    profile = load_profile()
    index = profile.bullet_index()
    blt = index["blt_emobot_ds_multimodal"]
    assert "0.67" in blt.text
    assert "0.67" in blt.numbers


def test_experience_for_bullet_returns_owning_experience() -> None:
    profile = load_profile()
    exp = profile.experience_for_bullet("blt_emobot_ds_timeseries")
    assert exp is not None
    assert exp.company == "Emobot"
    assert exp.title.startswith("Data Scientist")


def test_get_profile_caches_result() -> None:
    clear_cache()
    a = get_profile()
    b = get_profile()
    assert a is b


def test_load_missing_directory_raises(tmp_path: Path) -> None:
    with pytest.raises(ProfileLoadError):
        load_profile(tmp_path / "does-not-exist")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    # Minimal but invalid profile directory: identity.json broken
    (tmp_path / "identity.json").write_text("{ this is not json")
    with pytest.raises(ProfileLoadError):
        load_profile(tmp_path)


def test_duplicate_bullet_ids_rejected(tmp_path: Path, sample_profile_files: Path) -> None:
    assert sample_profile_files == tmp_path
    # Inject duplicate bullet id and reload
    exps_path = tmp_path / "experiences.json"
    exps = json.loads(exps_path.read_text())
    exps[0]["bullets"].append(exps[0]["bullets"][0])  # duplicate
    exps_path.write_text(json.dumps(exps))
    with pytest.raises(ValidationError):
        load_profile(tmp_path)


@pytest.fixture
def sample_profile_files(tmp_path: Path) -> Path:
    """Copy the real profile data into tmp_path so tests can mutate it safely."""
    from smartapply.config import get_settings

    src = get_settings().profile_dir
    for f in src.iterdir():
        (tmp_path / f.name).write_bytes(f.read_bytes())
    return tmp_path
