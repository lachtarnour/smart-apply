"""Autopilot page — daily high-volume drafting run."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from smartapply.app._helpers import apply_app_style
from smartapply.config import get_settings
from smartapply.jobsearch import AutopilotRunner
from smartapply.scrapers import SERPAPI_DATE_POSTED_LABELS

SERPAPI_LANGUAGE_OPTIONS = {
    "Bilingue EN + FR": "en,fr",
    "Anglais uniquement": "en",
    "Français uniquement": "fr",
}


st.set_page_config(page_title="Autopilot | SmartApply", page_icon="🚀", layout="wide")
apply_app_style()

settings = get_settings()

st.title("🚀 Autopilot candidatures")
st.caption("Recherche, sélection, CV, email, contact RH, brouillon Gmail ou dossier prêt.")

col1, col2 = st.columns(2)
with col1:
    query = st.text_input(
        "Requête",
        value="Data Scientist OR Machine Learning Engineer",
    )
    st.caption("Les rôles séparés par `OR` sont recherchés séparément. L'anglais est gardé, un alias FR est ajouté si utile.")
    location = st.text_input("Localisation", value=settings.serpapi_default_location)
    sources = st.multiselect(
        "Sources",
        options=["serpapi", "francetravail"],
        default=["serpapi", "francetravail"],
    )
with col2:
    date_options = list(SERPAPI_DATE_POSTED_LABELS)
    default_date = (
        settings.serpapi_date_posted
        if settings.serpapi_date_posted in SERPAPI_DATE_POSTED_LABELS
        else "week"
    )
    date_posted = st.selectbox(
        "Fraîcheur SerpApi",
        options=date_options,
        index=date_options.index(default_date),
        format_func=lambda value: SERPAPI_DATE_POSTED_LABELS[value],
        help="Appliqué uniquement à Google Jobs / SerpApi.",
    )
    language_label = st.selectbox(
        "Langue Google Jobs",
        options=list(SERPAPI_LANGUAGE_OPTIONS),
        index=0,
        help="Bilingue lance les recherches en contexte anglais puis français.",
    )
    target = st.number_input(
        "Objectif brouillons/dossiers",
        min_value=1,
        max_value=300,
        value=settings.autopilot_target_drafts,
    )
    max_per_source = st.number_input(
        "Résultats max par source",
        min_value=5,
        max_value=300,
        value=max(25, settings.autopilot_target_drafts),
    )
    gmail_draft = st.toggle("Créer des brouillons Gmail", value=False)
    quality_gate = st.toggle("Quality gate LLM strict", value=True)

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

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Tentées", data["attempted"])
            k2.metric("Brouillons", data["draft_created"])
            k3.metric("Dossiers formulaire", data["ready_for_form_submission"])
            k4.metric("Rejets qualité", data["quality_rejected"])

            if data["errors"]:
                st.warning("\n".join(data["errors"]))

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
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            with st.expander("Rapport JSON"):
                st.json(data)
        except Exception as e:
            st.error(f"Echec autopilot : {e}")
