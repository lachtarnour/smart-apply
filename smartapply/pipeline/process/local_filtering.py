"""Local deterministic filtering phase."""

from __future__ import annotations

from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import (
    list_pending_processing,
    mark_archived,
    mark_filtered,
    set_score,
    update_status,
)
from smartapply.filtering.types import FilterDisposition
from smartapply.pipeline.process.audit import _rejection_audit_components
from smartapply.pipeline.reports import LocalFilterReport


class LocalFilterMixin:
    """Apply deterministic filters and persist rejection audit data."""

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
                reasons.append("Manual override: kept by user")
            components = {
                "reasons": reasons,
                "filter_disposition": (
                    res.disposition.value if res.disposition is not None else "rejected"
                ),
            }
            if not (res.kept or force_keep):
                components = _rejection_audit_components("local_filter", reasons)
                components["filter_disposition"] = "rejected"
            set_score(
                session,
                job.id,
                rule_based_score=res.score,
                components=components,
            )
            if res.kept or force_keep:
                kept.append(job)
                mark_filtered(session, job.id)
                update_status(session, job.id, JobStatus.FILTERED)
            else:
                mark_archived(session, job.id)
        return kept

    def filter_pending(self, *, job_ids: list[int] | None = None) -> LocalFilterReport:
        """Apply only deterministic local gates, without ranking or LLM calls.

        Used right after fetch in the workflow: internships, alternance and
        too-senior roles disappear before the user spends attention or LLM
        budget. The macOS search location remains authoritative. Kept jobs get ``filtered_at``
        set so a later ``process_pending`` correctly resumes from ranking
        instead of re-filtering or seeing nothing pending.
        """
        with session_scope() as s:
            active_jobs = list(list_pending_processing(s))
            pending = [j for j in active_jobs if j.filtered_at is None]
            if job_ids is not None:
                selected_ids = set(job_ids)
                pending = [job for job in pending if job.id in selected_ids]
            if not pending:
                return LocalFilterReport(0, 0, 0, 0, [], [])

            dedup_scope_by_id = {int(job.id): job for job in active_jobs}
            for job in pending:
                dedup_scope_by_id[int(job.id)] = job
            duplicate_ids = self._mark_duplicates(s, list(dedup_scope_by_id.values()))
            unique_jobs = [j for j in pending if j.id not in duplicate_ids]
            kept_ids: list[int] = []
            uncertain_ids: list[int] = []
            pending_ids = {int(job.id) for job in pending}
            rejected_ids: list[int] = [
                int(job_id) for job_id in duplicate_ids if int(job_id) in pending_ids
            ]

            for job in unique_jobs:
                res = self.filter.evaluate(job)
                components = {
                    "reasons": res.reasons,
                    "filter_disposition": (
                        res.disposition.value if res.disposition is not None else "rejected"
                    ),
                }
                if not res.kept:
                    components = _rejection_audit_components(
                        "local_filter",
                        list(res.reasons),
                    )
                    components["filter_disposition"] = "rejected"
                set_score(
                    s,
                    job.id,
                    rule_based_score=res.score,
                    components=components,
                )
                if res.kept:
                    kept_ids.append(job.id)
                    if res.disposition is FilterDisposition.UNCERTAIN:
                        uncertain_ids.append(job.id)
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
                uncertain=len(uncertain_ids),
                uncertain_ids=uncertain_ids,
            )
