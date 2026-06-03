"""Classify a job offer into a role family.

The family id drives a deterministic skill-display contract applied after the
LLM produces its CV draft. It is intentionally local and free (regex over the
analysis + title) so we don't pay an LLM call for a routing decision.

Granularity is coarse on purpose. The contracts only need to distinguish
roles that demand different skill envelopes (e.g. an Analytics Engineer must
not display FAISS or NLP, a Data Scientist must keep a ML/IA baseline).
"""

from __future__ import annotations

import re
from typing import Final

from smartapply.llm.schemas import JobAnalysis


RoleFamily = str

OTHER: Final[RoleFamily] = "other"

# Families that must match against the *primary* signal only (title +
# role_type). They describe the core role: classifying a Data Scientist as
# MLOps just because the offer asks for ``ML Ops workflows`` as a required
# skill would be wrong. Other families can scan the full haystack.
_PRIMARY_ONLY_FAMILIES: Final[frozenset[str]] = frozenset({"mlops"})

# Ordered list of (family_id, regex patterns). Order matters: the first
# family with a matching pattern wins. Put the more specific families first
# (LLM/RAG before generic Data Scientist, MLOps before ML Engineer, ...).
_FAMILY_PATTERNS: Final[list[tuple[RoleFamily, list[str]]]] = [
    (
        "llm_engineer",
        [
            r"\bllm\b",
            r"\bllms\b",
            r"\bgen[- ]?ai\b",
            r"\bgenerative ai\b",
            r"\brag\b",
            r"\bretrieval[- ]augmented\b",
            r"\bvector (db|search|database|store)\b",
            r"\bprompt engineer",
            r"\blangchain\b",
            r"\bllamaindex\b",
        ],
    ),
    (
        "computer_vision",
        [
            r"\bcomputer vision\b",
            r"\bvision par ordinateur\b",
            r"\bopencv\b",
            r"\bobject detection\b",
            r"\bimage segmentation\b",
            r"\bsemantic segmentation\b",
            r"\binstance segmentation\b",
            r"\bimage processing\b",
            r"\bimage classification\b",
            r"\bvision pipeline",
        ],
    ),
    (
        "speech_audio",
        [
            r"\bspeech[- ]to[- ]text\b",
            r"\bspeech processing\b",
            r"\baudio processing\b",
            r"\btranscription\b",
            r"\bdiarization\b",
            r"\bwhisper\b",
            r"\bpyannote\b",
        ],
    ),
    (
        "reinforcement_learning",
        [
            r"\breinforcement learning\b",
            r"\bapprentissage par renforcement\b",
            r"\bcontrol tasks?\b",
            r"\bopenai gym\b",
            r"\bpolicy gradient\b",
        ],
    ),
    (
        "medical_ai",
        [
            r"\bmedical ai\b",
            r"\bdigital health\b",
            r"\bhealthtech\b",
            r"\bbiomark",
            r"\bclinical ai\b",
            r"\bsanté numérique\b",
            r"\bclinique",
            r"\bdispositif médical\b",
        ],
    ),
    (
        "mlops",
        [
            r"\bml[- ]?ops\b",
            r"\bdevops/ml\b",
            r"\bml platform\b",
            r"\bml infrastructure\b",
            r"\bmodel monitoring\b",
            r"\bmodel serving\b",
            r"\bplateforme ml\b",
        ],
    ),
    (
        "ml_engineer",
        [
            r"\bml engineer\b",
            r"\bmachine learning engineer\b",
            r"\bai engineer\b",
            r"\bingénieur (en )?ia\b",
            r"\bingénieur (en )?ml\b",
            r"\bml[- ]engineer\b",
            r"\bapplied (ai|ml) engineer\b",
        ],
    ),
    (
        "analytics_engineer",
        [
            r"\banalytics engineer\b",
            r"\bdbt\b",
            r"\bdata modeling\b",
            r"\bsnowflake\b",
            r"\banalytics engineering\b",
            r"\bsemantic layer\b",
        ],
    ),
    (
        "data_analyst",
        [
            r"\bdata analyst\b",
            r"\bproduct analyst\b",
            r"\bbusiness analyst\b",
            r"\banalyste (de )?donn",
            r"\bpower bi\b",
            r"\btableau\b",
            r"\balteryx\b",
            r"\bbi engineer\b",
        ],
    ),
    (
        "data_scientist",
        [
            r"\bdata scientist\b",
            r"\bdatascientist\b",
            r"\bdata[- ]scientist\b",
            r"\bscientifique des données\b",
            r"\bdata science\b",
        ],
    ),
    (
        "software_engineer",
        [
            r"\bsoftware engineer\b",
            r"\bsoftware developer\b",
            r"\bdéveloppeur\b",
            r"\bdeveloper\b",
            r"\bbackend engineer\b",
            r"\bbackend developer\b",
            r"\bfullstack\b",
            r"\bfull[- ]stack\b",
            r"\bfrontend\b",
            r"\bc\+\+",
            r"\btypescript\b",
            r"\bangular\b",
            r"\bnode\.?js\b",
            r"\bqt framework\b",
        ],
    ),
]


