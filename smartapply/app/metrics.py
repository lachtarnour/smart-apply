"""Database-backed metrics used by the Streamlit UI."""

from __future__ import annotations

from sqlalchemy import select

from smartapply.database import session_scope
from smartapply.database.models import LLMUsage
from smartapply.database.repository import list_jobs, total_cost


def total_jobs() -> int:
    with session_scope() as s:
        return len(list(list_jobs(s)))


def jobs_per_status() -> dict[str, int]:
    with session_scope() as s:
        counts: dict[str, int] = {}
        for job in list_jobs(s):
            counts[job.status] = counts.get(job.status, 0) + 1
    return counts


def total_cost_usd() -> float:
    with session_scope() as s:
        return float(total_cost(s))


def cost_by_purpose() -> dict[str, float]:
    with session_scope() as s:
        rows = s.execute(select(LLMUsage)).scalars().all()
        out: dict[str, float] = {}
        for row in rows:
            out[row.purpose] = out.get(row.purpose, 0.0) + row.cost_usd
    return out
