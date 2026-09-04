"""Bilingual, explainable role-relevance assessment.

The local filter must be conservative: explicit off-target roles can be
discarded, but unfamiliar wording must not become a false negative.  This
module therefore maps French and English phrases to canonical concepts and
returns one of three dispositions: relevant, uncertain, or off-target.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

from rapidfuzz import fuzz

from smartapply.filtering.text import contains_any, norm


class RoleRelevanceDisposition(str, Enum):
    RELEVANT = "relevant"
    UNCERTAIN = "uncertain"
    OFF_TARGET = "off_target"


@dataclass(frozen=True)
class RoleRelevanceAssessment:
    disposition: RoleRelevanceDisposition
    score: int
    concepts: tuple[str, ...]
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class _Concept:
    name: str
    patterns: tuple[str, ...]


def _phrase(value: str) -> str:
    """Turn a normalized phrase into a boundary-safe, whitespace-tolerant regex."""
    words = [re.escape(part) for part in norm(value).split() if part]
    separator = r"['\s_/-]+"
    return rf"(?<![a-z0-9]){separator.join(words)}(?![a-z0-9])"


def _phrases(*values: str) -> tuple[str, ...]:
    return tuple(_phrase(value) for value in values)


# Each family is a canonical concept.  Both languages intentionally live in
# the same family because real French offers frequently mix English terms.
_CONCEPTS = (
    _Concept(
        "agentic_ai",
        _phrases(
            "agentic ai",
            "agentic artificial intelligence",
            "agentic systems",
            "ai agent",
            "ai agents",
            "autonomous agent",
            "autonomous agents",
            "multi agent system",
            "multi agent systems",
            "multiagent system",
            "multiagent systems",
            "agent orchestration",
            "ia agentique",
            "systeme agentique",
            "systemes agentiques",
            "agent ia",
            "agents ia",
            "agent autonome",
            "agents autonomes",
            "systeme multi agents",
            "systemes multi agents",
            "orchestration d agents",
        ),
    ),
    _Concept(
        "machine_learning",
        _phrases(
            "machine learning",
            "statistical learning",
            "supervised learning",
            "unsupervised learning",
            "semi supervised learning",
            "reinforcement learning",
            "deep learning",
            "apprentissage automatique",
            "apprentissage statistique",
            "apprentissage supervise",
            "apprentissage non supervise",
            "apprentissage semi supervise",
            "apprentissage par renforcement",
            "apprentissage profond",
        )
        + (r"(?<![a-z0-9])ml(?![a-z0-9])",),
    ),
    _Concept(
        "generative_ai",
        _phrases(
            "generative ai",
            "gen ai",
            "large language model",
            "large language models",
            "language model",
            "language models",
            "retrieval augmented generation",
            "ia generative",
            "modele de langage",
            "modeles de langage",
            "generation augmentee par recuperation",
        )
        + (
            r"(?<![a-z0-9])genai(?![a-z0-9])",
            r"(?<![a-z0-9])llms?(?![a-z0-9])",
            r"(?<![a-z0-9])rag(?![a-z0-9])",
        ),
    ),
    _Concept(
        "data_science",
        _phrases(
            "data science",
            "science des donnees",
            "decision science",
            "science de la decision",
            "predictive analytics",
            "analyse predictive",
            "analyse de donnees",
            "analyse des donnees",
            "data analytics",
            "product analytics",
            "advanced analytics",
            "analytique avancee",
        ),
    ),
    _Concept(
        "statistical_modeling",
        _phrases(
            "statistical model",
            "statistical models",
            "statistical modeling",
            "statistical modelling",
            "bayesian inference",
            "bayesian modeling",
            "bayesian modelling",
            "probabilistic model",
            "probabilistic models",
            "predictive model",
            "predictive models",
            "feature engineering",
            "hypothesis testing",
            "anomaly detection",
            "survival analysis",
            "dimensionality reduction",
            "monte carlo simulation",
            "modelisation statistique",
            "inference bayesienne",
            "modelisation bayesienne",
            "modele bayesien",
            "modeles bayesiens",
            "modele statistique",
            "modeles statistiques",
            "modele probabiliste",
            "modeles probabilistes",
            "modelisation predictive",
            "modele predictif",
            "modeles predictifs",
            "ingenierie des variables",
            "test d hypothese",
            "tests d hypotheses",
            "detection d anomalies",
            "analyse de survie",
            "reduction de dimension",
            "simulation monte carlo",
        ),
    ),
    _Concept(
        "experimentation_causal",
        _phrases(
            "a b testing",
            "ab testing",
            "controlled experiment",
            "controlled experiments",
            "causal inference",
            "causal analysis",
            "causal impact",
            "uplift modeling",
            "uplift modelling",
            "econometric modeling",
            "experimentation",
            "test a b",
            "tests a b",
            "experience controlee",
            "experiences controlees",
            "inference causale",
            "analyse causale",
            "impact causal",
            "modelisation uplift",
            "modelisation econometrique",
            "econometrie",
        ),
    ),
    _Concept(
        "forecasting",
        _phrases(
            "forecasting",
            "forecast",
            "forecasts",
            "time series",
            "time series analysis",
            "time series modeling",
            "demand forecasting",
            "sales forecasting",
            "analyse de series temporelles",
            "modelisation de series temporelles",
            "series temporelles",
            "prevision",
            "previsions",
            "prevision de la demande",
            "prevision des ventes",
            "modeles de prevision",
        ),
    ),
    _Concept(
        "nlp",
        _phrases(
            "natural language processing",
            "computational linguistics",
            "text mining",
            "text classification",
            "semantic search",
            "traitement automatique du langage",
            "traitement du langage naturel",
            "linguistique informatique",
            "fouille de textes",
            "classification de textes",
            "recherche semantique",
        )
        + (r"(?<![a-z0-9])nlp(?![a-z0-9])",),
    ),
    _Concept(
        "speech_audio_ai",
        _phrases(
            "speech recognition",
            "speech processing",
            "audio classification",
            "speaker recognition",
            "speaker diarization",
            "automatic speech recognition",
            "reconnaissance vocale",
            "traitement de la parole",
            "traitement audio",
            "classification audio",
            "reconnaissance du locuteur",
            "diarisation des locuteurs",
        )
        + (r"(?<![a-z0-9])asr(?![a-z0-9])",),
    ),
    _Concept(
        "computer_vision",
        _phrases(
            "computer vision",
            "image recognition",
            "image segmentation",
            "object detection",
            "visual recognition",
            "vision par ordinateur",
            "reconnaissance d images",
            "segmentation d images",
            "detection d objets",
            "reconnaissance visuelle",
        ),
    ),
    _Concept(
        "recommendation_optimization",
        _phrases(
            "recommendation system",
            "recommendation systems",
            "recommender system",
            "recommender systems",
            "ranking model",
            "ranking models",
            "operations research",
            "mathematical optimization",
            "systeme de recommandation",
            "systemes de recommandation",
            "moteur de recommandation",
            "moteurs de recommandation",
            "modele de ranking",
            "modeles de ranking",
            "recherche operationnelle",
            "optimisation mathematique",
        ),
    ),
    _Concept(
        "graph_ml",
        _phrases(
            "graph machine learning",
            "graph neural network",
            "graph neural networks",
            "geometric deep learning",
            "knowledge graph",
            "knowledge graphs",
            "apprentissage sur graphes",
            "reseau de neurones de graphe",
            "reseaux de neurones de graphe",
            "apprentissage profond geometrique",
            "graphe de connaissances",
            "graphes de connaissances",
        )
        + (r"(?<![a-z0-9])gnns?(?![a-z0-9])",),
    ),
    _Concept(
        "data_mining",
        _phrases(
            "data mining",
            "pattern mining",
            "customer segmentation",
            "behavioral segmentation",
            "fouille de donnees",
            "extraction de connaissances",
            "segmentation client",
            "segmentation comportementale",
        ),
    ),
)

_ROLE_TITLE_PATTERNS = _phrases(
    "data scientist",
    "scientifique des donnees",
    "machine learning engineer",
    "ml engineer",
    "ingenieur machine learning",
    "ingenieur en apprentissage automatique",
    "ai engineer",
    "ia engineer",
    "ingenieur ia",
    "ingenieur en intelligence artificielle",
    "research engineer",
    "ingenieur de recherche",
    "research scientist",
    "chercheur en ia",
    "applied scientist",
    "data analyst",
    "analyste data",
    "analyste de donnees",
    "product data analyst",
    "product analyst",
    "analytics engineer",
    "ingenieur analytics",
    "decision scientist",
    "nlp engineer",
    "computer vision engineer",
)

_ROLE_NOUN_PATTERNS = _phrases(
    "engineer",
    "ingenieur",
    "scientist",
    "scientifique",
    "researcher",
    "chercheur",
    "analyst",
    "analyste",
    "specialist",
    "specialiste",
    "developer",
    "developpeur",
)

_ACTION_PATTERNS = _phrases(
    "build",
    "building",
    "design",
    "designing",
    "develop",
    "developing",
    "implement",
    "implementing",
    "train",
    "training models",
    "evaluate",
    "evaluating",
    "deploy",
    "deploying",
    "optimize",
    "optimizing",
    "analyse",
    "analyze",
    "analyzing",
    "modeling",
    "modelling",
    "predict",
    "predicting",
    "experiment",
    "experimenting",
    "industrialize",
    "productionize",
    "create",
    "creating",
    "concevoir",
    "construire",
    "creer",
    "developper",
    "implementer",
    "entrainer",
    "evaluer",
    "deployer",
    "optimiser",
    "analyser",
    "modeliser",
    "predire",
    "experimenter",
    "industrialiser",
    "realiser",
    "mettre en production",
)

_RESPONSIBILITY_PATTERNS = _phrases(
    "your responsibilities",
    "your missions",
    "what you will do",
    "you will",
    "you ll",
    "the role involves",
    "responsibilities include",
    "vos responsabilites",
    "vos missions",
    "vous serez charge",
    "vous serez chargee",
    "vous allez",
    "le poste consiste",
    "les missions incluent",
)

_CORE_TOOL_TOKENS = (
    "python",
    "pytorch",
    "tensorflow",
    "scikit-learn",
    "sklearn",
    "pandas",
    "numpy",
    "sql",
    "spark",
    "pyspark",
    "hugging face",
    "transformers",
    "xgboost",
    "lightgbm",
)

_COMPANY_CONTEXT_PATTERNS = _phrases(
    "we are a company",
    "our company",
    "our product",
    "our platform",
    "company specialized in",
    "company specialising in",
    "market leader in",
    "nous sommes une entreprise",
    "notre entreprise",
    "notre societe",
    "notre produit",
    "notre plateforme",
    "entreprise specialisee dans",
    "societe specialisee dans",
    "leader du marche",
)

_INCIDENTAL_PATTERNS = _phrases(
    "nice to have",
    "would be a plus",
    "is a plus",
    "preferred but not required",
    "awareness of",
    "familiarity with",
    "experience with",
    "knowledge of",
    "exposure to",
    "apprecie mais non requis",
    "serait un plus",
    "est un plus",
    "connaissance appreciee",
    "experience avec",
    "connaissance de",
    "familiarite avec",
)

_OFF_TARGET_TITLE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "sales_commercial",
        _phrases(
            "sales",
            "sales representative",
            "account executive",
            "business development",
            "commercial",
            "ingenieur commercial",
            "charge d affaires",
        ),
    ),
    (
        "legal_compliance",
        _phrases(
            "legal",
            "lawyer",
            "privacy officer",
            "data protection officer",
            "data protection",
            "juriste",
            "conformite",
            "responsable rgpd",
            "delegue a la protection des donnees",
            "protection des donnees",
        ),
    ),
    (
        "people_operations",
        _phrases(
            "human resources",
            "talent acquisition",
            "recruiter",
            "office manager",
            "administrative assistant",
            "operations coordinator",
            "ressources humaines",
            "recruteur",
            "recruteuse",
            "assistant administratif",
            "assistante administrative",
            "coordinateur operations",
            "coordinatrice operations",
        ),
    ),
    (
        "marketing_customer",
        _phrases(
            "marketing manager",
            "marketing specialist",
            "marketing coordinator",
            "customer success",
            "customer support",
            "communications manager",
            "charge de marketing",
            "chargee de marketing",
            "responsable marketing",
            "relation client",
            "support client",
            "charge de communication",
            "chargee de communication",
        ),
    ),
    (
        "data_literal_not_analytics",
        _phrases(
            "data center",
            "data centre",
            "data entry",
            "database administrator",
            "centre de donnees",
            "saisie de donnees",
            "administrateur de base de donnees",
        ),
    ),
)

_NON_TECHNICAL_AI_CONTEXT_PATTERNS = _phrases(
    "sell ai",
    "selling ai",
    "sell the ai",
    "sell our ai",
    "market ai",
    "marketing ai",
    "promote ai",
    "commercialiser l ia",
    "commercialiser une solution ia",
    "vendre une solution ia",
    "promouvoir l ia",
    "ai act compliance",
    "ai regulation",
    "conformite ai act",
    "reglementation de l ia",
    "use generative ai tools",
    "utiliser des outils d ia generative",
)


@lru_cache(maxsize=128)
def _compiled_any(patterns: tuple[str, ...]) -> re.Pattern[str]:
    if not patterns:
        return re.compile(r"(?!x)x")
    return re.compile("|".join(f"(?:{pattern})" for pattern in patterns))


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return _compiled_any(patterns).search(text) is not None


def _concepts_in(text: str) -> set[str]:
    return {concept.name for concept in _CONCEPTS if _matches(text, concept.patterns)}


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?:\r?\n|[.!?;•]+)", text) if part.strip()]


def _fuzzy_target_role(title: str, target_roles: list[str]) -> str | None:
    """Recover small spelling/formatting variations without broad matching."""
    for target in target_roles:
        target_norm = norm(target)
        if len(target_norm) < 7:
            continue
        if fuzz.token_set_ratio(title, target_norm) >= 92:
            return target_norm
    return None


def _off_target_title_marker(title: str) -> str | None:
    for marker, patterns in _OFF_TARGET_TITLE_PATTERNS:
        if _matches(title, patterns):
            return marker
    return None


def assess_role_relevance(
    *,
    title: str,
    description: str,
    positive_title_keywords: tuple[str, ...],
    target_roles: list[str],
) -> RoleRelevanceAssessment:
    """Assess bilingual role relevance using independent, contextual evidence.

    An uncertain result is deliberately fail-open.  It proceeds to the
    semantic ranking stage instead of being archived simply because the local
    vocabulary did not recognise an emerging expression.
    """
    title = norm(title)
    description = norm(description)
    concepts = _concepts_in(f"{title}\n{description}")
    title_concepts = _concepts_in(title)
    evidence: list[str] = []
    evidence_kinds: set[str] = set()
    score = 0

    configured_target = next(
        (
            norm(role)
            for role in target_roles
            if norm(role) and _phrase(norm(role)) and re.search(_phrase(norm(role)), title)
        ),
        None,
    )
    configured_keyword = next(
        (
            norm(keyword)
            for keyword in positive_title_keywords
            if norm(keyword) and re.search(_phrase(norm(keyword)), title)
        ),
        None,
    )
    built_in_role = _matches(title, _ROLE_TITLE_PATTERNS)
    fuzzy_target = None
    if not (configured_target or configured_keyword or built_in_role):
        fuzzy_target = _fuzzy_target_role(title, target_roles)

    strong_title = bool(configured_target or configured_keyword or built_in_role or fuzzy_target)
    if strong_title:
        score += 6
        evidence_kinds.add("title_role")
        if configured_target:
            evidence.append(f"target_title:{configured_target}")
        elif configured_keyword:
            evidence.append(f"recognized_title:{configured_keyword}")
        elif fuzzy_target:
            evidence.append(f"fuzzy_target_title:{fuzzy_target}")
        else:
            evidence.append("recognized_bilingual_role_title")

    role_noun_with_concept = bool(title_concepts) and _matches(title, _ROLE_NOUN_PATTERNS)
    if role_noun_with_concept and not strong_title:
        score += 5
        strong_title = True
        evidence_kinds.update(("title_role", "title_concept"))
        evidence.append("specialized_role_title")
    elif title_concepts and not strong_title:
        score += 3
        evidence_kinds.add("title_concept")
        evidence.append("concept_in_title")

    mission_concepts: set[str] = set()
    contextual_mentions: set[str] = set()
    incidental_mentions: set[str] = set()
    tool_in_mission = False
    for sentence in _sentences(description):
        sentence_concepts = _concepts_in(sentence)
        if not sentence_concepts:
            continue
        has_action = _matches(sentence, _ACTION_PATTERNS) or _matches(
            sentence, _RESPONSIBILITY_PATTERNS
        )
        if _matches(sentence, _COMPANY_CONTEXT_PATTERNS) or (
            _matches(sentence, _INCIDENTAL_PATTERNS) and not has_action
        ):
            incidental_mentions.update(sentence_concepts)
            continue
        contextual_mentions.update(sentence_concepts)
        if has_action:
            mission_concepts.update(sentence_concepts)
            if contains_any(sentence, _CORE_TOOL_TOKENS):
                tool_in_mission = True

    if contextual_mentions:
        score += min(2, len(contextual_mentions))
        evidence_kinds.add("concept")
        evidence.append("contextual_concept")
    if mission_concepts:
        score += 4 + min(2, len(mission_concepts) - 1)
        evidence_kinds.add("mission")
        evidence.append("candidate_mission")
    if tool_in_mission:
        score += 1
        evidence_kinds.add("tool")
        evidence.append("core_tool_in_mission")
    if incidental_mentions and not contextual_mentions:
        evidence.append("incidental_or_company_only_concept")

    off_target_marker = _off_target_title_marker(title)
    non_technical_ai_context = _matches(description, _NON_TECHNICAL_AI_CONTEXT_PATTERNS)
    if off_target_marker:
        evidence.append(f"off_target_title:{off_target_marker}")
        score -= 6
    if non_technical_ai_context:
        evidence.append("non_technical_ai_context")
        score -= 4

    # A precise Data/AI title wins over an adjacent domain word (for example,
    # "Marketing Data Analyst").  Without such a title or a concrete technical
    # mission, explicit off-target evidence is safe to reject.
    if (off_target_marker or non_technical_ai_context) and not (strong_title or mission_concepts):
        disposition = RoleRelevanceDisposition.OFF_TARGET
    elif strong_title or (score >= 5 and len(evidence_kinds) >= 2):
        disposition = RoleRelevanceDisposition.RELEVANT
    else:
        disposition = RoleRelevanceDisposition.UNCERTAIN

    return RoleRelevanceAssessment(
        disposition=disposition,
        score=score,
        concepts=tuple(sorted(concepts)),
        evidence=tuple(evidence),
    )


__all__ = [
    "RoleRelevanceAssessment",
    "RoleRelevanceDisposition",
    "assess_role_relevance",
]
