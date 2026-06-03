"""Apply a role-family contract to an LLM-produced CV.

The contract is a deterministic post-filter that:
1. Strips skills listed in ``forbidden`` (except when an explicit
   ``required_skill`` from the offer matches the term — in that case the
   forbidden lock lifts for that specific skill, on the assumption that the
   offer truly wants it).
2. Drops blocks whose ``category_id`` is not in ``allowed_categories``,
   unless one of their skills survived as offer-anchored (i.e. it appeared in
   ``required_skills`` or ``cv_keywords_to_include``).
3. Adds the ``must_show`` skills that are missing, anchoring a coherent
   baseline for the role (e.g. PyTorch + Scikit-learn for a Data Scientist).
4. Fills a minimum number of skills from contract-approved fallback skills.
5. Reorders ``selected_skills`` and ``skills_order`` so that ``must_show``
   categories come first, then the rest in their existing order.

The contract operates on canonical profile skills only — anything that does
not exist in the candidate's ``allowed_skills`` whitelist is silently
ignored, so the contract can never reintroduce an unsupported claim.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from smartapply.cv.role_family import classify, has_data_scientist_ia_signal
from smartapply.llm import AdaptedCV, JobAnalysis, SkillSelectionBlock


_CONTRACTS_PATH = Path(__file__).with_name("role_contracts.json")

_DS_IA_EXTRA_SKILLS: tuple[str, ...] = ("NLP", "Transformers", "Hugging Face")


@lru_cache(maxsize=1)
def load_contracts() -> dict[str, dict[str, Any]]:
    """Read the V1 contracts JSON. Cached across calls."""
    with _CONTRACTS_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _normalize(term: str) -> str:
    return " ".join((term or "").lower().split())


def _is_explicit_offer_skill(term: str, offer_terms: set[str]) -> bool:
    """True if ``term`` matches an explicit offer term (exact or substring).

    Mirrors the loose matching used by ``_ensure_supported_offer_skills`` so
    the two post-filters agree on what counts as "the offer asked for it".
    """
    norm = _normalize(term)
    if not norm:
        return False
    if norm in offer_terms:
        return True
    if len(norm) <= 2:
        return False
    for other in offer_terms:
        if not other:
            continue
        if len(other) <= 2:
            continue
        if norm == other or norm in other or other in norm:
            return True
        if re.search(rf"(?<![a-z0-9]){re.escape(norm)}(?![a-z0-9])", other):
            return True
    return False


def _augmented_must_show(
    family: str,
    contract: dict[str, Any],
    analysis: JobAnalysis,
    job_title: str,
) -> dict[str, list[str]]:
    """``must_show`` plus the DS-IA conditional augmentation."""
    base: dict[str, list[str]] = {
        cid: list(skills) for cid, skills in contract.get("must_show", {}).items()
    }
    if family == "data_scientist" and has_data_scientist_ia_signal(
        analysis, job_title
    ):
        ml_ai = base.setdefault("ml_ai", [])
        existing_lower = {s.lower() for s in ml_ai}
        for skill in _DS_IA_EXTRA_SKILLS:
            if skill.lower() not in existing_lower:
                ml_ai.append(skill)
                existing_lower.add(skill.lower())
    return base


def _active_forbidden(
    contract: dict[str, Any],
    analysis: JobAnalysis,
) -> set[str]:
    """``forbidden`` minus the terms explicitly requested by the offer."""
    forbidden = {_normalize(s) for s in contract.get("forbidden", []) if s}
    if not forbidden:
        return set()
    offer_terms = {
        _normalize(term)
        for term in list(analysis.required_skills) + list(analysis.cv_keywords_to_include)
        if term
    }
    return {
        skill
        for skill in forbidden
        if not _is_explicit_offer_skill(skill, offer_terms)
    }


def _offer_anchored_skills(analysis: JobAnalysis) -> set[str]:
    return {
        _normalize(term)
        for term in list(analysis.required_skills) + list(analysis.cv_keywords_to_include)
        if term
    }


def _selected_skill_count(skills_by_category: dict[str, list[str]]) -> int:
    return sum(len(skills) for skills in skills_by_category.values())


def _add_skill_if_supported(
    skills_by_category: dict[str, list[str]],
    category_order: list[str],
    *,
    category_id: str,
    skill: str,
    forbidden_active: set[str],
    allowed_skills_lower: set[str],
) -> bool:
    norm = _normalize(skill)
    if not norm:
        return False
    if norm in forbidden_active:
        return False
    if norm not in allowed_skills_lower:
        return False
    if category_id not in skills_by_category:
        skills_by_category[category_id] = []
        category_order.append(category_id)
    existing_lower = {s.lower() for s in skills_by_category[category_id]}
    if norm in existing_lower:
        return False
    skills_by_category[category_id].append(skill)
    return True


def _fill_minimum_skills(
    filtered: dict[str, list[str]],
    category_order: list[str],
    *,
    contract: dict[str, Any],
    allowed_categories: set[str],
    forbidden_active: set[str],
    allowed_skills_lower: set[str],
) -> None:
    """Add contract-approved fallback skills until ``min_total_skills`` is met."""
    min_total = int(contract.get("min_total_skills", 0) or 0)
    fill_skills = contract.get("fill_skills", {})
    if min_total <= 0 or not isinstance(fill_skills, dict):
        return

    for cid, skills in fill_skills.items():
        if allowed_categories and cid not in allowed_categories:
            continue
        if not isinstance(skills, list):
            continue
        for skill in skills:
            if _selected_skill_count(filtered) >= min_total:
                return
            if isinstance(skill, str):
                _add_skill_if_supported(
                    filtered,
                    category_order,
                    category_id=cid,
                    skill=skill,
                    forbidden_active=forbidden_active,
                    allowed_skills_lower=allowed_skills_lower,
                )


def _apply_global_baseline(
    filtered: dict[str, list[str]],
    category_order: list[str],
    *,
    contracts: dict[str, dict[str, Any]],
    allowed_skills_lower: set[str],
) -> list[str]:
    """Always keep the candidate's core positioning visible in the CV."""
    baseline = contracts.get("_global_baseline", {})
    if not baseline.get("enabled", True):
        return []
    skills_by_category = baseline.get("skills", {})
    if not isinstance(skills_by_category, dict):
        return []

    baseline_categories: list[str] = []
    for cid, skills in skills_by_category.items():
        if not isinstance(skills, list):
            continue
        for skill in skills:
            if not isinstance(skill, str):
                continue
            if _normalize(skill) in {
                _normalize(existing)
                for existing_skills in filtered.values()
                for existing in existing_skills
            }:
                continue
            _add_skill_if_supported(
                filtered,
                category_order,
                category_id=cid,
                skill=skill,
                forbidden_active=set(),
                allowed_skills_lower=allowed_skills_lower,
            )
        if filtered.get(cid) and cid not in baseline_categories:
            baseline_categories.append(cid)
    return baseline_categories


