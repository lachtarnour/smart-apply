"""Extract the required years-of-experience from a job description.

The candidate is junior-to-mid (1-3 years), so offers asking for ``5+ ans``
or ``5-7 years`` are out of scope and must be hard-rejected at the filter
layer before any LLM call.

The extractor is bilingual (FR + EN) and intentionally conservative: it
only matches phrases that explicitly tie a number to an experience unit
(``ans``, ``an``, ``years``, ``yrs``) and an experience context (``+``,
``d'expérience``, ``of experience``, ``minimum``, ``at least``, ``5-7``).
"""

from __future__ import annotations

import re


# Phrases like ``Bac+5`` are French diploma levels, NOT experience years.
# Strip them first so a stray ``+5`` doesn't masquerade as a senior signal.
_DIPLOMA_LEVEL_RE = re.compile(
    r"\bbac\s*\+\s*\d+|master\s*\+\s*\d+|m\s*\+\s*\d+",
    re.IGNORECASE,
)


# Each pattern captures the MIN years required as named group ``years``.
# Order from most specific to least specific — first match wins is fine,
# we aggregate then take min().
_EXPERIENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "minimum 5 ans" / "at least 5 years" / "au moins 5 ans"
    re.compile(
        r"(?:min(?:imum)?\.?|at\s+least|au\s+moins)\s+"
        r"(?P<years>\d{1,2})\s*\+?\s*(?:ans?|years?|yrs?)\b",
        re.IGNORECASE,
    ),
    # "5+ ans" / "5+ years" / "5 + years"
    re.compile(
        r"\b(?P<years>\d{1,2})\s*\+\s*(?:ans?|years?|yrs?)\b",
        re.IGNORECASE,
    ),
    # "5-7 ans" / "5 à 7 years" / "5 to 7 years"
    re.compile(
        r"\b(?P<years>\d{1,2})\s*(?:[-–]|to|\bà\b|\ba\b)\s*\d{1,2}\s*(?:ans?|years?)\b",
        re.IGNORECASE,
    ),
    # "5 ans d'expérience" / "5 years of experience" / "5 ans d'exp"
    re.compile(
        r"\b(?P<years>\d{1,2})\s*(?:ans?|years?|yrs?)\s+"
        r"(?:d['’]?exp[ée]?r?i?e?n?c?e?|of\s+exp[ée]?rience)",
        re.IGNORECASE,
    ),
    # "5 ans minimum" / "5 years minimum" / "5 years required" / "5 ans requis"
    re.compile(
        r"\b(?P<years>\d{1,2})\s*(?:ans?|years?|yrs?)\s+"
        r"(?:minimum|min\.?|required|requis|exig[ée]e?s?)\b",
        re.IGNORECASE,
    ),
    # "expérience de 5 ans" / "experience of 5 years"
    re.compile(
        r"(?:exp[ée]rience|experience)\s+(?:de|of)\s+"
        r"(?P<years>\d{1,2})\s*\+?\s*(?:ans?|years?)\b",
        re.IGNORECASE,
    ),
)


def required_min_years(text: str | None) -> int | None:
    """Return the minimum required years of experience, or None if unstated.

    Returns the SMALLEST explicit requirement found — so a job saying
    ``"3 ans minimum, 5+ ans préféré"`` returns ``3`` (the floor, not the
    ideal). Diplomas like ``Bac+5`` are stripped before matching.
    """
    if not text:
        return None

    cleaned = _DIPLOMA_LEVEL_RE.sub(" ", text)

    years_found: list[int] = []
    for pattern in _EXPERIENCE_PATTERNS:
        for match in pattern.finditer(cleaned):
            try:
                value = int(match.group("years"))
            except (ValueError, IndexError):
                continue
            if 1 <= value <= 30:  # sanity bounds
                years_found.append(value)

    if not years_found:
        return None
    return min(years_found)
