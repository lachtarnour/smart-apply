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
4. Reorders ``selected_skills`` and ``skills_order`` so that ``must_show``
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
        existing_lower = {s.lower() for s in filtered[cid]}
        for skill in skills:
            norm = _normalize(skill)
            if norm in forbidden_active:
                continue
            if norm in existing_lower:
                continue
            if norm not in allowed_skills_lower:
                continue
            filtered[cid].append(skill)
            existing_lower.add(skill.lower())

    # Promote must_show categories to the top, preserve the rest of the order.
    must_show_order: list[str] = [
        cid for cid in must_show.keys() if filtered.get(cid)
    ]
    final_order: list[str] = list(must_show_order)
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