# Offer signals that turn on extra ml_ai display for Data Scientist roles
# (NLP / Transformers / Hugging Face on top of the base PyTorch + Scikit-learn).
_DS_IA_SIGNAL_PATTERNS: Final[list[str]] = [
    r"\bnlp\b",
    r"\bllm\b",
    r"\bllms\b",
    r"\bgen[- ]?ai\b",
    r"\bgenerative ai\b",
    r"\bia\b",
    r"\bartificial intelligence\b",
    r"\bintelligence artificielle\b",
    r"\btransformers?\b",
    r"\bhugging[- ]face\b",
    r"\bfine[- ]tuning\b",
    r"\btextes?\b",
    r"\blanguage models?\b",
    r"\bmodèles? de langue\b",
    r"\btraitement (du|de) langage\b",
]


def _primary_haystack(analysis: JobAnalysis, title: str) -> str:
    """Title + role_type only — what the role IS, not what it touches."""
    parts: list[str] = [title or "", analysis.role_type or ""]
    return " ".join(p for p in parts if p).lower()


def _haystack(analysis: JobAnalysis, title: str) -> str:
    """Full extended haystack used by broad families.

    Intentionally drops ``nice_to_have``: bonus skills are too noisy to drive
    a role classification (e.g. a Data Scientist offer that lists Power BI as
    nice-to-have should not be tagged as a Data Analyst).
    """
    parts: list[str] = [
        title or "",
        analysis.role_type or "",
        analysis.domain or "",
        " ".join(analysis.main_tasks),
        " ".join(analysis.required_skills),
        " ".join(analysis.cv_keywords_to_include),
    ]
    return " ".join(p for p in parts if p).lower()


def classify(analysis: JobAnalysis, *, title: str = "") -> RoleFamily:
    """Return the role family id, or ``other`` when no pattern matches."""
    primary = _primary_haystack(analysis, title)
    extended = _haystack(analysis, title)
    for family_id, patterns in _FAMILY_PATTERNS:
        scope = primary if family_id in _PRIMARY_ONLY_FAMILIES else extended
        for pattern in patterns:
            if re.search(pattern, scope):
                return family_id
    return OTHER


def has_data_scientist_ia_signal(
    analysis: JobAnalysis,
    title: str = "",
) -> bool:
    """True when a Data Scientist offer also asks for AI/NLP/LLM/GenAI.

    Used to augment the data_scientist contract with NLP + Transformers +
    Hugging Face on the ml_ai block. A vanilla DS role (forecasting,
    classical stats, predictive modeling) gets a leaner ml_ai baseline.
    """
    haystack = _haystack(analysis, title)
    return any(re.search(p, haystack) for p in _DS_IA_SIGNAL_PATTERNS)
