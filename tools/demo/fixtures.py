"""Offline, fictional fixtures. Imported only by the demo entry points."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def configure(runtime: Path, *, reset: bool = False) -> None:
    runtime = runtime.resolve()
    marker = runtime / ".elan-demo"
    if runtime.exists() and any(runtime.iterdir()) and (
        not marker.is_file() or marker.read_text() != "fictional-demo-v1"
    ):
        raise RuntimeError(f"Refusing to use a non-demo directory: {runtime}")
    if reset and runtime.exists():
        if not marker.is_file() or marker.read_text() != "fictional-demo-v1":
            raise RuntimeError(f"Refusing to reset an unmarked directory: {runtime}")
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    if (runtime / "demo.db").exists() and not marker.exists():
        raise RuntimeError("Existing database is not a demo database")
    marker.write_text("fictional-demo-v1")
    os.environ.update(
        ELAN_HOME=str(runtime),
        ELAN_ENV_FILE=str(runtime / ".env"),
        DATABASE_URL="sqlite:///" + str(runtime / "demo.db"),
        PROFILE_DIR=str(runtime / "profile"),
        OUTPUT_DIR=str(runtime / "documents"),
        CACHE_DIR=str(runtime / "cache"),
        LLM_PROVIDER="mock",
        EMBEDDINGS_PROVIDER="mock",
        OPENAI_API_KEY="",
        SERPAPI_API_KEY="",
        FRANCETRAVAIL_CLIENT_ID="",
        FRANCETRAVAIL_CLIENT_SECRET="",
        APIFY_TOKEN="",
        WTTJ_COOKIE="",
        LOG_LEVEL="WARNING",
    )
    write_profile(runtime / "profile")


def bullet(key, text, keywords):
    return dict(
        id=key,
        text=text,
        keywords=keywords,
        numbers=[],
        evidence_level="verified",
        allowed_claims=[text],
        links=[],
    )


def write_profile(path: Path):
    path.mkdir(exist_ok=True)
    for src in (REPO / "smartapply/profile/mock_profile").glob("*.json"):
        shutil.copy2(src, path / src.name)
    payloads = {
        "identity": dict(
            full_name="Camille Martin",
            title="Data Scientist · NLP",
            summary="Data Scientist spécialisée en NLP, recherche documentaire et évaluation de modèles. Python, SQL et apprentissage automatique.",
            location="Paris, France",
            email="camille.martin@example.com",
        ),
        "experiences": [
            dict(
                id="exp_atelier",
                company="Atelier Data",
                title="Data Scientist",
                location="Paris",
                start_date="2024-01",
                end_date="Present",
                keywords=["Python", "NLP", "Machine Learning", "SQL"],
                bullets=[
                    bullet(
                        "atelier_nlp",
                        "Développement de modèles NLP pour classer des documents et extraire les informations utiles aux équipes métier.",
                        ["Python", "NLP"],
                    ),
                    bullet(
                        "atelier_eval",
                        "Construction de jeux de test et évaluation des modèles avec scikit-learn ; analyse des erreurs et documentation des résultats.",
                        ["scikit-learn", "Machine Learning"],
                    ),
                    bullet(
                        "atelier_data",
                        "Préparation de données textuelles avec Python et SQL, nettoyage et contrôle de leur qualité.",
                        ["Python", "SQL"],
                    ),
                ],
            ),
            dict(
                id="exp_sillage",
                company="Sillage Analytics",
                title="Stagiaire Data Science",
                location="Lyon",
                start_date="2023-03",
                end_date="2023-09",
                keywords=["Python", "SQL"],
                bullets=[
                    bullet(
                        "sillage_model",
                        "Entraînement de modèles de classification et comparaison des performances sur des données structurées.",
                        ["Python", "Machine Learning"],
                    ),
                    bullet(
                        "sillage_report",
                        "Restitution des résultats et des limites des modèles auprès des équipes produit.",
                        ["Machine Learning"],
                    ),
                ],
            ),
        ],
        "projects": [
            dict(
                id="proj_rag",
                name="Assistant de recherche documentaire",
                status="portfolio",
                keywords=["NLP", "Python", "RAG"],
                bullets=[
                    bullet(
                        "rag_search",
                        "Conception d’un assistant RAG en Python pour rechercher des passages pertinents dans une base documentaire.",
                        ["RAG", "Python"],
                    )
                ],
            ),
            dict(
                id="proj_classif",
                name="Classification de textes",
                status="portfolio",
                keywords=["NLP", "scikit-learn"],
                bullets=[
                    bullet(
                        "classif_eval",
                        "Comparaison de modèles de classification de textes avec scikit-learn et analyse des erreurs par catégorie.",
                        ["NLP", "scikit-learn"],
                    )
                ],
            ),
        ],
        "skills": dict(
            categories=[
                dict(
                    id="ml_ai",
                    name="Machine Learning & NLP",
                    skills=["Machine Learning", "NLP", "RAG", "scikit-learn"],
                ),
                dict(
                    id="data_analysis",
                    name="Programmation & données",
                    skills=["Python", "SQL", "Pandas", "NumPy"],
                ),
            ],
            core={"data_analysis": ["Python", "SQL"]},
            matching_keywords={"ml_ai": ["NLP", "Machine Learning", "RAG"]},
            profiles=[],
        ),
        "education": [
            dict(
                id="edu_master",
                title="Master",
                field="Data Science",
                institution="Université de Lyon",
                start_year=2021,
                end_year=2023,
            )
        ],
        "languages": [
            dict(name="Français", level="Langue maternelle"),
            dict(name="Anglais", level="Professionnel"),
        ],
        "certificates": [],
        "template_style": dict(
            primary_color_hex="7155C9",
            text_color_hex="242132",
            muted_color_hex="726B83",
            font_family="Arial",
        ),
    }
    for name, value in payloads.items():
        (path / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2))


DESCRIPTIONS = [
    "Aurore Labs développe un moteur de recherche documentaire pour les équipes métier. "
    "Nous recherchons un Data Scientist NLP en CDI à Paris, avec télétravail hybride. "
    "Vos missions : préparer les données textuelles avec Python et SQL, développer des modèles NLP, "
    "construire un assistant RAG et évaluer la qualité des réponses. Vous travaillerez avec "
    "l’équipe produit pour analyser les erreurs et améliorer la pertinence des résultats. "
    "Compétences attendues : Python, SQL, NLP, RAG, scikit-learn. Expérience de 2 ans en data science. "
    "Les décisions techniques sont documentées et les modèles sont évalués sur des jeux de test.",
    "Nova Studio développe des modèles de machine learning pour améliorer la recherche de contenus. "
    "Poste de Machine Learning Engineer en CDI à Paris, organisation hybride. "
    "Missions : préparer les données en Python et SQL, entraîner des modèles de classification, "
    "comparer les performances avec scikit-learn et analyser les erreurs. "
    "Vous collaborez avec les équipes produit sur les jeux de test et la documentation. "
    "Compétences : Python, SQL, scikit-learn, Machine Learning. Expérience de 2 ans souhaitée.",
    "Lumen Recherche conçoit des outils de compréhension automatique de documents. "
    "Data Scientist en CDI à Paris, télétravail hybride. "
    "Vous développez des modèles NLP en Python, préparez les données avec SQL et Pandas, "
    "évaluez les modèles avec scikit-learn et présentez les résultats aux équipes produit. "
    "Profil : expérience de 2 ans en data science, maîtrise de Python, SQL et Machine Learning.",
]


def jobs(source: str, *, initial=False):
    from smartapply.offers import RawJob

    for i in range(2 if initial else 3):
        yield RawJob(
            external_id=f"demo-{source}-{i + 1}",
            source=source,
            title=["Data Scientist NLP", "Machine Learning Engineer", "Data Scientist"][i]
            + ("" if initial else " (F/H)"),
            company=["Aurore Labs", "Nova Studio", "Lumen Recherche"][i],
            location="Paris, France",
            contract_type="CDI",
            remote_policy="hybrid",
            description=DESCRIPTIONS[i] + ("" if initial else " Rejoignez notre équipe à Paris."),
            application_url=f"https://{source}.example.com/offres/demo-{i + 1}",
            source_data={"demo": True},
            published_date=datetime.now(timezone.utc),
        )


def install_providers(delay: float = 0):
    from smartapply.llm.mock_provider import MockLLMProvider
    from smartapply.llm.schemas import ApplicationDraft, JobAnalysis
    from smartapply.scrapers.base import Scraper
    from smartapply.scrapers.registry import _BUILDERS

    class DemoScraper(Scraper):
        name = "serpapi"

        def search(self, query, location=None, *, max_results=None, **kwargs):
            for job in jobs("serpapi"):
                if kwargs.get("stop_requested", lambda: False)():
                    return
                time.sleep(delay)
                yield job

    # Process-local registry only: never modifies the production connectors.
    _BUILDERS["serpapi"] = DemoScraper
    profile = json.loads((Path(os.environ["PROFILE_DIR"]) / "experiences.json").read_text())
    analysis = JobAnalysis(
        fit_score=0.92,
        role_type="Data Scientist NLP",
        seniority="mid",
        domain="Recherche documentaire",
        main_tasks=[
            "Développer des modèles NLP",
            "Évaluer un assistant RAG",
            "Préparer les données textuelles",
        ],
        required_skills=["Python", "SQL", "NLP", "RAG", "scikit-learn"],
        nice_to_have=[],
        match_reasons=[
            "Expérience en NLP et classification de textes",
            "Projet RAG et pratique de Python / SQL",
        ],
        risks=["Modalités du télétravail à confirmer"],
        cv_keywords_to_include=["Python", "NLP", "RAG", "SQL"],
        offer_language="fr",
        company_context="Aurore Labs développe un moteur de recherche documentaire pour les équipes métier.",
        offer_interest_points=[
            "Améliorer la pertinence de la recherche documentaire",
            "Évaluer les modèles avec l’équipe produit",
        ],
    )
    letter = """Madame, Monsieur,

