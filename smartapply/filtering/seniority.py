"""Seniority and candidate-management signals."""

from __future__ import annotations

import re

from smartapply.filtering.text import matches_any_pattern

_CANDIDATE_LEADERSHIP_PATTERNS = (
    r"\bvous\s+managez\s+une\s+equipe\b",
    r"\bvous\s+managerez\s+une\s+equipe\b",
    r"\bvous\s+encadrez\s+une\s+equipe\b",
    r"\bvous\s+encadrerez\s+une\s+equipe\b",
    r"\bvous\s+piloterez\s+une\s+equipe\b",
    r"\bvous\s+pilotez\s+une\s+equipe\b",
    r"\bvous\s+dirigez\s+une\s+equipe\b",
    r"\bvous\s+dirigerez\s+une\s+equipe\b",
    r"\bvous\s+supervisez\s+une\s+equipe\b",
    r"\bvous\s+superviserez\s+une\s+equipe\b",
    r"\bresponsable\s+d[' ]?une\s+equipe\b",
    r"\bmanagement\s+d[' ]?equipe\b",
    r"\bencadrement\s+d[' ]?une\s+equipe\b",
    r"\bencadrement\s+d[' ]?equipe\b",
    r"\bleadership\s+d[' ]?equipe\b",
    r"\bresponsabilite\s+hierarchique\b",
    r"\bresponsabilite\s+manageriale\b",
    r"\bfaire\s+grandir\s+l[' ]?equipe\b",
    r"\bvous\s+serez\s+responsable\s+d[' ]?une\s+equipe\b",
    r"\byou\s+(?:will\s+)?(?:manage|lead|supervise|direct)\s+"
    r"(?:a|an|the|our)?\s*(?:data\s+|analytics\s+|ml\s+|ai\s+)?team\b",
    r"\b(?:manage|lead|supervise|direct|build\s+and\s+lead)\s+"
    r"(?:a|an|the|our)?\s*(?:data\s+|analytics\s+|ml\s+|ai\s+)?team\s+of\b",
    r"\bresponsible\s+for\s+(?:the\s+)?(?:management|leadership|supervision)\s+"
    r"of\s+(?:a|an|the)?\s*team\b",
    r"\bresponsible\s+for\s+(?:managing|leading|supervising)\s+"
    r"(?:a|an|the)?\s*team\b",
    r"\bline\s+management\s+(?:responsibility|responsibilities|of)\b",
    r"\bpeople\s+management\s+(?:responsibility|responsibilities|experience)\b",
    r"\b(?:have|with)\s+\d{1,2}\s+direct\s+reports\b",
)
_TITLE_SENIORITY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("senior", re.compile(r"(?<![a-z0-9])senior(?![a-z0-9])")),
    ("sr.", re.compile(r"(?<![a-z0-9])sr\.(?![a-z0-9])")),
    ("lead", re.compile(r"(?<![a-z0-9])lead(?![a-z0-9])")),
    ("principal", re.compile(r"(?<![a-z0-9])principal(?![a-z0-9])")),
    ("staff", re.compile(r"(?<![a-z0-9])staff(?![a-z0-9])")),
    ("responsable", re.compile(r"(?<![a-z0-9])responsable(?![a-z0-9])")),
    ("directeur", re.compile(r"(?<![a-z0-9])directeur(?![a-z0-9])")),
    ("directrice", re.compile(r"(?<![a-z0-9])directrice(?![a-z0-9])")),
    ("head of", re.compile(r"(?<![a-z0-9])head\s+of(?![a-z0-9])")),
    ("manager", re.compile(r"(?<![a-z0-9])manager(?![a-z0-9])")),
)


def has_candidate_leadership_responsibility(description: str) -> bool:
    return matches_any_pattern(description, _CANDIDATE_LEADERSHIP_PATTERNS)


def has_hidden_senior_role(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:"
            r"senior\s+(?:(?:en|dans|sur)\s+)?(?:data|donnees|analytics|"
            r"machine learning|ml|ai|ia|big data).{0,35}"
            r"(?:role|position|job|poste|profil)"
            r"|(?:poste|role|position|job|profil)\s+(?:de\s+)?senior\s+"
            r"(?:(?:en|dans|sur)\s+)?(?:data|donnees|analytics|"
            r"machine learning|ml|ai|ia|big data)"
            r"|(?:this|the)\s+(?:role|position|job)\s+(?:is|will\s+be)\s+"
            r"(?:a\s+)?senior\s+(?:data|analytics|machine learning|ml|ai|ia)"
            r"|(?:nous\s+recherchons|nous\s+recrutons|we\s+are\s+"
            r"(?:looking\s+for|hiring))\s+(?:un|une|a|an)?\s*senior\s+"
            r"(?:data|donnees|analytics|machine learning|ml|ai|ia)"
            r")\b",
            text,
        )
    )


def title_seniority_or_management_marker(
    title: str,
    configured_markers: tuple[str, ...],
) -> str | None:
    for marker, pattern in _TITLE_SENIORITY_PATTERNS:
        if pattern.search(title):
            return marker
    for marker in configured_markers:
        normalized = marker.strip()
        if normalized and normalized in title:
            return normalized
    return None
