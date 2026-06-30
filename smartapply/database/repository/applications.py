"""Application repository helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from smartapply.database.models import Application, JobStatus


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
    session: Session,
    *,
    status: str | None = None,
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
    """Update the human follow-up state for one application."""
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
    if (email_sent or form_submitted) and _strategy_complete(app):
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
