"""Load the candidate profile from a directory of JSON files.

The directory layout is intentionally split per concern so each file can
evolve independently and stay small. The loader composes them into a single
``Profile`` instance.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from smartapply.config import get_settings
from smartapply.profile.schema import Profile

REQUIRED_FILES = {
    "identity": "identity.json",
    "preferences": "preferences.json",
    "skills": "skills.json",
    "experiences": "experiences.json",
    "style_guide": "style_guide.json",
}

OPTIONAL_FILES = {
    "projects": "projects.json",
    "education": "education.json",
    "languages": "languages.json",
    "certificates": "certificates.json",
    "template_style": "template_style.json",
}


class ProfileLoadError(RuntimeError):
    """Raised when the profile directory is missing or malformed."""


def _read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise ProfileLoadError(f"Profile file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise ProfileLoadError(f"Invalid JSON in {path}: {e}") from e


def load_profile(profile_dir: Path | str | None = None) -> Profile:
    """Build a ``Profile`` from the JSON files in ``profile_dir``."""
    profile_dir = Path(profile_dir) if profile_dir else get_settings().profile_dir

    data: dict[str, Any] = {}
    for key, name in REQUIRED_FILES.items():
        data[key] = _read_json(profile_dir / name)

    for key, name in OPTIONAL_FILES.items():
        path = profile_dir / name
        if path.exists():
            data[key] = _read_json(path)

    return Profile.model_validate(data)


@lru_cache(maxsize=4)
def _get_profile_cached(profile_dir: str) -> Profile:
    return load_profile(Path(profile_dir))


def get_profile(profile_dir: Path | str | None = None) -> Profile:
    """Cached accessor — use this in pipelines to avoid re-reading."""
    resolved_dir = Path(profile_dir) if profile_dir else get_settings().profile_dir
    return _get_profile_cached(str(resolved_dir.expanduser().resolve()))


def clear_cache() -> None:
    _get_profile_cached.cache_clear()
