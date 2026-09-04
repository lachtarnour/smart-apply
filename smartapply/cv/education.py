"""Display helpers for education entries in generated CVs."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from smartapply.profile import Degree

_UNIVERSITY_OF_RE = re.compile(
    r"^\s*universit(?:e|\u00e9)\s+(?:d['\u2019]|de\s+|du\s+)",
    re.IGNORECASE,
)
_UNIVERSITY_DES_RE = re.compile(
    r"^\s*universit(?:e|\u00e9)\s+des\s+",
    re.IGNORECASE,
)
_UNIVERSITY_PREFIX_RE = re.compile(
    r"^\s*universit(?:e|\u00e9)\s+",
    re.IGNORECASE,
)
_UNIVERSITY_SUFFIX_RE = re.compile(
    r"\s+universit(?:e|\u00e9)\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EducationDisplay:
    title: str
    field: str | None
    institution: str
    url: Any | None
    start_date: str | None
    end_date: str | None
    start_year: int
    end_year: int


def english_institution_name(name: str) -> str:
    """Return an English display name for common French institution prefixes."""
    text = " ".join(name.split())
    if not text:
        return text

    match = _UNIVERSITY_DES_RE.match(text)
    if match:
        return f"University of the {text[match.end() :].strip()}"

    match = _UNIVERSITY_OF_RE.match(text)
    if match:
        return f"University of {text[match.end() :].strip()}"

    match = _UNIVERSITY_PREFIX_RE.match(text)
    if match:
        rest = text[match.end() :].strip()
        return f"{rest} University" if rest else "University"

    match = _UNIVERSITY_SUFFIX_RE.search(text)
    if match:
        return f"{text[: match.start()].rstrip()} University"

    return text


def education_entries_for_english(degrees: Iterable[Degree]) -> list[EducationDisplay]:
    """Build CV education display entries for English-language resumes."""
    return [
        EducationDisplay(
            title=degree.title,
            field=degree.field,
            institution=english_institution_name(degree.institution),
            url=degree.url,
            start_date=degree.start_date,
            end_date=degree.end_date,
            start_year=degree.start_year,
            end_year=degree.end_year,
        )
        for degree in degrees
    ]