def apply_contract(
    adapted: AdaptedCV,
    *,
    analysis: JobAnalysis,
    job_title: str,
    allowed_skills_lower: set[str],
    contracts: dict[str, dict[str, Any]] | None = None,
) -> tuple[AdaptedCV, str]:
    """Apply the role-family contract for ``analysis``.

    Returns the updated CV plus the family id used (``other`` is a no-op).
    """
    family = classify(analysis, title=job_title)
    contracts = contracts or load_contracts()
    contract = contracts.get(family)
    if contract is None:
        return adapted, family

    allowed_categories = set(contract.get("allowed_categories", []))
    forbidden_active = _active_forbidden(contract, analysis)
    must_show = _augmented_must_show(family, contract, analysis, job_title)
    offer_terms = _offer_anchored_skills(analysis)

    # Build the filtered selection. Preserve LLM ordering for kept categories.
    filtered: dict[str, list[str]] = {}
    category_order: list[str] = []
    for block in adapted.selected_skills:
        cid = block.category_id
        kept: list[str] = []
        for skill in block.skills:
            if _normalize(skill) in forbidden_active:
                continue
            kept.append(skill)
        if not kept:
            continue
        if allowed_categories and cid not in allowed_categories:
            # Keep only the skills explicitly required by the offer — the
            # category survives only if at least one such skill remains.
            offer_kept = [
                skill for skill in kept if _is_explicit_offer_skill(skill, offer_terms)
            ]
            if not offer_kept:
                continue
            kept = offer_kept
        filtered[cid] = kept
        category_order.append(cid)

    # Add must_show skills that are missing (must already exist in the
    # candidate's profile whitelist — never invent).
    for cid, skills in must_show.items():
        if cid not in filtered:
            filtered[cid] = []
            category_order.append(cid)
        for skill in skills:
            _add_skill_if_supported(
                filtered,
                category_order,
                category_id=cid,
                skill=skill,
                forbidden_active=forbidden_active,
                allowed_skills_lower=allowed_skills_lower,
            )

    _fill_minimum_skills(
        filtered,
        category_order,
        contract=contract,
        allowed_categories=allowed_categories,
        forbidden_active=forbidden_active,
        allowed_skills_lower=allowed_skills_lower,
    )
    baseline_order = _apply_global_baseline(
        filtered,
        category_order,
        contracts=contracts,
        allowed_skills_lower=allowed_skills_lower,
    )

    # Promote must_show categories to the top, preserve the rest of the order.
    priority_order: list[str] = []
    priority_candidates = list(baseline_order) + list(must_show.keys())
    for cid in ("ml_ai", "data_analysis", "data_infra"):
        if cid in priority_candidates and filtered.get(cid):
            priority_order.append(cid)
    for cid in priority_candidates:
        if filtered.get(cid) and cid not in priority_order:
            priority_order.append(cid)
    final_order: list[str] = list(priority_order)
    for cid in category_order:
        if cid not in final_order and filtered.get(cid):
            final_order.append(cid)

    new_selected = [
        SkillSelectionBlock(category_id=cid, skills=filtered[cid])
        for cid in final_order
    ]
    return (
        adapted.model_copy(
            update={
                "selected_skills": new_selected,
                "skills_order": list(final_order),
            }
        ),
        family,
    )
