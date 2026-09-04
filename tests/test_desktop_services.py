"""Tests for native desktop batch workflows and offer-table data."""

from __future__ import annotations

from datetime import datetime, timezone
from threading import Barrier, get_ident
from types import SimpleNamespace

import pytest

from smartapply.database import Job, JobStatus, ShortlistOrigin, session_scope
from smartapply.database.repository import (
    create_or_get_application,
    mark_archived,
    set_analysis,
    set_score,
    set_shortlisted,
    upsert_job,
)
from smartapply.desktop.services import DesktopService
from smartapply.desktop.source_health import SourceHealth


def _job(*, external_id: str, description: str = "Description") -> int:
    with session_scope() as session:
        job = upsert_job(
            session,
            external_id=external_id,
            title="Machine Learning Engineer",
            company="Acme",
            location="Paris",
            contract_type="CDI",
            description=description,
            source="manual",
        )
        session.flush()
        return job.id


def test_profile_directory_is_created_at_the_active_location(
    tmp_path,
    monkeypatch,
) -> None:
    profile_dir = tmp_path / "profile"
    monkeypatch.setenv("PROFILE_DIR", str(profile_dir))
    from smartapply.config import get_settings

    get_settings.cache_clear()
    try:
        resolved = DesktopService.ensure_profile_directory()
    finally:
        get_settings.cache_clear()

    assert resolved == profile_dir.resolve()
    assert resolved.is_dir()


def test_job_rows_include_experience_and_application_state(isolated_db) -> None:
    job_id = _job(
        external_id="manual:table",
        description="Nous recherchons un profil avec 3+ ans d'expérience requis.",
    )
    with session_scope() as session:
        create_or_get_application(session, job_id)

    rows = DesktopService().list_jobs()

    assert len(rows) == 1
    assert rows[0].experience == "3+ ans"
    assert rows[0].application_id is not None


def test_job_detail_keeps_profile_matches_and_review_points(isolated_db) -> None:
    job_id = _job(external_id="manual:feedback")
    with session_scope() as session:
        set_analysis(
            session,
            job_id,
            role_type="Data Scientist",
            seniority="junior",
            domain="IA appliquée",
            main_tasks=[],
            required_skills=["Python"],
            nice_to_have=[],
            match_reasons=["Python et machine learning correspondent au profil."],
            risks=["Vérifier le niveau d’expérience demandé."],
            cv_keywords_to_include=["Python"],
            raw_response={},
            model_used="test",
        )
        set_score(
            session,
            job_id,
            final_score=0.89,
            components={"reasons": ["search_context:origin=personalized_matches"]},
        )

    detail = DesktopService().get_job(job_id)

    assert detail is not None
    assert detail.match_reasons == ("Python et machine learning correspondent au profil.",)
    assert detail.risks == ("Vérifier le niveau d’expérience demandé.",)
    assert detail.archive_reasons == ()


def test_archived_job_detail_shows_only_human_readable_decisive_reason(isolated_db) -> None:
    job_id = _job(external_id="manual:archived-feedback")
    with session_scope() as session:
        set_score(
            session,
            job_id,
            components={
                "rejection_stage": "local_filter",
                "rejection_reasons": [
                    "search_context:origin=personalized_matches,chips=pages=150",
                    "remote_structured:hybrid",
                    "offer_language:en",
                    "experience_structured_welcometothejungle:5",
                    "experience_required_too_high:5+ years",
                ],
            },
        )
        mark_archived(session, job_id)

    detail = DesktopService().get_job(job_id)

    assert detail is not None
    assert detail.archive_reasons == ("Expérience demandée trop élevée : au moins 5 ans",)


def test_manual_archive_records_a_clear_reason(isolated_db) -> None:
    job_id = _job(external_id="manual:user-archive")

    DesktopService().archive_job(job_id)
    detail = DesktopService().get_job(job_id)

    assert detail is not None
    assert detail.status == JobStatus.ARCHIVED
    assert detail.archive_reasons == ("Archivée manuellement",)


def test_rescue_jobs_only_reinjects_archived_selection(isolated_db) -> None:
    archived_id = _job(external_id="manual:archived")
    active_id = _job(external_id="manual:active")
    with session_scope() as session:
        mark_archived(session, archived_id)

    report = DesktopService().rescue_jobs([archived_id, archived_id, active_id, 999_999])

    assert report == {"requested": 3, "rescued": 1, "skipped": 2}
    with session_scope() as session:
        rescued = session.get(Job, archived_id)
        assert rescued is not None
        assert rescued.status == JobStatus.SHORTLISTED
        assert rescued.shortlisted_at is not None
        assert rescued.archived_at is None


