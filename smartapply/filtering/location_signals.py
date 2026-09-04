"""Location scoring helpers for the local filter."""

from __future__ import annotations

import re

_FOREIGN_LOCATION_MARKERS = (
    "allemagne",
    "amsterdam",
    "autriche",
    "australia",
    "australie",
    "barcelona",
    "belgique",
    "berlin",
    "brussels",
    "bruxelles",
    "canada",
    "chine",
    "china",
    "copenhagen",
    "danemark",
    "denmark",
    "dublin",
    "emirats arabes unis",
    "espagne",
    "etats unis",
    "finland",
    "finlande",
    "frankfurt",
    "germany",
    "grece",
    "greece",
    "inde",
    "india",
    "italie",
    "italy",
    "japon",
    "japan",
    "london",
    "londres",
    "luxembourg",
    "madrid",
    "milan",
    "munich",
    "netherlands",
    "new york",
    "norvege",
    "norway",
    "pays bas",
    "pologne",
    "poland",
    "prague",
    "republique tcheque",
    "remote us",
    "royaume uni",
    "san francisco",
    "singapore",
    "singapour",
    "spain",
    "stockholm",
    "suede",
    "suisse",
    "switzerland",
    "tchequie",
    "toronto",
    "uk",
    "united kingdom",
    "united states",
    "usa",
    "vienna",
    "warsaw",
    "zurich",
)
_FOREIGN_MARKER_RE = re.compile(
    r"(?<![a-z0-9])("
    + "|".join(
        re.escape(marker) for marker in sorted(_FOREIGN_LOCATION_MARKERS, key=len, reverse=True)
    )
    + r")(?![a-z0-9])"
)
_FOREIGN_JOB_CONTEXT_TEMPLATES = (
    r"\bposte\b.{0,90}\b(?:basee?|situee?|localisee?)\b.{0,90}"
    r"(?P<marker><markers>)",
    r"(?:^|[\n.;:]\s*)\b(?:basee?|situee?|localisee?)\s+"
    r"(?:a|au|en|aux)\s+(?P<marker><markers>)",
    r"\b(?:localisation|lieu)\s*:\s*.{0,80}(?P<marker><markers>)",
    r"\b(?:position|role|job)\b.{0,90}\b(?:is\s+|will\s+be\s+)?"
    r"(?:based|located)\b.{0,90}(?P<marker><markers>)",
    r"(?:^|[\n.;:]\s*)\b(?:based|located)\s+(?:in|at)\s+"
    r"(?P<marker><markers>)",
    r"\b(?:location|workplace|office)\s*:\s*.{0,80}(?P<marker><markers>)",
    r"\b(?:expatriation|relocation)\b.{0,90}(?P<marker><markers>)",
    r"\bremote\s+us\b",
)
_FOREIGN_CONTEXT_RES = tuple(
    re.compile(template.replace("<markers>", _FOREIGN_MARKER_RE.pattern))
    for template in _FOREIGN_JOB_CONTEXT_TEMPLATES
)


def visible_foreign_location_marker(title: str, description: str) -> str | None:
    """Return a foreign marker only when it describes the offer location.

    The title is treated as strong evidence; in the description we require an
    explicit job-location context so company footprints abroad do not reject a
    French role.
    """
    if title_match := _FOREIGN_MARKER_RE.search(title):
        return title_match.group(1)
    for pattern in _FOREIGN_CONTEXT_RES:
        match = pattern.search(description)
        if match:
            return match.groupdict().get("marker") or match.group(0)
    return None
