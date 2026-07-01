"""Autopilot page — daily high-volume drafting run."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    SERPAPI_LANGUAGE_OPTIONS,
    apply_app_style,
    render_badge_row,
    render_info_panel,
    render_page_header,
)
from smartapply.config import get_settings
from smartapply.jobsearch import AutopilotRunner
from smartapply.scrapers import SERPAPI_DATE_POSTED_LABELS

st.set_page_config(page_title="Autopilot | SmartApply", page_icon="🚀", layout="wide")
apply_app_style()

settings = get_settings()


def _serpapi_effective_config(
    *,
    max_results: int,
    date_posted: str,
    location: str | None,
) -> str:
    fallback_target = settings.serpapi_low_result_fallback_target
    effective_fallback = min(max_results, fallback_target) if fallback_target > 0 else 0
    freshness = SERPAPI_DATE_POSTED_LABELS.get(date_posted, date_posted)
    return (
        "SerpApi config effective : "
        f"lieu {location or settings.serpapi_default_location} · "
        f"fraîcheur {freshness} · "
        f"résultats/source {max_results} · "
        f"fallback {effective_fallback} · "
        f"pages max {settings.serpapi_max_pages}"
    )


render_page_header(
    "Autopilot",
    "Mode avancé pour produire plusieurs dossiers en une seule passe contrôlée.",
    icon="🚀",
    badges=[
        ("Quality gate recommandé", "good"),
        ("Brouillons Gmail optionnels", "blue"),
        ("SerpApi peut consommer des crédits", "warn"),
    ],
)

date_options = list(SERPAPI_DATE_POSTED_LABELS)
default_date = (
    settings.serpapi_date_posted
    if settings.serpapi_date_posted in SERPAPI_DATE_POSTED_LABELS
    else "week"
)

left, right = st.columns(2)
with left:
    with st.container():
        st.markdown("### 1. Cible de recherche")
        query = st.text_input(
            "Requête",
            value="Data Scientist OR Machine Learning Engineer OR IA Engineer",
        )
        st.caption("Les rôles séparés par `OR` sont recherchés séparément. L'anglais est gardé, un alias FR est ajouté si utile.")
        location = st.text_input("Localisation", value=settings.serpapi_default_location)

    with st.container():
        st.markdown("### 2. Sources et fraîcheur")
        sources = st.multiselect(
            "Sources",
            options=["serpapi", "francetravail", "linkedin", "welcometothejungle"],
            default=["serpapi", "francetravail", "linkedin", "welcometothejungle"],
        )
        date_posted = st.selectbox(
            "Fraîcheur des offres",
            options=date_options,
            index=date_options.index(default_date),
            format_func=lambda value: SERPAPI_DATE_POSTED_LABELS[value],
            help="Appliqué à Google Jobs (chip date_posted) et à France Travail (minCreationDate).",
        )
        language_label = st.selectbox(
            "Langue Google Jobs",
            options=list(SERPAPI_LANGUAGE_OPTIONS),
            index=0,
            help="Bilingue lance les recherches en contexte anglais puis français.",
        )

with right:
    with st.container():
        st.markdown("### 3. Volume")
        target = st.number_input(
            "Objectif brouillons/dossiers",
            min_value=1,
            max_value=300,
            value=settings.autopilot_target_drafts,
        )
        max_source_limit = (
            settings.linkedin_max_results if "linkedin" in sources else 300
        )
        max_source_default = (
            settings.linkedin_max_results
            if "linkedin" in sources
            else settings.autopilot_target_drafts
        )
        max_per_source = st.number_input(
            "Résultats max par source",
            min_value=1,
            max_value=int(max_source_limit),
            value=min(int(max_source_default), int(max_source_limit)),
        )
        with st.expander("Détails de recherche", expanded=False):
            if "serpapi" in sources:
                st.write(
                    _serpapi_effective_config(
                        max_results=int(max_per_source),
                        date_posted=date_posted,
                        location=location,
                    )
                )
            else:
                st.caption("SerpApi désactivé pour ce run.")
            if "linkedin" in sources:
                st.caption(
                    "LinkedIn/Apify : "
                    f"limite globale {settings.linkedin_max_results} depuis .env."
                )

    with st.container():
        st.markdown("### 4. Sécurité")
        gmail_draft = st.toggle("Créer des brouillons Gmail", value=False)
        quality_gate = st.toggle("Quality gate IA strict", value=True)
        render_badge_row(
            [
                ("Rien n'est envoyé automatiquement", "good"),
                ("Brouillons Gmail optionnels", "blue" if gmail_draft else "neutral"),
                ("Quality gate actif" if quality_gate else "Quality gate désactivé", "good" if quality_gate else "warn"),
            ]
        )
        if "serpapi" in sources:
            render_info_panel(
                "Crédits SerpApi",
                "La recherche Google Jobs peut consommer des crédits. Réduis le volume ou retire SerpApi pour un run gratuit France Travail.",
                kind="warning",
            )

st.markdown("### 5. Lancement")

if st.button("Lancer Autopilot", type="primary", disabled=not query or not sources):
    with st.spinner("Autopilot en cours..."):
        try:
            report = AutopilotRunner().run(
                query=query,
                location=location or None,
                sources=sources,
                max_per_source=int(max_per_source),
                target_drafts=int(target),
                create_gmail_drafts=gmail_draft,
                require_quality_gate=quality_gate,
                date_posted=date_posted,
                serpapi_hl=SERPAPI_LANGUAGE_OPTIONS[language_label],
            )
            data = report.to_dict()
            st.success(
                f"{data['productive_outputs']} sortie(s) prête(s), "
                f"{data['draft_created']} brouillon(s) Gmail, "
                f"{data['ready_for_form_submission']} dossier(s) formulaire."
            )

            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Tentées", data["attempted"])
            k2.metric("Sorties prêtes", data["productive_outputs"])
            k3.metric("Brouillons Gmail", data["draft_created"])
            k4.metric("Dossiers formulaire", data["ready_for_form_submission"])
            k5.metric("Rejets qualité", data["quality_rejected"])

            if data["errors"]:
                render_info_panel(
                    "Erreurs pendant le run",
                    "Certaines offres n'ont pas pu être traitées. Les détails restent visibles dans le rapport technique.",
                    kind="warning",
                )
                with st.expander("Erreurs techniques"):
                    st.write("\n".join(data["errors"]))

            if data["applications"]:
                rows = [
                    {
                        "job_id": a["job_id"],
                        "application_id": a["application_id"],
                        "status": a["status"],
                        "contact": a["contact_email"],
                        "formulaire": a.get("contact_form_url"),
                        "source": a["contact_source"],
                        "draft": a["gmail_draft_id"],
                        "reason": (a.get("quality_review") or {}).get("decision_reason"),
                    }
                    for a in data["applications"]
                ]
                st.markdown("### Applications générées")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            with st.expander("Rapport technique"):
                st.json(data)
        except Exception as e:
            st.error(f"Echec autopilot : {e}")
