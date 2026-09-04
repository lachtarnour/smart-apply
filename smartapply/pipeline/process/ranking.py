"""Semantic ranking phase."""

from __future__ import annotations

from sqlalchemy import select

from smartapply.database import session_scope
from smartapply.database.models import Application, Job, JobScore, ShortlistOrigin
from smartapply.database.repository import (
    list_pending_processing,
    mark_ranked,
    set_score,
    set_shortlisted,
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
            rankable_jobs = [job for job in active_jobs if job.ranked_at is None]
            pending = list(rankable_jobs)
            if job_ids is not None:
                selected_ids = set(job_ids)
                pending = [job for job in pending if job.id in selected_ids]
            duplicate_ids: set[int] = set()
            ranked: list[tuple[Job, object]] = []
            if pending:
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
                ranked = self.scorer.rank(already_kept + newly_kept)
                self._persist_scores(s, ranked)

            candidates = self._ranked_shortlist_candidates(s)
            shortlist_n = min(
                top_k_ranked or self.settings.top_k_ranked,
                len(candidates),
            )
            shortlisted_jobs = self._replace_automatic_shortlist(
                s,
                candidates,
                shortlist_n,
            )
            ranked_ids = [int(job.id) for job in candidates]
            shortlisted_ids = [int(job.id) for job in shortlisted_jobs]

        return RankingReport(
            total=len(pending),
            kept_after_filter=len(ranked_ids),
            duplicates_removed=len(duplicate_ids),
            ranked=len(ranked_ids),
            shortlisted=len(shortlisted_ids),
            ranked_ids=ranked_ids,
            shortlisted_ids=shortlisted_ids,
        )

    def _persist_scores(
        self,
        session,
        ranked: list[tuple[Job, object]],
    ) -> None:
        for job, comp in ranked:
            previous_components = (
                dict(job.score.components) if job.score is not None and job.score.components else {}
            )
            components = comp.to_dict()
            if previous_components.get("reasons"):
                components["reasons"] = previous_components["reasons"]
            if previous_components.get("filter_disposition"):
                components["filter_disposition"] = previous_components["filter_disposition"]
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

    @staticmethod
    def _ranked_shortlist_candidates(session) -> list[Job]:
        """Return every active, scored offer that still has no application."""
        return list(
            session.execute(
                select(Job)
                .join(JobScore, JobScore.job_id == Job.id)
                .outerjoin(Application, Application.job_id == Job.id)
                .where(
                    Job.archived_at.is_(None),
                    Job.filtered_at.is_not(None),
                    JobScore.final_score.is_not(None),
                    Application.id.is_(None),
                )
                .order_by(JobScore.final_score.desc(), Job.id.asc())
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _replace_automatic_shortlist(
        session,
        candidates: list[Job],
        shortlist_n: int,
    ) -> list[Job]:
        """Replace the automatic Top while preserving explicitly pinned offers."""
        automatic_top = candidates[:shortlist_n]
        automatic_ids = {int(job.id) for job in automatic_top}
        previous_automatic = session.execute(
            select(Job).where(
                Job.shortlisted_at.is_not(None),
                Job.shortlist_origin == ShortlistOrigin.AUTOMATIC,
            )
        ).scalars()
        for job in previous_automatic:
            if int(job.id) not in automatic_ids:
                set_shortlisted(session, job.id, selected=False)

        for job in automatic_top:
            set_shortlisted(
                session,
                job.id,
                selected=True,
                origin=ShortlistOrigin.AUTOMATIC,
            )

        selected_by_id = {int(job.id): job for job in automatic_top}
        manual_jobs = session.execute(
            select(Job).where(
                Job.shortlisted_at.is_not(None),
                Job.shortlist_origin == ShortlistOrigin.MANUAL,
                Job.archived_at.is_(None),
            )
        ).scalars()
        for job in manual_jobs:
            selected_by_id.setdefault(int(job.id), job)
        return list(selected_by_id.values())
