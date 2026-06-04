"""Phase 1 — scrape and persist raw jobs.

Wraps the active scrapers behind a uniform interface so the rest of the
pipeline never thinks about source-specific details.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from smartapply.database import session_scope
from smartapply.database.models import JobStatus
from smartapply.database.repository import get_job_by_external_id, upsert_job
from smartapply.logging_setup import get_logger
from smartapply.parsing import clean_description
from smartapply.scrapers import ManualScraper, get_scraper
from smartapply.scrapers.base import RawJob

logger = get_logger(__name__)

OR_SPLIT_RE = re.compile(r"\s+\bOR\b\s+", flags=re.IGNORECASE)
ROLE_QUERY_ALIASES_FR: dict[str, tuple[str, ...]] = {
    "data scientist": ("Data Science", "Scientifique des données"),
    "data analyst": ("Analyste Data",),
    "machine learning engineer": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "machine learning ing": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "ml engineer": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "ml ing": (
        "Machine Learning",
        "ML Engineer",
        "Ingénieur Machine Learning",
    ),
    "nlp engineer": ("NLP Engineer", "Ingénieur NLP"),
    "computer vision engineer": (
        "Computer Vision",
        "Ingénieur Vision par ordinateur",
    ),
    "ai engineer": (
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ),
    "ai ing": (
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ),
    "artificial intelligence engineer": (
        "Ingénieur IA",
        "Ingénieur Intelligence Artificielle",
        "AI ML Engineer",
    ),
    "research engineer": ("Ingénieur Recherche IA",),
    "research engineer ai": ("Ingénieur Recherche IA",),
    "mlops engineer": ("Ingénieur MLOps",),
    "analytics engineer": ("Analytics Engineer",),
}


def split_or_query(query: str) -> list[str]:
    """Split a user query like ``A OR B OR C`` into concrete searches.

    Job APIs do not all interpret boolean syntax consistently. Running one
    precise search per role is more predictable, then persistence de-duplicates
    the offers by external id.
    """
    parts = [part.strip() for part in OR_SPLIT_RE.split(query.strip())]
    return [part for part in parts if part] or [query.strip()]


def expand_query_for_source(source: str, query: str) -> list[str]:
    """Return source-aware search variants while preserving the user query.

    Google Jobs and France Travail can be uneven with English role titles in
    France. We keep the original wording so fully English offers are still
    found, then add a French alias when it is known to improve recall.
    """
    normalized = re.sub(r"\s+", " ", query.strip())
    if source.lower() not in {"serpapi", "francetravail"}:
        return [normalized]
    key = normalized.lower()
    suffix = ""
    if key.endswith(" cdi"):
        key = key[:-4].strip()
        if source.lower() == "serpapi":
            normalized = re.sub(r"\s+cdi$", "", normalized, flags=re.IGNORECASE).strip()
        else:
            suffix = " CDI"
    variants = [normalized]
    for alias in ROLE_QUERY_ALIASES_FR.get(key, ()):
        alias_query = f"{alias}{suffix}"
        if alias_query.lower() != normalized.lower():
            variants.append(alias_query)
    return variants


def normalize_query_for_source(source: str, query: str) -> str:
    """Compatibility wrapper: prefer ``expand_query_for_source``."""
    return expand_query_for_source(source, query)[0]


@dataclass
class IngestReport:
    source: str
    fetched: int
    persisted: int
    job_ids: list[int] = field(default_factory=list)
    inserted: int = 0
    updated_pending: int = 0
    skipped_processed: int = 0


class Ingestor:
    """Single responsibility: turn external job postings into persisted rows."""

    def from_source(
        self,
        source: str,
        query: str,
        location: str | None = None,
        *,
        max_results: int = 20,
        split_or: bool = True,
        **search_kwargs,
    ) -> IngestReport:
        scraper = get_scraper(source)
        if not scraper.is_available():
            raise RuntimeError(
                f"Source {source!r} is not configured. "
                "Check your .env (SERPAPI_API_KEY or FRANCETRAVAIL_*)."
            )
        query_parts = split_or_query(query) if split_or else [query.strip()]
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
        raw_jobs = self._collect_round_robin(
            scraper=scraper,
            queries=queries,
            location=location,
            max_results=max_results,
            search_kwargs=search_kwargs,
        )
        return self._persist(source, raw_jobs)

    def _collect_round_robin(
        self,
        *,
        scraper,
        queries: list[str],
        location: str | None,
        max_results: int | None,
        search_kwargs: dict,
    ) -> list[RawJob]:
        """Collect results fairly across expanded queries.

        ``max_results`` is the global target, not a per-query quota. Each
        concrete query can yield up to that target; this avoids wasting paid
        SerpApi pages by taking only 2-4 jobs from a 10-result page. A
        round-robin pass prevents the first broad query from consuming the
        whole target before the other role titles get a chance.
        """
        if not queries:
            return []
        raw_jobs: list[RawJob] = []
        seen_external_ids: set[str] = set()
        iterators = [
            iter(
                scraper.search(
                    concrete_query,
                    location=location,
                    max_results=max_results,
                    **search_kwargs,
                )
            )
            for concrete_query in queries
        ]
        active = [True] * len(iterators)
        while any(active):
            for i, iterator in enumerate(iterators):
                if not active[i]:
                    continue
                if max_results is not None and len(raw_jobs) >= max_results:
                    return raw_jobs
                try:
                    raw = next(iterator)
                except StopIteration:
                    active[i] = False
                    continue
                if raw.external_id in seen_external_ids:
                    continue
                seen_external_ids.add(raw.external_id)
                raw_jobs.append(raw)
                if max_results is not None and len(raw_jobs) >= max_results:
                    return raw_jobs
        return raw_jobs

    def from_url(self, url: str) -> IngestReport:
        return self._persist("manual", [ManualScraper().from_url(url)])

    def from_text(
        self,
        text: str,
        *,
        title: str,
        company: str,
        location: str | None = None,
        application_url: str | None = None,
    ) -> IngestReport:
        raw = ManualScraper().from_text(
            text,
            title=title,
            company=company,
            location=location,
            application_url=application_url,
        )
        return self._persist("manual", [raw])

    def _persist(self, source: str, raws: list[RawJob]) -> IngestReport:
        job_ids: list[int] = []
        inserted = 0
        updated_pending = 0
        skipped_processed = 0
        with session_scope() as s:
            for raw in raws:
                existing = get_job_by_external_id(s, raw.external_id)
                existing_status = existing.status if existing is not None else None
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
        )
