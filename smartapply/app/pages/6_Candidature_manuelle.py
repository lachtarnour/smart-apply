"""One-shot manual application page."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

import streamlit as st

from smartapply.app._helpers import (
    apply_app_style,
    pipeline_singleton,
    render_empty_state,
    render_html_open_button,
    render_info_panel,
    render_page_header,
    status_label,
)
from smartapply.app.workflow.step5_send import (
    _html_document_path,
    _render_close_button_styles,
    _render_send_card,
)
from smartapply.database import session_scope
from smartapply.database.models import Job
from smartapply.database.repository import list_jobs
from smartapply.offers import ManualOfferInput

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

st.set_page_config(
    page_title="Candidature manuelle | CandiPilot",
    page_icon="CP",
    layout="wide",
)
apply_app_style()

render_page_header(
    "Offre manuelle",
    "Créer un dossier complet depuis une offre copiée-collée ou reçue hors scraper.",
    icon="CP",
    badges=[
        ("Import structuré", "blue"),
        ("Analyse IA directe", "good"),
        ("Aucun envoi automatique", "neutral"),
    ],
)
_render_close_button_styles()


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _email_from_text(value: str | None) -> str | None:
    match = EMAIL_RE.search(value or "")
    return match.group(0).lower() if match else None


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


def _render_application_result(
    app,
    *,  # noqa: ANN001
    process=None,  # noqa: ANN001
    ingest=None,  # noqa: ANN001
) -> None:
    st.success(f"Candidature #{app.application_id} générée.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Offre", app.job_id)
    m2.metric("Statut", status_label(app.status or ""))
    m3.metric("Analyse", "OK" if process and process.analyzed else "Déjà prête")
    m4.metric("Import", f"{ingest.persisted} dispo." if ingest else "Offre existante")

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


def _render_result(report: dict[str, Any]) -> None:
    ingest = report["ingest"]
    process = report["process"]
    applications = report["applications"]

    if not applications:
        st.warning("Aucune candidature générée pour cette offre.")
        st.json(_report_to_dict(report), expanded=False)
        return

    app = applications[0]
    _render_application_result(app, process=process, ingest=ingest)

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Voir les candidatures", width="stretch"):
            st.switch_page("pages/2_Candidatures.py")
    with c2, st.expander("Détails techniques", expanded=False):
        st.json(_report_to_dict(report), expanded=False)


def _remember_current_job_from_report(report: dict[str, Any]) -> None:
    applications = report.get("applications")
    if applications:
        st.session_state["manual_current_job_id"] = int(applications[0].job_id)
        return

    ingest = report.get("ingest")
    job_ids = getattr(ingest, "job_ids", None)
    if job_ids:
        st.session_state["manual_current_job_id"] = int(job_ids[0])


def _current_manual_job_id() -> int | None:
    current = st.session_state.get("manual_current_job_id")
    if current:
        return int(current)

    last_report = st.session_state.get("manual_one_shot_last_report")
    if isinstance(last_report, dict):
        _remember_current_job_from_report(last_report)
        current = st.session_state.get("manual_current_job_id")
        if current:
            return int(current)

    with session_scope() as s:
        latest = list_jobs(s, source="manual", limit=1)
        if not latest:
            return None
        return int(latest[0].id)


def _manual_job_detail(job_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        job = s.get(Job, int(job_id))
        if job is None:
            return None
        source_data = job.source_data if isinstance(job.source_data, dict) else {}
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "status": job.status,
            "location": job.location or "",
            "url": job.application_url or "",
            "description": job.cleaned_description or job.description or "",
            "recruiter": str(source_data.get("recruiter") or ""),
            "analysis_ready": job.analysis is not None,
        }


def _manual_application_row(job_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        job = s.get(Job, int(job_id))
        if job is None or job.application is None:
            return None
        app = job.application
        docs = {doc.doc_type: doc for doc in app.documents}
        cv_html = docs.get("cv_html")
        letter_pdf = docs.get("motivation_letter_pdf")
        letter_html = docs.get("motivation_letter_html")
        analysis_raw = (
            job.analysis.raw_response
            if job.analysis and isinstance(job.analysis.raw_response, dict)
            else {}
        )
        return {
            "id": app.id,
            "job_id": app.job_id,
            "title": job.title,
            "company": job.company,
            "application_url": job.application_url,
            "job_description": job.cleaned_description or job.description,
            "job_location": job.location,
            "source_data": job.source_data,
            "analysis_raw": analysis_raw,
            "status": app.status,
            "status_label": status_label(app.status),
            "strategy": app.application_strategy,
            "contact": app.contact.email if app.contact else None,
            "contact_full_name": app.contact.full_name if app.contact else None,
            "contact_job_title": app.contact.job_title if app.contact else None,
            "contact_location_hint": app.contact.location_hint if app.contact else None,
            "contact_reason": app.contact.decision_reason if app.contact else None,
            "contact_confidence": app.contact.confidence if app.contact else None,
            "email_cc": app.email_cc,
            "subject": app.email_subject or "",
            "body": app.email_body or "",
            "cv_html_path": _html_document_path(
                cv_html,
                app.cv_pdf_path,
                app.cv_docx_path,
            ),
            "cv_pdf_path": app.cv_pdf_path,
            "cv_docx_path": app.cv_docx_path,
            "eml_path": app.eml_path,
            "letter_html_path": _html_document_path(
                letter_html,
                letter_pdf.path if letter_pdf else None,
            ),
            "letter_pdf_path": letter_pdf.path if letter_pdf else None,
            "form_url": app.form_submission_url,
            "gmail_draft_id": app.gmail_draft_id,
            "email_sent_at": app.email_sent_at,
            "form_submitted_at": app.form_submitted_at,
            "validation_warnings": app.validation_warnings or [],
        }


def _render_generate_current_offer(job_id: int, detail: dict[str, Any]) -> None:
    render_info_panel(
        "Dossier à générer",
        "Cette offre est enregistrée, mais le CV, la lettre et l'email final ne sont pas encore produits.",
        kind="warning",
    )
    st.markdown(
        f"""
        <div class="sa-panel">
          <h3 style="margin:0;">{detail['title']}</h3>
          <div class="sa-muted">{detail['company']} · {detail['location'] or 'Lieu non indiqué'} · {status_label(detail['status'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if detail["url"]:
        st.link_button("Ouvrir l'offre", detail["url"])
    contact_key = f"manual_current_contact_{job_id}"
    st.session_state.setdefault(
        contact_key,
        _email_from_text(detail.get("recruiter")) or "",
    )
    manual_contact = st.text_input(
        "Contact si tu l'as déjà",
        key=contact_key,
        placeholder="recrutement@entreprise.com",
    )
    if st.button("Générer la candidature complète", type="primary", width="stretch"):
        with st.spinner("Analyse, CV, lettre et email..."):
            try:
                pipeline = _pipeline_for_manual_run()
                process = pipeline.analyze_jobs([int(job_id)])
                app_report = pipeline.apply_to(
                    int(job_id),
                    contact_email=_clean(manual_contact),
                    contact_form_url=detail["url"] or None,
                    create_gmail_draft=False,
                )
                st.session_state["manual_workspace_last_application"] = {
                    "process": process,
                    "application": app_report,
                }
                st.session_state["manual_current_job_id"] = int(job_id)
                st.rerun()
            except Exception as e:
                st.error(f"Génération impossible : {e}")


def _render_current_manual_offer_workspace() -> None:
    st.divider()
    st.markdown("### Offre actuelle")

    job_id = _current_manual_job_id()
    if job_id is None:
        render_empty_state(
            "Aucune offre actuelle",
            "Colle une offre dans le formulaire au-dessus pour créer le dossier.",
        )
        return

    detail = _manual_job_detail(job_id)
    if detail is None:
        st.warning("Offre actuelle introuvable.")
        return

    row = _manual_application_row(job_id)
    if row is None:
        _render_generate_current_offer(job_id, detail)
        return

    _render_send_card(row)


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
                _remember_current_job_from_report(report)
            except Exception as e:
                st.error(f"Candidature manuelle : {e}")

if st.session_state.get("manual_one_shot_last_report"):
    st.divider()
    _render_result(st.session_state["manual_one_shot_last_report"])

_render_current_manual_offer_workspace()
