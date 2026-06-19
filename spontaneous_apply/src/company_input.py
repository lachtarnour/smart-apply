from __future__ import annotations

import csv
from pathlib import Path

from spontaneous_apply.src.models import CompanySeed
from spontaneous_apply.src.settings import get_settings


def load_companies(seed_csv_path: str | Path | None = None) -> list[CompanySeed]:
    path = Path(seed_csv_path) if seed_csv_path else get_settings().companies_seed_csv
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [
            CompanySeed(
                company_name=(row.get("company_name") or "").strip(),
                wttj_url=_empty_to_none(row.get("wttj_url")),
                sector_hint=_empty_to_none(row.get("sector_hint")),
                spontaneous_score=_empty_to_none(row.get("spontaneous_score")),
            )
            for row in reader
            if (row.get("company_name") or "").strip()
        ]


def _empty_to_none(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None
