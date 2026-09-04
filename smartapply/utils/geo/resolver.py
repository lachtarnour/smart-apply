"""Resolve free-text French location strings to official INSEE codes.

Backed by ``geo.api.gouv.fr`` (open data, no auth, no per-call rate limit).
The full commune and region referentials are fetched **once** and cached on
disk. All lookups are pure in-memory dict access after the initial warm-up,
so the cost of resolving a location during a search is effectively zero.

Why a dedicated module rather than a hardcoded dict in the FT scraper?

- Coverage: the API exposes the **34 945 French communes** and the 18
  official regions. A handcrafted table only covers what the maintainer
  remembers to add.
- Maintenance: the cache refreshes itself; we never have to ship a new
  release just because a mid-tier city was missing.
- Correctness: INSEE codes returned here are the same the FT search API
  expects, so no manual transcription mistakes can creep in.
- Reusability: the resolver returns a generic :class:`ResolvedLocation`,
  not FT-specific params. SerpApi or future scrapers can plug into the
  same primitive.

The module degrades gracefully when offline. If the cache is missing and
the API is unreachable, the resolver returns an *unresolved* result that
callers can fall back to (typically a keyword search) so we never lose
recall on a network blip.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import requests
from unidecode import unidecode

from smartapply.logging_setup import get_logger

logger = get_logger(__name__)


# ---- Public API -------------------------------------------------------------

GEO_API_COMMUNES_URL: Final[str] = "https://geo.api.gouv.fr/communes"
GEO_API_REGIONS_URL: Final[str] = "https://geo.api.gouv.fr/regions"

# Bump when the on-disk cache shape changes so existing installs refresh.
_CACHE_SCHEMA_VERSION: Final[int] = 1
_CACHE_FILENAME: Final[str] = f"french_geo_v{_CACHE_SCHEMA_VERSION}.json"
_FETCH_TIMEOUT_SECONDS: Final[int] = 20


@dataclass(frozen=True)
class ResolvedLocation:
    """Outcome of resolving a free-text French location string.

    Exactly one of the following predicates is true:

    - :attr:`national` — the input means "search the whole country"
      (empty string, "France", "Remote", "Télétravail", …). Callers
      should apply no geo filter at all.
    - :attr:`region` — a 2-3 char INSEE region code (e.g. ``"11"`` for
      Île-de-France).
    - :attr:`departement` — a 2-3 char INSEE departement code (e.g.
      ``"75"`` for Paris, ``"2A"`` for Corse-du-Sud, ``"974"`` for La
      Réunion).
    - :attr:`commune` — a 5-char INSEE commune code (e.g. ``"75056"``
      for Paris).
    - :attr:`unresolved` — the original input that we could not map.
      Callers should fall back to a free-text search to preserve recall.
    """

    national: bool = False
    region: str | None = None
    departement: str | None = None
    commune: str | None = None
    unresolved: str | None = None

    @property
    def is_resolved(self) -> bool:
        """True when the location was mapped to either national or a code."""
        return self.national or any((self.region, self.departement, self.commune))


def resolve_french_location(
    location: str | None,
    *,
    prefer: str = "departement",
) -> ResolvedLocation:
    """Resolve ``location`` to an INSEE code or ``national``/``unresolved``.

    Parameters
    ----------
    location:
        A free-text location string. ``None`` and empty strings are treated
        as a national search.
    prefer:
        Granularity preference when a city name has a corresponding
        departement. ``"departement"`` (default) returns the departement
        code (broader, recommended for job searches because most "Paris"
        jobs sit in 75 and "Lyon" jobs in 69). ``"commune"`` returns the
        precise INSEE code (narrow, useful if you want to filter on a
        single town). Region resolution is unaffected by this flag.

    Returns
    -------
    ResolvedLocation
        Either national, a structured code, or an unresolved fallback.
    """
    if prefer not in ("departement", "commune"):
        raise ValueError(f"prefer must be 'departement' or 'commune', got {prefer!r}")

    raw = (location or "").strip()
    key = _normalize_key(raw)

    if not key or key in _NATIONAL_TERMS:
        return ResolvedLocation(national=True)

    # Aliases are tiny, stable, and resolve before any network/cache work.
    if key in _REGION_ALIASES:
        return ResolvedLocation(region=_REGION_ALIASES[key])
    if key in _DISTRICT_ALIASES:
        return ResolvedLocation(departement=_DISTRICT_ALIASES[key])
    # Top cities are pinned so we work even with no cache and no network.
    # When ``prefer="commune"`` we still need the cache to obtain the
    # 5-char INSEE code, so the pin only short-circuits departement mode.
    if prefer == "departement" and key in _TOP_CITY_ALIASES:
        return ResolvedLocation(departement=_TOP_CITY_ALIASES[key])

    cache = _get_cache()

    region_code = cache.regions_by_name.get(key)
    if region_code is not None:
        return ResolvedLocation(region=region_code)

    commune = cache.communes_by_name.get(key)
    if commune is not None:
        if prefer == "commune":
            return ResolvedLocation(commune=commune.insee)
        return ResolvedLocation(departement=commune.dept)

    # Cache miss but the city is pinned: fall back to the alias rather
    # than declaring it unresolved.
    if key in _TOP_CITY_ALIASES:
        return ResolvedLocation(departement=_TOP_CITY_ALIASES[key])

    return ResolvedLocation(unresolved=raw or None)


def reset_cache_for_tests() -> None:
    """Drop the in-memory cache. Tests use this to start from a clean state."""
    with _CACHE_LOCK:
        global _CACHE
        _CACHE = None


# ---- Internal -------------------------------------------------------------


@dataclass(frozen=True)
class _CommuneRow:
    insee: str
    dept: str
    region: str


@dataclass
class _GeoCache:
    """In-memory snapshot of resolved geo data."""

    communes_by_name: dict[str, _CommuneRow] = field(default_factory=dict)
    regions_by_name: dict[str, str] = field(default_factory=dict)
    fetched_at: str | None = None
    schema_version: int = _CACHE_SCHEMA_VERSION


_CACHE: _GeoCache | None = None
_CACHE_LOCK = threading.Lock()


# Free-text inputs that mean "the whole country / no geo filter".
_NATIONAL_TERMS: frozenset[str] = frozenset(
    {
        "",
        "france",
        "france entiere",
        "france metropolitaine",
        "metropole",
        "national",
        "nationwide",
        "remote",
        "remote france",
        "teletravail",
        "telework",
        "anywhere",
        "partout",
        "partout en france",
    }
)

# Region aliases that the geo API does not return verbatim (PACA, IDF, …)
# or that have been rebranded (Sud = PACA). The dict maps normalized
# aliases to the official INSEE region code, so a single lookup wins
# before any cache access.
_REGION_ALIASES: dict[str, str] = {
    "idf": "11",
    "ile-de-france": "11",
    "ile de france": "11",
    "ara": "84",
    "auvergne-rhone-alpes": "84",
    "auvergne rhone alpes": "84",
    "hauts-de-france": "32",
    "hauts de france": "32",
    "nouvelle-aquitaine": "75",
    "nouvelle aquitaine": "75",
    "occitanie": "76",
    "provence-alpes-cote d'azur": "93",
    "provence alpes cote d'azur": "93",
    "paca": "93",
    "sud": "93",
    "sud paca": "93",
    "pays de la loire": "52",
    "pdl": "52",
    "bretagne": "53",
    "grand est": "44",
    "normandie": "28",
    "bourgogne-franche-comte": "27",
    "bourgogne franche comte": "27",
    "centre-val de loire": "24",
    "centre val de loire": "24",
    "corse": "94",
    "guadeloupe": "01",
    "martinique": "02",
    "guyane": "03",
    "la reunion": "04",
    "reunion": "04",
    "mayotte": "06",
}

# Business districts and tech hubs that are NOT communes by name but that
# users routinely type. Maps to the containing departement.
_DISTRICT_ALIASES: dict[str, str] = {
    "la defense": "92",
    "sophia-antipolis": "06",
    "sophia antipolis": "06",
    "paris-saclay": "91",
    "plateau de saclay": "91",
    "saclay": "91",
    "silicon sentier": "75",
}

# Top French cities pinned to their departement so the resolver still
# works **before the cache is built** (e.g. on the very first launch,
# offline, in CI without network, or while waiting for the API). These
# entries are matched against the in-memory cache anyway and would
# resolve the same way; pinning them ensures zero first-call latency
# for the cases users hit 95 % of the time.
_TOP_CITY_ALIASES: dict[str, str] = {
    "paris": "75",
    "marseille": "13",
    "lyon": "69",
    "toulouse": "31",
    "nice": "06",
    "nantes": "44",
    "montpellier": "34",
    "strasbourg": "67",
    "bordeaux": "33",
    "lille": "59",
    "rennes": "35",
    "reims": "51",
    "le havre": "76",
    "saint-etienne": "42",
    "toulon": "83",
    "grenoble": "38",
    "dijon": "21",
    "angers": "49",
    "nimes": "30",
    "villeurbanne": "69",
    "clermont-ferrand": "63",
    "aix-en-provence": "13",
    "brest": "29",
    "tours": "37",
    "amiens": "80",
    "limoges": "87",
    "annecy": "74",
    "perpignan": "66",
    "boulogne-billancourt": "92",
    "metz": "57",
    "besancon": "25",
    "orleans": "45",
    "rouen": "76",
    "mulhouse": "68",
    "caen": "14",
    "nancy": "54",
}


def _normalize_key(text: str | None) -> str:
    """Lowercase, deaccent, collapse whitespace, strip ``, France``."""
    if not text:
        return ""
    norm = unidecode(text).strip().lower()
    norm = re.sub(r"\s+", " ", norm)
    norm = re.sub(r",\s*france\s*$", "", norm).strip()
    norm = re.sub(r"^france\s*,\s*", "", norm).strip()
    return norm


def _cache_path() -> Path:
    # Local import to avoid an import cycle (config imports nothing from utils).
    from smartapply.config import get_settings

    return get_settings().cache_dir / _CACHE_FILENAME


def _get_cache() -> _GeoCache:
    """Return the in-memory cache, loading or rebuilding it on demand."""
    global _CACHE
    with _CACHE_LOCK:
        if _CACHE is not None:
            return _CACHE
        cache = _load_cache_from_disk(_cache_path())
        if cache is None:
            cache = _build_cache_from_api()
            if cache.communes_by_name or cache.regions_by_name:
                _write_cache_to_disk(_cache_path(), cache)
        _CACHE = cache
        return cache


def _load_cache_from_disk(path: Path) -> _GeoCache | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("French geo cache unreadable at %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("schema_version") != _CACHE_SCHEMA_VERSION:
        # An older or newer schema: ignore and let the API refresh build a new one.
        return None
    communes_raw = payload.get("communes_by_name") or {}
    regions_raw = payload.get("regions_by_name") or {}
    if not isinstance(communes_raw, dict) or not isinstance(regions_raw, dict):
        return None
    communes: dict[str, _CommuneRow] = {}
    for name, row in communes_raw.items():
        if not isinstance(name, str) or not isinstance(row, dict):
            continue
        insee = row.get("insee")
        dept = row.get("dept")
        region = row.get("region")
        if not (isinstance(insee, str) and isinstance(dept, str) and isinstance(region, str)):
            continue
        communes[name] = _CommuneRow(insee=insee, dept=dept, region=region)
    regions = {
        name: code
        for name, code in regions_raw.items()
        if isinstance(name, str) and isinstance(code, str)
    }
    return _GeoCache(
        communes_by_name=communes,
        regions_by_name=regions,
        fetched_at=payload.get("fetched_at")
        if isinstance(payload.get("fetched_at"), str)
        else None,
        schema_version=_CACHE_SCHEMA_VERSION,
    )


def _write_cache_to_disk(path: Path, cache: _GeoCache) -> None:
    """Atomic write: dump to a sibling temp file then rename in-place."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Cannot create french geo cache dir %s: %s", path.parent, exc)
        return
    serialized = {
        "schema_version": _CACHE_SCHEMA_VERSION,
        "fetched_at": cache.fetched_at or datetime.now(timezone.utc).isoformat(),
        "communes_by_name": {
            name: {"insee": row.insee, "dept": row.dept, "region": row.region}
            for name, row in cache.communes_by_name.items()
        },
        "regions_by_name": dict(cache.regions_by_name),
    }
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            json.dump(serialized, tmp, ensure_ascii=False)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)
    except OSError as exc:
        logger.warning("Failed to write french geo cache to %s: %s", path, exc)


