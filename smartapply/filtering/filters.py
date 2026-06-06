"""Local rule-based job filtering — cheap, deterministic, no LLM."""

from __future__ import annotations

import re

from smartapply.filtering import contract_signals, location_signals, role_signals
from smartapply.filtering import seniority as seniority_signals
from smartapply.filtering.preferences import ruleset_from_preferences
from smartapply.filtering.rules import RuleSet
from smartapply.filtering.source_facts import FilterFacts, build_filter_facts
from smartapply.filtering.text import contains_any as _contains_any
from smartapply.filtering.text import has_word as _has_word
from smartapply.filtering.text import norm as _norm
from smartapply.filtering.types import FilterResult, HasJobFields
from smartapply.utils.contracts import (
    INCOMPATIBLE_CONTRACT_TAGS,
    TAG_CONTRACTOR,
    TAG_PART_TIME,
    contract_matches_accepted,
    contract_type_tags,
    contract_types_to_tags,
)
from smartapply.utils.experience import required_min_years
from smartapply.utils.location import is_foreign_location, is_french_location

_has_apprenticeship_contract_context = (
    contract_signals.has_apprenticeship_contract_context
)
_has_cdd_contract_context = contract_signals.has_cdd_contract_context
_has_freelance_contract_context = contract_signals.has_freelance_contract_context
_has_independent_contract_context = contract_signals.has_independent_contract_context
_has_stage_contract_context = contract_signals.has_stage_contract_context
_visible_blocked_contract_marker = contract_signals.visible_blocked_contract_marker

_visible_foreign_location_marker = location_signals.visible_foreign_location_marker
_has_france_scope = location_signals.has_france_scope
_is_remote_france = location_signals.is_remote_france
_specific_preferred_locations = location_signals.specific_preferred_locations

_ANALYTICAL_OWNERSHIP_TOKENS = role_signals.ANALYTICAL_OWNERSHIP_TOKENS
_CORE_DATA_TECH_TOKENS = role_signals.CORE_DATA_TECH_TOKENS
_DATA_AI_ANCHOR_TOKENS = role_signals.DATA_AI_ANCHOR_TOKENS
_DATA_ENGINEERING_PLATFORM_TOKENS = role_signals.DATA_ENGINEERING_PLATFORM_TOKENS
_FINANCE_REPORTING_CONTEXT_TOKENS = role_signals.FINANCE_REPORTING_CONTEXT_TOKENS
_ML_ANALYTICS_SCOPE_TOKENS = role_signals.ML_ANALYTICS_SCOPE_TOKENS
_NEGATED_CORE_DATA_TECH_TOKENS = role_signals.NEGATED_CORE_DATA_TECH_TOKENS
_REPORTING_BI_TOKENS = role_signals.REPORTING_BI_TOKENS
_WEB_ANALYTICS_TRACKING_TOKENS = role_signals.WEB_ANALYTICS_TRACKING_TOKENS

_has_candidate_leadership_responsibility = (
    seniority_signals.has_candidate_leadership_responsibility
)
_has_hidden_senior_role = seniority_signals.has_hidden_senior_role
_title_seniority_or_management_marker = (
    seniority_signals.title_seniority_or_management_marker
)

_PRESTATAIRE_CONTEXT_PATTERNS = (
    r"\bmission\s+(?:en\s+)?freelance\b",
    r"\bmission\s+de\s+prestation\b",
    r"\bcontexte\s+de\s+la\s+prestation\b",
    r"\bprestation\s+s\s+inscrit\b",
    r"\btarif\s+journalier\b",
    r"\btjm\b",
    r"\bdate\s+de\s+prochaine\s+disponibilite\b",
    r"\bfreelance\b",
    r"\bfreelancer\b",
    r"\bcontractor\b",
    r"\bportage\s+salarial\b",
    r"\bstatut\s+independant\b",
)
_PRESTATAIRE_SOURCE_MARKERS = (
    "free-work",
    "free work",
    "freelance.com",
    "freelance com",
    "freelancerepublik",
    "freelance-republik",
    "malt",
    "lehibou",
    "comet",
)


def _fact_source_suffix(facts: FilterFacts) -> str:
    source = _norm(facts.source).replace(" ", "_")
    return source or "unknown"


