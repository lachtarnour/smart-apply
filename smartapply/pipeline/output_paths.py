"""Output directory helpers for generated application artifacts."""

from __future__ import annotations

from pathlib import Path


def application_output_dir(output_dir: Path, application_id: int | None) -> Path:
    """Return the artifact directory for one persisted application."""
    if application_id is None:
        raise ValueError("application_id is required before rendering artifacts")
    return output_dir / str(int(application_id))
