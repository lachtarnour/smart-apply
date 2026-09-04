"""Smoke test for the native macOS shell."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS desktop smoke test")
def test_macos_desktop_shell_opens_without_errors(tmp_path: Path) -> None:
    pytest.importorskip("PySide6")
    env = {
        **os.environ,
        "QT_QPA_PLATFORM": "offscreen",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'desktop-smoke.db'}",
        "OUTPUT_DIR": str(tmp_path / "output"),
        "CACHE_DIR": str(tmp_path / "cache"),
    }
    result = subprocess.run(
        [sys.executable, "-m", "smartapply.desktop", "--smoke-test"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
