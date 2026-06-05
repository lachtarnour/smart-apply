"""Text helpers for deterministic filtering rules."""

from __future__ import annotations

import re

from unidecode import unidecode


def norm(s: str | None) -> str:
    return unidecode(s or "").lower()


def contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    for token in tokens:
        if len(token) <= 3 and token.isalnum():
            if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", text):
                return True
        elif token in text:
            return True
    return False


def has_word(text: str, marker: str) -> bool:
    return bool(
        re.search(
            rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])",
            text,
        )
    )


def matches_any_pattern(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)
