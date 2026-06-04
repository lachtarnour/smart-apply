"""Tests for the database module — models, session, repository."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Each test gets a fresh SQLite file."""
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    # Force settings reload
    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import reset_engine_cache
    reset_engine_cache()

    from smartapply.database.session import init_db
    init_db()
    yield
    reset_engine_cache()
    get_settings.cache_clear()


def test_init_creates_all_tables() -> None:
    from sqlalchemy import inspect

    from smartapply.database.session import get_engine

    insp = inspect(get_engine())
    tables = set(insp.get_table_names())
    expected = {
        "jobs",
        "job_scores",
        "job_analyses",
        "job_embeddings",
        "contacts",
        "applications",
        "generated_documents",
        "llm_cache",
        "llm_usage",
    }
    assert expected.issubset(tables)


def test_upsert_job_inserts_then_updates() -> None:
    from smartapply.database import session_scope
    from smartapply.database.repository import upsert_job

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="serpapi:abc",
            title="Data Scientist",
            company="Acme",
            description="desc",
            source="serpapi",
        )
        first_id = job.id

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="serpapi:abc",
            title="Data Scientist Senior",
            description="updated",
        )
        assert job.id == first_id
        assert job.title == "Data Scientist Senior"
        assert job.company == "Acme"


def test_score_and_top_jobs() -> None:
    from smartapply.database import session_scope
    from smartapply.database.repository import set_score, top_jobs_by_score, upsert_job

    with session_scope() as s:
        for i, score in enumerate([0.3, 0.9, 0.6]):
            j = upsert_job(
                s,
                external_id=f"manual:{i}",
                title=f"Title {i}",
                company="Acme",
                description="desc",
                source="manual",
            )
            set_score(s, j.id, final_score=score)

    with session_scope() as s:
        top = top_jobs_by_score(s, k=2)
        scores = [j.score.final_score for j in top]
        assert scores == [0.9, 0.6]


def test_contact_and_application_flow() -> None:
    from smartapply.database import session_scope
    from smartapply.database.repository import (
        add_contact,
        add_document,
        create_or_get_application,
        update_application_tracking,
        upsert_job,
    )

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="manual:42",
            title="ML Engineer",
            company="Acme",
            description="desc",
            source="manual",
        )
        contact = add_contact(s, company="Acme", email="jobs@acme.example", confidence=0.8)
        app = create_or_get_application(s, job.id)
        app.contact_id = contact.id
        add_document(s, app.id, doc_type="cv_docx", path="/tmp/cv.docx")
        add_document(s, app.id, doc_type="email_body", content="Hello,")

        # idempotent
        same = create_or_get_application(s, job.id)
        assert same.id == app.id
        assert len(app.documents) == 2

        tracked = update_application_tracking(
            s,
            app.id,
            status="sent",
            notes="Relancer dans une semaine.",
        )
        assert tracked.status == "sent"
        assert tracked.job.status == "sent"
        assert tracked.notes == "Relancer dans une semaine."


def test_contact_lookup_cache_upsert_reuses_unique_key() -> None:
    from datetime import datetime, timezone

    from smartapply.database import session_scope
    from smartapply.database.repository import upsert_contact_lookup_cache

    with session_scope() as s:
        first = upsert_contact_lookup_cache(
            s,
            provider_key="anymailfinder",
            lookup_key="company:acme|loc:paris",
            company="Acme",
            domain=None,
            application_url=None,
            status="miss",
            contacts=[],
            expires_at=datetime.now(timezone.utc),
        )
        second = upsert_contact_lookup_cache(
            s,
            provider_key="anymailfinder",
            lookup_key="company:acme|loc:paris",
            company="Acme SAS",
            domain="acme.example",
            application_url="https://acme.example/jobs",
            status="hit",
            contacts=[{"email": "jobs@acme.example"}],
            expires_at=datetime.now(timezone.utc),
        )

        assert second.id == first.id
        assert second.company == "Acme SAS"
        assert second.status == "hit"
        assert second.contacts == [{"email": "jobs@acme.example"}]


def test_upsert_document_replaces_stale_duplicate_rows() -> None:
    from smartapply.database import session_scope
    from smartapply.database.models import GeneratedDocument
    from smartapply.database.repository import (
        add_document,
        create_or_get_application,
        upsert_document,
        upsert_job,
    )

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="manual:doc-upsert",
            title="ML Engineer",
            company="Acme",
            description="desc",
            source="manual",
        )
        app = create_or_get_application(s, job.id)
        add_document(s, app.id, doc_type="cv_pdf", path="/tmp/old-1.pdf")
        add_document(s, app.id, doc_type="cv_pdf", path="/tmp/old-2.pdf")
        upsert_document(s, app.id, doc_type="cv_pdf", path="/tmp/new.pdf")
        app_id = app.id

    with session_scope() as s:
        docs = (
            s.query(GeneratedDocument)
            .filter(
                GeneratedDocument.application_id == app_id,
                GeneratedDocument.doc_type == "cv_pdf",
            )
            .all()
        )
        assert len(docs) == 1
        assert docs[0].path == "/tmp/new.pdf"


