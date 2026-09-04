"""UI-agnostic application services for the desktop client."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import joinedload

from smartapply.config import ENV_FILE, get_settings
from smartapply.database import init_db, session_scope
from smartapply.database.models import (
    Application,
    AppSetting,
    GeneratedDocument,
    Job,
    JobStatus,
    ShortlistOrigin,
)
from smartapply.database.repository import (
    mark_archived,
    rescue_archived_job,
    set_score,
    set_shortlisted,
    update_application_tracking,
)
from smartapply.desktop.source_health import (
    SourceHealth,
    check_source_health,
    pending_source_health,
)
from smartapply.jobsearch.archive_reasons import archive_reason_labels
from smartapply.jobsearch.status import STATUS_FLOW, status_label
from smartapply.jobsearch.workflow import next_action_for
from smartapply.profile import get_profile
from smartapply.utils.experience import required_min_years


def _date_text(value: datetime | None, *, with_time: bool = False) -> str:
    if value is None:
        return "—"
    return value.strftime("%d/%m/%Y · %H:%M" if with_time else "%d/%m/%Y")


def _text_list(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value if str(item).strip())


def _desktop_next_action(status: str, updated_at: datetime | None) -> str:
    if status == JobStatus.READY_FOR_FORM_SUBMISSION:
        return "Relire le CV et la lettre"
    return next_action_for(status, updated_at)


@dataclass(frozen=True)
class DashboardApplication:
    id: int
    company: str
    title: str
    status: str
    status_label: str
    next_action: str
    updated_at: str


@dataclass(frozen=True)
class DashboardSnapshot:
    jobs: int
    pending: int
    ready: int
    review: int
    sent: int
    analyzed: int
    llm_cost_usd: float
    recent: tuple[DashboardApplication, ...] = ()


@dataclass(frozen=True)
class JobRow:
    id: int
    company: str
    title: str
    location: str
    source: str
    status: str
    status_label: str
    filter_disposition: str
    score: float | None
    contract: str
    experience: str
    shortlisted: bool
    application_id: int | None
    scraped_at: str


@dataclass(frozen=True)
class JobDetail(JobRow):
    remote: str = ""
    url: str = ""
    description: str = ""
    role_type: str = ""
    domain: str = ""
    seniority: str = ""
    match_reasons: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    archive_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShortlistSummary:
    total: int
    ready_to_generate: int


@dataclass(frozen=True)
class ApplicationRow:
    id: int
    job_id: int
    company: str
    title: str
    status: str
    status_label: str
    next_action: str
    updated_at: str


@dataclass(frozen=True)
class ApplicationDetail(ApplicationRow):
    location: str = ""
    source: str = ""
    job_url: str = ""
    form_url: str = ""
    letter_subject: str = ""
    letter_body: str = ""
    notes: str = ""
    form_submitted_at: str = ""
    cv_docx_path: str = ""
    cv_pdf_path: str = ""
    letter_pdf_path: str = ""
    match_reasons: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def output_directory(self) -> str:
        for raw in (
            self.cv_pdf_path,
            self.cv_docx_path,
            self.letter_pdf_path,
        ):
            if raw:
                return str(Path(raw).expanduser().resolve().parent)
        return ""


@dataclass(frozen=True)
class ProfileSnapshot:
    name: str
    title: str
    location: str
    email: str
    summary: str
    target_roles: tuple[str, ...]
    contracts: tuple[str, ...]
    remote_policies: tuple[str, ...]
    accepted_job_languages: tuple[str, ...]
    skill_categories: tuple[tuple[str, tuple[str, ...]], ...]
    experiences: int
    projects: int
    education: int
    profile_dir: str


@dataclass(frozen=True)
class RuntimeDiagnostics:
    database_url: str
    database_path: str
    database_exists: bool
    output_dir: str
    profile_dir: str
    env_file: str
    llm_provider: str
    llm_model: str
    source_ready: dict[str, bool]
    source_health: dict[str, SourceHealth]


@dataclass
class SearchResult:
    reports: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False

    @property
    def fetched(self) -> int:
        return sum(int(report.get("fetched", 0)) for report in self.reports)

    @property
    def persisted(self) -> int:
        return sum(int(report.get("persisted", 0)) for report in self.reports)


class DesktopService:
    """Small synchronous facade; the GUI runs slow calls through TaskWorker."""

    READY_STATUSES = {JobStatus.READY_FOR_FORM_SUBMISSION}
    REVIEW_STATUSES = {JobStatus.QUALITY_REJECTED}

    def initialize(self) -> None:
        init_db()

    def dashboard(self) -> DashboardSnapshot:
        from smartapply.database.models import LLMUsage

        with session_scope() as session:
            jobs = session.scalar(select(func.count()).select_from(Job)) or 0
            pending = (
                session.scalar(
                    select(func.count())
                    .select_from(Job)
                    .where(Job.archived_at.is_(None), Job.analyzed_at.is_(None))
                )
                or 0
            )
            analyzed = (
                session.scalar(
                    select(func.count()).select_from(Job).where(Job.status == JobStatus.ANALYZED)
                )
                or 0
            )
            ready = (
                session.scalar(
                    select(func.count())
                    .select_from(Application)
                    .where(Application.status.in_(self.READY_STATUSES))
                )
                or 0
            )
            review = (
                session.scalar(
                    select(func.count())
                    .select_from(Application)
                    .where(Application.status.in_(self.REVIEW_STATUSES))
                )
                or 0
            )
            sent = (
                session.scalar(
                    select(func.count())
                    .select_from(Application)
                    .where(Application.status == JobStatus.SENT)
                )
                or 0
            )
            cost = session.scalar(select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0))) or 0.0
            latest = (
                session.execute(
                    select(Application)
                    .options(joinedload(Application.job))
                    .order_by(Application.updated_at.desc())
                    .limit(8)
                )
                .scalars()
                .all()
            )
            recent = tuple(
                DashboardApplication(
                    id=app.id,
                    company=app.job.company if app.job else "Entreprise inconnue",
                    title=app.job.title if app.job else "Offre supprimée",
                    status=app.status,
                    status_label=self._desktop_status_label(app.status),
                    next_action=_desktop_next_action(app.status, app.updated_at),
                    updated_at=_date_text(app.updated_at, with_time=True),
                )
                for app in latest
            )
        return DashboardSnapshot(
            jobs=int(jobs),
            pending=int(pending),
            ready=int(ready),
            review=int(review),
            sent=int(sent),
            analyzed=int(analyzed),
            llm_cost_usd=float(cost),
            recent=recent,
        )

    def list_jobs(
        self,
        *,
        search: str = "",
        status: str | None = None,
        limit: int = 500,
    ) -> list[JobRow]:
        stmt = (
            select(Job)
            .options(
                joinedload(Job.score),
                joinedload(Job.analysis),
                joinedload(Job.application),
            )
            .order_by(Job.scraped_at.desc())
        )
        if status == JobStatus.SHORTLISTED:
            stmt = stmt.where(
                Job.shortlisted_at.is_not(None),
                Job.archived_at.is_(None),
            )
        elif status:
            stmt = stmt.where(Job.status == status)
        needle = search.strip()
        if needle:
            term = f"%{needle}%"
            stmt = stmt.where(
                or_(
                    Job.title.ilike(term),
                    Job.company.ilike(term),
                    Job.location.ilike(term),
                    Job.source.ilike(term),
                )
            )
        stmt = stmt.limit(limit)
        with session_scope() as session:
            jobs = session.execute(stmt).scalars().all()
            return [self._job_row(job) for job in jobs]

    def get_job(self, job_id: int) -> JobDetail | None:
        with session_scope() as session:
            job = session.execute(
                select(Job)
                .options(
                    joinedload(Job.score),
                    joinedload(Job.analysis),
                    joinedload(Job.application),
                )
                .where(Job.id == job_id)
            ).scalar_one_or_none()
            if job is None:
                return None
            base = self._job_row(job)
            analysis = job.analysis
            components = job.score.components if job.score and job.score.components else {}
            archived = bool(job.archived_at or job.status == JobStatus.ARCHIVED)
            raw_archive_reasons = components.get("rejection_reasons") or (
                components.get("reasons") if archived else []
            )
            return JobDetail(
                **asdict(base),
                remote=job.remote_policy or "",
                url=job.application_url or "",
                description=job.cleaned_description or job.description or "",
                role_type=analysis.role_type or "" if analysis else "",
                domain=analysis.domain or "" if analysis else "",
                seniority=analysis.seniority or "" if analysis else "",
                match_reasons=_text_list(analysis.match_reasons if analysis else None),
                risks=_text_list(analysis.risks if analysis else None),
                archive_reasons=archive_reason_labels(
                    raw_archive_reasons,
                    stage=str(components.get("rejection_stage") or ""),
                    archived=archived,
                ),
            )

    @staticmethod
    def _job_row(job: Job) -> JobRow:
        years = required_min_years(job.cleaned_description or job.description)
        seniority = job.analysis.seniority if job.analysis else ""
        components = job.score.components if job.score and job.score.components else {}
        filter_disposition = str(components.get("filter_disposition") or "")
        experience = f"{years}+ ans" if years is not None else (seniority or "—")
        return JobRow(
            id=job.id,
            company=job.company,
            title=job.title,
            location=job.location or "",
            source=job.source,
            status=job.status,
            status_label=DesktopService._desktop_status_label(job.status),
            filter_disposition=filter_disposition,
            score=(job.score.final_score if job.score else None),
            contract=job.contract_type or "",
            experience=experience,
            shortlisted=bool(job.shortlisted_at and not job.archived_at),
            application_id=job.application.id if job.application else None,
            scraped_at=_date_text(job.scraped_at),
        )

    def shortlist_summary(self) -> ShortlistSummary:
        from smartapply.pipeline.apply.persistence import reservation_is_stale

        with session_scope() as session:
            jobs = (
                session.execute(
                    select(Job)
                    .options(joinedload(Job.application).joinedload(Application.documents))
                    .where(
                        Job.shortlisted_at.is_not(None),
                        Job.archived_at.is_(None),
                    )
                )
                .unique()
                .scalars()
                .all()
            )
            ready = sum(
                job.application is None or reservation_is_stale(job.application) for job in jobs
            )
            return ShortlistSummary(total=len(jobs), ready_to_generate=ready)

    def shortlisted_generation_ids(self) -> list[int]:
        from smartapply.pipeline.apply.persistence import reservation_is_stale

        with session_scope() as session:
            jobs = (
                session.execute(
                    select(Job)
                    .options(joinedload(Job.application).joinedload(Application.documents))
                    .where(
                        Job.shortlisted_at.is_not(None),
                        Job.archived_at.is_(None),
                    )
                    .order_by(Job.shortlisted_at.asc(), Job.id.asc())
                )
                .unique()
                .scalars()
                .all()
            )
            return [
                int(job.id)
                for job in jobs
                if job.application is None or reservation_is_stale(job.application)
            ]

    def set_job_shortlisted(self, job_id: int, *, selected: bool) -> bool:
        """Persist a manual Top-selection decision across application runs."""
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None or job.archived_at is not None:
                return False
            updated = set_shortlisted(
                session,
                job_id,
                selected=selected,
                origin=ShortlistOrigin.MANUAL,
            )
            if updated is None:
                return False
            components = (
                dict(job.score.components) if job.score is not None and job.score.components else {}
            )
            components["manual_shortlist"] = {
                "selected": selected,
                "updated_at": datetime.now().astimezone().isoformat(),
            }
            set_score(session, job_id, components=components)
            return True

    def list_applications(
        self,
        *,
        search: str = "",
        status: str | None = None,
        limit: int = 500,
    ) -> list[ApplicationRow]:
        stmt = (
            select(Application)
            .join(Application.job)
            .options(joinedload(Application.job))
            .order_by(Application.updated_at.desc())
        )
        if status:
            stmt = stmt.where(Application.status == status)
        needle = search.strip()
        if needle:
            term = f"%{needle}%"
            stmt = stmt.where(or_(Job.title.ilike(term), Job.company.ilike(term)))
        stmt = stmt.limit(limit)
        with session_scope() as session:
            apps = session.execute(stmt).scalars().all()
            return [self._application_row(app) for app in apps]

    def get_application(self, application_id: int) -> ApplicationDetail | None:
        with session_scope() as session:
            app = (
                session.execute(
                    select(Application)
                    .options(
                        joinedload(Application.job),
                        joinedload(Application.job).joinedload(Job.analysis),
                        joinedload(Application.documents),
                    )
                    .where(Application.id == application_id)
                )
                .unique()
                .scalar_one_or_none()
            )
            if app is None or app.job is None:
                return None
            base = self._application_row(app)
            analysis = app.job.analysis
            docs: dict[str, GeneratedDocument] = {}
            for doc in sorted(app.documents, key=lambda item: item.id):
                docs[doc.doc_type] = doc
            letter = docs.get("motivation_letter")
            letter_pdf = docs.get("motivation_letter_pdf")
            extra = letter.extra if letter and isinstance(letter.extra, dict) else {}
            return ApplicationDetail(
                **asdict(base),
                location=app.job.location or "",
                source=app.job.source,
                job_url=app.job.application_url or "",
                form_url=app.form_submission_url or app.job.application_url or "",
                letter_subject=str(extra.get("subject", "")),
                letter_body=letter.content or "" if letter else "",
                notes=app.notes or "",
                form_submitted_at=_date_text(app.form_submitted_at, with_time=True)
                if app.form_submitted_at
                else "",
                cv_docx_path=app.cv_docx_path or "",
                cv_pdf_path=app.cv_pdf_path or "",
                letter_pdf_path=letter_pdf.path or "" if letter_pdf else "",
                match_reasons=_text_list(analysis.match_reasons if analysis else None),
                risks=_text_list(analysis.risks if analysis else None),
                warnings=_text_list(app.validation_warnings),
            )

    def application_output_directory(self, application_id: int) -> Path | None:
        """Return the actual artifact directory for one persisted application.

        Persisted document paths are the source of truth. This matters when the
        configured output directory has changed since the application was
        generated.
        """
        with session_scope() as session:
            app = session.execute(
                select(Application)
                .options(joinedload(Application.documents))
                .where(Application.id == application_id)
            ).unique().scalar_one_or_none()
            if app is None:
                return None

            for raw_path in (
                app.cv_pdf_path,
                app.cv_docx_path,
                *(doc.path for doc in app.documents),
            ):
                if raw_path:
                    return Path(raw_path).expanduser().resolve().parent

        from smartapply.pipeline.output_paths import application_output_dir

        return (
            application_output_dir(
                get_settings().output_dir,
                application_id,
            )
            .expanduser()
            .resolve()
        )

    @staticmethod
    def _application_row(app: Application) -> ApplicationRow:
        company = app.job.company if app.job else "Entreprise inconnue"
        title = app.job.title if app.job else "Offre supprimée"
        return ApplicationRow(
            id=app.id,
            job_id=app.job_id,
            company=company,
            title=title,
            status=app.status,
            status_label=DesktopService._desktop_status_label(app.status),
            next_action=_desktop_next_action(app.status, app.updated_at),
            updated_at=_date_text(app.updated_at, with_time=True),
        )

    def search_jobs(
        self,
        *,
        query: str,
        location: str,
        sources: list[str],
        max_results: int,
        date_posted: str,
        serpapi_hl: str = "en,fr",
        progress=None,
        stop_requested: Callable[[], bool] | None = None,
    ) -> SearchResult:
        from smartapply.pipeline import Pipeline
        from smartapply.pipeline.pipeline import freshness_kwargs

        if not location.strip():
            raise ValueError("Une localisation est requise pour lancer la recherche.")
        requested_sources = list(dict.fromkeys(sources))
        result = SearchResult()
        if not requested_sources:
            return result

        pipeline = Pipeline()

        def collect(source: str):
            if progress:
                progress(f"Recherche sur {self.source_label(source)}…")
            source_kwargs = freshness_kwargs(
                source,
                date_posted=date_posted,
                serpapi_hl=serpapi_hl,
            )
            if source == "serpapi":
                # The explicit app field is authoritative; do not retain the
                # historical SERPAPI_GL=fr country bias for London/Canada/etc.
                source_kwargs["use_configured_country_bias"] = False
            return pipeline.collect_source(
                source,
                query,
                location or None,
                max_results=max_results,
                stop_requested=stop_requested,
                **source_kwargs,
            )

        collections = {}
        with ThreadPoolExecutor(
            max_workers=min(4, len(requested_sources)),
            thread_name_prefix="elan-search",
        ) as executor:
            futures = {executor.submit(collect, source): source for source in requested_sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    collection = future.result()
                except Exception as exc:
                    result.errors.append(f"{self.source_label(source)} : {exc}")
                    continue
                collections[source] = collection
                result.cancelled = result.cancelled or collection.cancelled

        # SQLite gets a single writer after all network-bound collections.
        for source in requested_sources:
            collection = collections.get(source)
            if collection is None:
                continue
            if progress:
                progress(f"Enregistrement de {self.source_label(source)}…")
            try:
                report = pipeline.persist_collection(collection)
            except Exception as exc:
                result.errors.append(f"{self.source_label(source)} : {exc}")
            else:
                result.reports.append(asdict(report))
        result.cancelled = result.cancelled or bool(stop_requested and stop_requested())
        return result

    def process_pending(self, *, top_k: int, progress=None) -> dict[str, Any]:
        from smartapply.pipeline import Pipeline

        if progress:
            progress("Classement et analyse des offres…")
        return asdict(Pipeline().process_pending(top_k_analyze=top_k))

    def update_shortlist(self, *, top_k: int, progress=None) -> dict[str, Any]:
        """Apply the selected Top-K value without spending an LLM call."""
        from smartapply.pipeline import Pipeline

        if progress:
            progress("Mise à jour de la Top sélection…")
        return asdict(Pipeline().rank_pending(top_k_ranked=top_k))

    def analyze_job(self, job_id: int, *, progress=None) -> dict[str, Any]:
        from smartapply.pipeline import Pipeline

        if progress:
            progress("Analyse de l’offre selon votre profil…")
        return asdict(Pipeline().analyze_jobs([job_id]))

    def generate_application(
        self,
        job_id: int,
        *,
        progress=None,
    ) -> dict[str, Any]:
        from smartapply.pipeline import Pipeline

        if progress:
            progress("Création du CV et de la lettre…")
        report = Pipeline().apply_to(job_id)
        return asdict(report)

    def generate_applications(
        self,
        job_ids: list[int],
        *,
        progress=None,
    ) -> dict[str, Any]:
        """Analyze when needed and generate documents for every eligible job."""
        from smartapply.pipeline import ApplicationAlreadyExistsError, Pipeline
        from smartapply.pipeline.apply.persistence import reservation_is_stale

        requested_ids = list(dict.fromkeys(int(job_id) for job_id in job_ids if int(job_id) > 0))
        report: dict[str, Any] = {
            "requested": len(requested_ids),
            "generated": 0,
            "skipped": 0,
            "failed": 0,
            "application_ids": [],
            "errors": [],
            "warnings": [],
        }
        if not requested_ids:
            return report

        with session_scope() as session:
            jobs = (
                session.execute(
                    select(Job)
                    .options(joinedload(Job.application).joinedload(Application.documents))
                    .where(Job.id.in_(requested_ids))
                )
                .unique()
                .scalars()
                .all()
            )
            state = {
                job.id: {
                    "title": job.title,
                    "company": job.company,
                    "archived": bool(job.archived_at or job.status == JobStatus.ARCHIVED),
                    "analyzed": bool(job.analyzed_at),
                    "application_blocks_generation": bool(
                        job.application and not reservation_is_stale(job.application)
                    ),
                }
                for job in jobs
            }

        pipeline = Pipeline()
        total = len(requested_ids)
        for index, job_id in enumerate(requested_ids, start=1):
            item = state.get(job_id)
            if item is None or item["archived"] or item["application_blocks_generation"]:
                report["skipped"] += 1
                continue
            try:
                if progress:
                    progress(f"Création de la candidature {index}/{total}…")
                if not item["analyzed"]:
                    analysis = pipeline.analyze_jobs([job_id])
                    if analysis.analyzed == 0 and analysis.already_analyzed == 0:
                        analysis_errors = getattr(analysis, "errors", [])
                        if analysis_errors:
                            report["failed"] += 1
                            message = str(analysis_errors[0].get("message", "Analyse GPT échouée"))
                            report["errors"].append(
                                {"job_id": job_id, "message": f"Analyse : {message}"}
                            )
                        else:
                            report["skipped"] += 1
                        continue
                application = pipeline.apply_to(job_id)
            except ApplicationAlreadyExistsError:
                report["skipped"] += 1
                continue
            except Exception as exc:
                report["failed"] += 1
                report["errors"].append({"job_id": job_id, "message": str(exc)})
                continue
            report["generated"] += 1
            if application.application_id:
                report["application_ids"].append(int(application.application_id))
            issues = [
                *list(getattr(application, "validation_warnings", None) or []),
                *(
                    f"validation_error:{error}"
                    for error in list(getattr(application, "validation_errors", None) or [])
                ),
            ]
            if issues:
                report["warnings"].append(
                    {
                        "job_id": job_id,
                        "title": item["title"],
                        "company": item["company"],
                        "message": " · ".join(str(issue) for issue in issues),
                    }
                )
        return report

    def generate_shortlisted_applications(self, *, progress=None) -> dict[str, Any]:
        """Generate every still-eligible application in the persistent Top selection."""
        job_ids = self.shortlisted_generation_ids()
        return self.generate_applications(job_ids, progress=progress)

    def create_manual_application(
        self,
        *,
        title: str,
        company: str,
        location: str,
        description: str,
        application_url: str,
        progress=None,
    ) -> dict[str, Any]:
        from smartapply.pipeline import Pipeline

        pipeline = Pipeline()
        if progress:
            progress("Enregistrement de l’offre…")
        ingest = pipeline.ingest_text(
            description,
            title=title,
            company=company,
            location=location or None,
            application_url=application_url or None,
        )
        if not ingest.job_ids:
            raise RuntimeError("L’offre existe déjà et ne peut pas être régénérée.")
        job_id = int(ingest.job_ids[0])
        if progress:
            progress("Analyse de l’offre…")
        analysis = pipeline.analyze_jobs([job_id])
        if analysis.analyzed == 0 and analysis.already_analyzed == 0:
            analysis_errors = getattr(analysis, "errors", [])
            detail = str(analysis_errors[0].get("message", "")) if analysis_errors else ""
            raise RuntimeError(
                "L’analyse de l’offre n’a pas abouti." + (f" {detail}" if detail else "")
            )
        if progress:
            progress("Création du CV et de la lettre…")
        application = pipeline.apply_to(
            job_id,
            form_url=application_url.strip() or None,
        )
        return asdict(application)

    def update_application(
        self,
        application_id: int,
        *,
        status: str | None = None,
        notes: str | None = None,
        form_submitted: bool = False,
    ) -> ApplicationDetail | None:
        with session_scope() as session:
            update_application_tracking(
                session,
                application_id,
                status=status,
                notes=notes,
                form_submitted=form_submitted,
            )
        return self.get_application(application_id)

    def archive_job(self, job_id: int) -> None:
        with session_scope() as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            components = (
                dict(job.score.components) if job.score is not None and job.score.components else {}
            )
            components.update(
                {
                    "rejection_stage": "manual",
                    "rejection_reasons": ["manual_archive"],
                    "rejection_summary": "manual_archive",
                }
            )
            set_score(session, job_id, components=components)
            mark_archived(session, job_id)

    def rescue_job(self, job_id: int) -> None:
        with session_scope() as session:
            rescue_archived_job(
                session,
                job_id,
                justification="Restaurée depuis l’application macOS",
            )

    def rescue_jobs(self, job_ids: list[int], *, progress=None) -> dict[str, int]:
        """Re-inject all archived jobs in a selection in one transaction."""
        requested_ids = list(dict.fromkeys(int(job_id) for job_id in job_ids if int(job_id) > 0))
        rescued = 0
        skipped = 0
        with session_scope() as session:
            for index, job_id in enumerate(requested_ids, start=1):
                if progress:
                    progress(f"Restauration {index}/{len(requested_ids)}…")
                job = session.get(Job, job_id)
                if job is None or not (job.archived_at or job.status == JobStatus.ARCHIVED):
                    skipped += 1
                    continue
                rescue_archived_job(
                    session,
                    job_id,
                    justification="Restaurée depuis la sélection macOS",
                )
                rescued += 1
        return {"requested": len(requested_ids), "rescued": rescued, "skipped": skipped}

    def profile(self) -> ProfileSnapshot:
        profile = get_profile()
        settings = get_settings()
        return ProfileSnapshot(
            name=profile.identity.full_name,
            title=profile.identity.title,
            location=profile.identity.location,
            email=str(profile.identity.email),
            summary=profile.identity.summary,
            target_roles=tuple(profile.preferences.target_roles),
            contracts=tuple(profile.preferences.accepted_contract_types),
            remote_policies=tuple(profile.preferences.accepted_remote_policies),
            accepted_job_languages=tuple(profile.preferences.accepted_job_languages),
            skill_categories=tuple(
                (category.name, tuple(category.skills)) for category in profile.skills.categories
            ),
            experiences=len(profile.experiences),
            projects=len(profile.projects),
            education=len(profile.education),
            profile_dir=str(settings.profile_dir.expanduser().resolve()),
        )

    @staticmethod
    def ensure_profile_directory() -> Path:
        """Return the active profile folder, creating it when first opened."""
        path = get_settings().profile_dir.expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def diagnostics(self, *, check_sources: bool = False) -> RuntimeDiagnostics:
        settings = get_settings()
        url = make_url(settings.database_url)
        database_path = ""
        if url.get_backend_name() == "sqlite" and url.database:
            database_path = str(Path(url.database).expanduser().resolve())
        source_health = (
            check_source_health(settings) if check_sources else pending_source_health(settings)
        )
        sources = {key: health.ready for key, health in source_health.items()}
        return RuntimeDiagnostics(
            database_url=url.render_as_string(hide_password=True),
            database_path=database_path,
            database_exists=bool(database_path and Path(database_path).exists()),
            output_dir=str(settings.output_dir.expanduser().resolve()),
            profile_dir=str(settings.profile_dir.expanduser().resolve()),
            env_file=str(ENV_FILE),
            llm_provider=settings.llm_provider,
            llm_model=settings.openai_model_smart,
            source_ready=sources,
            source_health=source_health,
        )

    @staticmethod
    def job_statuses() -> list[tuple[str, str]]:
        return [(row["status"], row["label"]) for row in STATUS_FLOW]

    @staticmethod
    def top_k() -> int:
        with session_scope() as session:
            setting = session.get(AppSetting, "top_k_ranked")
            if setting is None:
                return int(get_settings().top_k_ranked)
            try:
                return max(1, min(100, int(setting.value)))
            except (TypeError, ValueError):
                return int(get_settings().top_k_ranked)

    @staticmethod
    def set_top_k(value: int) -> int:
        normalized = max(1, min(100, int(value)))
        with session_scope() as session:
            setting = session.get(AppSetting, "top_k_ranked")
            if setting is None:
                session.add(AppSetting(key="top_k_ranked", value=str(normalized)))
            else:
                setting.value = str(normalized)
        return normalized

    @staticmethod
    def application_statuses() -> list[tuple[str, str]]:
        allowed = {
            JobStatus.READY_FOR_FORM_SUBMISSION,
            JobStatus.QUALITY_REJECTED,
            JobStatus.SENT,
            JobStatus.INTERVIEW,
            JobStatus.REJECTED,
            JobStatus.ARCHIVED,
        }
        return [(row["status"], row["label"]) for row in STATUS_FLOW if row["status"] in allowed]

    @staticmethod
    def source_label(source: str) -> str:
        return {
            "serpapi": "Google Jobs",
            "francetravail": "France Travail",
            "linkedin": "LinkedIn",
            "welcometothejungle": "Welcome to the Jungle",
        }.get(source, source)

    @staticmethod
    def _desktop_status_label(status: str) -> str:
        return status_label(status)
