from __future__ import annotations

import csv
import re
from pathlib import Path

from spontaneous_apply.src.models import WTTJProfile


def discover_wttj_profile(
    company_name: str,
    preverified_csv_path: str | Path | None = None,
) -> WTTJProfile:
    if preverified_csv_path:
        profile = discover_from_preverified_csv(company_name, preverified_csv_path)
        if profile.has_wttj_profile:
            return profile

    return WTTJProfile(
        company_name=company_name,
        has_wttj_profile=False,
        wttj_url=None,
        wttj_status="not_found",
        discovery_method="not_implemented",
    )


def discover_from_preverified_csv(company_name: str, csv_path: str | Path) -> WTTJProfile:
    path = Path(csv_path)
    wanted = _normalize(company_name)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_name = row.get("company_name") or row.get("name") or row.get("entreprise") or ""
            if _normalize(row_name) != wanted:
                continue

            url = (
                row.get("wttj_url")
                or row.get("welcome_to_the_jungle_url")
                or row.get("url")
                or row.get("profile_url")
            )
            has_profile = bool(url)
            return WTTJProfile(
                company_name=company_name,
                has_wttj_profile=has_profile,
                wttj_url=url or None,
                wttj_status="active_profile" if has_profile else "not_found",
                discovery_method="preverified_csv",
            )

    return WTTJProfile(
        company_name=company_name,
        has_wttj_profile=False,
        wttj_url=None,
        wttj_status="not_found",
        discovery_method="preverified_csv",
    )


def probable_wttj_slugs(company_name: str) -> list[str]:
    cleaned = company_name.lower()
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return [cleaned] if cleaned else []


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().casefold())