def test_llm_cache_and_usage() -> None:
    from smartapply.database import session_scope
    from smartapply.database.repository import cache_get, cache_set, record_usage, total_cost

    with session_scope() as s:
        entry = cache_set(
            s,
            cache_key="k1",
            model="gpt-4o-mini",
            response='{"ok":true}',
            prompt_tokens=10,
            completion_tokens=20,
            purpose="job_analysis",
        )
        assert entry.id is not None
        record_usage(
            s,
            purpose="job_analysis",
            model="gpt-4o-mini",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0001,
        )
        record_usage(
            s,
            purpose="cv_adaptation",
            model="gpt-4o",
            prompt_tokens=100,
            completion_tokens=200,
            cost_usd=0.01,
            cached=True,
        )

    with session_scope() as s:
        cached = cache_get(s, "k1")
        assert cached is not None
        assert cached.response == '{"ok":true}'
        assert round(total_cost(s), 6) == round(0.0001 + 0.01, 6)


def test_mark_email_sent_auto_promotes_status_for_email_only_strategy() -> None:
    """An email_only application is fully sent once email_sent_at is set."""
    from smartapply.database import session_scope
    from smartapply.database.models import JobStatus
    from smartapply.database.repository import (
        create_or_get_application,
        update_application_tracking,
        upsert_job,
    )

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="manual:strat-email",
            title="Data Scientist",
            company="SmallCo",
            description="...",
            source="manual",
        )
        app = create_or_get_application(s, job.id)
        app.application_strategy = "email_only"
        app_id = app.id

    with session_scope() as s:
        update_application_tracking(s, app_id, email_sent=True)

    with session_scope() as s:
        from smartapply.database.models import Application

        app = s.get(Application, app_id)
        assert app.email_sent_at is not None
        assert app.status == JobStatus.SENT


def test_email_and_form_strategy_needs_both_actions_for_sent() -> None:
    """Large company: email alone is NOT enough — form submission also required."""
    from smartapply.database import session_scope
    from smartapply.database.models import Application, JobStatus
    from smartapply.database.repository import (
        create_or_get_application,
        update_application_tracking,
        upsert_job,
    )

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="manual:strat-both",
            title="Data Scientist",
            company="BigCorp",
            description="...",
            source="manual",
        )
        app = create_or_get_application(s, job.id)
        app.application_strategy = "email_and_form"
        app_id = app.id

    # Only email sent so far — not done
    with session_scope() as s:
        update_application_tracking(s, app_id, email_sent=True)
    with session_scope() as s:
        app = s.get(Application, app_id)
        assert app.email_sent_at is not None
        assert app.form_submitted_at is None
        assert app.status != JobStatus.SENT

    # Now also submit via form — done
    with session_scope() as s:
        update_application_tracking(s, app_id, form_submitted=True)
    with session_scope() as s:
        app = s.get(Application, app_id)
        assert app.form_submitted_at is not None
        assert app.status == JobStatus.SENT


def test_form_only_strategy_completes_with_form_submitted() -> None:
    from smartapply.database import session_scope
    from smartapply.database.models import Application, JobStatus
    from smartapply.database.repository import (
        create_or_get_application,
        update_application_tracking,
        upsert_job,
    )

    with session_scope() as s:
        job = upsert_job(
            s,
            external_id="manual:strat-form",
            title="Data Scientist",
            company="NoContactCo",
            description="...",
            source="manual",
        )
        app = create_or_get_application(s, job.id)
        app.application_strategy = "form_only"
        app_id = app.id

    with session_scope() as s:
        update_application_tracking(s, app_id, form_submitted=True)

    with session_scope() as s:
        app = s.get(Application, app_id)
        assert app.status == JobStatus.SENT


def test_auto_migrate_adds_missing_columns(tmp_path, monkeypatch) -> None:
    """When the model gains a column, init_db() should add it to existing DBs.

    We don't use SQLite ``DROP COLUMN`` (unsupported on some builds).
    Instead, we hand-craft a minimal pre-migration ``applications`` table
    and verify ``auto_migrate`` brings it up to spec.
    """
    db_path = tmp_path / "auto_migrate_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import reset_engine_cache
    reset_engine_cache()

    from sqlalchemy import create_engine, inspect, text

    # 1. Manually craft a minimal "legacy" applications table that lacks the
    #    new columns added later in development.
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE applications (
                    id INTEGER PRIMARY KEY,
                    job_id INTEGER NOT NULL,
                    status VARCHAR(50) DEFAULT 'analyzed' NOT NULL,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )
        )
    engine.dispose()

    # 2. init_db() should call create_all() (no-op on the existing table)
    #    AND auto_migrate() (adds the missing columns).
    from smartapply.database import get_engine, init_db

    reset_engine_cache()
    init_db()

    # 3. Verify the new columns now exist
    insp = inspect(get_engine())
    cols = {c["name"] for c in insp.get_columns("applications")}
    for expected_col in (
        "application_strategy",
        "form_submission_url",
        "email_sent_at",
        "form_submitted_at",
        "cv_docx_path",
        "cv_pdf_path",
        "email_subject",
        "email_body",
        "notes",
    ):
        assert expected_col in cols, f"missing column after auto_migrate: {expected_col}"

    # 4. Re-running init_db is a no-op (idempotent)
    from smartapply.database.session import auto_migrate

    assert auto_migrate() == []

    reset_engine_cache()
    get_settings.cache_clear()


def test_job_status_constants_unique() -> None:
    from smartapply.database.models import JobStatus

    statuses = [
        getattr(JobStatus, n) for n in dir(JobStatus) if n.isupper() and not n.startswith("_")
    ]
    assert len(set(statuses)) == len(statuses)
