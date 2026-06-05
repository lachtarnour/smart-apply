"""Location scoring helpers for the local filter."""

from __future__ import annotations

import re

from smartapply.filtering.text import norm

_BROAD_FRANCE_LOCATION_PREFS = {"france", "fr"}
_FOREIGN_LOCATION_MARKERS = (
    "allemagne",
    "belgique",
    "berlin",
    "canada",
    "espagne",
    "etats unis",
    "germany",
    "london",
    "londres",
    "luxembourg",
    "madrid",
    "new york",
    "remote us",
    "san francisco",
    "spain",
    "suisse",
    "switzerland",
    "uk",
    "united kingdom",
    "united states",
    "usa",
)
_FOREIGN_MARKER_RE = re.compile(
    r"(?<![a-z0-9])("
    + "|".join(re.escape(marker) for marker in sorted(_FOREIGN_LOCATION_MARKERS, key=len, reverse=True))
    + r")(?![a-z0-9])"
)
_FOREIGN_JOB_CONTEXT_TEMPLATES = (
    r"\bposte\b.{0,90}\b(?:base|situe|localise)\b.{0,90}(?P<marker><markers>)",
    r"\b(?:base|situe|localise)\s+(?:a|au|en|aux)\s+(?P<marker><markers>)",
    r"\b(?:localisation|lieu)\s*:\s*.{0,80}(?P<marker><markers>)",
    r"\b(?:expatriation|relocation)\b.{0,90}(?P<marker><markers>)",
    r"\bremote\s+us\b",
)
_FOREIGN_CONTEXT_RES = tuple(
    re.compile(template.replace("<markers>", _FOREIGN_MARKER_RE.pattern))
    for template in _FOREIGN_JOB_CONTEXT_TEMPLATES
)


def specific_preferred_locations(preferred_locations: list[str]) -> list[str]:
    return [
        normalized
        for loc in preferred_locations
        if (normalized := norm(loc)) and normalized not in _BROAD_FRANCE_LOCATION_PREFS
    ]


def has_france_scope(preferred_locations: list[str]) -> bool:
    return any(norm(loc) in _BROAD_FRANCE_LOCATION_PREFS for loc in preferred_locations)


def is_remote_france(location: str | None, remote: str) -> bool:
    if remote != "remote":
        return False
    normalized = norm(location)
    return "france" in normalized or bool(re.search(r"\bremote\b.*\bfr\b", normalized))


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