def _build_cache_from_api() -> _GeoCache:
    """Fetch the full commune + region referentials.

    Resilient by design: on failure we return an empty cache so that the
    resolver still answers (with ``unresolved``) instead of raising.
    """
    fetched_at = datetime.now(timezone.utc).isoformat()
    communes_payload = _fetch_json(
        GEO_API_COMMUNES_URL,
        params={"fields": "nom,code,codeDepartement,codeRegion,population"},
    )
    regions_payload = _fetch_json(GEO_API_REGIONS_URL, params={"fields": "nom,code"})

    communes_by_name = _build_communes_index(communes_payload or [])
    regions_by_name = _build_regions_index(regions_payload or [])
    return _GeoCache(
        communes_by_name=communes_by_name,
        regions_by_name=regions_by_name,
        fetched_at=fetched_at,
    )


def _fetch_json(url: str, *, params: dict[str, str]) -> list[dict[str, Any]] | None:
    try:
        response = requests.get(url, params=params, timeout=_FETCH_TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("French geo API call to %s failed: %s", url, exc)
        return None
    if not isinstance(payload, list):
        logger.warning("French geo API at %s returned non-list payload", url)
        return None
    return payload


def _is_overseas_dept(dept_code: str) -> bool:
    """True for the five overseas departements (971..976)."""
    return dept_code.startswith("97")


def _build_communes_index(payload: list[dict[str, Any]]) -> dict[str, _CommuneRow]:
    """Index communes by normalized name with metro-first tie-breaking.

    Multiple communes can share a name ("Saint-Denis", "Sainte-Marie", …).
    We pick the winner with two rules, in order:

    1. **Metro before overseas.** A metropolitan match (dept 01-95, 2A,
       2B) always beats an overseas one (dept 971-976), regardless of
       population. This is the right default for a French job search
       product where overseas searches are explicit, not implicit.
    2. **Highest population wins** among the remaining candidates so the
       resolver returns the famous one (Paris over Paris XV, Saint-Denis
       93 over Saint-Denis 11, etc.).
    """
    by_name: dict[str, _CommuneRow] = {}
    # Track (is_metro, population) to encode the priority lexicographically.
    rankings: dict[str, tuple[int, int]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = _normalize_key(item.get("nom"))
        if not name:
            continue
        insee = item.get("code")
        dept = item.get("codeDepartement")
        region = item.get("codeRegion")
        if not (isinstance(insee, str) and isinstance(dept, str) and isinstance(region, str)):
            continue
        population_raw = item.get("population")
        population = int(population_raw) if isinstance(population_raw, int) else 0
        is_metro = 0 if _is_overseas_dept(dept) else 1
        rank = (is_metro, population)
        if rankings.get(name, (-1, -1)) >= rank:
            continue
        by_name[name] = _CommuneRow(insee=insee, dept=dept, region=region)
        rankings[name] = rank
    return by_name


def _build_regions_index(payload: list[dict[str, Any]]) -> dict[str, str]:
    by_name: dict[str, str] = {}
    for item in payload:
        name = _normalize_key(item.get("nom"))
        code = item.get("code")
        if not name or not isinstance(code, str):
            continue
        by_name[name] = code
    return by_name
