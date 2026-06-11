"""Phase 1 — scrape and persist raw jobs.

Wraps the active scrapers behind a uniform interface so the rest of the
pipeline never thinks about source-specific details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

from smartapply.database import session_scope
from smartapply.database.models import JobStatus
from smartapply.database.repository import (
    get_job_by_external_id,
    get_known_external_ids,
    list_known_jobs,
    upsert_job,
)
from smartapply.logging_setup import get_logger
from smartapply.parsing import clean_description
from smartapply.scrapers import ManualScraper, get_scraper
from smartapply.scrapers.base import RawJob

logger = get_logger(__name__)

OR_SPLIT_RE = re.compile(r"\s+\bOR\b\s+", flags=re.IGNORECASE)
QUERY_AGNOSTIC_SOURCES = {"welcometothejungle"}
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


@dataclass
class IngestReport:
    source: str
    fetched: int
    persisted: int
    job_ids: list[int] = field(default_factory=list)
    inserted: int = 0
    updated_pending: int = 0
    skipped_processed: int = 0
    skipped_existing_during_collect: int = 0
    skipped_existing_during_persist: int = 0
    # Raw offers whose external_id was already in the DB and were dropped
    # during the round-robin *before* counting against ``max_results``.
    # This is the metric that surfaces "the scraper paginated past known
    # offers to look for genuinely new ones".
    skipped_known_during_collect: int = 0
    # True when the collector stopped because it hit the raw-fetch safety
    # cap (``max_results`` × scan budget) instead of either reaching
    # ``max_results`` new offers or exhausting the source. Useful in
    # the UI to suggest raising the slider.
    hit_raw_seen_cap: bool = False
    search_audit: list[dict[str, Any]] = field(default_factory=list)


# How many raw offers a single round-robin run is allowed to *examine*
# before giving up. The cap is multiplicative on ``max_results`` so a
# small request stays cheap while a 300-item request gets the headroom
# to skip a few thousand already-known offers if needed. The bound
# guarantees the loop terminates even if a misbehaving scraper yields
# endless duplicates.
_RAW_SEEN_MULTIPLIER = 10
_RAW_SEEN_MIN = 50


@dataclass(frozen=True)
class _CollectResult:
    """Outcome of one ``_collect_round_robin`` invocation."""

    raw_jobs: list[RawJob]
    skipped_known: int
    skipped_existing: int
    hit_raw_seen_cap: bool


@dataclass(frozen=True)
class _KnownJobIndex:
    external_ids: frozenset[str]
    application_urls: frozenset[str]

    @classmethod
    def from_jobs(cls, jobs: list[Any]) -> _KnownJobIndex:
        urls: set[str] = set()
        external_ids: set[str] = set()
        for job in jobs:
            if job.external_id:
                external_ids.add(str(job.external_id))
            url_key = _normalize_application_url(job.application_url)
            if url_key:
                urls.add(url_key)
        return cls(
            external_ids=frozenset(external_ids),
            application_urls=frozenset(urls),
        )

    def matches(self, raw: RawJob) -> bool:
        if raw.external_id and raw.external_id in self.external_ids:
            return True
        url_key = _normalize_application_url(raw.application_url)
        return bool(url_key and url_key in self.application_urls)


def _normalize_application_url(url: str | None) -> str:
    value = (url or "").strip()
    if not value or value.startswith("mailto:"):
        return ""
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    host = parsed.netloc.lower().removeprefix("www.")
    if not host:
        return ""
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")
    query = _normalized_non_tracking_query(parsed.query)
    normalized = f"{host}{path}".lower()
    if query:
        normalized = f"{normalized}?{query}"
    return normalized


def _normalized_non_tracking_query(query: str) -> str:
    tracking_prefixes = ("utm_",)
    tracking_names = {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "source",
        "utm",
    }
    kept = [
        (key, value)
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.lower() not in tracking_names
        and not key.lower().startswith(tracking_prefixes)
    ]
    return urlencode(sorted(kept), doseq=True)


class Ingestor:
    """Single responsibility: turn external job postings into persisted rows."""

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
                "Check your .env (SERPAPI_API_KEY or FRANCETRAVAIL_*)."
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
        collect_result = self._collect_round_robin(
            scraper=scraper,
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

    def _collect_round_robin(
        self,
        *,
        scraper,
        queries: list[str],
        location: str | None,
        max_results: int | None,
        search_kwargs: dict,
        known_external_ids: set[str] | None = None,
        known_index: _KnownJobIndex | None = None,
    ) -> _CollectResult:
        """Collect results fairly across expanded queries.

        ``max_results`` is the global target of **new** offers (not yet in
        the DB), not a per-query quota and not a raw-fetch quota. The
        round-robin keeps paginating past already-known offers until it
        either accumulates ``max_results`` new ones, exhausts the source,
        or hits the raw-scan safety cap.

        ``known_external_ids`` is the set of offers already persisted for
        this source. Offers in that set are skipped before counting
        against ``max_results`` so a few hundred known duplicates at the
        top of the API feed do not collapse the budget to zero.
        """
        if not queries:
            return _CollectResult([], 0, 0, False)
        known = known_external_ids or set()
        known_jobs = known_index or _KnownJobIndex(frozenset(), frozenset())
        raw_jobs: list[RawJob] = []
        seen_external_ids: set[str] = set()
        skipped_known = 0
        skipped_existing = 0
        raw_seen = 0
        # Give each iterator generous room so the scraper paginates deep
        # enough to surface new offers. The round-robin enforces the real
        # cap below; the per-iterator value is just a safety bound to
        # avoid SerpApi-style overshoots.
        if max_results is None:
            scraper_budget: int | None = None
            raw_seen_cap: int | None = None
        else:
            scraper_budget = max(_RAW_SEEN_MIN, max_results * _RAW_SEEN_MULTIPLIER)
            raw_seen_cap = scraper_budget
        iterators = [
            iter(
                scraper.search(
                    concrete_query,
                    location=location,
                    max_results=scraper_budget,
                    **search_kwargs,
                )
            )
            for concrete_query in queries
        ]
        active = [True] * len(iterators)
        hit_cap = False
        while any(active):
            for i, iterator in enumerate(iterators):
                if not active[i]:
                    continue
                if max_results is not None and len(raw_jobs) >= max_results:
                    return _CollectResult(raw_jobs, skipped_known, skipped_existing, hit_cap)
                if raw_seen_cap is not None and raw_seen >= raw_seen_cap:
                    hit_cap = True
                    return _CollectResult(raw_jobs, skipped_known, skipped_existing, hit_cap)
                try:
                    raw = next(iterator)
                except StopIteration:
                    active[i] = False
                    continue
                raw_seen += 1
                if raw.external_id in seen_external_ids:
                    # Intra-call deduplication (e.g. the same offer surfaced
                    # by two expanded queries) — silent, do not count.
                    continue
                seen_external_ids.add(raw.external_id)
                if raw.external_id in known:
                    # Already persisted by a previous run: skip *without*
                    # touching ``max_results`` so we keep looking for new
                    # offers further down the API feed.
                    skipped_known += 1
                    continue
                if known_jobs.matches(raw):
                    skipped_existing += 1
                    continue
                raw_jobs.append(raw)
                if max_results is not None and len(raw_jobs) >= max_results:
                    return _CollectResult(raw_jobs, skipped_known, skipped_existing, hit_cap)
        return _CollectResult(raw_jobs, skipped_known, skipped_existing, hit_cap)

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


def _audit_base_key(meta: dict[str, Any]) -> tuple:
    return (
        meta.get("query"),
        meta.get("location"),
        meta.get("google_domain"),
        meta.get("hl"),
        meta.get("gl"),
        meta.get("strict_chips"),
    )


def _build_search_audit(raws: list[RawJob]) -> list[dict[str, Any]]:
    """Summarize SerpApi strict-vs-fallback contribution for ingest reports."""
    strict_counts: dict[tuple, int] = {}
    fallback_counts: dict[tuple, int] = {}
    fallback_meta: dict[tuple, dict[str, Any]] = {}

    for raw in raws:
        meta = (raw.source_data or {}).get("_smartapply_search")
        if not isinstance(meta, dict):
            continue
        base_key = _audit_base_key(meta)
        origin = meta.get("result_origin")
        if origin == "strict":
            strict_counts[base_key] = strict_counts.get(base_key, 0) + 1
        elif origin == "fallback":
            fallback_key = (
                *base_key,
                meta.get("fallback_reason"),
                meta.get("fallback_chips"),
                meta.get("fallback_query"),
            )
            fallback_counts[fallback_key] = fallback_counts.get(fallback_key, 0) + 1
            fallback_meta[fallback_key] = meta

    audit: list[dict[str, Any]] = []
    for fallback_key, fallback_added in fallback_counts.items():
        base_key = fallback_key[:6]
        meta = fallback_meta[fallback_key]
        strict_results = strict_counts.get(base_key, 0)
        audit.append(
            {
                "query": meta.get("query"),
                "location": meta.get("location"),
                "google_domain": meta.get("google_domain"),
                "hl": meta.get("hl"),
                "gl": meta.get("gl"),
                "strict_results": strict_results,
                "fallback_added": fallback_added,
                "final_results": strict_results + fallback_added,
                "fallback_reason": meta.get("fallback_reason"),
                "strict_chips": meta.get("strict_chips"),
                "fallback_chips": meta.get("fallback_chips"),
                "fallback_query": meta.get("fallback_query"),
            }
        )
    return audit
