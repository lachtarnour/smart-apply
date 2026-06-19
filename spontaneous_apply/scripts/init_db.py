from __future__ import annotations

from spontaneous_apply.src.database import init_db


def main() -> None:
    db_path = init_db()
    print(f"Initialized database: {db_path}")


if __name__ == "__main__":
    main()

