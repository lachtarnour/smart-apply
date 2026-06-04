"""Composite job scoring — combines semantic similarity with cheap signals.

Weights (sum to 1.0):
- 0.35 semantic similarity (embeddings)
- 0.25 skills overlap
- 0.15 title similarity
- 0.10 seniority match
- 0.10 location match
- 0.05 domain match
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from rapidfuzz import fuzz
from unidecode import unidecode

from smartapply.profile import Profile
from smartapply.ranking.embeddings import (
    EmbeddingsProvider,
    cosine_similarity,
    get_embeddings_provider,
)
from smartapply.utils.location import is_foreign_location


WEIGHTS = {
    "semantic": 0.30,
    "skills": 0.25,
    "title": 0.10,
    # Seniority weighs heavy: the candidate is junior-to-mid and senior /
    # lead postings must be pushed down hard, even when other signals look
    # good (ESN job ads often look attractive on paper).
    "seniority": 0.25,
    # Location matters far less than it used to. Anything in France is fine;
    # only foreign offers get penalised.
    "location": 0.05,
    "domain": 0.05,
}


# Foreign-location detection lives in ``smartapply.utils.location`` so the
# filter (which hard-rejects them) and this scorer (defense-in-depth soft
# penalty) share the same source of truth.


@dataclass
class ScoreComponents:
    semantic: float
    skills: float
    title: float
    seniority: float
    location: float
    domain: float

    @property
    def final(self) -> float:
        return (
            WEIGHTS["semantic"] * self.semantic
            + WEIGHTS["skills"] * self.skills
            + WEIGHTS["title"] * self.title
            + WEIGHTS["seniority"] * self.seniority
            + WEIGHTS["location"] * self.location
            + WEIGHTS["domain"] * self.domain
        )

    def to_dict(self) -> dict[str, float]:
        return {
            "semantic": round(self.semantic, 4),
            "skills": round(self.skills, 4),
            "title": round(self.title, 4),
            "seniority": round(self.seniority, 4),
            "location": round(self.location, 4),
            "domain": round(self.domain, 4),
            "final": round(self.final, 4),
        }


class ScorableJob(Protocol):
    title: str
    description: str
    location: str | None


def _norm(s: str | None) -> str:
    return unidecode((s or "").lower())


def build_profile_text(profile: Profile) -> str:
    """Aggregate the profile into a single document for embedding."""
    parts = [profile.identity.title, profile.identity.summary]
    for category in profile.skills.categories:
        parts.append(category.name + ": " + ", ".join(category.skills))
    for exp in profile.experiences:
        parts.append(f"{exp.title} at {exp.company}: " + " ".join(b.text for b in exp.bullets))
    for proj in profile.projects:
        parts.append(f"{proj.name}: {proj.description}")
    return "\n".join(parts)


def build_job_text(job: ScorableJob) -> str:
    return f"{job.title}\n{job.description}"


def _analytics_without_python(title: str, description: str) -> bool:
    analytics_title = (
        "data analyst" in title
        or "analytics" in title
        or " bi" in f" {title}"
    )
    excludes_python = (
        "pas de developpement python" in description
        or "pas de python" in description
        or "no python" in description
        or "without python" in description
    )
    return analytics_title and excludes_python


class JobScorer:
    """Compute composite scores against a candidate profile."""

    def __init__(
        self,
        profile: Profile,
        embeddings: EmbeddingsProvider | None = None,
    ):
        self.profile = profile
        self.embeddings = embeddings or get_embeddings_provider()
        self._profile_vector: list[float] | None = None
        self._allowed_skills_lower: set[str] = {
            s.lower() for s in profile.skills.allowed_skills
        }

    # -------------------- score components --------------------

    def _semantic_score(self, job: ScorableJob, vec_cache: dict[int, list[float]]) -> float:
        if self._profile_vector is None:
            self._profile_vector = self.embeddings.embed_one(build_profile_text(self.profile))
        key = id(job)
        if key not in vec_cache:
            vec_cache[key] = self.embeddings.embed_one(build_job_text(job))
        sim = cosine_similarity(self._profile_vector, vec_cache[key])
        # Map [-1, 1] -> [0, 1]
        return max(0.0, (sim + 1.0) / 2.0)

    def _skills_score(self, job: ScorableJob) -> float:
        if not self._allowed_skills_lower:
            return 0.0
        text = _norm(job.description) + " " + _norm(job.title)
        if _analytics_without_python(_norm(job.title), _norm(job.description)):
            return 0.0
        hits = sum(1 for s in self._allowed_skills_lower if s in text)
        # Saturate at 8 matches
        return min(1.0, hits / 8.0)

    def _title_score(self, job: ScorableJob) -> float:
        target_roles = self.profile.preferences.target_roles
        if not target_roles:
            return 0.5
        title = _norm(job.title)
        best = max(fuzz.token_set_ratio(title, _norm(r)) for r in target_roles)
        if _analytics_without_python(title, _norm(job.description)):
            return min(best / 100.0, 0.35)
        return best / 100.0

    def _seniority_score(self, job: ScorableJob) -> float:
        title = _norm(job.title)
        text = _norm(job.description) + " " + title
        # Order matters: the FIRST match wins. We start with the strongest
        # negative signals (senior/lead in title) so they can't be diluted
        # by an incidental "junior" mention buried in the description.
        rules = [
            # ---- Strong negative: explicit seniority labels in the title ----
            (r"\b(senior|sr\.?|lead|principal|staff|expert)\b", title, 0.10),
            (r"\bchef de projet|tech lead|team lead\b", text, 0.10),
            # ---- Years-of-experience floors that are above target ----
            (r"\b(1[0-9]|[2-9][0-9])\+? ?(years|ans|an)\b", text, 0.10),  # 10+ ans
            (r"\b[6-9]\+? ?(years|ans|an)\b", text, 0.20),                 # 6-9 ans
            (r"\b5\+? ?(years|ans|an)\b", text, 0.25),                     # 5+ ans
            (r"\b4\+? ?(years|ans|an)\b", text, 0.40),                     # 4+ ans
            # ---- Internships and apprenticeships: out of scope here ----
            (r"\b(stage|stagiaire|intern(ship)?|alternance|apprenti)\b", text, 0.10),
            # ---- Positive matches for the candidate's target band ----
            (r"\b(junior|d[ée]butant)\b", text, 1.0),
            (r"\b2\+? ?(years|ans|an)\b", text, 0.95),
            (r"\b3\+? ?(years|ans|an)\b", text, 0.9),
        ]
        for pattern, haystack, score in rules:
            if re.search(pattern, haystack):
                return score
        return 0.7

    def _location_score(self, job: ScorableJob) -> float:
        """Score the job location for this candidate.

        Tiers:
        - 1.00 : matches a ``preferred_location`` exactly (Paris, IDF, ...).
        - 0.85 : France-friendly (no foreign marker detected). The candidate
                 said anywhere in France is fine, so we don't differentiate
                 between Paris and Châteaufort here.
        - 0.80 : explicitly remote AND remote is accepted by the candidate.
        - 0.20 : a foreign-country marker is present in the location string.
        - 0.50 : empty / unknown location — stay neutral.
        """
        prefs = self.profile.preferences
        loc = _norm(job.location)
        if not loc:
            return 0.5
        for preferred in prefs.preferred_locations:
            if _norm(preferred) in loc:
                return 1.0
        if "remote" in loc and "remote" in [p.lower() for p in prefs.accepted_remote_policies]:
            return 0.8
        if is_foreign_location(job.location):
            return 0.2
        # No preferred location matched, no remote, no foreign marker.
        # France-anywhere case: SerpApi/France Travail FR results that happen
        # to be outside IDF (Châteaufort, Saint-Herblain, Toulouse, ...).
        return 0.85

    def _domain_score(self, job: ScorableJob) -> float:
        domains = [_norm(d) for d in self.profile.preferences.domains_of_interest]
        if not domains:
            return 0.5
        text = _norm(job.description) + " " + _norm(job.title)
        hits = sum(1 for d in domains if d in text)
        return min(1.0, hits / 3.0)

    # -------------------- public API --------------------

    def score(self, job: ScorableJob, vec_cache: dict[int, list[float]] | None = None) -> ScoreComponents:
        cache = vec_cache if vec_cache is not None else {}
        return ScoreComponents(
            semantic=self._semantic_score(job, cache),
            skills=self._skills_score(job),
            title=self._title_score(job),
            seniority=self._seniority_score(job),
            location=self._location_score(job),
            domain=self._domain_score(job),
        )

    def rank(
        self,
        jobs: list[ScorableJob],
        top_k: int | None = None,
    ) -> list[tuple[ScorableJob, ScoreComponents]]:
        cache: dict[int, list[float]] = {}
        if jobs:
            if self._profile_vector is None:
                self._profile_vector = self.embeddings.embed_one(
                    build_profile_text(self.profile)
                )
            job_vectors = self.embeddings.embed([build_job_text(job) for job in jobs])
            cache.update({id(job): vector for job, vector in zip(jobs, job_vectors)})
        results = [(j, self.score(j, cache)) for j in jobs]
        results.sort(key=lambda r: r[1].final, reverse=True)
        if top_k is not None:
            return results[:top_k]
        return results
