"""Semantic ranking phase."""

from __future__ import annotations

from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import (
    list_pending_processing,
    mark_ranked,
    set_score,
    update_status,
)
from smartapply.pipeline.reports import RankingReport


class RankingMixin:
    """Rank locally kept jobs and persist shortlist status."""

    def rank_pending(
        self,
        top_k_ranked: int | None = None,
        *,
        job_ids: list[int] | None = None,
        local_filter_override_ids: list[int] | None = None,
    ) -> RankingReport:
        """Run dedup, local filter and ranking without calling the LLM."""
        with session_scope() as s:
            active_jobs = list(list_pending_processing(s))
            pending = list(active_jobs)
            if job_ids is not None:
                selected_ids = set(job_ids)
                pending = [job for job in pending if job.id in selected_ids]
            if not pending:
                return RankingReport(0, 0, 0, 0, 0, [], [])

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
            shortlist_n = min(
                top_k_ranked or self.settings.top_k_ranked,
                len(ranked),
            )
            shortlisted_jobs = self._persist_ranking(s, ranked, shortlist_n)
            ranked_ids = [int(job.id) for job, _ in ranked]
            shortlisted_ids = [int(job.id) for job in shortlisted_jobs]

        return RankingReport(
            total=len(pending),
            kept_after_filter=len(kept_jobs),
            duplicates_removed=len(duplicate_ids),
            ranked=len(ranked_ids),
            shortlisted=len(shortlisted_ids),
            ranked_ids=ranked_ids,
            shortlisted_ids=shortlisted_ids,
        )

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
            else:
                update_status(session, job.id, JobStatus.FILTERED)
        return [job for job, _ in ranked[:shortlist_n]]

