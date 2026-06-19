from __future__ import annotations

import argparse

from spontaneous_apply.src.models import CompanySeed
from spontaneous_apply.src.pipeline import run_for_company


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("company_name")
    parser.add_argument("--wttj-url", default=None)
    parser.add_argument("--preverified-csv", default=None)
    args = parser.parse_args()

    company = CompanySeed(company_name=args.company_name, wttj_url=args.wttj_url)
    result = run_for_company(company, preverified_csv_path=args.preverified_csv)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
