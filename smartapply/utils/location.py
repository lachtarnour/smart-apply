"""Location-related helpers shared by filtering and ranking.

The candidate explicitly accepts only French offers (plus EU remote when
the candidate has opted into remote). Anything else is treated as outside
the target market and hard-rejected at the filter layer, well before any
LLM call.
"""

from __future__ import annotations

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
