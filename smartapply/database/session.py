"""Engine and Session management."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Column, create_engine, inspect, text
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import Session, sessionmaker

from smartapply.config import get_settings
from smartapply.database.models import Base
from smartapply.logging_setup import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=True)


def init_db() -> None:
    """Create all tables, then add any new columns the models gained.

    The auto-migration step (``auto_migrate``) handles the dev workflow
    where the user added fields to a model after the DB was first created.
    It only does ``ALTER TABLE ADD COLUMN`` — drops/renames/type changes
    still require Alembic.
    """
    Base.metadata.create_all(get_engine())
    auto_migrate()


def drop_db() -> None:
    """Drop all tables — destructive, use only in tests."""
    Base.metadata.drop_all(get_engine())


def auto_migrate() -> list[str]:
    """Add columns present in the models but missing in the DB.

    Returns the list of SQL statements that were executed so callers can log
    them. Safe to run on every startup — when models and DB agree, it's a
    no-op single inspect() call.
    """
    engine = get_engine()
    inspector = inspect(engine)
    executed: list[str] = []

    with engine.begin() as conn:
        for table in Base.metadata.tables.values():
            if not inspector.has_table(table.name):
                continue  # create_all just made it; no ALTER needed
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                statement = _build_add_column_sql(table.name, column, engine.dialect)
                logger.info("Auto-migrate: %s", statement)
                conn.execute(text(statement))
                executed.append(statement)

    return executed


def _build_add_column_sql(table_name: str, column: Column, dialect: Dialect) -> str:
    """Render ``ALTER TABLE … ADD COLUMN …`` from a SQLAlchemy Column."""
    type_sql = column.type.compile(dialect=dialect)
    parts = [f"ALTER TABLE {table_name} ADD COLUMN {column.name} {type_sql}"]

    default_literal = _python_default_to_sql_literal(column)
    if default_literal is not None:
        parts.append(f"DEFAULT {default_literal}")

    if not column.nullable:
        # SQLite requires either a DEFAULT or the column to be nullable
        # when adding to a non-empty table. We've already added DEFAULT above
        # when the model provided one.
        parts.append("NOT NULL")

    return " ".join(parts)


def _python_default_to_sql_literal(column: Column) -> str | None:
    """Convert the model's Python default to a SQL literal."""
    default = column.default
    if default is None:
        return None
    value = getattr(default, "arg", None)
    if callable(value) or value is None:
        return None
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Provide a transactional scope around a series of operations."""
    factory = get_session_factory()
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine_cache() -> None:
    """Clear cached engine/session — useful in tests that switch DB urls."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
