"""Phase 2 — dedup + local filter + semantic ranking + LLM analysis.

The whole point of this phase is to spend cheap signals (deterministic
rules, embeddings) before any LLM call, then analyze only the top-K
shortlist with the cheap model.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import (
    list_pending_processing,
    mark_analyzed,
    mark_archived,
    mark_filtered,
    mark_ranked,
    set_analysis,
    set_score,
    update_status,
)
from smartapply.dedup import Deduplicator
from smartapply.filtering import JobFilter
from smartapply.llm import JobAnalysis, LLMProvider
from smartapply.llm.prompts import job_analysis as analysis_prompts
from smartapply.logging_setup import get_logger
from smartapply.profile import Profile
from smartapply.ranking import JobScorer

logger = get_logger(__name__)


_ANONYMOUS_COMPANY_MARKERS = (
    "non communiqu",  # "Entreprise non communiquée"
    "confidentiel",
    "anonyme",
)

_GENERIC_LOCATION_MARKERS = {
    "",
    "france",
    "remote",
    "remote france",
    "remote (france)",
    "remote fr",
    "teletravail",
    "hybride",
    "ile-de-france",
    "ile de france",
    "idf",
}


def _is_anonymous_company(name: str | None) -> bool:
    if not name:
        return True
    lowered = name.lower()
    return any(marker in lowered for marker in _ANONYMOUS_COMPANY_MARKERS)


def _should_replace_job_location(current: str | None, extracted: str | None) -> bool:
    extracted = " ".join((extracted or "").split())
    if not extracted:
        return False
    current_value = " ".join((current or "").split())
    if not current_value:
        return True
    current_norm = current_value.lower()
    extracted_norm = extracted.lower()
    if extracted_norm in current_norm or current_norm in extracted_norm:
        return False
    return current_norm in _GENERIC_LOCATION_MARKERS


@dataclass
class ProcessReport:
    total: int
    kept_after_filter: int
    duplicates_removed: int
    top_ranked: int
    analyzed: int


@dataclass
class LocalFilterReport:
    total: int
    kept: int
    rejected: int
    duplicates_removed: int
    kept_ids: list[int]
    rejected_ids: list[int]


class Processor:
    """Run dedup → filter → semantic ranking → LLM analysis on top-K."""

    def __init__(
        self,
        *,
        profile: Profile,
        deduplicator: Deduplicator,
        job_filter: JobFilter,
        scorer: JobScorer,
        llm: LLMProvider,
    ):
        self.profile = profile
        self.deduplicator = deduplicator
        self.filter = job_filter
        self.scorer = scorer
        self.llm = llm
        self.settings = get_settings()

    def process_pending(
        self,
        top_k_analyze: int | None = None,
        *,
        job_ids: list[int] | None = None,
        local_filter_override_ids: list[int] | None = None,
    ) -> ProcessReport:
        """Drive the rest of the pipeline using per-phase timestamps.

        Idempotent against partial runs: jobs that already passed an earlier
        phase (``filtered_at`` set) skip that phase and continue. This is what
        lets ``filter_pending`` and ``process_pending`` cooperate cleanly.
        """
        with session_scope() as s:
            pending = list(list_pending_processing(s))
            if job_ids is not None:
                selected_ids = set(job_ids)
                pending = [job for job in pending if job.id in selected_ids]
            if not pending:
                logger.info("No pending jobs to process.")
                return ProcessReport(0, 0, 0, 0, 0)

            override_ids = set(local_filter_override_ids or [])
            # Only dedup jobs not yet filtered — duplicates among already-kept
            # jobs would have been caught in the earlier pass.
            to_dedup = [j for j in pending if j.filtered_at is None]
            duplicate_ids = self._mark_duplicates(s, to_dedup)
            unique_jobs = [j for j in pending if j.id not in duplicate_ids]

            to_filter = [j for j in unique_jobs if j.filtered_at is None]
            already_kept = [j for j in unique_jobs if j.filtered_at is not None]
            newly_kept = self._apply_local_filter(
                s,
                to_filter,
                override_ids=override_ids,
            )
            kept_jobs = already_kept + newly_kept

            ranked = self.scorer.rank(kept_jobs)
            shortlist_n = min(top_k_analyze or self.settings.top_k_ranked, len(ranked))
            shortlisted_jobs = self._persist_ranking(s, ranked, shortlist_n)

        to_analyze = [j for j in shortlisted_jobs if j.analyzed_at is None]
        analyzed = self._analyze_in_parallel(to_analyze)

        return ProcessReport(
            total=len(pending),
            kept_after_filter=len(kept_jobs),
            duplicates_removed=len(duplicate_ids),
            top_ranked=len(shortlisted_jobs),
            analyzed=analyzed,
        )

    def _analyze_in_parallel(self, shortlisted_jobs: list[Job]) -> int:
        """Run ``_analyze_one`` concurrently over the shortlist.

        Each ``_analyze_one`` opens its own ``session_scope``, so SQLAlchemy
        sessions stay thread-local. OpenAI's SDK is thread-safe. We cap the
        worker pool via ``settings.llm_max_concurrent`` to respect provider
        rate limits.
        """
        if not shortlisted_jobs:
            return 0
        workers = min(self.settings.llm_max_concurrent, len(shortlisted_jobs))
        analyzed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(self._analyze_one, job_id=job.id): job
                for job in shortlisted_jobs
            }
            for future in as_completed(futures):
                job = futures[future]
                try:
                    future.result()
                    analyzed += 1
                except Exception as e:
                    logger.error("Analysis failed for job %s: %s", job.id, e)
        return analyzed

    # -------------------- internals --------------------

    def _mark_duplicates(self, session, pending: list[Job]) -> set[int]:
        report = self.deduplicator.deduplicate(pending)
        duplicate_ids = {j.id for group in report.duplicate_groups for j in group[1:]}
        for j in pending:
            if j.id in duplicate_ids:
                mark_archived(session, j.id)
        return duplicate_ids

    def _apply_local_filter(
        self,
        session,
        jobs: list[Job],
        *,
        override_ids: set[int] | None = None,
    ) -> list[Job]:
        kept: list[Job] = []
        override_ids = override_ids or set()
        for job in jobs:
            res = self.filter.evaluate(job)
            reasons = list(res.reasons)
            force_keep = job.id in override_ids
            if force_keep and not res.kept:
                reasons.append("Manual override: kept by user in Streamlit workflow")
            set_score(
                session,
                job.id,
                rule_based_score=res.score,
                components={"reasons": reasons},
            )
            if res.kept or force_keep:
                kept.append(job)
                mark_filtered(session, job.id)
                update_status(session, job.id, JobStatus.FILTERED)
            else:
                mark_archived(session, job.id)
        return kept

    def _persist_ranking(
        self,
        session,
        ranked: list[tuple[Job, object]],
        shortlist_n: int,
    ) -> list[Job]:
        for i, (job, comp) in enumerate(ranked):
            previous_components = (
                dict(job.score.components)
                if job.score is not None and job.score.components
                else {}
            )
            components = comp.to_dict()
            if previous_components.get("reasons"):
                components["reasons"] = previous_components["reasons"]
            set_score(
                session,
                job.id,
                semantic_score=comp.semantic,
                skill_score=comp.skills,
                title_score=comp.title,
                seniority_score=comp.seniority,
                location_score=comp.location,
                domain_score=comp.domain,
                final_score=comp.final,
                components=components,
            )
            mark_ranked(session, job.id)
            if i < shortlist_n:
                update_status(session, job.id, JobStatus.SHORTLISTED)
        return [job for job, _ in ranked[:shortlist_n]]

    def _analyze_one(self, *, job_id: int) -> None:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            user_prompt = analysis_prompts.build_user_prompt(
                profile=self.profile,
                job_title=job.title,
                job_company=job.company,
                job_location=job.location,
                application_url=job.application_url,
                job_description=job.cleaned_description or job.description,
            )
            analysis = self.llm.complete_json(
                system=analysis_prompts.SYSTEM,
                user=user_prompt,
                schema=JobAnalysis,
                model=self.llm.cheap_model,
                purpose="job_analysis",
                job_id=job.id,
            )
            set_analysis(
                s,
                job.id,
                role_type=analysis.role_type,
                seniority=analysis.seniority,
                domain=analysis.domain,
                main_tasks=analysis.main_tasks,
                required_skills=analysis.required_skills,
                nice_to_have=analysis.nice_to_have,
                match_reasons=analysis.match_reasons,
                risks=analysis.risks,
                cv_keywords_to_include=analysis.cv_keywords_to_include,
                raw_response=analysis.model_dump(),
                model_used=self.llm.cheap_model,
            )
            if analysis.extracted_company_name and _is_anonymous_company(job.company):
                job.company = analysis.extracted_company_name.strip()
            if _should_replace_job_location(job.location, analysis.extracted_location):
                job.location = analysis.extracted_location.strip()
            mark_analyzed(s, job.id)
            update_status(s, job.id, JobStatus.ANALYZED)

    def filter_pending(self, *, job_ids: list[int] | None = None) -> LocalFilterReport:
        """Apply only deterministic local gates, without ranking or LLM calls.

        Used right after fetch in the Streamlit workflow: internships,
        alternance, foreign locations and too-senior roles disappear before
        the user spends attention or LLM budget. Kept jobs get ``filtered_at``
        set so a later ``process_pending`` correctly resumes from ranking
        instead of re-filtering or seeing nothing pending.
        """
        with session_scope() as s:
            pending = list(list_pending_processing(s))
            pending = [j for j in pending if j.filtered_at is None]
            if job_ids is not None:
                selected_ids = set(job_ids)
                pending = [job for job in pending if job.id in selected_ids]
            if not pending:
                return LocalFilterReport(0, 0, 0, 0, [], [])

            duplicate_ids = self._mark_duplicates(s, pending)
            unique_jobs = [j for j in pending if j.id not in duplicate_ids]
            kept_ids: list[int] = []
            rejected_ids: list[int] = list(duplicate_ids)

            for job in unique_jobs:
                res = self.filter.evaluate(job)
                set_score(
                    s,
                    job.id,
                    rule_based_score=res.score,
                    components={"reasons": res.reasons},
                )
                if res.kept:
                    kept_ids.append(job.id)
                    mark_filtered(s, job.id)
                else:
                    rejected_ids.append(job.id)
                    mark_archived(s, job.id)

            return LocalFilterReport(
                total=len(pending),
                kept=len(kept_ids),
                rejected=len(rejected_ids),
                duplicates_removed=len(duplicate_ids),
                kept_ids=kept_ids,
                rejected_ids=rejected_ids,
            )
