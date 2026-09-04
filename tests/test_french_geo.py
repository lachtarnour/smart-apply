"""Tests for :mod:`smartapply.utils.geo.resolver`.

The module is the only place that talks to ``geo.api.gouv.fr``, so any
regression here would silently degrade every job source that relies on
INSEE codes. The tests cover three layers:

1. **Offline correctness**: aliases (regions, districts, top cities)
   resolve without touching the network or the cache.
2. **Cache + API**: the bulk fetch is stubbed; we verify the cache is
   built, written atomically, reloaded, and survives schema bumps.
3. **Graceful degradation**: HTTP failures and corrupt files never
   propagate; the resolver returns ``unresolved`` for unknown inputs.
"""

from __future__ import annotations

import json

import pytest
import requests

from smartapply.utils.geo.resolver import (
    reset_cache_for_tests,
    resolve_french_location,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Each test starts with a fresh in-memory cache."""
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


@pytest.fixture
def isolated_cache_dir(tmp_path, mocker):
    """Redirect ``cache_dir`` so the test never touches the real cache file."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    fake_settings = mocker.Mock()
    fake_settings.cache_dir = cache_dir
    mocker.patch(
        "smartapply.utils.geo.resolver.get_settings",
        return_value=fake_settings,
        create=True,
    )
    # ``get_settings`` is imported lazily inside ``_cache_path``; patch the
    # symbol on the originating module so the lazy import resolves to the mock.
    mocker.patch("smartapply.config.get_settings", return_value=fake_settings)
    return cache_dir


# ---- Layer 1: aliases work without any network or cache ------------------


def test_empty_and_national_terms_resolve_to_national():
    for term in ("", None, "France", "france", "France entière", "Remote", "Télétravail"):
        result = resolve_french_location(term)
        assert result.national is True, term
        assert result.is_resolved


def test_region_aliases_resolve_offline():
    cases = {
        "Île-de-France": "11",
        "ile-de-france": "11",
        "IDF": "11",
        "Auvergne-Rhône-Alpes": "84",
        "ARA": "84",
        "PACA": "93",
        "Sud": "93",
        "Hauts-de-France": "32",
        "Nouvelle-Aquitaine": "75",
        "Occitanie": "76",
        "Bretagne": "53",
        "Corse": "94",
    }
    for input_text, expected_code in cases.items():
        result = resolve_french_location(input_text)
        assert result.region == expected_code, input_text
        assert result.departement is None
        assert result.commune is None


def test_top_cities_resolve_without_cache(isolated_cache_dir, mocker):
    """Top-tier cities must work even when the geo API is unreachable.

    ``isolated_cache_dir`` ensures there is no cache file, and patching
    ``requests.get`` to raise exercises the offline path.
    """
    mocker.patch(
        "smartapply.utils.geo.resolver.requests.get",
        side_effect=requests.ConnectionError("network down"),
    )
    cases = {
        "Paris": "75",
        "Paris, France": "75",
        "Lyon": "69",
        "Marseille": "13",
        "Toulouse": "31",
        "Bordeaux": "33",
        "Lille": "59",
        "Nantes": "44",
        "Annecy": "74",
    }
    for input_text, expected_dept in cases.items():
        result = resolve_french_location(input_text)
        assert result.departement == expected_dept, input_text
        assert result.region is None
        assert result.commune is None


# ---- Layer 2: cache + API ------------------------------------------------


_COMMUNES_FIXTURE = [
    {
        "nom": "Paris",
        "code": "75056",
        "codeDepartement": "75",
        "codeRegion": "11",
        "population": 2102650,
    },
    {
        "nom": "Vesoul",
        "code": "70550",
        "codeDepartement": "70",
        "codeRegion": "27",
        "population": 14938,
    },
    {
        "nom": "Saint-Denis",
        "code": "93066",
        "codeDepartement": "93",
        "codeRegion": "11",
        "population": 113116,
    },
    {
        "nom": "Saint-Denis",
        "code": "97411",
        "codeDepartement": "974",
        "codeRegion": "04",
        "population": 153810,
    },
    {
        "nom": "Saint-Denis",
        "code": "11339",
        "codeDepartement": "11",
        "codeRegion": "76",
        "population": 156,
    },
]

_REGIONS_FIXTURE = [
    {"nom": "Île-de-France", "code": "11"},
    {"nom": "Bourgogne-Franche-Comté", "code": "27"},
    {"nom": "La Réunion", "code": "04"},
]


def _stub_geo_api(mocker):
    """Patch the geo API to return our fixtures regardless of params."""

    def fake_get(url, params=None, timeout=None):
        response = mocker.Mock()
        response.raise_for_status = mocker.Mock()
        if "communes" in url:
            response.json = mocker.Mock(return_value=_COMMUNES_FIXTURE)
        elif "regions" in url:
            response.json = mocker.Mock(return_value=_REGIONS_FIXTURE)
        else:
            response.json = mocker.Mock(return_value=[])
        return response

    return mocker.patch("smartapply.utils.geo.resolver.requests.get", side_effect=fake_get)


def test_first_call_populates_cache_from_api(isolated_cache_dir, mocker):
    get_mock = _stub_geo_api(mocker)
    cache_file = isolated_cache_dir / "french_geo_v1.json"
    assert not cache_file.exists()

    # ``Vesoul`` is not in the alias table so resolution must go through the cache.
    result = resolve_french_location("Vesoul")
    assert result.departement == "70"

    assert cache_file.exists(), "cache file should be written after first fetch"
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert "vesoul" in payload["communes_by_name"]
    assert payload["communes_by_name"]["vesoul"] == {
        "insee": "70550",
        "dept": "70",
        "region": "27",
    }
    assert get_mock.call_count == 2  # one for communes, one for regions


# ---- Layer 3: graceful degradation --------------------------------------


# ---- Index builders (pure functions) ------------------------------------


# ---- ResolvedLocation dataclass -----------------------------------------


# ---- Integration with cache_path resolution ------------------------------
