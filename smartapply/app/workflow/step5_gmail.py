"""Gmail draft helpers for workflow step 5."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

from smartapply.database import session_scope
from smartapply.database.models import Application, JobStatus
from smartapply.database.repository import upsert_document


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
