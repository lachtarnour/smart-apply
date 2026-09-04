"""Score repository helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from smartapply.database.models import Application, Job, JobScore


def set_score(session: Session, job_id: int, **components: Any) -> JobScore:
    score = session.execute(select(JobScore).where(JobScore.job_id == job_id)).scalar_one_or_none()
    if score is None:
        score = JobScore(job_id=job_id, **components)
        session.add(score)
    else:
        for key, value in components.items():
            setattr(score, key, value)
    return score


def top_jobs_by_score(
    session: Session,
    k: int,
    *,
    unapplied_only: bool = False,
) -> Sequence[Job]:
    stmt = select(Job).join(JobScore).where(JobScore.final_score.is_not(None))
    if unapplied_only:
        stmt = stmt.outerjoin(Application).where(Application.id.is_(None))
    stmt = stmt.order_by(JobScore.final_score.desc()).limit(k)
    return session.execute(stmt).scalars().all()
