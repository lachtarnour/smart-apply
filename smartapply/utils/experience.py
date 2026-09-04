"""Extract candidate-required years of experience from a job description.

The candidate is junior-to-mid (1-3 years), so offers asking for ``5+ ans``
or ``5-7 years`` are out of scope and must be hard-rejected at the filter
layer before any LLM call.

The extractor is bilingual (FR + EN) and intentionally conservative: it only
returns a number when the surrounding text clearly makes it a candidate
requirement. Company history, cabinet experience, optional preferences, and
ambiguous mentions return ``None`` so the offer can continue to ranking/LLM.
"""

from __future__ import annotations

import math
import re

from unidecode import unidecode

# Phrases like ``Bac+5`` are French diploma levels, NOT experience years.
# Strip them first so a stray ``+5`` doesn't masquerade as a senior signal.
_DIPLOMA_LEVEL_RE = re.compile(
    r"\bbac\s*\+\s*\d+|master\s*\+\s*\d+|m\s*\+\s*\d+",
    re.IGNORECASE,
)

_YEAR_MENTION_RE = re.compile(
    r"\b(?P<amount>\d{1,2})\s*"
    r"(?P<modifier>\+|(?:[-–]|to|a)\s*\d{1,2})?\s*"
    r"(?P<unit>ans?|annees?|years?|yrs?)\b"
)

_MONTH_MENTION_RE = re.compile(r"\b(?P<amount>\d{1,3})\s*(?P<unit>mois|months?)\b")

_COMPANY_EXPERIENCE_CONTEXT_RE = re.compile(
    r"\b(?:entreprise|societe|cabinet|groupe|acteur|editeur|client|"
    r"notre\s+client|marche|organisation|structure|company|firm|business|"
    r"employer|organisation|organization|our\s+company|our\s+team)\b"
    r"|"
    r"\b(?:forte?s?\s+de|depuis|plus\s+de|a\s+plus\s+de|"
    r"cree(?:e)?\s+il\s+y\s+a|fondee?\s+il\s+y\s+a|"
    r"existe\s+depuis|acteur\s+depuis|accompagne\s+depuis|"
    r"founded|established|operating\s+since|in\s+business\s+for|"
    r"has\s+been\s+(?:operating|active)|we\s+have\s+been)\b"
    r"|"
    r"\b(?:savoir-faire|savoir\s+faire|existence|histoire|anciennete|"
    r"track\s+record|company\s+history|industry\s+experience)\b"
)

_OPTIONAL_CONTEXT_RE = re.compile(
    r"\b(?:idealement|souhaite(?:e|s|es)?|souhaitable|apprecie(?:e|s|es)?|"
    r"serait\s+(?:apprecie|un\s+plus)|un\s+plus|est\s+un\s+plus|"
    r"prefere(?:e|s|es)?|ideally|preferably|preferred|desired|desirable|"
    r"optional|nice\s+to\s+have|would\s+be\s+(?:a\s+plus|preferred)|bonus|"
    r"premiere\s+experience\s+appreciee?|experience\s+significative)\b"
)

_AGE_CONTEXT_RE = re.compile(
    r"\b(?:age\s+limite|condition\s+d[' ]?age|condition\s+age)\b"
    r"|"
    r"\bmoins\s+(?:de|d[' ]?un|d[' ]?une)\b"
)

_CANDIDATE_SUBJECT_REQUIRED_RE = re.compile(
    r"\b(?:vous|tu)\s+"
    r"(?:(?:devez|devrez)\s+)?"
    r"(?:justifiez|dispos(?:ez|erez)|avez|aurez|possedez|possederez|"
    r"presentez|presenterez|beneficiez|justifier|disposer|avoir|posseder)\b"
    r"|"
    r"\byou\s+(?:(?:must|should|need\s+to|will)\s+)?"
    r"(?:have|bring|possess|demonstrate)\b"
    r"|"
    r"\b(?:the\s+)?(?:ideal\s+)?(?:candidates?|applicants?|person)\s+"
    r"(?:must\s+|should\s+|will\s+)?(?:has|have|brings?|possesses|"
    r"demonstrates?)\b"
    r"|"
    r"\b(?:candidat(?:e)?s?|profils?)\s+"
    r"(?:doit\s+|devra\s+)?(?:a|avoir|justifie|justifier|dispose|disposer|"
    r"possede|posseder)\b"
    r"|"
    r"\b(?:candidates?|applicants?|person|someone|profils?)\s+(?:avec|with)\b"
)

_REQUIRED_MARKER_RE = re.compile(
    r"\b(?:minimum|min\.?|minimale?|au\s+moins|at\s+least|required|"
    r"requis(?:e|es|s)?|exige(?:e|es|s)?|obligatoire|demande(?:e|es|s)?)\b"
)