def test_manual_top_selection_persists_across_service_instances(isolated_db) -> None:
    job_id = _job(external_id="manual:persistent-shortlist")

    assert DesktopService().set_job_shortlisted(job_id, selected=True) is True

    reloaded_service = DesktopService()
    detail = reloaded_service.get_job(job_id)
    summary = reloaded_service.shortlist_summary()
    top_rows = reloaded_service.list_jobs(status=JobStatus.SHORTLISTED)
    assert detail is not None and detail.shortlisted is True
    assert detail.status_label == "Top sélection"
    assert summary.total == 1
    assert summary.ready_to_generate == 1
    assert [row.id for row in top_rows] == [job_id]
    with session_scope() as session:
        persisted = session.get(Job, job_id)
        assert persisted is not None
        assert persisted.shortlist_origin == ShortlistOrigin.MANUAL

    assert reloaded_service.set_job_shortlisted(job_id, selected=False) is True
    final_detail = DesktopService().get_job(job_id)
    assert final_detail is not None
    assert final_detail.shortlisted is False
    assert final_detail.status == JobStatus.FILTERED
    assert final_detail.archive_reasons == ()


def test_top_k_preference_is_managed_and_persisted_by_the_application(isolated_db) -> None:
    service = DesktopService()

    assert service.set_top_k(12) == 12
    assert DesktopService().top_k() == 12
    assert service.set_top_k(500) == 100
    assert DesktopService().top_k() == 100


def test_generate_top_selection_ignores_non_selected_jobs(isolated_db, monkeypatch) -> None:
    first_id = _job(external_id="manual:top-first")
    second_id = _job(external_id="manual:top-second")
    outside_id = _job(external_id="manual:not-in-top")
    with session_scope() as session:
        set_shortlisted(session, first_id, selected=True)
        set_shortlisted(session, second_id, selected=True)

    analyzed_calls: list[int] = []
    generated_calls: list[int] = []

    class FakePipeline:
        def analyze_jobs(self, job_ids):
            analyzed_calls.extend(job_ids)
            return SimpleNamespace(analyzed=1, already_analyzed=0)

        def apply_to(self, job_id):
            generated_calls.append(job_id)
            return SimpleNamespace(application_id=job_id + 1000)

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    report = DesktopService().generate_shortlisted_applications()

    assert report["requested"] == 2
    assert report["generated"] == 2
    assert analyzed_calls == [first_id, second_id]
    assert generated_calls == [first_id, second_id]
    assert outside_id not in generated_calls


def test_generate_applications_analyzes_new_rows_and_skips_ineligible(
    isolated_db,
    monkeypatch,
) -> None:
    analyzed_id = _job(external_id="manual:analyzed")
    new_id = _job(external_id="manual:new")
    archived_id = _job(external_id="manual:archived-for-generation")
    existing_id = _job(external_id="manual:existing")
    with session_scope() as session:
        analyzed = session.get(Job, analyzed_id)
        assert analyzed is not None
        analyzed.analyzed_at = datetime.now(timezone.utc)
        analyzed.status = JobStatus.ANALYZED
        mark_archived(session, archived_id)
        create_or_get_application(session, existing_id)

    analyzed_calls: list[int] = []
    generated_calls: list[int] = []

    class FakePipeline:
        def analyze_jobs(self, job_ids):
            analyzed_calls.extend(job_ids)
            return SimpleNamespace(analyzed=1, already_analyzed=0)

        def apply_to(self, job_id):
            if job_id == existing_id:
                from smartapply.pipeline import ApplicationAlreadyExistsError

                raise ApplicationAlreadyExistsError(job_id)
            generated_calls.append(job_id)
            return SimpleNamespace(application_id=job_id + 1000)

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    report = DesktopService().generate_applications([analyzed_id, new_id, archived_id, existing_id])

    assert report["generated"] == 2
    assert report["skipped"] == 2
    assert report["failed"] == 0
    assert analyzed_calls == [new_id]
    assert generated_calls == [analyzed_id, new_id]


