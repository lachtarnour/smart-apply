"""Tests for :mod:`smartapply.utils.french_geo`.

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
from pathlib import Path

import pytest
import requests

from smartapply.utils import french_geo
from smartapply.utils.french_geo import (
    ResolvedLocation,
    _build_communes_index,
    _build_regions_index,
    _normalize_key,
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
        "smartapply.utils.french_geo.get_settings",
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
        "smartapply.utils.french_geo.requests.get",
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


def test_district_aliases_resolve_offline():
    cases = {
        "La Défense": "92",
        "Sophia-Antipolis": "06",
        "Sophia Antipolis": "06",
        "Paris-Saclay": "91",
        "Saclay": "91",
    }
    for input_text, expected_dept in cases.items():
        result = resolve_french_location(input_text)
        assert result.departement == expected_dept, input_text


def test_normalize_key_strips_france_suffix_and_accents():
    assert _normalize_key("Paris, France") == "paris"
    assert _normalize_key("France, Paris") == "paris"
    assert _normalize_key("Île-de-France") == "ile-de-france"
    assert _normalize_key("  Saint-Étienne   ") == "saint-etienne"
    assert _normalize_key("") == ""
    assert _normalize_key(None) == ""


# ---- Layer 2: cache + API ------------------------------------------------


_COMMUNES_FIXTURE = [
    {"nom": "Paris", "code": "75056", "codeDepartement": "75", "codeRegion": "11", "population": 2102650},
    {"nom": "Vesoul", "code": "70550", "codeDepartement": "70", "codeRegion": "27", "population": 14938},
    {"nom": "Saint-Denis", "code": "93066", "codeDepartement": "93", "codeRegion": "11", "population": 113116},
    {"nom": "Saint-Denis", "code": "97411", "codeDepartement": "974", "codeRegion": "04", "population": 153810},
    {"nom": "Saint-Denis", "code": "11339", "codeDepartement": "11", "codeRegion": "76", "population": 156},
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

    return mocker.patch("smartapply.utils.french_geo.requests.get", side_effect=fake_get)


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


def test_second_call_uses_cache_not_api(isolated_cache_dir, mocker):
    _stub_geo_api(mocker)
    resolve_french_location("Vesoul")  # warm the cache
    reset_cache_for_tests()  # drop in-memory, keep disk

    get_mock = mocker.patch(
        "smartapply.utils.french_geo.requests.get",
        side_effect=AssertionError("must not hit network"),
    )
    result = resolve_french_location("Vesoul")
    assert result.departement == "70"
    get_mock.assert_not_called()


def test_ambiguous_commune_prefers_metro_over_overseas(isolated_cache_dir, mocker):
    """``Saint-Denis`` exists in 93 (metro), 974 (La Réunion, more populated)
    and 11 (tiny village). Job searches in metro France are the dominant
    case, so the resolver must return 93 even though 974 has the highest
    raw population.
    """
    _stub_geo_api(mocker)
    result = resolve_french_location("Saint-Denis")
    assert result.departement == "93"


def test_build_communes_index_falls_back_to_overseas_when_no_metro():
    """If no metropolitan commune carries that name, the overseas one wins
    so we don't accidentally drop legitimate names like ``Saint-Pierre``."""
    payload = [
        {
            "nom": "Saint-Pierre",
            "code": "97416",
            "codeDepartement": "974",
            "codeRegion": "04",
            "population": 80000,
        },
    ]
    index = _build_communes_index(payload)
    assert index["saint-pierre"].dept == "974"


def test_build_communes_index_metro_wins_even_with_lower_population():
    """Metro priority is absolute: a tiny metro commune beats a giant
    overseas one. Tests the rule independently of the Saint-Denis case."""
    payload = [
        {
            "nom": "Foo",
            "code": "97400",
            "codeDepartement": "974",
            "codeRegion": "04",
            "population": 999_999,
        },
        {
            "nom": "Foo",
            "code": "01001",
            "codeDepartement": "01",
            "codeRegion": "84",
            "population": 100,
        },
    ]
    index = _build_communes_index(payload)
    assert index["foo"].dept == "01"


def test_commune_mode_returns_insee_code(isolated_cache_dir, mocker):
    _stub_geo_api(mocker)
    result = resolve_french_location("Vesoul", prefer="commune")
    assert result.commune == "70550"
    assert result.departement is None


def test_prefer_must_be_valid():
    with pytest.raises(ValueError):
        resolve_french_location("Paris", prefer="region")