_EXPERIENCE_REQUIRED_RE = re.compile(
    r"\b(?:experience|exp)\s+"
    r"(?:minimum|minimale?|requise?|exige(?:e|es|s)?|"
    r"demandee?|required)\b"
    r"|"
    r"\b(?:experience|exp)\s+demandee\b"
    r"|"
    r"\b(?:experience|exp)\s+required\b"
)

_EXPERIENCE_WORD_RE = re.compile(r"\b(?:experience|exp)\b")

_SIMILAR_ROLE_RE = re.compile(
    r"\b(?:sur|dans|in)\s+(?:un\s+|une\s+|a\s+)?"
    r"(?:poste|role|fonction|similar\s+role)\b"
)


def _normalize(text: str) -> str:
    return unidecode(text).lower()


def _context(text: str, match: re.Match[str], before: int = 120, after: int = 120) -> str:
    start = max(0, match.start() - before)
    end = min(len(text), match.end() + after)
    return text[start:end]


def _near_before(text: str, match: re.Match[str], size: int = 90) -> str:
    return text[max(0, match.start() - size) : match.start()]


def _near_after(text: str, match: re.Match[str], size: int = 90) -> str:
    return text[match.end() : min(len(text), match.end() + size)]


def _is_company_experience_context(window: str) -> bool:
    return bool(_COMPANY_EXPERIENCE_CONTEXT_RE.search(window))


def _is_preferred_or_optional_context(text: str, match: re.Match[str]) -> bool:
    local = _context(text, match, before=65, after=65)
    return bool(_OPTIONAL_CONTEXT_RE.search(local))


def _is_age_context(text: str, match: re.Match[str]) -> bool:
    local = _context(text, match, before=45, after=45)
    return bool(_AGE_CONTEXT_RE.search(local))


def _has_candidate_subject_required_context(text: str, match: re.Match[str]) -> bool:
    return bool(_CANDIDATE_SUBJECT_REQUIRED_RE.search(_near_before(text, match)))


def _has_hard_required_marker_context(text: str, match: re.Match[str]) -> bool:
    before = _near_before(text, match)
    after = _near_after(text, match)
    window = f"{before}{match.group(0)}{after}"
    return bool(
        _REQUIRED_MARKER_RE.search(before)
        or _REQUIRED_MARKER_RE.search(after)
        or _EXPERIENCE_REQUIRED_RE.search(window)
    )


def _is_candidate_required_context(
    text: str,
    match: re.Match[str],
    *,
    has_plus_or_range: bool,
) -> bool:
    before = _near_before(text, match)
    after = _near_after(text, match)
    window = f"{before}{match.group(0)}{after}"

    if _has_candidate_subject_required_context(text, match):
        return True

    if _has_hard_required_marker_context(text, match):
        return True

    if _SIMILAR_ROLE_RE.search(after):
        return True

    # A range or plus-form tied to experience is normally written as a hard
    # requirement. Optional wording is filtered before this helper is called.
    return has_plus_or_range and _EXPERIENCE_WORD_RE.search(window) is not None


def _mention_years(match: re.Match[str]) -> int | None:
    try:
        amount = int(match.group("amount"))
    except (ValueError, IndexError):
        return None

    unit = match.group("unit")
    if unit in {"mois", "month", "months"}:
        if amount < 12:
            return None
        return math.ceil(amount / 12)

    return amount


def required_min_years(text: str | None) -> int | None:
    """Return the minimum required years of experience, or None if unstated.

    Returns the SMALLEST explicit requirement found — so a job saying
    ``"3 ans minimum, 5+ ans préféré"`` returns ``3`` (the floor, not the
    ideal). Diplomas like ``Bac+5`` are stripped before matching.
    """
    if not text:
        return None

    cleaned = _DIPLOMA_LEVEL_RE.sub(" ", _normalize(text))

    years_found: list[int] = []
    for pattern in (_YEAR_MENTION_RE, _MONTH_MENTION_RE):
        for match in pattern.finditer(cleaned):
            value = _mention_years(match)
            if value is None or not 1 <= value <= 30:  # sanity bounds
                continue
            if _is_age_context(cleaned, match):
                continue

            has_plus_or_range = bool(pattern is _YEAR_MENTION_RE and match.group("modifier"))
            window = _context(cleaned, match)
            hard_required = _has_hard_required_marker_context(cleaned, match)
            candidate_subject = _has_candidate_subject_required_context(
                cleaned,
                match,
            )
            if _is_company_experience_context(window) and not (hard_required or candidate_subject):
                continue

            required = _is_candidate_required_context(
                cleaned,
                match,
                has_plus_or_range=has_plus_or_range,
            )

            if _is_preferred_or_optional_context(cleaned, match) and not hard_required:
                continue

            if required:
                years_found.append(value)
                continue

            if value > 11:
                continue

    if not years_found:
        return None
    return min(years_found)
