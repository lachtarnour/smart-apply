"""Job repository helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from smartapply.database.models import Job, JobScore, JobStatus


def upsert_job(session: Session, *, external_id: str, **fields: Any) -> Job:
    """Insert or update a job by external_id. Returns the persisted instance."""
    job = session.execute(select(Job).where(Job.external_id == external_id)).scalar_one_or_none()
    if job is None:
        job = Job(external_id=external_id, **fields)
        session.add(job)
        session.flush()
        return job
    for key, value in fields.items():
        if value is not None:
            setattr(job, key, value)
    return job


def get_job_by_external_id(session: Session, external_id: str) -> Job | None:
    return session.execute(
        select(Job).where(Job.external_id == external_id)
    ).scalar_one_or_none()


def get_known_external_ids(session: Session, source: str) -> set[str]:
    """Return every ``external_id`` already persisted for ``source``."""
    rows = session.execute(select(Job.external_id).where(Job.source == source)).scalars()
    return {row for row in rows if row}


def list_known_jobs(session: Session) -> Sequence[Job]:
    """Return every job already persisted in the database."""
    return session.execute(select(Job)).scalars().all()


def list_jobs(
    session: Session,
    *,
    status: str | None = None,
    source: str | None = None,
    limit: int | None = None,
) -> Sequence[Job]:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    if source:
        stmt = stmt.where(Job.source == source)
    stmt = stmt.order_by(Job.scraped_at.desc())
    if limit:
        stmt = stmt.limit(limit)
    return session.execute(stmt).scalars().all()


def update_status(session: Session, job_id: int, status: str) -> None:
    job = session.get(Job, job_id)
    if job is not None:
        job.status = status


def list_pending_processing(session: Session) -> Sequence[Job]:
    """All non-archived jobs that still have work left in the pipeline."""
    stmt = (
        select(Job)
        .where(Job.archived_at.is_(None))
        .where(Job.analyzed_at.is_(None))
        .order_by(Job.scraped_at.desc())
    )
    return session.execute(stmt).scalars().all()


def mark_filtered(session: Session, job_id: int) -> None:
    job = session.get(Job, job_id)
    if job is not None:
        job.filtered_at = datetime.now(timezone.utc)


def mark_ranked(session: Session, job_id: int) -> None:
    job = session.get(Job, job_id)
    if job is not None:
        job.ranked_at = datetime.now(timezone.utc)


def mark_analyzed(session: Session, job_id: int) -> None:
    job = session.get(Job, job_id)
    if job is not None:
        job.analyzed_at = datetime.now(timezone.utc)


def mark_archived(session: Session, job_id: int) -> None:
    """Mark archived in both the timestamp and the legacy status enum."""
    job = session.get(Job, job_id)
    if job is not None:
        job.archived_at = datetime.now(timezone.utc)
        job.status = JobStatus.ARCHIVED


def rescue_archived_job(
    session: Session,
    job_id: int,
    *,
    justification: str | None = None,
) -> Job | None:
    """Re-inject a previously archived job into the workflow at top rank."""
    from smartapply.database.repository.scores import set_score

    job = session.get(Job, job_id)
    if job is None:
        return None

    now = datetime.now(timezone.utc)
    previous_score = session.execute(
        select(JobScore).where(JobScore.job_id == job_id)
    ).scalar_one_or_none()
    previous_components: dict[str, Any] = (
        dict(previous_score.components)
        if previous_score is not None and previous_score.components
        else {}
    )

    job.archived_at = None
    job.analyzed_at = None
    job.filtered_at = now
    job.ranked_at = now
    job.status = JobStatus.SHORTLISTED

    audit: dict[str, Any] = {
        "manual_rescue": True,
        "rescued_at": now.isoformat(),
        "justification": (justification or "").strip(),
        "previous_rejection": {
            "stage": previous_components.get("rejection_stage"),
            "reasons": list(previous_components.get("rejection_reasons", []) or []),
            "summary": previous_components.get("rejection_summary"),
        },
    }
    set_score(
        session,
        job_id,
        rule_based_score=1.0,
        semantic_score=1.0,
        skill_score=1.0,
        title_score=1.0,
        seniority_score=1.0,
        location_score=1.0,
        domain_score=1.0,
        final_score=1.0,
        components=audit,
    )
    return job
