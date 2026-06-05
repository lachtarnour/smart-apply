"""High-level repository helpers — keep SQLAlchemy quirks out of the pipeline."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from smartapply.database.models import (
    Application,
    Contact,
    ContactLookupCache,
    GeneratedDocument,
    Job,
    JobAnalysis,
    JobScore,
    JobStatus,
    LLMCache,
    LLMUsage,
)


# -------------------------- Jobs --------------------------

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


# -------------------------- Per-phase pending queries --------------------------
# These derive what's left to do from the per-phase timestamps instead of the
# status enum. They survive partial runs cleanly: a filter_pending() followed
# by a process_pending() correctly picks up where the first stopped.

def list_pending_processing(session: Session) -> Sequence[Job]:
    """All non-archived jobs that still have work left in the pipeline.

    The processor uses this single query then routes each job to the right
    phase by inspecting its per-phase timestamps. Archived jobs are
    excluded — they're terminal.
    """
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
        from smartapply.database.models import JobStatus
        job.archived_at = datetime.now(timezone.utc)
        job.status = JobStatus.ARCHIVED


# -------------------------- Scores --------------------------

def set_score(session: Session, job_id: int, **components: Any) -> JobScore:
    score = session.execute(select(JobScore).where(JobScore.job_id == job_id)).scalar_one_or_none()
    if score is None:
        score = JobScore(job_id=job_id, **components)
        session.add(score)
    else:
        for key, value in components.items():
            setattr(score, key, value)
    return score


def top_jobs_by_score(session: Session, k: int) -> Sequence[Job]:
    stmt = (
        select(Job)
        .join(JobScore)
        .where(JobScore.final_score.is_not(None))
        .order_by(JobScore.final_score.desc())
        .limit(k)
    )
    return session.execute(stmt).scalars().all()


# -------------------------- Analyses --------------------------

def set_analysis(session: Session, job_id: int, **fields: Any) -> JobAnalysis:
    existing = session.execute(
        select(JobAnalysis).where(JobAnalysis.job_id == job_id)
    ).scalar_one_or_none()
    if existing is None:
        analysis = JobAnalysis(job_id=job_id, **fields)
        session.add(analysis)
        return analysis
    for key, value in fields.items():
        setattr(existing, key, value)
    return existing


# -------------------------- Contacts --------------------------

def add_contact(
    session: Session, *, company: str, email: str, **fields: Any
) -> Contact:
    existing = session.execute(
        select(Contact).where(Contact.company == company, Contact.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        for key, value in fields.items():
            if value is not None:
                setattr(existing, key, value)
        return existing
    contact = Contact(company=company, email=email, **fields)
    session.add(contact)
    session.flush()
    return contact


def find_contacts_for(session: Session, company: str) -> Sequence[Contact]:
    stmt = select(Contact).where(Contact.company == company).order_by(Contact.confidence.desc())
    return session.execute(stmt).scalars().all()


def get_contact_lookup_cache(
    session: Session,
    *,
    provider_key: str,
    lookup_key: str,
) -> ContactLookupCache | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(ContactLookupCache)
        .where(ContactLookupCache.provider_key == provider_key)
        .where(ContactLookupCache.lookup_key == lookup_key)
        .where(
            or_(
                ContactLookupCache.expires_at.is_(None),
                ContactLookupCache.expires_at >= now,
            )
        )
    )
    return session.execute(stmt).scalar_one_or_none()


def upsert_contact_lookup_cache(
    session: Session,
    *,
    provider_key: str,
    lookup_key: str,
    company: str,
    domain: str | None,
    application_url: str | None,
    status: str,
    contacts: Any | None,
    expires_at: datetime | None,
) -> ContactLookupCache:
    existing = session.execute(
        select(ContactLookupCache)
        .where(ContactLookupCache.provider_key == provider_key)
        .where(ContactLookupCache.lookup_key == lookup_key)
    ).scalar_one_or_none()
    fields = {
        "company": company,
        "domain": domain,
        "application_url": application_url,
        "status": status,
        "contacts": contacts,
        "checked_at": datetime.now(timezone.utc),
        "expires_at": expires_at,
    }
    if session.get_bind().dialect.name == "sqlite":
        stmt = (
            sqlite_insert(ContactLookupCache)
            .values(provider_key=provider_key, lookup_key=lookup_key, **fields)
            .on_conflict_do_update(
                index_elements=["provider_key", "lookup_key"],
                set_=fields,
            )
        )
        session.execute(stmt)
        session.flush()
        if existing is not None:
            session.refresh(existing)
            return existing
        return session.execute(
            select(ContactLookupCache)
            .where(ContactLookupCache.provider_key == provider_key)
            .where(ContactLookupCache.lookup_key == lookup_key)
        ).scalar_one()
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing
    entry = ContactLookupCache(
        provider_key=provider_key,
        lookup_key=lookup_key,
        **fields,
    )
    session.add(entry)
    session.flush()
    return entry


# -------------------------- Applications --------------------------

def create_or_get_application(session: Session, job_id: int) -> Application:
    existing = session.execute(
        select(Application).where(Application.job_id == job_id)
    ).scalar_one_or_none()
    if existing:
        return existing
    app = Application(job_id=job_id, status=JobStatus.ANALYZED)
    session.add(app)
    session.flush()
    return app


def list_applications(
    session: Session, *, status: str | None = None
) -> Sequence[Application]:
    stmt = select(Application).order_by(Application.updated_at.desc())
    if status:
        stmt = stmt.where(Application.status == status)
    return session.execute(stmt).scalars().all()


def update_application_tracking(
    session: Session,
    application_id: int,
    *,
    status: str | None = None,
    notes: str | None = None,
    email_sent: bool = False,
    form_submitted: bool = False,
) -> Application:
    """Update the human follow-up state for one application.

    ``email_sent`` / ``form_submitted`` flip the corresponding timestamp to
    ``utcnow``. Once both required actions for the application's strategy
    are recorded, the status auto-promotes to ``SENT``.
    """
    app = session.get(Application, application_id)
    if app is None:
        raise ValueError(f"Application {application_id} not found")
    if status is not None:
        app.status = status
        if app.job is not None:
            app.job.status = status
    if notes is not None:
        app.notes = notes
    now = datetime.now(timezone.utc)
    if email_sent:
        app.email_sent_at = now
    if form_submitted:
        app.form_submitted_at = now
    if email_sent or form_submitted:
        if _strategy_complete(app):
            app.status = JobStatus.SENT
            if app.job is not None:
                app.job.status = JobStatus.SENT
    return app


def _strategy_complete(app: Application) -> bool:
    """Return True when every action required by ``application_strategy`` is done."""
    strategy = app.application_strategy or "email_only"
    if strategy == "email_only":
        return app.email_sent_at is not None
    if strategy == "form_only":
        return app.form_submitted_at is not None
    if strategy == "email_and_form":
        return app.email_sent_at is not None and app.form_submitted_at is not None
    return False


def add_document(
    session: Session, application_id: int, doc_type: str, **fields: Any
) -> GeneratedDocument:
    doc = GeneratedDocument(application_id=application_id, doc_type=doc_type, **fields)
    session.add(doc)
    session.flush()
    return doc


def upsert_document(
    session: Session, application_id: int, doc_type: str, **fields: Any
) -> GeneratedDocument:
    """Create or replace the single current document of a given type.

    Re-generating an application should update paths/content instead of
    accumulating stale duplicate rows. If old duplicates already exist, keep
    the first one and remove the rest.
    """
    docs = session.execute(
        select(GeneratedDocument)
        .where(GeneratedDocument.application_id == application_id)
        .where(GeneratedDocument.doc_type == doc_type)
        .order_by(GeneratedDocument.id.asc())
    ).scalars().all()
    if not docs:
        return add_document(session, application_id, doc_type=doc_type, **fields)
    current = docs[0]
    for key, value in fields.items():
        setattr(current, key, value)
    for stale in docs[1:]:
        session.delete(stale)
    session.flush()
    return current


# -------------------------- LLM Cache / Usage --------------------------

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
