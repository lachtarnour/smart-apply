"""One-shot manual application page."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import streamlit as st

from smartapply.app._helpers import (
    apply_app_style,
    pipeline_singleton,
    render_html_open_button,
    render_page_header,
    status_label,
)
from smartapply.offers import ManualOfferInput

st.set_page_config(
    page_title="Candidature manuelle | SmartApply",
    page_icon="SA",
    layout="wide",
)
apply_app_style()

render_page_header(
    "Offre manuelle",
    "Créer un dossier complet depuis une offre copiée-collée ou reçue hors scraper.",
    icon="SA",
    badges=[
        ("Import structuré", "blue"),
        ("Analyse IA directe", "good"),
        ("Aucun envoi automatique", "neutral"),
    ],
)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _report_to_dict(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "ingest": asdict(report["ingest"]),
        "process": asdict(report["process"]) if report["process"] else None,
        "applications": [asdict(app) for app in report["applications"]],
    }


def _pipeline_for_manual_run():
    pipeline = pipeline_singleton()
    if not hasattr(pipeline, "run_manual_offer"):
        pipeline_singleton.cache_clear()
        pipeline = pipeline_singleton()
    return pipeline


def _render_result(report: dict[str, Any]) -> None:
    ingest = report["ingest"]
    process = report["process"]
    applications = report["applications"]

    if not applications:
        st.warning("Aucune candidature générée pour cette offre.")
        st.json(_report_to_dict(report), expanded=False)
        return

    app = applications[0]
    st.success(f"Candidature #{app.application_id} générée.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Offre", app.job_id)
    m2.metric("Statut", status_label(app.status or ""))
    m3.metric("Analyse", "OK" if process and process.analyzed else "Déjà prête")
    m4.metric("Import", f"{ingest.persisted} dispo.")

    if app.contact_email:
        st.write(f"Destinataire : `{app.contact_email}`")
    if app.contact_form_url:
        st.write(f"Formulaire : `{app.contact_form_url}`")
    if app.gmail_draft_id:
        st.write(f"Brouillon Gmail : `{app.gmail_draft_id}`")
    if app.validation_warnings:
        st.warning("Points à vérifier : " + " · ".join(app.validation_warnings[:5]))
    if app.validation_errors:
        st.error("Erreurs : " + " · ".join(app.validation_errors[:5]))

    st.markdown("**Documents finaux**")
    doc_cols = st.columns(2)
    with doc_cols[0]:
        render_html_open_button(
            "Ouvrir le CV HTML",
            app.cv_html_path,
            key=f"manual_open_cv_html_{app.application_id or app.job_id}",
        )
    with doc_cols[1]:
        render_html_open_button(
            "Ouvrir la lettre HTML",
            app.letter_html_path,
            key=f"manual_open_letter_html_{app.application_id or app.job_id}",
        )

    paths = {
        "CV PDF": app.cv_pdf_path,
        "Lettre PDF": app.letter_pdf_path,
        "CV HTML": app.cv_html_path,
        "Lettre HTML": app.letter_html_path,
        "Email EML": app.eml_path,
        "CV DOCX": app.docx_path,
    }
    for label, path in paths.items():
        if path:
            st.write(f"{label} : `{path}`")

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Voir les candidatures", width="stretch"):
            st.switch_page("pages/2_Candidatures.py")
    with c2, st.expander("Détails techniques", expanded=False):
        st.json(_report_to_dict(report), expanded=False)


with st.form("manual_one_shot_form"):
    c1, c2 = st.columns([1.15, 1])
    with c1:
        manual_title = st.text_input(
            "Titre du poste",
            placeholder="Data Scientist NLP",
        )
        manual_company = st.text_input(
            "Entreprise",
            placeholder="Acme",
        )
        manual_location = st.text_input(
            "Localisation",
            placeholder="Paris, Remote, Lyon...",
        )
    with c2:
        manual_company_url = st.text_input(
            "URL entreprise",
            placeholder="https://acme.com",
        )
        manual_application_url = st.text_input(
            "URL candidature/offre",
            placeholder="https://jobs.acme.com/...",
        )
        create_gmail_draft = st.toggle(
            "Créer un brouillon Gmail",
            value=False,
        )

    manual_recruiter = st.text_input(
        "Recruteur / contact",
        placeholder="Jean Dupont / jean@acme.com / LinkedIn...",
    )
    manual_job_text = st.text_area(
        "Description de l'offre",
        height=260,
        placeholder="Missions, stack, profil recherché, contrat, avantages...",
    )
    manual_company_description = st.text_area(
        "Description de l'entreprise",
        height=180,
        placeholder="Secteur, produit, équipe, contexte, clients...",
    )

    submitted = st.form_submit_button("Générer la candidature", type="primary")

if submitted:
    missing = []
    if not manual_title.strip():
        missing.append("titre du poste")
    if not manual_company.strip():
        missing.append("entreprise")
    if not manual_job_text.strip():
        missing.append("description de l'offre")

    if missing:
        st.error("Champs requis : " + ", ".join(missing) + ".")
    else:
        offer = ManualOfferInput(
            entreprise=manual_company.strip(),
            offre=manual_title.strip(),
            description_offre=manual_job_text.strip(),
            description_entreprise=_clean(manual_company_description),
            url_entreprise=_clean(manual_company_url),
            recruteur=_clean(manual_recruiter),
            localisation=_clean(manual_location),
            url_candidature=_clean(manual_application_url),
        )
        with st.spinner("Analyse et génération du dossier..."):
            try:
                report = _pipeline_for_manual_run().run_manual_offer(
                    offer,
                    create_gmail_draft=create_gmail_draft,
                )
                st.session_state["manual_one_shot_last_report"] = report
            except Exception as e:
                st.error(f"Candidature manuelle : {e}")

if st.session_state.get("manual_one_shot_last_report"):
    st.divider()
    _render_result(st.session_state["manual_one_shot_last_report"])
