"""Duplicate-review and canonical-offer repository helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from smartapply.database.models import Application, Job, JobDuplicateStatus, JobStatus


def canonical_job(session: Session, job_id: int) -> Job | None:
    """Resolve a confirmed alias to its canonical offer row."""
    current = session.get(Job, job_id)
    if current is None:
        return None
    seen: set[int] = set()
    while current.canonical_job_id is not None:
        if int(current.id) in seen:
            break
        seen.add(int(current.id))
        next_job = session.get(Job, int(current.canonical_job_id))
        if next_job is None:
            break
        current = next_job
    return current


def duplicate_group_ids(session: Session, job_id: int) -> set[int]:
    """Return the canonical row, its aliases and a pending review row."""
    job = session.get(Job, job_id)
    if job is None:
        return set()

    root = canonical_job(session, job_id)
    root_id = int(root.id if root is not None else job.id)
    ids = set(
        int(value)
        for value in session.scalars(
            select(Job.id).where(
                or_(Job.id == root_id, Job.canonical_job_id == root_id)
            )
        )
    )
    root_ids = {root_id}
    if job.duplicate_review_status == JobDuplicateStatus.PENDING:
        ids.add(int(job.id))
        if job.possible_duplicate_of_id is not None:
            possible_root = canonical_job(session, int(job.possible_duplicate_of_id))
            if possible_root is not None:
                root_ids.add(int(possible_root.id))
                ids.update(
                    int(value)
                    for value in session.scalars(
                        select(Job.id).where(
                            or_(
                                Job.id == int(possible_root.id),
                                Job.canonical_job_id == int(possible_root.id),
                            )
                        )
                    )
                )

    # A root must also be protected while another review row points to it. In
    # particular, this catches an already archived application attached to a
    # later source row before the user has confirmed the alias.
    for other in session.scalars(select(Job)).all():
        if other.duplicate_review_status != JobDuplicateStatus.PENDING:
            continue
        reference_root = _pending_reference_root(session, other)
        if reference_root is not None and int(reference_root.id) in root_ids:
            ids.add(int(other.id))
    return ids


def _pending_reference_root(session: Session, job: Job) -> Job | None:
    """Follow pending references and confirmed aliases without looping."""
    current = job
    seen: set[int] = set()
    while int(current.id) not in seen:
        seen.add(int(current.id))
        if (
            current.duplicate_review_status == JobDuplicateStatus.PENDING
            and current.possible_duplicate_of_id is not None
        ):
            next_job = session.get(Job, int(current.possible_duplicate_of_id))
            if next_job is not None:
                current = next_job
                continue
        return canonical_job(session, int(current.id))
    return None


def application_for_duplicate_group(session: Session, job_id: int) -> Application | None:
    """Return any application attached to an offer or one of its aliases."""
    ids = duplicate_group_ids(session, job_id)
    if not ids:
        return None
    return session.execute(
        select(Application)
        .where(Application.job_id.in_(ids))
        .order_by(Application.updated_at.desc(), Application.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def application_ids_for_confirmed_groups(session: Session, job_ids: list[int]) -> dict[int, int]:
    """Find existing dossiers for a batch without treating pending matches as confirmed."""
    if not job_ids:
        return {}
    parents = dict(
        session.execute(
            select(Job.id, Job.canonical_job_id).where(Job.canonical_job_id.is_not(None))
        ).all()
    )

    def root_id(job_id: int) -> int:
        seen: set[int] = set()
        while job_id in parents and job_id not in seen:
            seen.add(job_id)
            job_id = parents[job_id]
        return job_id

    applications_by_root: dict[int, int] = {}
    for application_id, owner_id in session.execute(
        select(Application.id, Application.job_id).order_by(
            Application.updated_at.desc(), Application.id.desc()
        )
    ):
        applications_by_root.setdefault(root_id(owner_id), application_id)
    return {
        job_id: applications_by_root[root_id(job_id)]
        for job_id in job_ids
        if root_id(job_id) in applications_by_root
    }


def pending_duplicate_job(session: Session, job_id: int) -> Job | None:
    """Return the pending review row for an offer, if one exists."""
    job = session.get(Job, job_id)
    if job is None:
        return None
    if job.duplicate_review_status == JobDuplicateStatus.PENDING:
        return job
    return None


def pending_duplicate_for_group(session: Session, job_id: int) -> Job | None:
    """Return another pending review row attached to the same offer group."""
    root = canonical_job(session, job_id)
    if root is None:
        return None
    for job in session.scalars(
        select(Job).where(Job.duplicate_review_status == JobDuplicateStatus.PENDING)
    ):
        if int(job.id) == int(job_id):
            continue
        reference_root = _pending_reference_root(session, job)
        if reference_root is not None and int(reference_root.id) == int(root.id):
            return job
    return None


def confirm_duplicate(session: Session, job_id: int) -> Job | None:
    """Confirm a review match and turn the row into an archived alias."""
    job = pending_duplicate_job(session, job_id)
    if job is None or job.possible_duplicate_of_id is None:
        return None
    root = canonical_job(session, int(job.possible_duplicate_of_id))
    if root is None or int(root.id) == int(job.id):
        return None

    job_archived = bool(job.archived_at or job.status == JobStatus.ARCHIVED)
    root_archived = bool(root.archived_at or root.status == JobStatus.ARCHIVED)
    if not job_archived and root_archived:
        # The pending row is the only actionable offer. Promote it to the
        # canonical row and retain the archived source as an alias, so a
        # confirmed duplicate never archives the active offer by mistake.
        aliases = session.scalars(
            select(Job).where(Job.canonical_job_id == int(root.id))
        ).all()
        for alias in aliases:
            alias.canonical_job_id = int(job.id)
        root.canonical_job_id = int(job.id)
        root.possible_duplicate_of_id = None
        root.duplicate_review_status = JobDuplicateStatus.CONFIRMED
        root.duplicate_match_type = job.duplicate_match_type or "fuzzy"
        root.duplicate_confidence = job.duplicate_confidence
        root.shortlisted_at = None
        root.shortlist_origin = None
        root.status = JobStatus.ARCHIVED
        root.archived_at = root.archived_at or datetime.now(timezone.utc)

        job.canonical_job_id = None
        job.possible_duplicate_of_id = None
        job.duplicate_review_status = JobDuplicateStatus.CONFIRMED
        return job

    job.canonical_job_id = int(root.id)
    job.possible_duplicate_of_id = None
    job.duplicate_review_status = JobDuplicateStatus.CONFIRMED
    job.archived_at = job.archived_at or datetime.now(timezone.utc)
    job.shortlisted_at = None
    job.shortlist_origin = None
    job.status = JobStatus.ARCHIVED
    return job


def reject_duplicate(session: Session, job_id: int) -> Job | None:
    """Reject a review match and release the row as an independent offer."""
    job = pending_duplicate_job(session, job_id)
    if job is None:
        return None
    was_archived = bool(job.archived_at or job.status == JobStatus.ARCHIVED)
    job.possible_duplicate_of_id = None
    job.duplicate_review_status = JobDuplicateStatus.REJECTED
    if was_archived:
        # A rejected match must not resurrect an offer that was already
        # archived before it entered the duplicate-review queue.
        job.status = JobStatus.ARCHIVED
        return job
    job.archived_at = None
    job.shortlisted_at = None
    job.shortlist_origin = None
    job.status = (
        JobStatus.ANALYZED
        if job.analyzed_at is not None
        else JobStatus.FILTERED
        if job.filtered_at is not None
        else JobStatus.SCRAPED
    )
    return job
