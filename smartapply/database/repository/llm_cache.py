"""LLM cache and usage repository helpers."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from smartapply.database.models import LLMCache, LLMUsage


def cache_get(session: Session, cache_key: str) -> LLMCache | None:
    return session.execute(
        select(LLMCache).where(LLMCache.cache_key == cache_key)
    ).scalar_one_or_none()


def cache_set(
    session: Session,
    *,
    cache_key: str,
    model: str,
    response: str,
    prompt_tokens: int,
    completion_tokens: int,
    purpose: str | None = None,
) -> LLMCache:
    entry = cache_get(session, cache_key)
    if entry is not None:
        return entry
    entry = LLMCache(
        cache_key=cache_key,
        model=model,
        response=response,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        purpose=purpose,
    )
    session.add(entry)
    session.flush()
    return entry


def record_usage(
    session: Session,
    *,
    purpose: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    cached: bool = False,
    job_id: int | None = None,
) -> LLMUsage:
    usage = LLMUsage(
        purpose=purpose,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost_usd,
        cached=cached,
        job_id=job_id,
    )
    session.add(usage)
    return usage


def total_cost(session: Session) -> float:
    rows: Iterable[LLMUsage] = session.execute(select(LLMUsage)).scalars()
    return float(sum(row.cost_usd for row in rows))
