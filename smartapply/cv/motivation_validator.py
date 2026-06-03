"""Light validation for generated motivation letters."""

from __future__ import annotations

import re

from smartapply.cv.validator import ValidationResult
from smartapply.llm import AdaptedCV, JobAnalysis, MotivationLetter
from smartapply.profile import Profile


_NON_DISPLAY_DOMAIN_TERMS = {
    "ai",
    "artificial intelligence",
    "deep learning",
    "machine learning",
    "data analysis",
    "computer vision",
    "nlp",
    "llm",
    "llms",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text or ""))


class MotivationLetterValidator:
    """Check that the letter stays tied to selected profile evidence."""

    def __init__(self, profile: Profile, min_words: int = 180, max_words: int = 280):
        self.profile = profile
        self.min_words = min_words
        self.max_words = max_words
        self.allowed_skills = profile.skills.allowed_skills
        self.projects_by_id = {p.id: p for p in profile.projects}
        self.experiences_by_id = {e.id: e for e in profile.experiences}

    def validate(
        self,
        letter: MotivationLetter,
        *,
        cv: AdaptedCV,
        analysis: JobAnalysis,
    ) -> ValidationResult:
        warnings: list[str] = []
        body_lower = _normalize(letter.body)

        count = _word_count(letter.body)
        if count < self.min_words:
            warnings.append(f"letter_too_short:{count}")
        if count > self.max_words:
            warnings.append(f"letter_too_long:{count}")

        for term in self._unsupported_offer_terms(analysis):
            if _normalize(term) in body_lower:
                warnings.append(f"unsupported_term_in_letter:{term}")

        if not self._references_selected_evidence(body_lower, cv):
            warnings.append("letter_may_not_reference_selected_evidence")

        return ValidationResult(ok=True, warnings=warnings)

    def _unsupported_offer_terms(self, analysis: JobAnalysis) -> list[str]:
        terms: list[str] = []
        seen: set[str] = set()
        for raw in list(analysis.required_skills) + list(analysis.cv_keywords_to_include):
            term = " ".join((raw or "").split())
            key = term.lower()
            if not term or key in seen or key in _NON_DISPLAY_DOMAIN_TERMS:
                continue
            seen.add(key)
            if self._term_supported_by_allowed_skill(term):
                continue
            terms.append(term)
        return terms

    def _term_supported_by_allowed_skill(self, term: str) -> bool:
        normalized = _normalize(term)
        for skill in self.allowed_skills:
            skill_norm = _normalize(skill)
            if not skill_norm:
                continue
            if normalized == skill_norm:
                return True
            if len(skill_norm) > 2 and (skill_norm in normalized or normalized in skill_norm):
                return True
        return False

    def _references_selected_evidence(self, body_lower: str, cv: AdaptedCV) -> bool:
        evidence_terms: set[str] = set()
        for project_id in cv.selected_project_ids:
            project = self.projects_by_id.get(project_id)
            if project:
                evidence_terms.add(project.name)
                evidence_terms.update(project.keywords[:4])
            evidence_terms.add(project_id)

        for exp in cv.selected_experiences:
            source = self.experiences_by_id.get(exp.source_id)
            if source:
                evidence_terms.add(source.company)
                evidence_terms.add(source.title)
                evidence_terms.update(source.keywords[:4])
            evidence_terms.add(exp.source_id)
            for bullet in exp.bullets:
                evidence_terms.add(bullet.source_id)

        normalized_terms = [
            _normalize(term)
            for term in evidence_terms
            if len(_normalize(term)) >= 4
        ]
        return any(term in body_lower for term in normalized_terms)
