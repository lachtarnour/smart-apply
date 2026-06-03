"""CV adapter — produces an AdaptedCV via the LLM, anchored on the profile."""

from __future__ import annotations

from smartapply.cv.role_contracts import apply_contract
from smartapply.cv.selector import CvBlockSelector, SelectionResult
from smartapply.llm import (
    AdaptedCV,
    ApplicationDraft,
    EmailDraft,
    JobAnalysis,
    LLMProvider,
    SkillSelectionBlock,
    get_llm_provider,
)
from smartapply.llm.prompts import application_draft, cv_adaptation
from smartapply.profile import Profile
from smartapply.ranking.embeddings import (
    EmbeddingsProvider,
    get_embeddings_provider,
)


class CvAdapter:
    def __init__(
        self,
        profile: Profile,
        llm: LLMProvider | None = None,
        embeddings: EmbeddingsProvider | None = None,
    ):
        self.profile = profile
        self.llm = llm or get_llm_provider()
        self.embeddings = embeddings or get_embeddings_provider()
        self.selector = CvBlockSelector(self.embeddings)

    def adapt(
        self,
        analysis: JobAnalysis,
        *,
        job_title: str,
        job_company: str,
        job_id: int | None = None,
    ) -> tuple[AdaptedCV, SelectionResult]:
        selection = self.selector.select(self.profile, analysis)
        prompt = cv_adaptation.build_user_prompt(
            profile=self.profile,
            analysis=analysis,
            job_title=job_title,
            job_company=job_company,
            selected_experiences=selection.experiences,
            selected_projects=selection.projects,
        )
        adapted = self.llm.complete_json(
            system=cv_adaptation.SYSTEM,
            user=prompt,
            schema=AdaptedCV,
            model=self.llm.smart_model,
            temperature=0.3,
            purpose="cv_adaptation",
            job_id=job_id,
        )
        adapted = self._ensure_supported_offer_skills(adapted, analysis)
        adapted = self._apply_role_family_contract(adapted, analysis, job_title)
        return adapted, selection

    def adapt_application(
        self,
        analysis: JobAnalysis,
        *,
        job_title: str,
        job_company: str,
        language: str = "fr",
        job_id: int | None = None,
    ) -> tuple[AdaptedCV, EmailDraft, SelectionResult]:
        selection = self.selector.select(self.profile, analysis)
        prompt = application_draft.build_user_prompt(
            profile=self.profile,
            analysis=analysis,
            job_title=job_title,
            job_company=job_company,
            selected_experiences=selection.experiences,
            selected_projects=selection.projects,
            language=language,
        )
        draft = self.llm.complete_json(
            system=application_draft.SYSTEM,
            user=prompt,
            schema=ApplicationDraft,
            model=self.llm.smart_model,
            temperature=0.3,
            purpose="application_draft",
            job_id=job_id,
        )
        adapted = self._ensure_supported_offer_skills(draft.to_cv(), analysis)
        adapted = self._apply_role_family_contract(adapted, analysis, job_title)
        return adapted, draft.to_email(), selection

    def _ensure_supported_offer_skills(
        self,
        adapted: AdaptedCV,
        analysis: JobAnalysis,
    ) -> AdaptedCV:
        """Deterministically keep supported offer-required skills visible.

        The LLM decides the section, but this guard fixes a common miss:
        offers often phrase skills as "Python programming" or "Experience
        with PyTorch". If the canonical profile skill is whitelisted, it must
        appear in the CV skills block; unsupported terms such as Kubernetes
        remain excluded.
        """
        category_by_skill: dict[str, str] = {}
        canonical_by_skill: dict[str, str] = {}
        for category in self.profile.skills.categories:
            for skill in category.skills:
                key = skill.lower()
                category_by_skill.setdefault(key, category.id)
                canonical_by_skill.setdefault(key, skill)

        selected_by_category: dict[str, list[str]] = {
            block.category_id: list(block.skills) for block in adapted.selected_skills
        }
        category_order = [block.category_id for block in adapted.selected_skills]

        for term in list(analysis.required_skills) + list(analysis.cv_keywords_to_include):
            for skill_key in self._matched_allowed_skill_keys(term, canonical_by_skill):
                category_id = category_by_skill[skill_key]
                canonical = canonical_by_skill[skill_key]
                if category_id not in selected_by_category:
                    selected_by_category[category_id] = []
                    category_order.append(category_id)
                existing = {skill.lower() for skill in selected_by_category[category_id]}
                if canonical.lower() not in existing:
                    selected_by_category[category_id].append(canonical)

        if not selected_by_category:
            return adapted

        skills_order = list(adapted.skills_order)
        for category_id in category_order:
            if category_id not in skills_order:
                skills_order.append(category_id)

        return adapted.model_copy(
            update={
                "selected_skills": [
                    SkillSelectionBlock(category_id=category_id, skills=skills)
                    for category_id in category_order
                    if (skills := selected_by_category.get(category_id))
                ],
                "skills_order": skills_order,
            }
        )

    def _apply_role_family_contract(
        self,
        adapted: AdaptedCV,
        analysis: JobAnalysis,
        job_title: str,
    ) -> AdaptedCV:
        """Strip off-role skills and anchor a coherent baseline per family."""
        allowed_skills_lower = {s.lower() for s in self.profile.skills.allowed_skills}
        adapted, _family = apply_contract(
            adapted,
            analysis=analysis,
            job_title=job_title,
            allowed_skills_lower=allowed_skills_lower,
        )
        return adapted

    @staticmethod
    def _matched_allowed_skill_keys(
        term: str,
        canonical_by_skill: dict[str, str],
    ) -> list[str]:
        normalized = " ".join((term or "").lower().split())
        if not normalized:
            return []
        matches: list[str] = []
        for skill_key in sorted(canonical_by_skill, key=len, reverse=True):
            if len(skill_key) <= 2:
                if normalized == skill_key:
                    matches.append(skill_key)
                continue
            if normalized == skill_key or skill_key in normalized or normalized in skill_key:
                matches.append(skill_key)
        return matches
