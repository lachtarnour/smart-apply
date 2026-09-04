"""Prepare predictable runtime paths before importing application services."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeContext:
    home: Path
    env_file: Path
    packaged: bool


def prepare_runtime_environment() -> RuntimeContext:
    """Use the same Application Support workspace in development and production."""
    packaged = bool(getattr(sys, "frozen", False))
    home = Path.home() / "Library" / "Application Support" / "Elan"
    home = Path(os.environ.get("ELAN_HOME", home)).expanduser().resolve()
    env_file = Path(os.environ.get("ELAN_ENV_FILE", home / ".env")).expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("ELAN_HOME", str(home))
    os.environ.setdefault("ELAN_ENV_FILE", str(env_file))
    os.chdir(home)
    return RuntimeContext(home=home, env_file=env_file, packaged=packaged)
