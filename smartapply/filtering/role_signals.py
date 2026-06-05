"""Role-family and scope tokens used by the local filter."""

from __future__ import annotations

import re

from smartapply.filtering.text import contains_any

REPORTING_BI_TOKENS = (
    "business intelligence",
    "dashboard",
    "dashboards",
    "ga4",
    "gtm",
    "looker",
    "lookml",
    "power bi",
    "power query",
    "qlik",
    "qliksense",
    "reporting",
    "tableau",
)

ANALYTICAL_OWNERSHIP_TOKENS = (
    "a/b",
    "ab testing",
    "acquisition",
    "arima",
    "bigquery",
    "conversion",
    "data warehouse",
    "dbt",
    "engagement",
    "etl",
    "forecasting",
    "machine learning",
    "ml",
    "modele",
    "modeles",
    "modeling",
    "modelisation",
    "modélisation",
    "numpy",
    "pandas",
    "predictif",
    "predictifs",
    "predictive",
    "product analytics",
    "prevision",
    "prévision",
    "python",
    "pyspark",
    "qualite des donnees",
    "qualité des données",
    "recommandations actionnables",
    "restitution finale",
    "semantic layer",
    "segmentation",
    "spark",
    "sql",
    "statistical",
    "statistique",
    "statistics",
)

WEB_ANALYTICS_TRACKING_TOKENS = (
    "data layer",
    "ga4",
    "google analytics",
    "gtm",
    "tagging plan",
    "tracking plan",
)

CORE_DATA_TECH_TOKENS = (
    "dbt",
    "etl",
    "machine learning",
    "ml",
    "python",
    "pyspark",
    "spark",
    "sql",
)

NEGATED_CORE_DATA_TECH_TOKENS = (
    "no python",
    "without python",
    "pas de python",
    "pas de developpement python",
    "pas de développement python",
    "no sql",
    "without sql",
    "pas de sql",
    "no analytics ownership",
    "without analytics ownership",
    "sans ownership analytique",
)

DATA_ENGINEERING_PLATFORM_TOKENS = (
    "airflow",
    "data platform",
    "data warehouse",
    "databricks",
    "etl",
    "informatica",
    "snowflake",
    "warehouse",
)

ML_ANALYTICS_SCOPE_TOKENS = (
    "ai",
    "analytics",
    "data science",
    "machine learning",
    "ml",
    "python",
    "statistical",
    "statistique",
    "statistics",
)

DATA_AI_ANCHOR_TOKENS = (
    "ai",
    "artificial intelligence",
    "computer vision",
    "data pipeline",
    "data science",
    "deep learning",
    "genai",
    "ia generative",
    "ia générative",
    "intelligence artificielle",
    "llm",
    "machine learning",
    "ml",
    "nlp",
    "python",
    "rag",
)

DESCRIPTION_ROLE_CONTEXT_TOKENS = (
    "analyse de donnees",
    "analyse de données",
    "analyse statistique",
    "analyser des donnees",
    "analyser des données",
    "analytics engineer",
    "data analyst",
    "data science",
    "data scientist",
    "data team",
    "equipe data",
    "intelligence artificielle",
    "machine learning",
    "mission data",
    "mission machine learning",
    "modeles predictifs",
    "modèles prédictifs",
    "pipelines data",
    "pole data",
    "pôle data",
    "poste data",
    "product analytics",
    "projets data",
)

FINANCE_REPORTING_CONTEXT_TOKENS = (
    "controle de gestion",
    "contrôle de gestion",
    "direction administrative et financière",
    "finance",
    "financier",
    "fp&a",
)

