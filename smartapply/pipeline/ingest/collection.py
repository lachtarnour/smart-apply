"""Round-robin source collection with known-offer skipping."""

from __future__ import annotations

from smartapply.offers import RawJob
from smartapply.pipeline.ingest.dedupe import _KnownJobIndex
from smartapply.pipeline.ingest.reports import _CollectResult

_RAW_SEEN_MULTIPLIER = 10
_RAW_SEEN_MIN = 50


def collect_round_robin(
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
