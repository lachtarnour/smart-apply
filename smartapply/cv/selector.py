"""Block selector — choose the experiences/projects most relevant to a job.

We compute embeddings for each block and rank them against an embedding of
the job analysis (main_tasks + required_skills + keywords). Top-K selection
keeps the LLM prompt small and focused.
"""

from __future__ import annotations

from dataclasses import dataclass

from smartapply.llm.schemas import JobAnalysis
from smartapply.profile import Experience, Profile, Project
from smartapply.ranking.embeddings import EmbeddingsProvider, cosine_similarity


@dataclass
class SelectionResult:
    experiences: list[Experience]
    projects: list[Project]
    experience_scores: dict[str, float]
    project_scores: dict[str, float]


class CvBlockSelector:
    def __init__(self, embeddings: EmbeddingsProvider):
        self.embeddings = embeddings

    @staticmethod
    def _experience_text(exp: Experience) -> str:
        bullets = " ".join(b.text for b in exp.bullets)
        return f"{exp.title} at {exp.company}: {bullets}"

    @staticmethod
    def _project_text(p: Project) -> str:
        return f"{p.name}: {p.description}"

    @staticmethod
    def _analysis_text(analysis: JobAnalysis) -> str:
        return (
            f"Role: {analysis.role_type}. Domain: {analysis.domain}.\n"
            f"Tasks: {' '.join(analysis.main_tasks)}\n"
            f"Required: {', '.join(analysis.required_skills)}\n"
            f"Keywords: {', '.join(analysis.cv_keywords_to_include)}"
        )

    def select(
        self,
        profile: Profile,
        analysis: JobAnalysis,
        *,
        top_k_experiences: int = 5,
        top_k_projects: int = 10,
    ) -> SelectionResult:
        analysis_vec = self.embeddings.embed_one(self._analysis_text(analysis))

        exp_scores: dict[str, float] = {}
        for exp in profile.experiences:
            v = self.embeddings.embed_one(self._experience_text(exp))
            exp_scores[exp.id] = cosine_similarity(analysis_vec, v)

        proj_scores: dict[str, float] = {}
        for proj in profile.projects:
            v = self.embeddings.embed_one(self._project_text(proj))
            proj_scores[proj.id] = cosine_similarity(analysis_vec, v)

        # Always keep the most recent experience — recency matters even if
        # the semantic match is lower than older roles.
        ordered_experiences = sorted(
            profile.experiences,
            key=lambda e: exp_scores.get(e.id, 0.0),
            reverse=True,
        )
        if profile.experiences:
            most_recent = profile.experiences[0]
            if most_recent not in ordered_experiences[:top_k_experiences]:
                ordered_experiences = [most_recent] + [
                    e for e in ordered_experiences if e.id != most_recent.id
                ]
        selected_experiences = ordered_experiences[:top_k_experiences]

        ordered_projects = sorted(
            profile.projects,
            key=lambda p: proj_scores.get(p.id, 0.0),
            reverse=True,
        )
        selected_projects = ordered_projects[:top_k_projects]

        return SelectionResult(
            experiences=selected_experiences,
            projects=selected_projects,
            experience_scores=exp_scores,
            project_scores=proj_scores,
        )
