"""Extract structured sections from a cleaned job description.

Returns a dict keyed by canonical section name (responsibilities, profile,
skills, benefits, contract). Best-effort and bilingual FR/EN.
"""

from __future__ import annotations

import re

# Map canonical section -> list of regex headings that introduce it.
SECTION_PATTERNS: dict[str, list[str]] = {
    "responsibilities": [
        r"missions?", r"vos missions", r"responsabilit[ée]s",
        r"responsibilit(?:ies|y)", r"what you('?ll| will) do",
        r"key responsibilities", r"role description",
        r"qu[' ]?attend[s ]?[- ]on de toi",
    ],
    "profile": [
        r"profil(?: recherch[ée])?", r"votre profil", r"qui (?:vous )?[êe]tes",
        r"qualifications?", r"requirements?", r"required (?:knowledge|skills)",
        r"who you are", r"about you", r"we[' ]?re looking for",
    ],
    "skills": [
        r"comp[ée]tences?(?: requises| techniques)?", r"hard skills?",
        r"stack(?: technique)?", r"tech stack", r"technical skills?",
        r"environnement technique",
    ],
    "benefits": [
        r"avantages?", r"benefits?", r"perks?", r"ce que nous offrons",
        r"why (?:join|work with) us", r"what we offer",
    ],
    "contract": [
        r"conditions?", r"informations? compl[ée]mentaires?",
        r"contract", r"contrat", r"r[ée]mun[ée]ration",
    ],
}

_HEADING_LINE_RE = re.compile(
    r"^[\s>•\-*]*(?P<text>[^\n]{1,80})\s*:?\s*$"
)


def _match_heading(line: str) -> str | None:
    """Return canonical section name if the line looks like a heading we know."""
    m = _HEADING_LINE_RE.match(line.strip())
    if not m:
        return None
    candidate = m.group("text").strip().lower().rstrip(":")
    if len(candidate) > 60:
        return None
    for canonical, patterns in SECTION_PATTERNS.items():
        for p in patterns:
            if re.fullmatch(rf"{p}", candidate):
                return canonical
    return None


def extract_sections(text: str) -> dict[str, str]:
    """Best-effort extraction of canonical sections from a cleaned description."""
    if not text:
        return {}

    lines = text.splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer, current
        if current and buffer:
            joined = "\n".join(buffer).strip()
            if joined:
                sections.setdefault(current, []).append(joined)
        buffer = []

    for line in lines:
        heading = _match_heading(line)
        if heading is not None:
            flush()
            current = heading
            continue
        if current is not None:
            buffer.append(line)
    flush()

    return {key: "\n\n".join(chunks) for key, chunks in sections.items() if chunks}
