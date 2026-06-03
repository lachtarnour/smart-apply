"""Rule sets for the local job filter.

Keep rules data-driven and overridable so they can be tuned per profile
without changing code. ``Profile.preferences`` is the source of truth for
target roles, deal-breakers, locations and contract types.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default boost / penalty weights for the rule-based score (0-1 range).
DEFAULT_POSITIVE_TITLE_KEYWORDS = (
    "data scientist",
    "machine learning",
    "ml engineer",
    "ai engineer",
    "ai researcher",
    "research engineer",
    "applied scientist",
    "nlp engineer",
    "data analyst",
    "product analyst",
    "product data analyst",
    "analytics engineer",
    "data analytics",
    "mlops",
    "deep learning",
    "computer vision",
)

DEFAULT_NEGATIVE_TITLE_KEYWORDS = (
    "sales",
    "marketing",
    "manager",
    "head of",
    "director",
    "vp ",
    "chief",
    "lead 10",
    "principal",
    "intern only",
    "alternance",
    "stage de fin",
    "stage",
)

DEFAULT_TITLE_HARD_REJECT_KEYWORDS = (
    "enseignant",
    "teacher",
    "technicien",
    "technician",
    "chef",
    "formateur",
    "formatrice",
    "trainer",
    "instructor",
    "audit devops",
    "devops audit",
    "senior responsable",
)

# Hard reject when these appear in the offer TITLE — the candidate is junior
# to mid (~2 years) so explicit seniority labels are deal-breakers regardless
# of what the description says.
DEFAULT_SENIORITY_TITLE_HARD_REJECT = (
    "senior ",
    "sr.",
    "lead ",
    "principal ",
    "staff ",
)

DEFAULT_SENIORITY_BLOCK_TERMS = (
    "10+ years",
    "10 ans minimum",
    "15+ years",
    "20+ years",
)

# Job description tokens that are strong negative signals.
DEFAULT_NEGATIVE_DESC_TOKENS = (
    "reporting only without analytical ownership",
    "bi only without python or sql",
    "no technical",
    "no coding",
    "purely managerial",
)

# Contract types that should be hard-rejected regardless of other signals.
# Matched as a substring against the normalized ``contract_type`` field.
# We rely on ATS values like "Internship", "Stage", "Alternance",
# "Apprentissage" coming straight from SerpApi / France Travail.
DEFAULT_BLOCKED_CONTRACT_TYPES = (
    "stage",
    "stagiaire",
    "internship",
    "alternance",
    "apprenti",  # covers apprenti, apprentissage, apprenticeship
)


@dataclass
class RuleSet:
    """A bundle of rules used by the filter."""

    target_roles: list[str] = field(default_factory=list)
    deal_breakers: list[str] = field(default_factory=list)
    preferred_locations: list[str] = field(default_factory=list)
    accepted_contract_types: list[str] = field(default_factory=list)
    accepted_remote_policies: list[str] = field(default_factory=list)

    positive_title_keywords: tuple[str, ...] = DEFAULT_POSITIVE_TITLE_KEYWORDS
    negative_title_keywords: tuple[str, ...] = DEFAULT_NEGATIVE_TITLE_KEYWORDS
    title_hard_reject_keywords: tuple[str, ...] = DEFAULT_TITLE_HARD_REJECT_KEYWORDS
    seniority_title_hard_reject: tuple[str, ...] = DEFAULT_SENIORITY_TITLE_HARD_REJECT
    seniority_block_terms: tuple[str, ...] = DEFAULT_SENIORITY_BLOCK_TERMS
    negative_desc_tokens: tuple[str, ...] = DEFAULT_NEGATIVE_DESC_TOKENS
    blocked_contract_types: tuple[str, ...] = DEFAULT_BLOCKED_CONTRACT_TYPES

    min_score: float = 0.3
    """A job is rejected if its rule_based_score falls below this floor."""

    max_required_years: int = 5
    """Hard reject if the offer asks for >= this many years of experience.

    Default 5 — the candidate has ~2 years, so anything asking for 5+ ans /
    5+ years is out of scope. Lowering this value tightens the funnel,
    raising it relaxes it.
    """
