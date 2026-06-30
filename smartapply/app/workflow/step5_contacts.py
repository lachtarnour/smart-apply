"""Contact lookup and attachment helpers for workflow step 5."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import streamlit as st

from smartapply.app._helpers import pipeline_singleton
from smartapply.contacts import ContactCandidate, domain_from_url, is_job_board_domain
from smartapply.database import session_scope
from smartapply.database.models import Application, JobStatus
from smartapply.database.repository import add_contact, upsert_document
from smartapply.pipeline.output_paths import application_output_dir

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DECISION_MAKER_CATEGORY_LABELS = {
    "ceo": "CEO / Owner / President / Founder",
    "engineering": "Engineering",
    "finance": "Finance",
    "hr": "Human Resources (HR)",
    "it": "IT (Information Technology)",
    "logistics": "Logistics",
    "marketing": "Marketing",
    "operations": "Operations / Administration",
    "buyer": "Procurement (Buyer)",
    "sales": "Sales",
}


def _is_valid_email(value: str) -> bool:
    return bool(EMAIL_RE.match(value.strip().lower()))


def _render_contact_lookup_controls(row: dict[str, Any]) -> None:
    app_id = int(row["id"])
    domain_default = _suggest_contact_domain(row)
    company_default = str(row.get("company") or "").strip()
    mode = st.radio(
        "Mode de recherche",
        ("Décisionnaire", "Personne précise", "Automatique"),
        horizontal=True,
        key=f"wf_contact_lookup_mode_v2_{app_id}",
    )

    if mode == "Décisionnaire":
        _render_decision_maker_lookup(row, domain_default, company_default)
        return

    if mode == "Personne précise":
        _render_person_lookup(row, domain_default, company_default)
        return

    if st.button(
        "🔎 Chercher un contact email automatiquement",
        key=f"wf_lookup_contact_{app_id}",
        help="Utilise la stratégie analyzer/source configurée.",
    ):
        found = _lookup_contact_for_application(row)
        if found:
            st.rerun()


def _render_decision_maker_lookup(
    row: dict[str, Any],
    domain_default: str,
    company_default: str,
) -> None:
    app_id = int(row["id"])
    domain_key = f"wf_decision_domain_{app_id}"
    company_key = f"wf_decision_company_{app_id}"
    st.session_state.setdefault(domain_key, domain_default)
    st.session_state.setdefault(company_key, company_default)
    lookup_by = st.radio(
        "Chercher par",
        ("Domaine", "Nom entreprise"),
        horizontal=True,
        key=f"wf_decision_lookup_by_{app_id}",
    )
    if lookup_by == "Domaine":
        st.text_input("Domaine", key=domain_key, placeholder="entreprise.com")
    else:
        st.text_input("Nom de l'entreprise", key=company_key)

    options = list(DECISION_MAKER_CATEGORY_LABELS)
    categories = st.multiselect(
        "decision_maker_category",
        options=options,
        default=["hr"],
        format_func=lambda value: f"{value} · {DECISION_MAKER_CATEGORY_LABELS.get(value, value)}",
        key=f"wf_decision_categories_{app_id}",
    )
    if st.button("Chercher décisionnaire", key=f"wf_lookup_decision_maker_{app_id}"):
        found = _lookup_decision_maker_for_application(
            row,
            domain=str(st.session_state.get(domain_key) or "") if lookup_by == "Domaine" else "",
            company_name=str(st.session_state.get(company_key) or "")
            if lookup_by == "Nom entreprise"
            else "",
            categories=categories,
        )
        if found:
            st.rerun()


def _render_person_lookup(
    row: dict[str, Any],
    domain_default: str,
    company_default: str,
) -> None:
    app_id = int(row["id"])
    person_key = f"wf_person_name_{app_id}"
    domain_key = f"wf_person_domain_{app_id}"
    company_key = f"wf_person_company_{app_id}"
    st.session_state.setdefault(person_key, "")
    st.session_state.setdefault(domain_key, domain_default)
    st.session_state.setdefault(company_key, company_default)
    st.text_input("Nom de la personne", key=person_key, placeholder="Prénom Nom")
    lookup_by = st.radio(
        "Entreprise via",
        ("Domaine", "Nom entreprise"),
        horizontal=True,
        key=f"wf_person_lookup_by_{app_id}",
    )
    if lookup_by == "Domaine":
        st.text_input("Domaine", key=domain_key, placeholder="entreprise.com")
    else:
        st.text_input("Nom de l'entreprise", key=company_key)

    if st.button("Chercher personne", key=f"wf_lookup_person_{app_id}"):
        found = _lookup_person_for_application(
            row,
            full_name=str(st.session_state.get(person_key) or ""),
            domain=str(st.session_state.get(domain_key) or "") if lookup_by == "Domaine" else "",
            company_name=str(st.session_state.get(company_key) or "")
            if lookup_by == "Nom entreprise"
            else "",
        )
        if found:
            st.rerun()


def _suggest_contact_domain(row: dict[str, Any]) -> str:
    hint = _row_analysis_value(row, "contact_domain_hint")
    if hint and _row_analysis_value(row, "contact_domain_kind") == "company_domain":
        domain = _domain_from_contact_input(hint)
        if domain:
            return domain

    source_data = row.get("source_data")
    if isinstance(source_data, dict):
        candidates: list[Any] = [
            source_data.get("company_domain"),
            source_data.get("company_website"),
        ]
        company_profile = source_data.get("company_profile")
        if isinstance(company_profile, dict):
            candidates.extend(
                [
                    company_profile.get("domain"),
                    company_profile.get("website"),
                ]
            )
        for candidate in candidates:
            domain = _domain_from_contact_input(candidate)
            if domain:
                return domain

    application_domain = _domain_from_contact_input(row.get("application_url"))
    if application_domain and not is_job_board_domain(application_domain):
        return application_domain
    return ""


def _domain_from_contact_input(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = domain_from_url(raw if "://" in raw else f"https://{raw}")
    if parsed:
        return parsed
    return raw.lower().removeprefix("www.").split("/", 1)[0].split(":", 1)[0]


def _contact_job_location(row: dict[str, Any]) -> str | None:
    return (
        _row_analysis_value(row, "extracted_location") or str(row.get("job_location") or "") or None
    )


def _row_analysis_value(row: dict[str, Any], key: str) -> str:
    raw = row.get("analysis_raw")
    if not isinstance(raw, dict):
        return ""
    return str(raw.get(key) or "").strip()


def _regenerate_final_eml(app: Application, *, recipient: str, cc_recipient: str | None) -> str | None:
    from smartapply.email_agent import export_eml
    from smartapply.profile import get_profile

    subject = str(app.email_subject or "").strip()
    body = str(app.email_body or "").strip()
    if not subject or not body:
        return None

    docs = {doc.doc_type: doc for doc in app.documents}
    cv_pdf_doc = docs.get("cv_pdf")
    letter_pdf_doc = docs.get("motivation_letter_pdf")
    attachments = [
        path
        for path in (
            app.cv_pdf_path or (cv_pdf_doc.path if cv_pdf_doc else None),
            letter_pdf_doc.path if letter_pdf_doc else None,
        )
        if path and Path(path).exists()
    ]
    output_dir = pipeline_singleton().settings.output_dir
    eml_path = (
        Path(app.eml_path)
        if app.eml_path
        else application_output_dir(output_dir, app.id) / "draft.eml"
    )
    written = export_eml(
        subject=subject,
        body=body,
        sender=get_profile().identity.email,
        recipient=recipient,
        cc_recipient=cc_recipient,
        attachments=attachments,
        out_path=eml_path,
    )
    app.eml_path = str(written)
    return str(written)


def _save_manual_contact_for_application(row: dict[str, Any], email: str) -> bool:
    normalized = email.strip().lower()
    if not _is_valid_email(normalized):
        st.error("Adresse email invalide.")
        return False

    return _attach_contact_candidate_to_application(
        row,
        ContactCandidate(
            email=normalized,
            source_url="manual_final_step",
            confidence=1.0,
            provider="manual",
            decision_reason="manual_final_step",
        ),
        success_prefix="Contact enregistré",
    )


def _lookup_contact_for_application(row: dict[str, Any]) -> bool:
    service = pipeline_singleton().contact_service
    candidate = service.find(
        company=str(row.get("company") or ""),
        application_url=str(row.get("application_url") or "") or None,
        contact_domain_hint=_row_analysis_value(row, "contact_domain_hint"),
        contact_domain_kind=_row_analysis_value(row, "contact_domain_kind") or "unknown",
        job_description=str(row.get("job_description") or "") or None,
        analysis=row.get("analysis_raw") if isinstance(row.get("analysis_raw"), dict) else None,
        job_location=_contact_job_location(row),
        source_data=row.get("source_data") if isinstance(row.get("source_data"), dict) else None,
    )
    if candidate is None:
        decision = service.last_lookup_decision
        if decision is not None and decision.warnings:
            st.warning(
                "Aucun contact fiable trouvé. "
                + " · ".join(str(warning) for warning in decision.warnings[:4])
            )
        else:
            st.warning("Aucun contact email fiable trouvé pour cette candidature.")
        return False

    return _attach_contact_candidate_to_application(
        row,
        candidate,
        success_prefix="Contact trouvé et attaché",
    )


def _lookup_decision_maker_for_application(
    row: dict[str, Any],
    *,
    domain: str,
    company_name: str,
    categories: list[str],
) -> bool:
    if not domain.strip() and not company_name.strip():
        st.error("Renseigne un domaine ou un nom d'entreprise.")
        return False
    if not categories:
        st.error("Sélectionne au moins une catégorie.")
        return False

    candidate = pipeline_singleton().contact_service.find_decision_maker(
        domain=domain,
        company_name=company_name,
        categories=categories,
        job_location=_contact_job_location(row),
    )
    if candidate is None:
        st.warning("Aucun décisionnaire fiable trouvé.")
        return False
    return _attach_contact_candidate_to_application(
        row,
        candidate,
        success_prefix="Décisionnaire trouvé et attaché",
    )


def _lookup_person_for_application(
    row: dict[str, Any],
    *,
    full_name: str,
    domain: str,
    company_name: str,
) -> bool:
    if not full_name.strip():
        st.error("Renseigne le nom de la personne.")
        return False
    if not domain.strip() and not company_name.strip():
        st.error("Renseigne un domaine ou un nom d'entreprise.")
        return False

    candidate = pipeline_singleton().contact_service.find_person(
        full_name=full_name,
        domain=domain,
        company_name=company_name,
        job_location=_contact_job_location(row),
    )
    if candidate is None:
        st.warning("Aucun email fiable trouvé pour cette personne.")
        return False
    return _attach_contact_candidate_to_application(
        row,
        candidate,
        success_prefix="Personne trouvée et attachée",
    )


def _attach_contact_candidate_to_application(
    row: dict[str, Any],
    candidate: ContactCandidate,
    *,
    success_prefix: str,
) -> bool:
    with session_scope() as s:
        app = s.get(Application, int(row["id"]))
        if app is None:
            st.error("Candidature introuvable.")
            return False
        contact_row = add_contact(
            s,
            company=app.job.company if app.job else str(row.get("company") or ""),
            email=candidate.email,
            source_url=candidate.source_url,
            confidence=candidate.confidence,
            full_name=candidate.full_name,
            job_title=candidate.job_title,
            location_hint=candidate.location_hint,
            decision_reason=candidate.decision_reason or f"final_step:{candidate.provider}",
        )
        app.contact_id = contact_row.id
        app.application_strategy = "email_and_form" if app.form_submission_url else "email_only"
        if app.status == JobStatus.READY_FOR_FORM_SUBMISSION:
            app.status = JobStatus.EMAIL_GENERATED
            if app.job is not None:
                app.job.status = JobStatus.EMAIL_GENERATED
        eml_path = _regenerate_final_eml(
            app,
            recipient=candidate.email,
            cc_recipient=app.email_cc,
        )
        if eml_path:
            upsert_document(s, app.id, doc_type="eml", path=eml_path)

    st.success(f"{success_prefix} : {candidate.email}")
    return True
