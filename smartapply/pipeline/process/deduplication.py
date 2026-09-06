"""Duplicate handling for pending jobs."""

from __future__ import annotations

from datetime import timezone

from smartapply.database.models import Job


class DeduplicationMixin:
    """Keep fuzzy duplicate decisions in the explicit human-review queue."""

    def _mark_duplicates(self, session, pending: list[Job]) -> set[int]:
        # Fuzzy similarity is deliberately review-only.  The ingestion phase
        # has already handled exact technical identities (source ID/direct
        # offer URL); silently archiving a fuzzy match here could hide a real
        # second opening and make the user submit the wrong offer.
        return set()

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
