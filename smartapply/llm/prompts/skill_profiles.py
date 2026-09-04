"""Prompt helpers for profile skill families."""

from __future__ import annotations

from smartapply.profile import Profile


def format_skill_profiles(profile: Profile) -> str:
    """Render skill profile choices with their effective display skills."""
    if not profile.skills.profiles:
        return "- mixed: default compact skills profile"
    lines: list[str] = []
    for skill_profile in profile.skills.profiles:
        effective = profile.skills.effective_category_skills(skill_profile.id)
        blocks = [f"{cid}: {', '.join(skills)}" for cid, skills in effective.items()]
        description = f" — {skill_profile.description}" if skill_profile.description else ""
        lines.append(
            f"- {skill_profile.id}: {skill_profile.name}{description} ({'; '.join(blocks)})"
        )
    return "\n".join(lines)