def test_generate_applications_reports_analysis_failure_details(
    isolated_db,
    monkeypatch,
) -> None:
    job_id = _job(external_id="manual:analysis-failure")

    class FakePipeline:
        def analyze_jobs(self, job_ids):
            return SimpleNamespace(
                analyzed=0,
                already_analyzed=0,
                errors=[{"job_id": job_ids[0], "message": "quota indisponible"}],
            )

        def apply_to(self, job_id):  # noqa: ARG002
            raise AssertionError("generation must not run after failed analysis")

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    report = DesktopService().generate_applications([job_id])

    assert report["generated"] == 0
    assert report["skipped"] == 0
    assert report["failed"] == 1
    assert report["errors"] == [{"job_id": job_id, "message": "Analyse : quota indisponible"}]


def test_generate_applications_returns_document_warnings(
    isolated_db,
    monkeypatch,
) -> None:
    job_id = _job(external_id="manual:generation-warning")
    with session_scope() as session:
        job = session.get(Job, job_id)
        assert job is not None
        job.analyzed_at = datetime.now(timezone.utc)
        job.status = JobStatus.ANALYZED

    class FakePipeline:
        def apply_to(self, received_job_id):
            assert received_job_id == job_id
            return SimpleNamespace(
                application_id=73,
                validation_warnings=["cv_pdf_not_generated"],
                validation_errors=[],
            )

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    report = DesktopService().generate_applications([job_id])

    assert report["generated"] == 1
    assert report["warnings"] == [
        {
            "job_id": job_id,
            "title": "Machine Learning Engineer",
            "company": "Acme",
            "message": "cv_pdf_not_generated",
        }
    ]


def test_manual_generation_returns_document_warnings(monkeypatch) -> None:
    from smartapply.pipeline import ApplyReport

    class FakePipeline:
        def ingest_text(self, *args, **kwargs):  # noqa: ARG002
            return SimpleNamespace(job_ids=[42])

        def analyze_jobs(self, job_ids):
            assert job_ids == [42]
            return SimpleNamespace(analyzed=1, already_analyzed=0)

        def apply_to(self, job_id, *, form_url):
            assert job_id == 42
            assert form_url == "https://example.test/apply"
            return ApplyReport(
                job_id=job_id,
                application_id=7,
                validation_warnings=["letter_pdf_not_generated"],
            )

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    report = DesktopService().create_manual_application(
        title="Data Scientist",
        company="Acme",
        location="Paris",
        description="Une description suffisamment complète.",
        application_url="https://example.test/apply",
    )

    assert report["application_id"] == 7
    assert report["validation_warnings"] == ["letter_pdf_not_generated"]


def test_diagnostics_use_verified_source_health(monkeypatch) -> None:
    verified = {
        "serpapi": SourceHealth(True, False, "unavailable", "Quota épuisé."),
        "francetravail": SourceHealth(False, False, "unconfigured", "Absent."),
        "linkedin": SourceHealth(True, True, "available", "Jeton valide."),
        "welcometothejungle": SourceHealth(
            True,
            False,
            "unavailable",
            "Session expirée.",
        ),
    }
    monkeypatch.setattr(
        "smartapply.desktop.services.check_source_health",
        lambda settings: verified,  # noqa: ARG005
    )

    diagnostics = DesktopService().diagnostics(check_sources=True)

    assert diagnostics.source_health == verified
    assert diagnostics.source_ready == {
        "serpapi": False,
        "francetravail": False,
        "linkedin": True,
        "welcometothejungle": False,
    }


def test_search_requires_the_location_selected_in_the_app(isolated_db) -> None:
    with pytest.raises(ValueError, match="localisation"):
        DesktopService().search_jobs(
            query="Data Scientist",
            location="   ",
            sources=["serpapi"],
            max_results=10,
            date_posted="week",
        )


def test_generate_application_lets_pipeline_validate_existing_reservation(
    isolated_db,
    monkeypatch,
) -> None:
    from smartapply.pipeline import ApplicationAlreadyExistsError

    job_id = _job(external_id="manual:single-existing")
    with session_scope() as session:
        app = create_or_get_application(session, job_id)
        application_id = app.id

    class FakePipeline:
        def apply_to(self, received_job_id):
            assert received_job_id == job_id
            raise ApplicationAlreadyExistsError(job_id, application_id)

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    with pytest.raises(ApplicationAlreadyExistsError) as exc_info:
        DesktopService().generate_application(job_id)

    assert exc_info.value.application_id == application_id


