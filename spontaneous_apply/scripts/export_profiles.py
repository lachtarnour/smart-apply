from __future__ import annotations

import argparse
import json

from spontaneous_apply.src.database import connection, init_db
from spontaneous_apply.src.settings import get_settings


def export_profiles(output_path: str | None = None) -> None:
    init_db()
    settings = get_settings()
    path = settings.company_profiles_jsonl if output_path is None else settings._resolve(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with connection() as conn, path.open("w", encoding="utf-8") as f:
        rows = conn.execute(
            """
            SELECT structured_json
            FROM structured_company_profiles
            ORDER BY created_at, id
            """
        ).fetchall()
        for row in rows:
            payload = json.loads(row["structured_json"])
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    export_profiles(args.output)


if __name__ == "__main__":
    main()

