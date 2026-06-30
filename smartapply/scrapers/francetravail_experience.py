"""France Travail experience normalization helpers."""

from __future__ import annotations

import re
from typing import Any

from unidecode import unidecode

_EXPERIENCE_DURATION_RE = re.compile(
    r"\b(?P<amount>\d{1,3})\s*"
    r"(?P<unit>an(?:\(s\)|s)?|annee(?:\(s\)|s)?|mois|years?|months?)"
    r"(?=\W|$)",
    re.IGNORECASE,
)

_EXPERIENCE_REQUIRED_CODES = {"e", "exige", "exigee", "obligatoire", "required"}
_EXPERIENCE_PREFERRED_CODES = {"s", "souhaite", "souhaitee", "preferred"}
_EXPERIENCE_NOT_REQUIRED_CODES = {
    "d",
    "debutant accepte",
    "aucune experience",
    "non exige",
    "non exigee",
}

def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", unidecode(str(value or "")).strip().lower())


def _experience_requirement(raw_value: Any, label: str | None) -> tuple[bool | None, str]:
    if isinstance(raw_value, bool):
        return raw_value, "required" if raw_value else "not_required"

    raw_norm = _norm(raw_value).strip(" .:-")
    label_norm = _norm(label)
    haystack = " ".join(part for part in (raw_norm, label_norm) if part)

    if raw_norm in _EXPERIENCE_NOT_REQUIRED_CODES or any(
        marker in haystack
        for marker in ("debutant accepte", "aucune experience", "sans experience")
    ):
        return False, "beginner_accepted"

    if raw_norm in _EXPERIENCE_PREFERRED_CODES or any(
        marker in haystack for marker in ("souhaite", "apprecie", "preferred")
    ):
        return False, "preferred"

    if raw_norm in _EXPERIENCE_REQUIRED_CODES or any(
        marker in haystack for marker in ("exige", "obligatoire", "required", "demandee")
    ):
        return True, "required"

    if label_norm and _EXPERIENCE_DURATION_RE.search(label_norm):
        return True, "required"

    return None, "unspecified"


def _parse_experience_duration(*values: str | None) -> dict[str, Any]:
    for value in values:
        if not value:
            continue
        match = _EXPERIENCE_DURATION_RE.search(_norm(value))
        if not match:
            continue
        amount = int(match.group("amount"))
        raw_unit = match.group("unit")
        unit = "months" if raw_unit.startswith(("mois", "month")) else "years"
        min_months = amount if unit == "months" else amount * 12
        min_years: int | float = (
            amount if unit == "years" else round(min_months / 12, 2)
        )
        return {
            "amount": amount,
            "unit": unit,
            "min_months": min_months,
            "min_years": min_years,
        }
    return {}


def _extract_experience(raw: dict[str, Any]) -> dict[str, Any] | None:
    raw_required = raw.get("experienceExige")
    label = _clean_text(raw.get("experienceLibelle"))
    comment = _clean_text(raw.get("experienceCommentaire"))

    if raw_required is None and not label and not comment:
        return None

    required, requirement = _experience_requirement(raw_required, label)
    experience: dict[str, Any] = {"requirement": requirement}
    if required is not None:
        experience["required"] = required
    if label:
        experience["label"] = label
    if comment:
        experience["comment"] = comment
    experience.update(_parse_experience_duration(label, comment))
    return experience


def _format_experience_duration(experience: dict[str, Any]) -> str | None:
    amount = experience.get("amount")
    unit = experience.get("unit")
    min_months = experience.get("min_months")
    if not isinstance(amount, int) or unit not in {"years", "months"}:
        return None
    if unit == "years":
        suffix = "an" if amount == 1 else "ans"
        return f"{amount} {suffix} d'expérience"
    if isinstance(min_months, int) and min_months >= 60:
        years = min_months // 12
        suffix = "an" if years == 1 else "ans"
        return f"{years} {suffix} d'expérience ({min_months} mois)"
    suffix = "mois"
    return f"{amount} {suffix} d'expérience"


def _format_experience_section(experience: dict[str, Any] | None) -> str | None:
    if not experience:
        return None

    requirement = experience.get("requirement")
    if requirement == "required":
        prefix = "Expérience demandée"
    elif requirement == "preferred":
        prefix = "Expérience souhaitée"
    else:
        prefix = "Expérience"

    duration = _format_experience_duration(experience)
    label = experience.get("label")
    comment = experience.get("comment")
    details: list[str] = []
    if duration:
        details.append(duration)
        if comment:
            details.append(str(comment))
    elif label:
        details.append(str(label))
        if comment and _norm(comment) not in _norm(label):
            details.append(str(comment))
    elif comment:
        details.append(str(comment))

    if not details:
        return None
    return f"{prefix}: {' - '.join(details)}"