Je souhaite rejoindre Aurore Labs au poste de Data Scientist NLP. Votre moteur de recherche documentaire et le travail sur la pertinence des réponses correspondent à mon intérêt pour les outils qui rendent l’information plus accessible aux équipes métier. La place accordée à l’évaluation des modèles et à la collaboration avec l’équipe produit motive particulièrement ma candidature.

Chez Atelier Data, je développe des modèles NLP pour classer des documents et en extraire les informations utiles. Je prépare les données textuelles avec Python et SQL, construis des jeux de test et analyse les erreurs des modèles avec scikit-learn. Cette expérience m’a appris à relier les résultats d’évaluation aux besoins des utilisateurs, à contrôler la qualité des données et à documenter les limites des solutions proposées.

Mon projet d’assistant de recherche documentaire m’a également permis de concevoir une approche RAG pour retrouver des passages pertinents dans une base de documents. En complément, mon travail sur la classification de textes a renforcé ma pratique de la comparaison de modèles et de l’analyse des erreurs par catégorie. Ces expériences constituent des points d’appui concrets pour contribuer aux missions que vous décrivez.

Je serais heureuse de mettre ces compétences au service de votre équipe et de poursuivre mon apprentissage au contact de vos équipes produit. Je souhaite contribuer à des résultats utiles, mesurables et compréhensibles, tout en portant attention aux limites des modèles utilisés.