_ROLE_RELEVANCE_TITLE_RE = re.compile(
    r"(?<![a-z0-9])("
    r"ai engineer|analyste data|analytics engineer|applied scientist|"
    r"business data|computer vision|data analyst|data science|data scientist|"
    r"deep learning|genai|ia generative|ingenieur ia|intelligence artificielle|"
    r"llm|machine learning|ml engineer|nlp|product data analyst|"
    r"research engineer|scientifique des donnees|statisticien data"
    r")(?![a-z0-9])"
)
_ANALYST_TITLE_RE = re.compile(r"(?<![a-z0-9])(?:analyst|analyste|analytics)(?![a-z0-9])")
_DATA_TITLE_RE = re.compile(r"(?<![a-z0-9])(?:data|donnees|données|ia|ai|ml)(?![a-z0-9])")
_STRONG_DATA_AI_DEV_TITLE_RE = re.compile(
    r"(?<![a-z0-9])(?:ai|bi\s*/\s*etl|business\s+intelligence|data|"
    r"data\s+bi|donnees|données|etl|genai|ia|llm|machine\s+learning|"
    r"ml|power\s+bi|reporting\s+bi|talend)(?![a-z0-9])"
)
_SYSTEM_NETWORK_ADMIN_RE = re.compile(
    r"\badministrateur\b.{0,50}\b(?:systeme|système|reseau|réseau)\b"
)
_OFF_TARGET_TITLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "qa/test",
        re.compile(
            r"\b(?:assurance\s+qualite|assurance\s+qualité|qa|quality assurance|"
            r"recetteur|testeur|testeuse)\b"
        ),
    ),
    ("cybersecurity", re.compile(r"\b(?:cybersecurite|cybersécurité)\b")),
    ("support", re.compile(r"\b(?:support|helpdesk|hotline|exploitation applicative)\b")),
    ("erp", re.compile(r"\b(?:erp|sage\s*x3)\b")),
    ("php", re.compile(r"\b(?:php|symfony|laravel|drupal|wordpress)\b")),
    ("cobol/as400", re.compile(r"\b(?:cobol|as\s*400|as400)\b")),
    ("frontend_backend", re.compile(r"\b(?:angular|react|node\.?js|spring)\b")),
    ("cplusplus", re.compile(r"\b(?:c\+\+|c#)\b")),
    ("embedded", re.compile(r"\b(?:embarque|embarqué|embarques|embarqués|fpga)\b")),
    ("system_network", re.compile(r"\b(?:systeme|système|reseau|réseau)\b")),
    ("administrator", re.compile(r"\badministrateur\b")),
    ("agility_it", re.compile(r"\b(?:agilite|agilité|operating model)\b")),
    ("automatisme", re.compile(r"\bautomatisme\b")),
    ("digital_learning", re.compile(r"\b(?:digital learning|pedagogique|pédagogique)\b")),
    ("actuarial", re.compile(r"\bactuariell?e?s?\b")),
    ("documentaliste", re.compile(r"\bdocumentaliste\b")),
    ("comptable", re.compile(r"\b(?:comptable|comptabilite|comptabilité)\b")),
    ("conducteur", re.compile(r"\bconducteur\b")),
    ("gestionnaire", re.compile(r"\bgestionnaire\b")),
)
_SOFTWARE_WITHOUT_DATA_AI_RE = re.compile(
    r"\b(?:developpeur|developpeuse|ingenieur logiciel|software engineer)\b"
)


def title_off_target_marker(title: str) -> str | None:
    if _SYSTEM_NETWORK_ADMIN_RE.search(title):
        return "system_network"
    for marker, pattern in _OFF_TARGET_TITLE_PATTERNS:
        if pattern.search(title):
            if marker == "system_network" and _STRONG_DATA_AI_DEV_TITLE_RE.search(title):
                continue
            return marker
    if _SOFTWARE_WITHOUT_DATA_AI_RE.search(
        title
    ) and not _STRONG_DATA_AI_DEV_TITLE_RE.search(title):
        return "software_engineering"
    return None


def should_skip_configured_title_hard_reject(title: str, blocker: str) -> bool:
    """Keep Data/AI dev titles from generic configured fullstack/dev blockers."""
    normalized = blocker.strip()
    if normalized in {"full stack", "full-stack", "fullstack"}:
        return bool(_STRONG_DATA_AI_DEV_TITLE_RE.search(title))
    if normalized == "expert":
        return bool(
            re.search(
                r"(?<![a-z0-9])(?:ai|data|ia|intelligence\s+artificielle|llm|"
                r"machine\s+learning|ml)(?![a-z0-9])",
                title,
            )
        )
    return False


def has_analytics_title_scope(title: str) -> bool:
    return bool(
        re.search(
            r"(?<![a-z0-9])(?:analyste\s+data|analytics\s+engineer|"
            r"business\s+analyst\s+data|data\s+analyst|product\s+analyst|"
            r"product\s+data\s+analyst)(?![a-z0-9])",
            title,
        )
    )


def has_role_relevance_signal(
    *,
    title: str,
    description: str,
    positive_title_keywords: tuple[str, ...],
    target_roles: list[str],
) -> bool:
    if any(keyword and keyword in title for keyword in positive_title_keywords):
        return True
    if any(role and role in title for role in target_roles):
        return True
    if _ROLE_RELEVANCE_TITLE_RE.search(title):
        return True
    if _STRONG_DATA_AI_DEV_TITLE_RE.search(title):
        return True
    if _DATA_TITLE_RE.search(title):
        return True
    if _ANALYST_TITLE_RE.search(title) and (
        contains_any(description, CORE_DATA_TECH_TOKENS)
        or contains_any(description, ANALYTICAL_OWNERSHIP_TOKENS)
    ):
        return True
    return contains_any(description, DESCRIPTION_ROLE_CONTEXT_TOKENS) and contains_any(
        description,
        CORE_DATA_TECH_TOKENS,
    )
