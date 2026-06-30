"""Prompt builder for job analysis — first LLM call after filtering."""

from __future__ import annotations

from smartapply.llm.prompts.loader import load_prompt, render_prompt
from smartapply.offers import AnalyzerInput
from smartapply.profile import Profile

SYSTEM = load_prompt("job_analysis/system_long.j2")


def system_for_variant(variant: str | None) -> str:
    """Return the production job-analysis system prompt for a named variant."""
    normalized = (variant or "long").strip().lower()
    if normalized != "long":
        raise ValueError(
            f"Unsupported job analysis prompt variant: {variant!r}. "
            "Set PROMPT=long."
        )
    return SYSTEM


def build_user_prompt(
    *,
    profile: Profile,
    job_title: str,
    job_description: str,
    job_company: str = "",
    job_location: str | None = None,
    application_url: str | None = None,
    source_metadata: str | None = None,
) -> str:
    profile_block = (
        f"Candidate title: {profile.identity.title}\n"
        f"Summary: {profile.identity.summary}\n"
        f"Skills: {', '.join(sorted(profile.skills.allowed_skills))}\n"
        f"Target roles: {', '.join(profile.preferences.target_roles)}\n"
        f"Seniority: {profile.preferences.seniority or 'unspecified'}\n"
        f"Preferred locations: {', '.join(profile.preferences.preferred_locations)}\n"
    )
    source_metadata_block = _source_metadata_block(source_metadata)
    return render_prompt(
        "job_analysis/user.j2",
        profile_block=profile_block,
        job_title=job_title,
        job_company=job_company,
        job_location=job_location or "",
        application_url=application_url or "",
        source_metadata_block=source_metadata_block,
        job_description=job_description.strip(),
    )


def build_user_prompt_from_input(
    *,
    profile: Profile,
    analyzer_input: AnalyzerInput,
) -> str:
    """Build the analyzer prompt from the canonical job-analysis input."""
    return build_user_prompt(
        profile=profile,
        job_title=analyzer_input.title,
        job_company=analyzer_input.company,
        job_location=analyzer_input.location,
        application_url=analyzer_input.application_url,
        source_metadata=analyzer_input.source_metadata,
        job_description=analyzer_input.offer_body,
    )


def _source_metadata_block(source_metadata: str | None) -> str:
    metadata = (source_metadata or "").strip()
    if not metadata:
        return ""
    return render_prompt("job_analysis/source_metadata_block.j2", metadata=metadata)