Je suis disponible pour échanger sur votre moteur de recherche documentaire, vos méthodes d’évaluation et les attentes du poste.

Bien cordialement,
Camille Martin"""
    parts = letter.split("\n\n")
    letter = (
        parts[0]
        + "\n"
        + parts[1]
        + "\n\n"
        + parts[2]
        + " "
        + parts[3]
        + "\n\n"
        + parts[4]
        + " "
        + parts[5]
        + "\n"
        + parts[6]
    )
    draft = ApplicationDraft(
        cv_title="Data Scientist NLP",
        professional_summary="Data Scientist spécialisée en NLP et recherche documentaire. Expérience en Python, SQL, évaluation de modèles et conception d’assistants RAG.",
        selected_experiences=[
            dict(
                source_id=e["id"],
                bullets=[dict(source_id=b["id"], text=b["text"]) for b in e["bullets"]],
            )
            for e in profile
        ],
        selected_project_ids=["proj_rag", "proj_classif"],
        skills_order=["ml_ai", "data_analysis"],
        selected_skills=[
            dict(category_id="ml_ai", skills=["NLP", "RAG", "scikit-learn", "Machine Learning"]),
            dict(category_id="data_analysis", skills=["Python", "SQL", "Pandas", "NumPy"]),
        ],
        warnings=[],
        motivation_letter_subject="Candidature au poste de Data Scientist NLP",
        motivation_letter_body=letter,
    )
    MockLLMProvider.clear()
    MockLLMProvider.register("job_analysis", analysis)
    MockLLMProvider.register("application_draft", draft)
    MockLLMProvider.register("cv_adaptation", draft.to_cv())


def seed():
    from smartapply.database import init_db
    from smartapply.pipeline import Pipeline
    from smartapply.pipeline.ingest import IngestCollection
    from smartapply.pipeline.ingestor import Ingestor

    init_db()
    report = Ingestor().persist_collection(
        IngestCollection(
            source="welcometothejungle", raw_jobs=list(jobs("welcometothejungle", initial=True))
        )
    )
    Pipeline().filter_pending(job_ids=report.job_ids)
    return report
