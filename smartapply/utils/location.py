"""Location-related helpers shared by filtering and ranking.

The candidate explicitly accepts only French offers (plus EU remote when
the candidate has opted into remote). Anything else is treated as outside
the target market and hard-rejected at the filter layer, well before any
LLM call.
"""

from __future__ import annotations

import re

from unidecode import unidecode


# Markers that place a job clearly OUTSIDE France. This list is intentionally
# explicit — we'd rather miss a borderline foreign job than reject a French
# one by accident. Lower-cased, ASCII-folded.
FOREIGN_LOCATION_MARKERS: tuple[str, ...] = (
    # Country names
    " usa",
    "united states",
    "united kingdom",
    " uk",
    "england",
    "scotland",
    "ireland",
    "germany",
    "deutschland",
    "spain",
    "espana",
    "italy",
    "italia",
    "netherlands",
    "belgium",
    "belgique",
    "luxembourg",
    "switzerland",
    "suisse",
    "portugal",
    "poland",
    "polska",
    "czech",
    "denmark",
    "sweden",
    "norway",
    "finland",
    "austria",
    "greece",
    "romania",
    "canada",
    "australia",
    "mexico",
    "brazil",
    "india",
    "japan",
    "china",
    "singapore",
    "dubai",
    "uae",
    # Foreign cities frequent in tech postings
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
    # US state codes after a comma (matches "City, CA", "City, NY", ...)
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
    return None


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
    if any(marker in norm for marker in EU_REMOTE_MARKERS):
        return False
    return any(marker in norm for marker in FOREIGN_LOCATION_MARKERS)