def test_search_collects_sources_in_parallel_then_persists_serially(
    isolated_db,
    monkeypatch,
) -> None:
    from smartapply.pipeline.ingest import IngestCollection, IngestReport

    rendezvous = Barrier(2, timeout=2)
    collection_threads: list[int] = []
    persistence_calls: list[tuple[str, int]] = []
    caller_thread = get_ident()

    class FakePipeline:
        def collect_source(self, source, *args, **kwargs):  # noqa: ARG002
            collection_threads.append(get_ident())
            rendezvous.wait()
            return IngestCollection(source=source, raw_jobs=[])

        def persist_collection(self, collection):
            persistence_calls.append((collection.source, get_ident()))
            return IngestReport(
                source=collection.source,
                fetched=0,
                persisted=0,
            )

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    result = DesktopService().search_jobs(
        query="Data Scientist",
        location="Paris",
        sources=["serpapi", "linkedin"],
        max_results=10,
        date_posted="week",
    )

    assert len(set(collection_threads)) == 2
    assert persistence_calls == [
        ("serpapi", caller_thread),
        ("linkedin", caller_thread),
    ]
    assert not result.errors


def test_search_propagates_cooperative_cancellation(
    isolated_db,
    monkeypatch,
) -> None:
    from smartapply.pipeline.ingest import IngestCollection, IngestReport

    class FakePipeline:
        def collect_source(self, source, *args, stop_requested=None, **kwargs):  # noqa: ARG002
            return IngestCollection(
                source=source,
                raw_jobs=[],
                cancelled=bool(stop_requested and stop_requested()),
            )

        def persist_collection(self, collection):
            return IngestReport(
                source=collection.source,
                fetched=0,
                persisted=0,
                cancelled=collection.cancelled,
            )

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    result = DesktopService().search_jobs(
        query="Data Scientist",
        location="Paris",
        sources=["serpapi", "linkedin"],
        max_results=10,
        date_posted="week",
        stop_requested=lambda: True,
    )

    assert result.cancelled is True
    assert len(result.reports) == 2


def test_search_preserves_source_warnings_for_the_interface(
    isolated_db,
    monkeypatch,
) -> None:
    from smartapply.pipeline.ingest import IngestCollection, IngestReport

    class FakePipeline:
        def collect_source(self, source, *args, **kwargs):  # noqa: ARG002
            return IngestCollection(
                source=source,
                raw_jobs=[],
                warnings=["WTTJ : une fiche était illisible."],
            )

        def persist_collection(self, collection):
            return IngestReport(
                source=collection.source,
                fetched=0,
                persisted=0,
                warnings=collection.warnings,
            )

    monkeypatch.setattr("smartapply.pipeline.Pipeline", FakePipeline)

    result = DesktopService().search_jobs(
        query="Data Scientist",
        location="France",
        sources=["welcometothejungle"],
        max_results=10,
        date_posted="week",
    )

    assert result.reports[0]["warnings"] == ["WTTJ : une fiche était illisible."]


def test_application_output_directory_is_scoped_to_selected_application(
    isolated_db,
) -> None:
    first_job_id = _job(external_id="manual:first-folder")
    second_job_id = _job(external_id="manual:second-folder")
    with session_scope() as session:
        first = create_or_get_application(session, first_job_id)
        second = create_or_get_application(session, second_job_id)
        session.flush()
        first_id = first.id
        second_id = second.id

    service = DesktopService()

    assert (
        service.application_output_directory(first_id)
        == (isolated_db / "output" / str(first_id)).resolve()
    )
    assert (
        service.application_output_directory(second_id)
        == (isolated_db / "output" / str(second_id)).resolve()
    )
    assert service.application_output_directory(999_999) is None


def test_application_output_directory_uses_persisted_document_location(
    isolated_db,
) -> None:
    job_id = _job(external_id="manual:persisted-folder")
    with session_scope() as session:
        application = create_or_get_application(session, job_id)
        application.cv_pdf_path = str(isolated_db / "output" / "custom-name" / "CV.pdf")
        session.flush()
        application_id = application.id

    assert DesktopService().application_output_directory(application_id) == (
        isolated_db / "output" / "custom-name"
    ).resolve()
