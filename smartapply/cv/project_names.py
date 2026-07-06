"""Project display-name normalization for generated application content."""

from __future__ import annotations

import re

from smartapply.llm import AdaptedCV, MotivationLetter
from smartapply.profile import Profile

_LEGACY_ALIASES_BY_PROJECT_ID: dict[str, tuple[str, ...]] = {
    "proj_smartapply": ("SmartApply", "Smart Apply"),
}


def normalize_project_aliases(text: str, profile: Profile) -> str:
    """Replace old project display names with the current profile names."""
    updated = text
    for project in profile.projects:
        for alias in _LEGACY_ALIASES_BY_PROJECT_ID.get(project.id, ()):
            if alias == project.name:
                continue
            updated = re.sub(
                rf"(?<![\w-]){re.escape(alias)}(?![\w-])",
                project.name,
                updated,
            )
    return updated


def normalize_adapted_cv_project_aliases(adapted: AdaptedCV, profile: Profile) -> AdaptedCV:
    """Normalize project aliases in every free-text CV field."""
    experiences = []
    for exp in adapted.selected_experiences:
        bullets = [
            bullet.model_copy(
                update={"text": normalize_project_aliases(bullet.text, profile)}
            )
            for bullet in exp.bullets
        ]
        experiences.append(exp.model_copy(update={"bullets": bullets}))

    return adapted.model_copy(
        update={
            "cv_title": normalize_project_aliases(adapted.cv_title, profile),
            "professional_summary": normalize_project_aliases(
                adapted.professional_summary,
                profile,
            ),
            "selected_experiences": experiences,
        }
    )


def normalize_letter_project_aliases(
    letter: MotivationLetter,
    profile: Profile,
) -> MotivationLetter:
    """Normalize project aliases in the generated motivation letter."""
    return letter.model_copy(
        update={
            "subject": normalize_project_aliases(letter.subject, profile),
            "body": normalize_project_aliases(letter.body, profile),
        }
    )
