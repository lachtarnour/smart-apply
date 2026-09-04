"""Shared helpers for source fact builders."""

from __future__ import annotations

import math
from typing import Any

from smartapply.filtering.text import norm


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = norm(value)
    if normalized in {"true", "1", "yes", "required", "exige", "exigee", "e"}:
        return True
    if normalized in {"false", "0", "no", "not_required", "debutant accepte", "d"}:
        return False
    return None


def _coerce_years(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        years = float(value)
    else:
        try:
            years = float(str(value).replace(",", "."))
        except ValueError:
            return None
    if not math.isfinite(years) or years < 0:
        return None
    return years


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _format_years(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)