def test_unresolved_when_unknown_and_no_cache(isolated_cache_dir, mocker):
    mocker.patch(
        "smartapply.utils.french_geo.requests.get",
        side_effect=requests.ConnectionError("offline"),
    )
    result = resolve_french_location("Atlantis")
    assert result.unresolved == "Atlantis"
    assert not result.is_resolved


def test_unresolved_when_unknown_with_populated_cache(isolated_cache_dir, mocker):
    _stub_geo_api(mocker)
    result = resolve_french_location("Atlantis")
    assert result.unresolved == "Atlantis"


# ---- Layer 3: graceful degradation --------------------------------------


def test_corrupt_cache_file_is_ignored(isolated_cache_dir, mocker):
    cache_file = isolated_cache_dir / "french_geo_v1.json"
    cache_file.write_text("{ this is not json", encoding="utf-8")
    _stub_geo_api(mocker)

    # Should still resolve via the fresh API fetch.
    result = resolve_french_location("Vesoul")
    assert result.departement == "70"


def test_cache_with_old_schema_is_ignored(isolated_cache_dir, mocker):
    cache_file = isolated_cache_dir / "french_geo_v1.json"
    cache_file.write_text(
        json.dumps({"schema_version": 0, "communes_by_name": {}, "regions_by_name": {}}),
        encoding="utf-8",
    )
    _stub_geo_api(mocker)
    result = resolve_french_location("Vesoul")
    assert result.departement == "70"


def test_api_failure_yields_empty_cache_but_aliases_still_work(
    isolated_cache_dir, mocker
):
    mocker.patch(
        "smartapply.utils.french_geo.requests.get",
        side_effect=requests.RequestException("boom"),
    )
    assert resolve_french_location("Paris").departement == "75"
    assert resolve_french_location("PACA").region == "93"
    # Unknown city without cache → unresolved.
    assert resolve_french_location("Vesoul").unresolved == "Vesoul"


def test_atomic_write_does_not_leave_tmp_files(isolated_cache_dir, mocker):
    _stub_geo_api(mocker)
    resolve_french_location("Vesoul")
    tmp_files = list(isolated_cache_dir.glob("*.tmp"))
    assert tmp_files == [], f"orphan temp files: {tmp_files}"


# ---- Index builders (pure functions) ------------------------------------


def test_build_communes_index_keeps_metro_homonym_over_overseas():
    by_name = _build_communes_index(_COMMUNES_FIXTURE)
    # 3 Saint-Denis in fixture: 93066 (metro, 113K), 97411 (overseas, 154K),
    # 11339 (metro, 156). Metro-first beats overseas regardless of size,
    # then population picks 93066 within the metro candidates.
    assert by_name["saint-denis"].insee == "93066"
    # Unrelated communes are still present.
    assert by_name["paris"].insee == "75056"
    assert by_name["vesoul"].insee == "70550"


def test_build_communes_index_ignores_malformed_rows():
    payload = [
        {"nom": "Paris", "code": "75056", "codeDepartement": "75", "codeRegion": "11"},
        {"nom": None, "code": "1", "codeDepartement": "1", "codeRegion": "1"},
        {"nom": "Test", "code": None, "codeDepartement": "1", "codeRegion": "1"},
        {"nom": "Test2", "code": "1", "codeDepartement": None, "codeRegion": "1"},
        "not a dict",
    ]
    by_name = _build_communes_index(payload)  # type: ignore[arg-type]
    assert "paris" in by_name
    assert len(by_name) == 1


def test_build_regions_index_normalizes_names():
    by_name = _build_regions_index(_REGIONS_FIXTURE)
    assert by_name["ile-de-france"] == "11"
    assert by_name["bourgogne-franche-comte"] == "27"
    assert by_name["la reunion"] == "04"


# ---- ResolvedLocation dataclass -----------------------------------------


def test_resolved_location_is_resolved_property():
    assert ResolvedLocation(national=True).is_resolved
    assert ResolvedLocation(region="11").is_resolved
    assert ResolvedLocation(departement="75").is_resolved
    assert ResolvedLocation(commune="75056").is_resolved
    assert not ResolvedLocation().is_resolved
    assert not ResolvedLocation(unresolved="Atlantis").is_resolved


def test_resolved_location_is_frozen():
    from dataclasses import FrozenInstanceError

    location = ResolvedLocation(departement="75")
    with pytest.raises(FrozenInstanceError):
        location.departement = "69"  # type: ignore[misc]


# ---- Integration with cache_path resolution ------------------------------


def test_cache_path_uses_settings_cache_dir(isolated_cache_dir):
    path = french_geo._cache_path()
    assert isinstance(path, Path)
    assert path.parent == isolated_cache_dir
    assert path.name == "french_geo_v1.json"
