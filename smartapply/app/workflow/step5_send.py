"""Workflow step 5: final review and Gmail draft creation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import pipeline_singleton, status_label
from smartapply.app.workflow.state import reset_workflow
from smartapply.app.workflow.step4_generate import _existing_generated_application_ids
from smartapply.app.workflow.widgets import _download_button, _status_pill
from smartapply.database import session_scope
from smartapply.database.models import Application, JobStatus
from smartapply.database.repository import add_contact, update_application_tracking, upsert_document


def step5_send() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 5 · Finalisation Gmail et formulaires</h3>
          <div class="sa-muted">Dernier contrôle avant action : ajuste l'email, vérifie les pièces jointes, crée les brouillons Gmail ou marque les formulaires soumis.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    app_ids = st.session_state["wf_generated_app_ids"]
    if not app_ids:
        app_ids = _existing_generated_application_ids()
        if not app_ids:
            st.warning("Aucune candidature générée. Retourne à l'étape 4.")
            return
        st.session_state["wf_generated_app_ids"] = app_ids
        st.info(
            "Mode reprise : j'affiche les candidatures déjà générées en base."
        )

    with session_scope() as s:
        apps = s.query(Application).filter(Application.id.in_(app_ids)).all()
        # Pull out the data we need into plain dicts to avoid using detached
        # SQLAlchemy objects after the session closes.
        rows = []
        for app in apps:
            docs = {doc.doc_type: doc for doc in app.documents}
            letter_pdf = docs.get("motivation_letter_pdf")
            analysis_raw = (
                app.job.analysis.raw_response
                if app.job and app.job.analysis and isinstance(app.job.analysis.raw_response, dict)
                else {}
            )
            rows.append(
                {
                    "id": app.id,
                    "job_id": app.job_id,
                    "title": app.job.title,
                    "company": app.job.company,
                    "application_url": app.job.application_url,
                    "job_description": app.job.cleaned_description or app.job.description,
                    "job_location": app.job.location,
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
                    "cv_pdf_path": app.cv_pdf_path,
                    "cv_docx_path": app.cv_docx_path,
                    "eml_path": app.eml_path,
                    "letter_pdf_path": letter_pdf.path if letter_pdf else None,
                    "form_url": app.form_submission_url,
                    "gmail_draft_id": app.gmail_draft_id,
                    "email_sent_at": app.email_sent_at,
                    "form_submitted_at": app.form_submitted_at,
                    "validation_warnings": app.validation_warnings or [],
                }
            )

    if not rows:
        st.info("Pas de candidature à envoyer.")
        return

    drafts_done = sum(1 for row in rows if row["gmail_draft_id"])
    with_contact = sum(1 for row in rows if row["contact"])
    with_form = sum(1 for row in rows if row["form_url"])
    sent_done = sum(1 for row in rows if row["email_sent_at"] or row["form_submitted_at"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Candidatures", len(rows))
    m2.metric("Contacts trouvés", with_contact)
    m3.metric("Formulaires", with_form)
    m4.metric("Actions faites", drafts_done + sent_done)

    summary_df = pd.DataFrame(
        [
            {
                "id": row["id"],
                "company": row["company"],
                "title": row["title"],
                "strategy": row["strategy"],
                "contact": row["contact"] or "—",
                "gmail": "créé" if row["gmail_draft_id"] else "à faire",
                "form": "soumis" if row["form_submitted_at"] else ("à faire" if row["form_url"] else "—"),
                "status": row["status_label"],
            }
            for row in rows
        ]
    )
    st.dataframe(summary_df, hide_index=True, width="stretch")

    st.caption(
        "Rien n'est envoyé automatiquement. Le bouton Gmail crée seulement un brouillon, après validation manuelle."
    )
    for row in rows:
        _render_send_card(row)

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("⬅ Retour à l'étape 4", key="wf_step5_back", width="stretch"):
            st.session_state["wf_step"] = 4
            st.rerun()
    with col_reset:
        if st.button("🔄 Nouveau workflow", key="wf_reset", width="stretch"):
            reset_workflow()
            st.rerun()

    st.divider()


def _render_send_card(row: dict[str, Any]) -> None:
    app_id = row["id"]
    strategy_icon = {
        "email_only": "📧",
        "email_and_form": "📧🗂",
        "form_only": "🗂",
    }.get(row["strategy"], "")
    expanded_default = row["status"] != JobStatus.SENT
    with st.expander(
        f"{strategy_icon} [{app_id}] {row['title']} @ {row['company']}  ·  {row['status_label']}",
        expanded=expanded_default,
    ):
        subject_key = f"wf_final_subject_{app_id}"
        body_key = f"wf_final_body_{app_id}"
        st.session_state.setdefault(subject_key, row["subject"])
        st.session_state.setdefault(body_key, row["body"])

        col1, col2 = st.columns([2, 1])
        with col1:
            status_kind = "good" if row["gmail_draft_id"] or row["email_sent_at"] else "warn"
            st.markdown(
                f"{_status_pill(str(row['strategy']), 'blue')} "
                f"{_status_pill(str(row['status_label']), status_kind)}",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Contact** : `{row['contact'] or '— aucun —'}`")
            contact_bits = [
                row.get("contact_full_name"),
                row.get("contact_job_title"),
                f"raison={row.get('contact_reason')}" if row.get("contact_reason") else None,
                f"lieu={row.get('contact_location_hint')}" if row.get("contact_location_hint") else None,
                (
                    f"score={float(row['contact_confidence']):.2f}"
                    if row.get("contact_confidence") is not None
                    else None
                ),
            ]
            contact_summary = " · ".join(str(bit) for bit in contact_bits if bit)
            if contact_summary:
                st.caption(contact_summary)
            if row.get("email_cc"):
                st.markdown(f"**CC** : `{row['email_cc']}`")
            if row["form_url"]:
                st.link_button("Ouvrir le formulaire ATS", row["form_url"], width="stretch")
            if row["validation_warnings"]:
                with st.expander(
                    f"Warnings validation CV ({len(row['validation_warnings'])})",
                    expanded=False,
                ):
                    for warning in row["validation_warnings"]:
                        st.write(f"- {warning}")

            st.markdown("**Documents finaux**")
            doc_cols = st.columns(3)
            with doc_cols[0]:
                _download_button(
                    "CV PDF",
                    row.get("cv_pdf_path"),
                    "application/pdf",
                    f"wf_send_cv_pdf_{app_id}",
                )
            with doc_cols[1]:
                _download_button(
                    "CV DOCX",
                    row.get("cv_docx_path"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    f"wf_send_cv_docx_{app_id}",
                )
            with doc_cols[2]:
                _download_button(
                    "Lettre PDF",
                    row.get("letter_pdf_path"),
                    "application/pdf",
                    f"wf_send_letter_pdf_{app_id}",
                )

            st.text_input("Sujet final", key=subject_key)
            st.text_area(
                "Email final",
                height=240,
                key=body_key,
            )
            if st.button(
                "Recharger l'email généré",
                key=f"wf_reset_email_{app_id}",
            ):
                st.session_state[subject_key] = row["subject"]
                st.session_state[body_key] = row["body"]
                st.rerun()
        with col2:
            reviewed = st.checkbox(
                "J'ai vérifié le contact, le CV, la lettre et l'email",
                key=f"wf_reviewed_{app_id}",
            )
            final_subject = str(st.session_state.get(subject_key, "")).strip()
            final_body = str(st.session_state.get(body_key, "")).strip()
            if row["contact"]:
                if row["strategy"] == "form_only":
                    st.caption(
                        "Stratégie initiale formulaire. Comme un contact est disponible, "
                        "tu peux aussi préparer un email si tu le choisis."
                    )
            else:
                st.caption("Aucun contact email attaché à cette candidature.")
                if st.button(
                    "🔎 Chercher un contact email",
                    key=f"wf_lookup_contact_{app_id}",
                    help="Action manuelle. Peut utiliser le fournisseur de contacts configuré.",
                ):
                    _lookup_contact_for_application(row)
                    st.rerun()

            # ---- Gmail draft button ----
            if row["gmail_draft_id"]:
                st.success(f"✓ Brouillon Gmail : `{row['gmail_draft_id']}`")
            else:
                disabled = (
                    not row["contact"]
                    or not reviewed
                    or not final_subject
                    or not final_body
                )
                # Dry-run preview: shows exactly what would be passed to
                # ``drafts().create`` if the user clicked the button. No
                # Gmail call is made; if the MIME cannot be built we
                # surface the validation error in the same expander so
                # the user fixes it before clicking.
                with st.expander(
                    "Aperçu du brouillon avant création (dry-run)",
                    expanded=False,
                ):
                    _render_gmail_dry_run_preview(
                        {
                            **row,
                            "subject": final_subject,
                            "body": final_body,
                        }
                    )
                if st.button(
                    "📧 Créer le brouillon Gmail",
                    disabled=disabled,
                    key=f"wf_gmail_{app_id}",
                    type="primary",
                ):
                    _create_gmail_draft(
                        {
                            **row,
                            "subject": final_subject,
                            "body": final_body,
                        }
                    )
                    st.rerun()
                if row["strategy"] == "form_only":
                    st.caption(
                        "Formulaire prioritaire. Le brouillon Gmail reste possible "
                        "si tu as volontairement attaché un contact."
                    )
                elif not row["contact"]:
                    st.caption("Pas de contact → cherche un contact ou soumets via le formulaire.")
                elif not reviewed:
                    st.caption("Coche la validation finale avant Gmail.")
                elif not final_subject or not final_body:
                    st.caption("Sujet et email final obligatoires.")

            st.divider()

            # ---- Manual tracking buttons ----
            if row["email_sent_at"]:
                st.markdown(f"✓ Email envoyé : `{row['email_sent_at'].strftime('%d/%m %H:%M')}`")
            else:
                if st.button(
                    "✉ Marquer email envoyé",
                    key=f"wf_mark_email_{app_id}",
                    disabled=not row["contact"],
                ):
                    with session_scope() as s:
                        update_application_tracking(s, app_id, email_sent=True)
                    st.rerun()

            if row["strategy"] in ("email_and_form", "form_only"):
                if row["form_submitted_at"]:
                    st.markdown(
                        f"✓ Form soumis : `{row['form_submitted_at'].strftime('%d/%m %H:%M')}`"
                    )
                else:
                    if st.button(
                        "🗂 Marquer formulaire soumis",
                        key=f"wf_mark_form_{app_id}",
                    ):
                        with session_scope() as s:
                            update_application_tracking(s, app_id, form_submitted=True)
                        st.rerun()


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
            app.cv_pdf_path or (cv_pdf_doc.path if cv_pdf_doc else None) or app.cv_docx_path,
            letter_pdf_doc.path if letter_pdf_doc else None,
        )
        if path and Path(path).exists()
    ]
    output_dir = pipeline_singleton().settings.output_dir
    eml_path = Path(app.eml_path) if app.eml_path else output_dir / f"job-{app.job_id}" / "draft.eml"
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


def _lookup_contact_for_application(row: dict[str, Any]) -> None:
    service = pipeline_singleton().contact_service
    candidate = service.find(
        company=str(row.get("company") or ""),
        application_url=str(row.get("application_url") or "") or None,
        contact_domain_hint=_row_analysis_value(row, "contact_domain_hint"),
        contact_domain_kind=_row_analysis_value(row, "contact_domain_kind") or "unknown",
        job_description=str(row.get("job_description") or "") or None,
        analysis=row.get("analysis_raw") if isinstance(row.get("analysis_raw"), dict) else None,
        job_location=_row_analysis_value(row, "extracted_location")
        or str(row.get("job_location") or "")
        or None,
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
        return

    with session_scope() as s:
        app = s.get(Application, int(row["id"]))
        if app is None:
            st.error("Candidature introuvable.")
            return
        company = app.job.company if app.job else str(row.get("company") or "")
        contact_row = add_contact(
            s,
            company=company,
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

    st.success(f"Contact trouvé et attaché : {candidate.email}")


def _render_gmail_dry_run_preview(row: dict[str, Any]) -> None:
    """Render a no-network preview of what the Gmail draft would contain.

    Uses ``dry_run_draft`` which validates inputs and builds the MIME
    body locally without touching Gmail. Any validation problem
    (missing attachment, blocked extension, oversized body, …) is
    surfaced as a Streamlit error so the user fixes it before clicking
    the real button.
    """
    from smartapply.email_agent.gmail_draft import (
        GmailDraftError,
        dry_run_draft,
    )
    from smartapply.profile import get_profile

    subject = str(row.get("subject") or "").strip()
    body = str(row.get("body") or "").strip()
    recipient = str(row.get("contact") or "").strip()
    cc_recipient = str(row.get("email_cc") or "").strip() or None
    attachments = [
        p
        for p in (
            row.get("cv_pdf_path"),
            row.get("cv_docx_path"),
            row.get("letter_pdf_path"),
        )
        if p and Path(p).exists()
    ]
    sender = get_profile().identity.email if recipient else None

    if not (recipient and subject and body):
        st.info(
            "Renseigne destinataire, sujet et corps de mail pour voir "
            "l'aperçu du brouillon."
        )
        return

    try:
        preview = dry_run_draft(
            subject=subject,
            body=body,
            recipient=recipient,
            cc_recipient=cc_recipient,
            sender=sender,
            attachment_paths=attachments,
        )
    except GmailDraftError as exc:
        st.error(f"Impossible de construire le brouillon : {exc}")
        return

    st.markdown(f"**Destinataire** : `{preview.to}`")
    if cc_recipient:
        st.markdown(f"**CC** : `{cc_recipient}`")
    st.markdown(f"**Objet** : `{preview.subject}`")
    if preview.attachment_names:
        attachments_inline = ", ".join(f"`{name}`" for name in preview.attachment_names)
        st.markdown(f"**Pièces jointes** : {attachments_inline}")
    else:
        st.caption("Aucune pièce jointe.")
    st.caption(
        f"Taille encodée (base64) ~ {preview.encoded_size_bytes // 1024} Ko. "
        "Aucun appel Gmail n'a été effectué."
    )
    st.text_area(
        "Aperçu du body (lecture seule)",
        preview.body_preview,
        height=200,
        disabled=True,
        label_visibility="collapsed",
    )


def _create_gmail_draft(row: dict[str, Any]) -> None:
    from smartapply.email_agent import export_eml
    from smartapply.email_agent.gmail_draft import create_draft_result
    from smartapply.profile import get_profile

    subject = str(row.get("subject") or "").strip()
    body = str(row.get("body") or "").strip()
    recipient = str(row.get("contact") or "").strip()
    cc_recipient = str(row.get("email_cc") or "").strip() or None
    if not recipient:
        st.error("Contact email manquant.")
        return
    if not subject or not body:
        st.error("Sujet et corps de mail obligatoires.")
        return

    sender = get_profile().identity.email
    attachments = [
        p
        for p in (
            row.get("cv_pdf_path"),
            row.get("cv_docx_path"),
            row.get("letter_pdf_path"),
        )
        if p and Path(p).exists()
    ]

    eml_path = row.get("eml_path")
    if eml_path:
        try:
            export_eml(
                subject=subject,
                body=body,
                sender=sender,
                recipient=recipient,
                cc_recipient=cc_recipient,
                attachments=attachments,
                out_path=eml_path,
            )
        except Exception as e:
            st.warning(f"Email .eml non régénéré : {e}")

    with session_scope() as s:
        app = s.get(Application, row["id"])
        if app is not None:
            app.email_subject = subject
            app.email_body = body
            upsert_document(
                s,
                app.id,
                doc_type="email",
                content=body,
                extra={"subject": subject},
            )
            if eml_path:
                app.eml_path = eml_path
                upsert_document(s, app.id, doc_type="eml", path=eml_path)

    result = create_draft_result(
        subject=subject,
        body=body,
        recipient=recipient,
        cc_recipient=cc_recipient,
        sender=sender,
        attachment_paths=attachments,
    )
    if result.status != "draft_created" or not result.draft_id:
        st.error(result.error or "Gmail n'a pas renvoyé d'identifiant de brouillon.")
        return

    # Persist the draft_id and bump status
    with session_scope() as s:
        app = s.get(Application, row["id"])
        if app is not None:
            app.email_subject = subject
            app.email_body = body
            app.gmail_draft_id = result.draft_id
            app.status = JobStatus.DRAFT_CREATED
            if app.job is not None:
                app.job.status = JobStatus.DRAFT_CREATED
    st.success(f"✓ Brouillon Gmail créé : {result.draft_id}")


# ============================================================
