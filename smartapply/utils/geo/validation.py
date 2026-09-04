"""French location validation helpers shared by filtering and ranking.

The candidate explicitly accepts only French offers (plus EU remote when
the candidate has opted into remote). Anything else is treated as outside
the target market and hard-rejected at the filter layer, well before any
LLM call.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import requests
from unidecode import unidecode

GEO_API_COMMUNES_URL = "https://geo.api.gouv.fr/communes"
FRENCH_COMMUNES_CACHE_FILE = "french_communes.json"

# Markers that place a job clearly OUTSIDE France. They are split by signal
# strength so French communes with foreign-looking names ("Montréal, France")
# are not rejected before the official commune check, while explicit foreign
# countries/admin codes still win over French city names ("Paris, TX").
FOREIGN_COUNTRY_MARKERS: tuple[str, ...] = (
    "usa",
    "us",
    "united states",
    "etats unis",
    "etats-unis",
    "united kingdom",
    "royaume uni",
    "royaume-uni",
    "uk",
    "england",
    "scotland",
    "ireland",
    "germany",
    "allemagne",
    "deutschland",
    "spain",
    "espagne",
    "espana",
    "italy",
    "italie",
    "italia",
    "netherlands",
    "pays bas",
    "pays-bas",
    "belgium",
    "belgique",
    "luxembourg",
    "switzerland",
    "suisse",
    "portugal",
    "poland",
    "pologne",
    "polska",
    "czech",
    "republique tcheque",
    "tchequie",
    "denmark",
    "danemark",
    "sweden",
    "suede",
    "norway",
    "norvege",
    "finland",
    "finlande",
    "austria",
    "autriche",
    "greece",
    "grece",
    "romania",
    "roumanie",
    "canada",
    "australia",
    "australie",
    "mexico",
    "mexique",
    "brazil",
    "bresil",
    "india",
    "inde",
    "japan",
    "japon",
    "china",
    "chine",
    "singapore",
    "singapour",
    "uae",
    "emirats arabes unis",
)

# ISO country codes are accepted only as a comma-separated location suffix,
# e.g. ``Stuttgart, DE``. Word-boundary matching would be unsafe for short
# codes such as ``IT`` or ``SE`` in ordinary prose and city names.
FOREIGN_COUNTRY_CODE_MARKERS: tuple[str, ...] = (
    ", at",
    ", au",
    ", be",
    ", bg",
    ", br",
    ", ca",
    ", ch",
    ", cn",
    ", cy",
    ", cz",
    ", de",
    ", dk",
    ", ee",
    ", es",
    ", fi",
    ", gb",
    ", gr",
    ", hr",
    ", hu",
    ", ie",
    ", in",
    ", it",
    ", jp",
    ", lt",
    ", lu",
    ", lv",
    ", mt",
    ", mx",
    ", nl",
    ", no",
    ", pl",
    ", pt",
    ", ro",
    ", se",
    ", sg",
    ", si",
    ", sk",
    ", uk",
    ", us",
)

# Strong administrative/location suffixes, mostly US state codes after a comma
# (matches "City, CA", "City, NY", ...). These intentionally run before the
# French commune check because "Paris, TX" must be rejected.
FOREIGN_ADMIN_MARKERS: tuple[str, ...] = (
    ", ca",
    ", ny",
    ", tx",
    ", wa",
    ", il",
    ", fl",
    ", ma",
    ", co",
    ", or",
)

# Foreign cities frequent in tech postings. These run after the French commune
# check because some city names are ambiguous across countries.
FOREIGN_CITY_MARKERS: tuple[str, ...] = (
    "berlin",
    "munich",
    "munchen",
    "hamburg",
    "cologne",
    "koln",
    "frankfurt",
    "madrid",
    "barcelona",
    "valencia",
    "milan",
    "milano",
    "rome",
    "roma",
    "amsterdam",
    "rotterdam",
    "brussels",
    "bruxelles",
    "zurich",
    "geneva",
    "geneve",
    "lisbon",
    "lisboa",
    "warsaw",
    "warszawa",
    "prague",
    "dublin",
    "vienna",
    "wien",
    "stockholm",
    "copenhagen",
    "kobenhavn",
    "oslo",
    "helsinki",
    "san francisco",
    "new york",
    "seattle",
    "boston",
    "austin",
    "chicago",
    "los angeles",
    "london",
    "manchester",
    "edinburgh",
    "toronto",
    "montreal",
    "dubai",
)

# Markers that override foreign detection: an offer tagged as remote on a
# Europe/France scope is still acceptable for a French candidate.
EU_REMOTE_MARKERS: tuple[str, ...] = (
    "remote (eu)",
    "remote, eu",
    "remote europe",
    "europe remote",
    "remote (france)",
    "remote, france",
    "remote france",
    "remote (fr)",
    "remote, fr",
)


def _normalize_location(location: str | None) -> str:
    return unidecode(location or "").lower()


def _wordish_location(location: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _normalize_location(location)).strip()


def _contains_marker(text: str, marker: str) -> bool:
    marker_norm = marker.strip()
    if not marker_norm:
        return False
    if marker_norm.startswith(","):
        admin_code = marker_norm[1:].strip()
        if not admin_code:
            return False
        return bool(re.search(rf",\s*{re.escape(admin_code)}(?=$|[\s,])", text))

    marker_words = _wordish_location(marker_norm)
    if not marker_words:
        return False
    text_words = _wordish_location(text)
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(marker_words)}(?![a-z0-9])",
            text_words,
        )
    )


def _contains_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(_contains_marker(text, marker) for marker in markers)


def _normalize_commune_name(name: str | None) -> str:
    return _wordish_location(name)


def _communes_cache_path() -> Path:
    from smartapply.config import get_settings

    return get_settings().cache_dir / FRENCH_COMMUNES_CACHE_FILE


def _extract_commune_names(payload: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for item in payload:
        name = _normalize_commune_name(item.get("nom"))
        if name:
            names.add(name)
    return names


def _read_communes_cache(path: Path) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, list):
        return set()
    return {name for name in payload if isinstance(name, str) and name}


def _write_communes_cache(path: Path, names: set[str]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(sorted(names), ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return


def _fetch_official_commune_names() -> set[str]:
    try:
        response = requests.get(
            GEO_API_COMMUNES_URL,
            params={"fields": "nom", "format": "json"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return set()
    if not isinstance(payload, list):
        return set()
    return _extract_commune_names(payload)


@lru_cache(maxsize=1)
def _official_french_commune_names() -> frozenset[str]:
    cache_path = _communes_cache_path()
    cached = _read_communes_cache(cache_path)
    if cached:
        return frozenset(cached)

    fetched = _fetch_official_commune_names()
    if fetched:
        _write_communes_cache(cache_path, fetched)
    return frozenset(fetched)


def _official_commune_in_text(location: str | None) -> str | None:
    norm = _normalize_commune_name(location)
    if not norm:
        return None
    padded = f" {norm} "
    for commune in _official_french_commune_names():
        if len(commune) < 3 and norm != commune:
            continue
        if f" {commune} " in padded:
            return commune
    return None


FRENCH_CITY_ALIASES: dict[str, tuple[str, ...]] = {
    "paris": ("paris", "ile de france", "ile-de-france", "idf"),
    "lyon": ("lyon", "lyonnais"),
    "marseille": ("marseille",),
    "toulouse": ("toulouse",),
    "nice": ("nice",),
    "nantes": ("nantes",),
    "montpellier": ("montpellier",),
    "strasbourg": ("strasbourg",),
    "bordeaux": ("bordeaux",),
    "lille": ("lille",),
    "rennes": ("rennes",),
    "reims": ("reims",),
    "saint-etienne": ("saint etienne", "saint-etienne"),
    "toulon": ("toulon",),
    "grenoble": ("grenoble",),
    "dijon": ("dijon",),
    "angers": ("angers",),
    "nimes": ("nimes",),
    "villeurbanne": ("villeurbanne",),
    "clermont-ferrand": ("clermont ferrand", "clermont-ferrand"),
    "aix-en-provence": ("aix en provence", "aix-en-provence"),
    "brest": ("brest",),
    "limoges": ("limoges",),
    "tours": ("tours",),
    "amiens": ("amiens",),
    "perpignan": ("perpignan",),
    "metz": ("metz",),
    "besancon": ("besancon",),
    "orleans": ("orleans",),
    "rouen": ("rouen",),
    "mulhouse": ("mulhouse",),
    "caen": ("caen",),
    "nancy": ("nancy",),
    "argenteuil": ("argenteuil",),
    "montreuil": ("montreuil",),
    "roubaix": ("roubaix",),
    "tourcoing": ("tourcoing",),
    "nanterre": ("nanterre",),
    "vitry-sur-seine": ("vitry sur seine", "vitry-sur-seine"),
    "creteil": ("creteil",),
    "avignon": ("avignon",),
    "poitiers": ("poitiers",),
    "versailles": ("versailles",),
    "colombes": ("colombes",),
    "courbevoie": ("courbevoie",),
    "rueil-malmaison": ("rueil malmaison", "rueil-malmaison"),
    "saint-denis": ("saint denis", "saint-denis"),
    "boulogne-billancourt": ("boulogne billancourt", "boulogne-billancourt"),
    "issy-les-moulineaux": ("issy les moulineaux", "issy-les-moulineaux"),
    "levallois-perret": ("levallois perret", "levallois-perret"),
    "la-defense": ("la defense", "la-defense"),
    "massy": ("massy",),
    "saclay": ("saclay", "paris saclay", "paris-saclay"),
    "chateaufort": ("chateaufort", "châteaufort"),
    "velizy-villacoublay": ("velizy villacoublay", "velizy-villacoublay", "velizy"),
    "saint-herblain": ("saint herblain", "saint-herblain"),
    "sophia-antipolis": ("sophia antipolis", "sophia-antipolis"),
}


def canonical_french_city(location: str | None) -> str | None:
    """Return a canonical French city key when one is visible in text."""
    norm = _normalize_location(location)
    if not norm:
        return None
    padded = f" {re.sub(r'[^a-z0-9]+', ' ', norm)} "
    for city, aliases in FRENCH_CITY_ALIASES.items():
        for alias in aliases:
            alias_norm = re.sub(r"[^a-z0-9]+", " ", _normalize_location(alias)).strip()
            if not alias_norm:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(alias_norm)}(?![a-z0-9])", padded):
                return city
    return _official_commune_in_text(location)


def is_french_location(location: str | None) -> bool:
    """True when the text points to a French place or French admin code.

    The commune list comes from the official French API Geo and is cached
    locally, so the filter is robust across ordinary French city names without
    doing a network request for every job offer.
    """
    if not location:
        return False
    norm = _normalize_location(location)
    if "france" in norm:
        return True
    if canonical_french_city(location):
        return True
    # France Travail often emits locations like "75 - Paris" or "69 - Rhône".
    return bool(re.search(r"(?<!\d)(?:0[1-9]|[1-8]\d|9[0-5])\s*-", norm))


def french_city_mismatch(target_location: str | None, observed_text: str | None) -> bool:
    """True only when both texts expose different known French cities."""
    target_city = canonical_french_city(target_location)
    observed_city = canonical_french_city(observed_text)
    return bool(target_city and observed_city and target_city != observed_city)


def is_foreign_location(location: str | None) -> bool:
    """True when the location clearly points to a non-FR market.

    Returns False for empty/unknown locations (caller decides what to do),
    for FR cities and departement codes, and for EU-wide remote postings.
    """
    if not location:
        return False
    norm = _normalize_location(location)
    if _contains_any_marker(norm, EU_REMOTE_MARKERS):
        return False
    if _contains_any_marker(norm, FOREIGN_COUNTRY_MARKERS):
        return True
    if _contains_any_marker(norm, FOREIGN_COUNTRY_CODE_MARKERS):
        return True
    if _contains_any_marker(norm, FOREIGN_ADMIN_MARKERS):
        return True
    if is_french_location(location):
        return False
    return _contains_any_marker(norm, FOREIGN_CITY_MARKERS)
