"""Cross-source job deduplication.

Two jobs are treated as duplicates when:
- their normalized company names match exactly, and
- their fuzzy title score >= ``title_threshold``, and
- their fuzzy description score >= ``desc_threshold``.

The class returns transitive groups of duplicates and a deduplicated list
(keeping the first occurrence — useful when iterating sources in
priority order).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from rapidfuzz import fuzz
from unidecode import unidecode

from smartapply.config import get_settings

_COMPANY_SUFFIXES = re.compile(
    r"\b(s\.?a\.?s\.?|s\.?a\.?|sarl|s\.a\.r\.l\.|ltd\.?|inc\.?|llc|gmbh|b\.?v\.?|n\.?v\.?|plc|co\.?|corp\.?|corporation|company)\b",
    flags=re.IGNORECASE,
)


@runtime_checkable
class JobLike(Protocol):
    title: str
    company: str
    description: str
    external_id: str


@dataclass
class DedupReport:
    unique: list[JobLike]
    duplicate_groups: list[list[JobLike]]

    @property
    def n_duplicates_removed(self) -> int:
        return sum(len(g) - 1 for g in self.duplicate_groups)


def normalize_company(name: str) -> str:
    s = unidecode(name or "").lower().strip()
    s = _COMPANY_SUFFIXES.sub(" ", s)
    s = re.sub(r"[^\w]+", " ", s).strip()
    return s


def normalize_title(title: str) -> str:
    s = unidecode(title or "").lower()
    # Drop common H/F-like role suffixes / contract indicators
    s = re.sub(r"\b(h/f|f/h|m/f|cdi|cdd|stagiaire|freelance|junior|senior)\b", "", s)
    s = re.sub(r"[^\w\s]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


class Deduplicator:
    def __init__(
        self,
        title_threshold: int | None = None,
        desc_threshold: int | None = None,
    ):
        settings = get_settings()
        self.title_threshold = (
            title_threshold if title_threshold is not None else settings.dedup_title_threshold
        )
        self.desc_threshold = (
            desc_threshold if desc_threshold is not None else settings.dedup_desc_threshold
        )

    # -------------------- public API --------------------

    def deduplicate(self, jobs: Sequence[JobLike]) -> DedupReport:
        # Bucket by normalized company; only jobs sharing the same company
        # bucket get compared. This makes N² comparisons local instead of global.
        buckets: dict[str, list[int]] = {}
        for idx, job in enumerate(jobs):
            key = normalize_company(job.company)
            buckets.setdefault(key, []).append(idx)

        # Union-Find for transitive grouping
        parent = list(range(len(jobs)))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                # Keep the smallest index as root to preserve original order
                if ra < rb:
                    parent[rb] = ra
                else:
                    parent[ra] = rb

        for indices in buckets.values():
            if len(indices) < 2:
                continue
            for i_pos, i in enumerate(indices):
                for j in indices[i_pos + 1 :]:
                    if self._are_duplicates(jobs[i], jobs[j]):
                        union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(len(jobs)):
            groups.setdefault(find(i), []).append(i)

        unique: list[JobLike] = []
        duplicate_groups: list[list[JobLike]] = []
        for _root, members in groups.items():
            members.sort()
            unique.append(jobs[members[0]])
            if len(members) > 1:
                duplicate_groups.append([jobs[m] for m in members])

        # Preserve original ordering
        unique.sort(key=lambda j: jobs.index(j))
        return DedupReport(unique=unique, duplicate_groups=duplicate_groups)

    # -------------------- internals --------------------

    def _are_duplicates(self, a: JobLike, b: JobLike) -> bool:
        title_a, title_b = normalize_title(a.title), normalize_title(b.title)
        title_score = fuzz.token_set_ratio(title_a, title_b)
        if title_score < self.title_threshold:
            return False
        # Truncate descriptions to keep the comparison fast
        desc_a = (a.description or "")[:2000]
        desc_b = (b.description or "")[:2000]
        if not desc_a or not desc_b:
            # No description on one side — rely on title alone
            return title_score >= self.title_threshold + 5
        desc_score = fuzz.token_set_ratio(desc_a, desc_b)
        return desc_score >= self.desc_threshold
