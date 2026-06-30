"""Phase 2 — dedup + local filter + semantic ranking + LLM analysis."""

from __future__ import annotations

from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.repository import list_pending_processing
from smartapply.dedup import Deduplicator
from smartapply.filtering import JobFilter
from smartapply.llm import LLMProvider
from smartapply.logging_setup import get_logger
from smartapply.pipeline.process import (
    AnalysisMixin,
    DeduplicationMixin,
    LocalFilterMixin,
    RankingMixin,
    _is_anonymous_company,
    _should_replace_job_location,
)
from smartapply.pipeline.reports import ProcessReport
from smartapply.profile import Profile
from smartapply.ranking import JobScorer

logger = get_logger(__name__)


class Processor(AnalysisMixin, LocalFilterMixin, RankingMixin, DeduplicationMixin):
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
            active_jobs = list(list_pending_processing(s))
            pending = list(active_jobs)
            if job_ids is not None:
                selected_ids = set(job_ids)
                pending = [job for job in pending if job.id in selected_ids]
            if not pending:
                logger.info("No pending jobs to process.")
                return ProcessReport(0, 0, 0, 0, 0)

            override_ids = set(local_filter_override_ids or [])
            duplicate_ids = self._mark_duplicates(s, active_jobs)
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


__all__ = [
    "Processor",
    "_is_anonymous_company",
    "_should_replace_job_location",
]
