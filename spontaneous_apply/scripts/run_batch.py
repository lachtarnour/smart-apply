from __future__ import annotations

import argparse

from spontaneous_apply.src.company_input import load_companies
from spontaneous_apply.src.database import (
    connection,
    get_or_create_company,
    init_db,
    mark_company_status,
)
from spontaneous_apply.src.pipeline import run_for_company


def run_batch(seed_csv_path: str | None = None, preverified_csv_path: str | None = None) -> None:
    init_db()
    companies = load_companies(seed_csv_path)

    for company in companies:
        try:
            run_for_company(company, preverified_csv_path=preverified_csv_path)
        except Exception as e:
            with connection() as conn:
                record = get_or_create_company(conn, company)
                mark_company_status(conn, record.id, "failed")
            print(f"{company.company_name}: failed: {e}")
            continue


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-csv", default=None)
    parser.add_argument("--preverified-csv", default=None)
    args = parser.parse_args()
    run_batch(args.seed_csv, args.preverified_csv)


if __name__ == "__main__":
    main()

