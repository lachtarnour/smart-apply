"""Shared geo cache utilities."""

from __future__ import annotations

from pathlib import Path


def settings_cache_path(filename: str) -> Path:
    """Return a file path inside the configured SmartApply cache directory."""
    from smartapply.config import get_settings

    return get_settings().cache_dir / filename