def _format_years(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _contract_for_matching(
    job_contract_type: str | None,
    facts: FilterFacts,
) -> str | None:
    if job_contract_type and contract_type_tags(job_contract_type):
        return job_contract_type
    return facts.structured_contract_type or job_contract_type


def _structured_contract_tags(facts: FilterFacts) -> set[str]:
    tags = contract_type_tags(facts.structured_contract_type)
    return tags


def _prestataire_is_corroborated(
    *,
    title: str,
    description: str,
    company: str,
    application_url: str | None,
) -> bool:
    visible_text = f"{title}\n{description}\n{company}"
    if any(re.search(pattern, visible_text) for pattern in _PRESTATAIRE_CONTEXT_PATTERNS):
        return True
    url_text = _norm(application_url)
    return any(marker in url_text for marker in _PRESTATAIRE_SOURCE_MARKERS)


def _reason_value(value: str | None) -> str:
    return _norm(value).replace(" ", "_") or "unknown"


def _rome_context_reason(facts: FilterFacts) -> str | None:
    parts = [
        value
        for value in (
            facts.structured_rome_code,
            facts.structured_rome_label,
            facts.structured_appellation_label,
        )
        if value
    ]
    if not parts:
        return None
    return "rome_context:" + ":".join(_reason_value(part) for part in parts)


def _search_context_reason(facts: FilterFacts) -> str | None:
    parts = []
    if facts.structured_search_origin:
        parts.append(f"origin={_reason_value(facts.structured_search_origin)}")
    if facts.structured_search_chips:
        parts.append(f"chips={_reason_value(facts.structured_search_chips)}")
    if not parts:
        return None
    return "search_context:" + ",".join(parts)


__all__ = [
    "FilterResult",
    "HasJobFields",
    "JobFilter",
    "ruleset_from_preferences",
    "_has_apprenticeship_contract_context",
    "_has_cdd_contract_context",
    "_has_candidate_leadership_responsibility",
    "_has_freelance_contract_context",
    "_has_independent_contract_context",
    "_has_stage_contract_context",
    "_visible_blocked_contract_marker",
]


class JobFilter:
    """Score-and-filter pipeline that runs entirely locally."""

    def __init__(self, rules: RuleSet, *, use_source_facts: bool = True):
        self.rules = rules
        self.use_source_facts = use_source_facts

    def evaluate(self, job: HasJobFields) -> FilterResult:
        facts = build_filter_facts(job) if self.use_source_facts else FilterFacts()
        title = _norm(job.title)
        company = _norm(job.company)
        description = _norm(job.description)
        location_value = facts.structured_location or job.location
        location = _norm(location_value)
        contract = _norm(job.contract_type)
        remote_value = job.remote_policy or facts.structured_remote_policy
        remote = _norm(remote_value)
        combined = f"{title}\n{description}"

        reasons: list[str] = []
        score = 0.5  # neutral baseline
        if rome_context := _rome_context_reason(facts):
            reasons.append(rome_context)
        if search_context := _search_context_reason(facts):
            reasons.append(search_context)
        if facts.structured_remote_policy:
            reasons.append(
                f"remote_structured:{_reason_value(facts.structured_remote_policy)}"
            )

        # --- Hard reject: foreign location ---
        # The candidate only targets the French market. Foreign offers are
        # dropped before any LLM analysis to save tokens.
        if is_foreign_location(location_value):
            reasons.append(f"location_rejected_foreign:{(location_value or '').lower()}")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        if foreign_marker := _visible_foreign_location_marker(title, description):
            reasons.append(f"location_rejected_foreign_text:{foreign_marker}")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: too-many years of experience required ---
        # Bilingual regex extraction (FR + EN). See utils.experience.
        # We check both title and description because senior signals often
        # live in titles ("Senior Data Scientist - 7+ years").
        if facts.experience_min_years is not None:
            required_years = facts.experience_min_years
            reasons.append(
                f"experience_structured_{_fact_source_suffix(facts)}:"
                f"{_format_years(required_years)}"
            )
        elif facts.experience_required is False and facts.experience_requirement:
            required_years = None
            reasons.append(
                f"experience_structured_{_fact_source_suffix(facts)}:"
                f"{facts.experience_requirement}"
            )
        else:
            required_years = required_min_years(
                f"{job.title or ''}\n{job.description or ''}"
            )
        if required_years is not None and required_years >= self.rules.max_required_years:
            reasons.append(
                f"experience_required_too_high:{_format_years(required_years)}+ years"
            )
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: blocked contract type (internship, alternance, ...) ---
        # Soft penalty on contract_off was not enough — internships sometimes
        # slipped through with a high semantic score. Now they're rejected
        # before any LLM analysis.
        if facts.structured_alternance is True:
            reasons.append("blocked_contract_structured:alternance (tag 'apprenticeship')")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        contract_tags = contract_type_tags(job.contract_type)
        incompatible_tags = sorted(contract_tags & INCOMPATIBLE_CONTRACT_TAGS)
        if contract and incompatible_tags:
            reasons.append(
                f"blocked_contract_type:{contract} (tag '{incompatible_tags[0]}')"
            )
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        structured_contract = facts.structured_contract_type
        structured_contract_norm = _norm(structured_contract)
        structured_contract_tags = _structured_contract_tags(facts)
        if structured_contract_norm == "prestataire":
            if _prestataire_is_corroborated(
                title=title,
                description=description,
                company=company,
                application_url=getattr(job, "application_url", None),
            ):
                structured_contract_tags.add(TAG_CONTRACTOR)
            else:
                reasons.append("contract_structured_uncorroborated:prestataire")
        structured_incompatible = sorted(
            structured_contract_tags & INCOMPATIBLE_CONTRACT_TAGS
        )
        if structured_contract_norm and structured_incompatible:
            reasons.append(
                f"blocked_contract_structured:{structured_contract_norm} "
                f"(tag '{structured_incompatible[0]}')"
            )
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        work_time = facts.structured_work_time
        work_time_tags = contract_type_tags(work_time)
        part_time_not_accepted = TAG_PART_TIME not in contract_types_to_tags(
            self.rules.accepted_contract_types
        )
        if TAG_PART_TIME in work_time_tags and part_time_not_accepted:
            reasons.append(
                f"blocked_work_time_structured:{_reason_value(work_time)} "
                "(tag 'part_time')"
            )
            return FilterResult(kept=False, score=0.0, reasons=reasons)
        if work_time:
            reasons.append(f"work_time_structured:{_reason_value(work_time)}")

        if contract and self.rules.blocked_contract_types:
            matched = next(
                (b for b in self.rules.blocked_contract_types if b in contract),
                None,
            )
            if matched:
                reasons.append(f"blocked_contract_type:{contract} (matched '{matched}')")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        # Some sources put "Freelance" / "Indépendant" only in the title or
        # description while the structured contract is missing. Keep the same
        # configurable blocked_contract_types list, but search visible text too.
        if self.rules.blocked_contract_types:
            matched = _visible_blocked_contract_marker(
                title=title,
                description=description,
                blocked_contract_types=self.rules.blocked_contract_types,
            )
            if matched:
                reasons.append(f"blocked_contract_visible_text:{matched}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        accepted_contract_text = " ".join(
            _norm(contract_type) for contract_type in self.rules.accepted_contract_types
        )
        if "cdd" not in accepted_contract_text and _has_cdd_contract_context(
            title,
            description,
        ):
            reasons.append("blocked_contract_visible_text:cdd")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: off-target job families in title ---
        # These titles are not "weak signals"; they represent a different job
        # family and should not consume LLM budget even if the description
        # contains Python, data or DevOps keywords.
        if off_target := role_signals.title_off_target_marker(title):
            reasons.append(f"title_hard_reject:{off_target}")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        if self.rules.title_hard_reject_keywords:
            blocker = next(
                (
                    kw
                    for kw in self.rules.title_hard_reject_keywords
                    if kw in title
                    and not role_signals.should_skip_configured_title_hard_reject(
                        title,
                        kw,
                    )
                ),
                None,
            )
            if blocker:
                reasons.append(f"title_hard_reject:{blocker}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard reject: seniority label in title ---
        # Catches "Senior Data Scientist", "LEAD DATA SCIENTIST", "Sr. ML
        # Engineer", "Staff Data Scientist", "Principal AI Engineer" — labels
        # that signal a level above the candidate's profile (~2 years).
        blocker = _title_seniority_or_management_marker(
            title,
            self.rules.seniority_title_hard_reject,
        )
        if blocker:
            reasons.append(f"seniority_in_title:{blocker.strip()}")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        # --- Hard negative signals (deal breakers, blocked seniority, etc.) ---
        for bad in self.rules.deal_breakers:
            title_match = _has_word(title, bad) if bad == "sales" else bad and bad in title
            description_match = (
                _has_word(description, bad)
                if bad == "sales"
                else bad and bad in description
            )
            if title_match:
                reasons.append(f"deal_breaker_in_title:{bad}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)
            if description_match and len(bad) > 3:
                reasons.append(f"deal_breaker_in_description:{bad}")
                score -= 0.15

        for blocker in self.rules.seniority_block_terms:
            if blocker in description or blocker in title:
                reasons.append(f"seniority_blocked:{blocker}")
                return FilterResult(kept=False, score=0.0, reasons=reasons)

        hidden_senior_role = _has_hidden_senior_role(combined)
        team_leadership_role = _has_candidate_leadership_responsibility(description)
        if hidden_senior_role or team_leadership_role:
            reasons.append("seniority_or_leadership_in_description")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        for token in self.rules.negative_desc_tokens:
            if token in description:
                reasons.append(f"negative_desc_token:{token}")
                score -= 0.15

        web_analytics_tracking_focus = (
            _contains_any(combined, _WEB_ANALYTICS_TRACKING_TOKENS)
            and not _contains_any(combined, _DATA_AI_ANCHOR_TOKENS)
            and not (
                role_signals.has_analytics_title_scope(title)
                and _contains_any(combined, _ANALYTICAL_OWNERSHIP_TOKENS)
            )
        )
        if web_analytics_tracking_focus:
            reasons.append("web_analytics_tracking_focus")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        finance_reporting_bi_focus = (
            _contains_any(combined, ("power bi", "powerbi", "power query"))
            and _contains_any(combined, ("reporting", "tableaux de bord", "dashboard"))
            and _contains_any(combined, _FINANCE_REPORTING_CONTEXT_TOKENS)
            and not _contains_any(combined, _CORE_DATA_TECH_TOKENS)
            and not _contains_any(combined, _ANALYTICAL_OWNERSHIP_TOKENS)
        )
        if finance_reporting_bi_focus:
            reasons.append("finance_reporting_bi_without_core_data_tech")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        reporting_without_core_data_tech = (
            ("reporting" in title or "reporting" in description or "dashboard" in description)
            and _contains_any(description, _NEGATED_CORE_DATA_TECH_TOKENS)
        )
        if reporting_without_core_data_tech:
            reasons.append("reporting_without_core_data_tech")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        reporting_bi_focus = (
            (
                "analyst" in title
                or "analyste" in title
                or "analytics" in title
                or "reporting" in title
            )
            and _contains_any(combined, _REPORTING_BI_TOKENS)
            and not _contains_any(combined, _ANALYTICAL_OWNERSHIP_TOKENS)
        )
        if reporting_bi_focus:
            reasons.append("reporting_bi_without_analytical_ownership")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        pure_data_engineering_role = (
            bool(re.search(r"\bdata engineer(?:ing)?\b", title))
            and _contains_any(combined, _DATA_ENGINEERING_PLATFORM_TOKENS)
            and not _contains_any(combined, _ML_ANALYTICS_SCOPE_TOKENS)
        )
        if pure_data_engineering_role:
            reasons.append("pure_data_engineering_role")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

        mep_data_center_focus = (
            ("mep" in title or "mep" in description)
            and ("data center" in title or "data center" in description)
        )
        if mep_data_center_focus:
            reasons.append("mep_data_center_focus")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

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
            if (_has_word(title, kw) if kw == "sales" else kw in title):
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
            specific_locations = _specific_preferred_locations(
                self.rules.preferred_locations
            )
            accepts_france = _has_france_scope(self.rules.preferred_locations)
            if any(loc in location for loc in specific_locations):
                score += 0.1
                reasons.append("location_preferred")
            elif _is_remote_france(location_value, remote):
                score += 0.05
                reasons.append("location_remote_france")
            elif accepts_france and is_french_location(location_value):
                score += 0.05
                reasons.append("location_accepted_france")
            elif remote == "remote" and "remote" in self.rules.accepted_remote_policies:
                score += 0.05
                reasons.append("location_remote_accepted")
            else:
                score -= 0.05
                reasons.append("location_unknown")

        # --- Contract type ---
        contract_for_matching = _contract_for_matching(job.contract_type, facts)
        contract = _norm(contract_for_matching)
        if self.rules.accepted_contract_types and contract:
            if contract_matches_accepted(
                contract_for_matching,
                self.rules.accepted_contract_types,
            ):
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

        if not role_signals.has_role_relevance_signal(
            title=title,
            description=description,
            positive_title_keywords=self.rules.positive_title_keywords,
            target_roles=self.rules.target_roles,
        ):
            reasons.append("missing_role_relevance")
            return FilterResult(kept=False, score=0.0, reasons=reasons)

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
