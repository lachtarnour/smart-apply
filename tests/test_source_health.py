"""Tests for non-billable desktop source diagnostics."""

from __future__ import annotations

import json
from types import SimpleNamespace

import requests

from smartapply.desktop import source_health
from smartapply.desktop.source_health import SourceHealth
from smartapply.scrapers.wttj.contracts import WTTJAuthenticationError


def _settings(**overrides):  # noqa: ANN003, ANN202
    values = {
        "serpapi_api_key": "",
        "francetravail_client_id": "",
        "francetravail_client_secret": "",
        "francetravail_scope": "scope",
        "apify_token": "",
        "wttj_cookie": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _response(status: int, payload: dict) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(payload).encode()  # noqa: SLF001 - test response fixture
    response.headers["Content-Type"] = "application/json"
    return response


def test_serpapi_health_marks_exhausted_quota_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        source_health.requests,
        "get",
        lambda *args, **kwargs: _response(  # noqa: ARG005
            200,
            {"account_status": "Active", "total_searches_left": 0},
        ),
    )

    result = source_health._check_serpapi(  # noqa: SLF001
        _settings(serpapi_api_key="secret"),
        timeout=1,
    )

    assert result.ready is False
    assert result.state == "unavailable"
    assert "épuisé" in result.message


def test_serpapi_health_marks_http_429_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        source_health.requests,
        "get",
        lambda *args, **kwargs: _response(429, {"error": "rate limit"}),  # noqa: ARG005
    )

    result = source_health.check_source_health(
        _settings(serpapi_api_key="secret"),
        timeout=1,
    )

    assert result["serpapi"].ready is False
    assert result["serpapi"].state == "unavailable"
    assert result["serpapi"].message == "Quota ou limite de requêtes atteint."


def test_live_health_isolates_expired_wttj_from_other_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        source_health,
        "fetch_matches_api_page",
        lambda **kwargs: (_ for _ in ()).throw(  # noqa: ARG005
            WTTJAuthenticationError("cookie rejected")
        ),
    )
    monkeypatch.setattr(
        source_health,
        "_check_serpapi",
        lambda settings, timeout: SourceHealth(  # noqa: ARG005
            configured=True,
            ready=True,
            state="available",
            message="Compte valide.",
        ),
    )

    result = source_health.check_source_health(
        _settings(serpapi_api_key="key", wttj_cookie="expired"),
        timeout=1,
    )

    assert result["serpapi"].ready is True
    assert result["welcometothejungle"].ready is False
    assert result["welcometothejungle"].message == "Session WTTJ expirée ou refusée."
    assert result["francetravail"].state == "unconfigured"
    assert result["linkedin"].state == "unconfigured"


def test_pending_health_never_claims_a_configured_source_is_available() -> None:
    result = source_health.pending_source_health(
        _settings(serpapi_api_key="key", apify_token="token")
    )

    assert result["serpapi"].state == "checking"
    assert result["serpapi"].ready is False
    assert result["linkedin"].state == "checking"
    assert result["welcometothejungle"].state == "unconfigured"
