"""Phase 1 — scrape and persist raw jobs."""

from __future__ import annotations

from typing import Any

from smartapply.database import session_scope
from smartapply.database.models import JobStatus
from smartapply.database.repository import (
    get_job_by_external_id,
    get_known_external_ids,
    list_known_jobs,
    upsert_job,
)
from smartapply.logging_setup import get_logger
from smartapply.offers import ManualOfferInput, RawJob
from smartapply.parsing import clean_description
from smartapply.pipeline.ingest import (
    QUERY_AGNOSTIC_SOURCES,
    IngestReport,
    _build_search_audit,
    _KnownJobIndex,
    _normalize_application_url,
    collect_round_robin,
    expand_query_for_source,
    split_or_query,
)
from smartapply.scrapers import ManualScraper, get_scraper

logger = get_logger(__name__)


class Ingestor:
    """Turn external job postings into persisted rows."""

    def from_source(
        self,
        source: str,
        query: str,
        location: str | None = None,
        *,
        max_results: int | None = 20,
        split_or: bool = True,
        **search_kwargs,
    ) -> IngestReport:
        scraper = get_scraper(source)
        if not scraper.is_available():
            raise RuntimeError(
                f"Source {source!r} is not configured. "
                "Check your .env (SERPAPI_API_KEY, FRANCETRAVAIL_* or APIFY_TOKEN)."
            )
        source_key = source.lower()
        should_split_query = split_or and source_key not in QUERY_AGNOSTIC_SOURCES
        query_parts = split_or_query(query) if should_split_query else [query.strip()]
        queries: list[str] = []
        seen_queries: set[str] = set()
        for part in query_parts:
            for expanded_part in expand_query_for_source(source, part):
                query_key = expanded_part.lower()
                if query_key in seen_queries:
                    continue
                seen_queries.add(query_key)
                queries.append(expanded_part)
        logger.info(
            "Ingesting from %s: q=%r split_queries=%r location=%r",
            source,
            query,
            queries,
            location,
        )
        with session_scope() as s:
            known_external_ids = get_known_external_ids(s, source)
            known_index = _KnownJobIndex.from_jobs(list_known_jobs(s))
        collect_result = collect_round_robin(
            scraper=scraper,
            source=source,
            queries=queries,
            location=location,
            max_results=max_results,
            search_kwargs=search_kwargs,
            known_external_ids=known_external_ids,
            known_index=known_index,
        )
        search_audit = _build_search_audit(collect_result.raw_jobs)
        return self._persist(
            source,
            collect_result.raw_jobs,
            search_audit=search_audit,
            collect_skipped_known=collect_result.skipped_known,
            collect_skipped_existing=collect_result.skipped_existing,
            hit_raw_seen_cap=collect_result.hit_raw_seen_cap,
        )

    def from_url(self, url: str) -> IngestReport:
        return self._persist("manual", [ManualScraper().from_url(url)])

    def from_manual_offer(self, offer: ManualOfferInput) -> IngestReport:
        return self._persist("manual", [ManualScraper().from_structured(offer)])

    def from_text(
        self,
        text: str,
        *,
        title: str,
        company: str,
        location: str | None = None,
        application_url: str | None = None,
        company_description: str | None = None,
        company_url: str | None = None,
        recruiter: str | None = None,
        structured: bool = False,
    ) -> IngestReport:
        raw = ManualScraper().from_text(
            text,
            title=title,
            company=company,
            location=location,
            application_url=application_url,
            company_description=company_description,
            company_url=company_url,
            recruiter=recruiter,
            structured=structured,
        )
        return self._persist("manual", [raw])

    def _persist(
        self,
        source: str,
        raws: list[RawJob],
        *,
        search_audit: list[dict[str, Any]] | None = None,
        collect_skipped_known: int = 0,
        collect_skipped_existing: int = 0,
        hit_raw_seen_cap: bool = False,
    ) -> IngestReport:
        job_ids: list[int] = []
        inserted = 0
        updated_pending = 0
        skipped_processed = 0
        skipped_existing = 0
        with session_scope() as s:
            known_index = _KnownJobIndex.from_jobs(list_known_jobs(s))
            for raw in raws:
                existing = get_job_by_external_id(s, raw.external_id)
                existing_status = existing.status if existing is not None else None
                if existing is None and known_index.matches(raw):
                    skipped_existing += 1
                    continue
                job = upsert_job(
                    s,
                    external_id=raw.external_id,
                    title=raw.title,
                    company=raw.company,
                    location=raw.location,
                    contract_type=raw.contract_type,
                    remote_policy=raw.remote_policy,
                    description=raw.description,
                    cleaned_description=clean_description(raw.description),
                    application_url=raw.application_url,
                    apply_options=raw.apply_options,
                    source=raw.source,
                    source_data=raw.source_data,
                    published_date=raw.published_date,
                )
                if existing_status is None:
                    inserted += 1
                    job_ids.append(job.id)
                elif existing_status == JobStatus.SCRAPED:
                    updated_pending += 1
                    job_ids.append(job.id)
                else:
                    skipped_processed += 1
        return IngestReport(
            source=source,
            fetched=len(raws),
            persisted=len(job_ids),
            job_ids=job_ids,
            inserted=inserted,
            updated_pending=updated_pending,
            skipped_processed=skipped_processed,
            skipped_existing_during_collect=collect_skipped_existing,
            skipped_existing_during_persist=skipped_existing,
            skipped_known_during_collect=collect_skipped_known,
            hit_raw_seen_cap=hit_raw_seen_cap,
            search_audit=search_audit or [],
        )


__all__ = [
    "IngestReport",
    "Ingestor",
    "_normalize_application_url",
    "expand_query_for_source",
    "split_or_query",
]
