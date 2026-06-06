"""Playwright smoke tests for the Streamlit workflow page."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_streamlit(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 30
    last_error: Exception | None = None
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, _ = process.communicate(timeout=1)
            raise AssertionError(f"Streamlit exited early:\n{stdout}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # noqa: BLE001 - keep polling until timeout.
            last_error = exc
        time.sleep(0.5)
    raise AssertionError(f"Streamlit did not start at {url}: {last_error}")


def test_workflow_steps_open_without_visible_errors(tmp_path: Path) -> None:
    playwright = pytest.importorskip("playwright.sync_api")

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'workflow-smoke.db'}",
        "OUTPUT_DIR": str(tmp_path / "output"),
        "CACHE_DIR": str(tmp_path / "cache"),
        "SAMPLES_DIR": str(tmp_path / "samples"),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            "smartapply/app/main.py",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_streamlit(base_url, process)
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.goto(f"{base_url}/Workflow", wait_until="networkidle", timeout=30_000)
            for step in range(1, 6):
                button = page.get_by_role("button", name=f"Aller étape {step}")
                playwright.expect(button).to_be_visible(timeout=15_000)
                button.click()
                page.wait_for_load_state("networkidle", timeout=30_000)
                page.wait_for_timeout(300)
                visible_errors = page.locator(
                    'text=/Traceback|Exception|ModuleNotFoundError|ImportError/i'
                ).count()
                assert visible_errors == 0, f"visible Streamlit error on step {step}"
            browser.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
