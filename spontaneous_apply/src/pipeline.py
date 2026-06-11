from __future__ import annotations

from spontaneous_apply.src.database import (
    connection,
    get_or_create_company,
    init_db,
    mark_company_status,
    save_wttj_profile,
)
from spontaneous_apply.src.models import CompanySeed
from spontaneous_apply.src.wttj_discovery import discover_wttj_profile


def run_for_company(company: CompanySeed | str, preverified_csv_path: str | None = None):
    init_db()
    with connection() as conn:
        company_record = get_or_create_company(conn, company)
        mark_company_status(conn, company_record.id, "wttj_searching")

        wttj_profile = discover_wttj_profile(
            company_record.company_name,
            preverified_csv_path=preverified_csv_path,
        )
        save_wttj_profile(conn, company_record.id, wttj_profile)

        if not wttj_profile.has_wttj_profile:
            mark_company_status(conn, company_record.id, "wttj_not_found")
            return wttj_profile

        mark_company_status(conn, company_record.id, "wttj_found")
        return wttj_profile

