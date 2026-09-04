"""Duplicate handling for pending jobs."""

from __future__ import annotations

from datetime import timezone

from smartapply.database.models import Job
from smartapply.database.repository import mark_archived, set_score
from smartapply.pipeline.process.audit import _rejection_audit_components


class DeduplicationMixin:
    """Mark duplicate jobs while preserving the best active root."""

    def _mark_duplicates(self, session, pending: list[Job]) -> set[int]:
        report = self.deduplicator.deduplicate(pending)
        duplicate_ids: set[int] = set()
        for group in report.duplicate_groups:
            root = self._dedup_root(group)
            for duplicate in group:
                if duplicate.id == root.id:
                    continue
                duplicate_ids.add(int(duplicate.id))
                reasons = [
                    f"duplicate_of:{root.id}",
                    f"duplicate_reference:{root.company} — {root.title}",
                ]
                previous_components = (
                    dict(duplicate.score.components)
                    if duplicate.score is not None and duplicate.score.components
                    else {}
                )
                set_score(
                    session,
                    duplicate.id,
                    components={
                        **previous_components,
                        **_rejection_audit_components("deduplication", reasons),
                    },
                )
                mark_archived(session, duplicate.id)
        return duplicate_ids

    @staticmethod
    def _dedup_root(group: list[Job]) -> Job:
        """Keep the most advanced active job when several rows are duplicates."""

        def scraped_timestamp(job: Job) -> float:
            if job.scraped_at is None:
                return float("inf")
            scraped_at = job.scraped_at
            if scraped_at.tzinfo is None:
                scraped_at = scraped_at.replace(tzinfo=timezone.utc)
            return scraped_at.timestamp()

        def priority(job: Job) -> tuple[int, int, float, int]:
            progress = 0
            if job.filtered_at is not None:
                progress += 1
            if job.ranked_at is not None:
                progress += 1
            if job.analysis is not None or job.analyzed_at is not None:
                progress += 1
            return (
                -progress,
                0 if job.application is not None else 1,
                scraped_timestamp(job),
                int(job.id),
            )

        return min(group, key=priority)
