"""Local rule-based job filtering — cheap, deterministic, no LLM."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from unidecode import unidecode

from smartapply.filtering.rules import RuleSet
from smartapply.profile import JobPreferences
from smartapply.utils.experience import required_min_years
from smartapply.utils.location import is_foreign_location


@dataclass
class FilterResult:
    kept: bool
    score: float
    reasons: list[str]


class HasJobFields(Protocol):
    title: str
    company: str
    description: str
    location: str | None
    contract_type: str | None
    remote_policy: str | None


def _norm(s: str | None) -> str:
    return unidecode(s or "").lower()


def ruleset_from_preferences(prefs: JobPreferences) -> RuleSet:
    return RuleSet(
        target_roles=[r.lower() for r in prefs.target_roles],
        deal_breakers=[d.lower() for d in prefs.deal_breakers],
        preferred_locations=[loc.lower() for loc in prefs.preferred_locations],
        accepted_contract_types=[c.lower() for c in prefs.accepted_contract_types],
        accepted_remote_policies=[p.lower() for p in prefs.accepted_remote_policies],
    )


class JobFilter:
    """Score-and-filter pipeline that runs entirely locally."""

    def __init__(self, rules: RuleSet):
        self.rules = rules

    def evaluate(self, job: HasJobFields) -> FilterResult:
        title = _norm(job.title)
        description = _norm(job.description)
        location = _norm(job.location)
        contract = _norm(job.contract_type)
        remote = _norm(job.remote_policy)

        reasons: list[str] = []
        score = 0.5  # neutral baseline

        # --- Hard reject: foreign location ---
        # The candidate only targets the French market. Foreign offers are
        # dropped before any LLM analysis to save tokens.
        if is_foreign_location(job.location):
            reasons.append(f"foreign_location:{(job.location or '').lower()}")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: too-many years of experience required ---
        # Bilingual regex extraction (FR + EN). See utils.experience.
        # We check both title and description because senior signals often
        # live in titles ("Senior Data Scientist - 7+ years").
        required_years = required_min_years(
            f"{job.title or ''}\n{job.description or ''}"
        )
        if required_years is not None and required_years >= self.rules.max_required_years:
            reasons.append(f"experience_required_too_high:{required_years}+ years")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: blocked contract type (internship, alternance, ...) ---
        # Soft penalty on contract_off was not enough — internships sometimes
        # slipped through with a high semantic score. Now they're rejected
        # before any LLM analysis.
        if contract and self.rules.blocked_contract_types:
            matched = next(
                (b for b in self.rules.blocked_contract_types if b in contract),
                None,
            )
            if matched:
                reasons.append(f"blocked_contract_type:{contract} (matched '{matched}')")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: off-target job families in title ---
        # These titles are not "weak signals"; they represent a different job
        # family and should not consume LLM budget even if the description
        # contains Python, data or DevOps keywords.
        if self.rules.title_hard_reject_keywords:
            blocker = next(
                (kw for kw in self.rules.title_hard_reject_keywords if kw in title),
                None,
            )
            if blocker:
                reasons.append(f"title_hard_reject:{blocker}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: seniority label in title ---
        # Catches "Senior Data Scientist", "LEAD DATA SCIENTIST", "Sr. ML
        # Engineer", "Staff Data Scientist", "Principal AI Engineer" — labels
        # that signal a level above the candidate's profile (~2 years).
        if self.rules.seniority_title_hard_reject:
            blocker = next(
                (kw for kw in self.rules.seniority_title_hard_reject if kw in title),
                None,
            )
            if blocker:
                reasons.append(f"seniority_in_title:{blocker.strip()}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard negative signals (deal breakers, blocked seniority, etc.) ---
        for bad in self.rules.deal_breakers:
            if bad and bad in title:
                reasons.append(f"deal_breaker_in_title:{bad}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)
            if bad and bad in description and len(bad) > 3:
                reasons.append(f"deal_breaker_in_description:{bad}")
                score -= 0.15

        for blocker in self.rules.seniority_block_terms:
            if blocker in description or blocker in title:
                reasons.append(f"seniority_blocked:{blocker}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        for token in self.rules.negative_desc_tokens:
            if token in description:
                reasons.append(f"negative_desc_token:{token}")
                score -= 0.15

        analytics_without_python = (
            ("data analyst" in title or " bi" in f" {title}" or "analytics" in title)
            and (
                "pas de developpement python" in description
                or "pas de python" in description
                or "no python" in description
                or "without python" in description
            )
        )
        if analytics_without_python:
            reasons.append("analytics_without_python")
            score -= 0.45

        for kw in self.rules.negative_title_keywords:
            if kw in title:
                reasons.append(f"negative_title:{kw}")
                score -= 0.2

        # --- Positive title signals ---
        positive_hits = 0
        for kw in self.rules.positive_title_keywords:
            if kw in title:
                positive_hits += 1
                reasons.append(f"positive_title:{kw}")
        if positive_hits > 0:
            score += min(0.25, 0.1 * positive_hits)

        target_hit = False
        for role in self.rules.target_roles:
            if role in title:
                target_hit = True
                reasons.append(f"target_role:{role}")
                break
        if target_hit:
            score += 0.2

        # --- Location ---
        if self.rules.preferred_locations:
            if any(loc in location for loc in self.rules.preferred_locations):
                score += 0.1
                reasons.append("location_match")
            elif remote == "remote" and "remote" in self.rules.accepted_remote_policies:
                score += 0.05
                reasons.append("remote_acceptable")
            else:
                score -= 0.1
                reasons.append("location_mismatch")

        # --- Contract type ---
        if self.rules.accepted_contract_types and contract:
            if any(ct in contract for ct in self.rules.accepted_contract_types):
                reasons.append(f"contract_ok:{contract}")
            else:
                score -= 0.1
                reasons.append(f"contract_off:{contract}")

        # --- Remote policy ---
        if self.rules.accepted_remote_policies and remote:
            if any(rp in remote for rp in self.rules.accepted_remote_policies):
                reasons.append(f"remote_ok:{remote}")
            else:
                score -= 0.05

        # Clamp
        score = max(0.0, min(1.0, score))

        kept = score >= self.rules.min_score
        if not kept:
            reasons.append(f"below_min_score:{self.rules.min_score}")
        return FilterResult(kept=kept, score=score, reasons=reasons)

    def filter_many(
        self, jobs: list[HasJobFields]
    ) -> tuple[list[HasJobFields], list[tuple[HasJobFields, FilterResult]]]:
        kept: list[HasJobFields] = []
        evaluated: list[tuple[HasJobFields, FilterResult]] = []
        for job in jobs:
            result = self.evaluate(job)
            evaluated.append((job, result))
            if result.kept:
                kept.append(job)
        return kept, evaluated
