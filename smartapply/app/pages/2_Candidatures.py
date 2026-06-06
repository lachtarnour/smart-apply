"""Generated applications — downloads and Gmail draft action."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    apply_app_style,
    pipeline_singleton,
    render_badge_row,
    render_empty_state,
    render_info_panel,
    render_page_header,
    status_label,
)
from smartapply.database import session_scope
from smartapply.database.models import Application, JobStatus
from smartapply.database.repository import (
    add_contact,
    list_applications,
    update_application_tracking,
    upsert_document,
)
from smartapply.email_agent.eml_export import MISSING_RECIPIENT_PLACEHOLDER, export_eml
from smartapply.jobsearch import APPLICATION_STATUSES, next_action_for
from smartapply.pipeline.output_paths import application_output_dir

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_missing(value) -> bool:  # noqa: ANN001
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value) -> str:  # noqa: ANN001
    return "" if _is_missing(value) else str(value)


def _optional_text(value) -> str | None:  # noqa: ANN001
    text = _text(value).strip()
    return text or None


def _email_text(value) -> str:  # noqa: ANN001
    return _text(value).strip().lower()


def _is_valid_email(value: str) -> bool:
    return bool(value and EMAIL_RE.match(value))


def _session_text_default(key: str, value) -> None:  # noqa: ANN001
    current = st.session_state.get(key)
    if _is_missing(current) or not isinstance(current, str):
        st.session_state[key] = _text(value)
    else:
        st.session_state.setdefault(key, _text(value))


def _contact_summary(row) -> str:  # noqa: ANN001
    parts: list[str] = []
    full_name = _optional_text(row.get("contact_full_name"))
    job_title = _optional_text(row.get("contact_job_title"))
    reason = _optional_text(row.get("contact_reason"))
    location_hint = _optional_text(row.get("contact_location_hint"))
    confidence = row.get("contact_confidence")
    if full_name:
        parts.append(full_name)
    if job_title:
        parts.append(job_title)
    if reason:
        parts.append(f"raison={reason}")
    if location_hint:
        parts.append(f"lieu={location_hint}")
    try:
        if not _is_missing(confidence):
            parts.append(f"score={float(confidence):.2f}")
    except (TypeError, ValueError):
        pass
    return " · ".join(parts)


def _attachment_paths_from_app(app: Application) -> list[str]:
    docs = {doc.doc_type: doc for doc in app.documents}
    cv_pdf_doc = docs.get("cv_pdf")
    letter_pdf_doc = docs.get("motivation_letter_pdf")
    cv_path = (
        _optional_text(app.cv_pdf_path)
        or _optional_text(cv_pdf_doc.path if cv_pdf_doc else None)
    )
    paths = [
        cv_path,
        _optional_text(letter_pdf_doc.path if letter_pdf_doc else None),
    ]
    return [path for path in paths if path and Path(path).exists()]


def _regenerate_eml(
    app: Application,
    *,
    recipient: str | None,
    cc_recipient: str | None,
) -> str | None:
    subject = _text(app.email_subject).strip()
    body = _text(app.email_body).strip()
    if not subject or not body:
        return None
    output_dir = pipeline_singleton().settings.output_dir
    eml_path = (
        Path(app.eml_path)
        if app.eml_path
        else application_output_dir(output_dir, app.id) / "draft.eml"
    )
    written = export_eml(
        subject=subject,
        body=body,
        sender=pipeline_singleton().profile.identity.email,
        recipient=recipient or MISSING_RECIPIENT_PLACEHOLDER,
        cc_recipient=cc_recipient,
        attachments=_attachment_paths_from_app(app),
        out_path=eml_path,
    )
    app.eml_path = str(written)
    return str(written)


st.set_page_config(page_title="Candidatures | SmartApply", page_icon="📝", layout="wide")
apply_app_style()
render_page_header(
    "Centre de contrôle des candidatures",
    "Piloter les dossiers générés, vérifier les contacts, relire les documents et préparer les actions sans envoi automatique.",
    icon="📝",
    badges=[
        ("Revue manuelle obligatoire", "warn"),
        ("Brouillons Gmail optionnels", "blue"),
        ("Aucun envoi automatique", "neutral"),
    ],
)

with session_scope() as s:
    apps = list_applications(s)
    rows = []
    for a in apps:
        docs = {doc.doc_type: doc for doc in a.documents}
        letter_doc = docs.get("motivation_letter")
        letter_extra = (
            letter_doc.extra if letter_doc and isinstance(letter_doc.extra, dict) else {}
        )
        cv_pdf_doc = docs.get("cv_pdf")
        letter_pdf_doc = docs.get("motivation_letter_pdf")
        rows.append(
            {
                "id": a.id,
                "job_id": a.job_id,
                "company": a.job.company if a.job else "",
                "title": a.job.title if a.job else "",
                "status": a.status,
                "status_label": status_label(a.status),
                "next_action": next_action_for(
                    a.status,
                    a.updated_at,
                    has_contact=a.contact is not None,
                    has_gmail_draft=bool(a.gmail_draft_id),
                ),
                "subject": _text(a.email_subject),
                "body": _text(a.email_body),
                "email_cc": _text(a.email_cc),
                "letter_subject": _text(letter_extra.get("subject", "")),
                "letter_body": _text(letter_doc.content if letter_doc else ""),
                "contact": _text(a.contact.email if a.contact else ""),
                "contact_full_name": _text(a.contact.full_name if a.contact else ""),
                "contact_job_title": _text(a.contact.job_title if a.contact else ""),
                "contact_location_hint": _text(a.contact.location_hint if a.contact else ""),
                "contact_reason": _text(a.contact.decision_reason if a.contact else ""),
                "contact_confidence": a.contact.confidence if a.contact else None,
                "contact_source_url": _text(a.contact.source_url if a.contact else ""),
                "strategy": _text(a.application_strategy),
                "form_url": _optional_text(a.form_submission_url),
                "cv_path": _optional_text(a.cv_docx_path),
                "cv_pdf_path": _optional_text(a.cv_pdf_path)
                or _optional_text(cv_pdf_doc.path if cv_pdf_doc else None),
                "letter_pdf_path": _optional_text(letter_pdf_doc.path if letter_pdf_doc else None),
                "eml_path": _optional_text(a.eml_path),
                "notes": _text(a.notes),
                "updated_at": a.updated_at,
            }
        )

df = pd.DataFrame(rows)
if df.empty:
    render_empty_state(
        "Aucune candidature générée",
        "Crée d'abord une candidature depuis le Workflow ou la page Offres.",
    )
    st.stop()

col_search, col_status = st.columns([1.5, 1])
with col_search:
    search = st.text_input("Rechercher", placeholder="Entreprise, poste, contact, action...")
with col_status:
    status_values = ["(tous)"] + sorted(df["status"].dropna().unique().tolist())
    status_filter = st.selectbox(
        "Statut",
        options=status_values,
        format_func=lambda value: "Tous les statuts" if value == "(tous)" else status_label(value),
    )

visible_df = df.copy()
if status_filter != "(tous)":
    visible_df = visible_df[visible_df["status"] == status_filter]
if search.strip():
    needle = search.strip().lower()
    cols = ["company", "title", "status_label", "next_action", "subject", "contact"]
    mask = pd.Series(False, index=visible_df.index)
    for col in cols:
        mask = mask | visible_df[col].fillna("").astype(str).str.lower().str.contains(
            needle,
            regex=False,
        )
    visible_df = visible_df[mask]

if visible_df.empty:
    render_empty_state(
        "Aucune candidature ne correspond aux filtres",
        "Élargis la recherche ou affiche tous les statuts.",
    )
    st.stop()

ready_statuses = {
    JobStatus.EMAIL_GENERATED,
    JobStatus.READY_FOR_FORM_SUBMISSION,
    JobStatus.DRAFT_CREATED,
}
needs_review = visible_df[
    visible_df["contact"].fillna("").astype(str).eq("")
    | visible_df["status"].isin([JobStatus.CONTACT_MISSING, JobStatus.QUALITY_REJECTED])
]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Candidatures visibles", len(visible_df))
k2.metric("Prêtes", int(visible_df["status"].isin(ready_statuses).sum()))
k3.metric("À revoir", len(needs_review))
k4.metric("Contact trouvé", int(visible_df["contact"].fillna("").astype(str).ne("").sum()))
k5.metric("Formulaire requis", int(visible_df["form_url"].notna().sum()))

st.markdown("### 1. Liste des candidatures")
st.dataframe(
    visible_df.drop(
        columns=[
            "status",
            "body",
            "letter_subject",
            "letter_body",
            "email_cc",
            "contact_full_name",
            "contact_job_title",
            "contact_location_hint",
            "contact_reason",
            "contact_confidence",
            "contact_source_url",
            "cv_path",
            "cv_pdf_path",
            "letter_pdf_path",
            "eml_path",
            "form_url",
        ]
    ),
    hide_index=True,
    width="stretch",
    height=380,
)

st.divider()

st.markdown("### 2. Détail candidature sélectionnée")
app_id = st.selectbox(
    "Candidature",
    options=visible_df["id"].astype(int).tolist(),
    format_func=lambda app_id: (
        f"[{app_id}] "
        f"{visible_df.loc[visible_df['id'] == app_id, 'company'].iloc[0]} — "
        f"{visible_df.loc[visible_df['id'] == app_id, 'title'].iloc[0]}"
    ),
)
row = df[df["id"] == int(app_id)]

if row.empty:
    st.warning("Inconnue.")
    st.stop()

r = row.iloc[0]
contact = _optional_text(r["contact"])
email_cc = _optional_text(r["email_cc"])
subject_key = f"applications_subject_{int(app_id)}"
body_key = f"applications_body_{int(app_id)}"
_session_text_default(subject_key, r["subject"])
_session_text_default(body_key, r["body"])
contact_valid_now = _is_valid_email(contact or "")
has_form = bool(_optional_text(r["form_url"]))
has_draft = _text(r["status"]) == JobStatus.DRAFT_CREATED
placeholder_visible = any(
    MISSING_RECIPIENT_PLACEHOLDER in value
    for value in [contact or "", _text(r["subject"]), _text(r["body"])]
)
st.markdown(
    f"""
    <div class="sa-panel">
      <h3 style="margin:0;">{_text(r['title'])}</h3>
      <div class="sa-muted">{_text(r['company'])} · prochaine action : {_text(r['next_action'])}</div>
    </div>
    """,
    unsafe_allow_html=True,
)
render_badge_row(
    [
        (status_label(_text(r["status"])), "good" if _text(r["status"]) in ready_statuses else "blue"),
        ("Contact fiable" if contact_valid_now else "Contact à vérifier", "good" if contact_valid_now else "warn"),
        ("Formulaire requis", "purple" if has_form else "neutral"),
        ("Brouillon Gmail créé" if has_draft else "Revue nécessaire", "good" if has_draft else "warn"),
    ]
)
if not contact_valid_now:
    render_info_panel(
        "Contact à vérifier avant usage",
        "Aucun destinataire fiable n'est attaché à cette candidature. Corrige le contact avant d'utiliser l'EML ou Gmail.",
        kind="warning",
    )
if placeholder_visible:
    render_info_panel(
        "Destinataire placeholder détecté",
        "Le fichier email contient encore un destinataire temporaire. Remplace-le par un email valide avant toute utilisation.",
        kind="danger",
    )

meta_col, contact_col = st.columns([1.2, 1])
with meta_col:
    st.markdown(
        f"""
        <div class="sa-kv">
          <div class="sa-kv-label">Statut</div><div class="sa-kv-value">{status_label(_text(r['status']))}</div>
          <div class="sa-kv-label">Stratégie</div><div class="sa-kv-value">{_text(r['strategy']) or '—'}</div>
          <div class="sa-kv-label">Contact</div><div class="sa-kv-value">{contact or '—'}</div>
          <div class="sa-kv-label">CC</div><div class="sa-kv-value">{email_cc or '—'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with contact_col:
    contact_summary = _contact_summary(r)
    with st.expander("Détails contact", expanded=not contact_valid_now):
        st.write(f"Email : `{contact or '—'}`")
        if email_cc:
            st.write(f"CC : `{email_cc}`")
        st.write(contact_summary or "Pas de détail contact disponible.")
        if _optional_text(r["contact_source_url"]):
            st.caption(f"Source : {_optional_text(r['contact_source_url'])}")

form_url = _optional_text(r["form_url"])
if form_url:
    st.link_button("Ouvrir le formulaire", form_url)

with st.expander("Modifier le destinataire / CC", expanded=False):
    contact_key = f"applications_contact_{int(app_id)}"
    cc_key = f"applications_cc_{int(app_id)}"
    _session_text_default(contact_key, contact or "")
    _session_text_default(cc_key, email_cc or "")
    st.text_input(
        "Destinataire principal",
        key=contact_key,
        placeholder="recrutement@entreprise.com",
    )
    st.text_input(
        "CC optionnel",
        key=cc_key,
        placeholder="head.of.data@entreprise.com",
        help=(
            "À garder exceptionnel : un responsable Data/IA très fiable, "
            "même entreprise, localisation non contradictoire."
        ),
    )
    verify_col, save_col = st.columns(2)
    primary_email = _email_text(st.session_state.get(contact_key))
    cc_email = _email_text(st.session_state.get(cc_key))
    with verify_col:
        if st.button("Vérifier le destinataire", key=f"verify_contact_{int(app_id)}"):
            if not _is_valid_email(primary_email):
                st.error("Adresse destinataire invalide.")
            else:
                result = pipeline_singleton().contact_service.verify_email(primary_email)
                if result is True:
                    st.success("Adresse vérifiée par le fournisseur.")
                elif result is False:
                    st.error("Adresse refusée par la vérification.")
                else:
                    st.info("Aucun vérificateur disponible ou réponse non concluante.")
    with save_col:
        if st.button("Enregistrer contact / CC", key=f"save_contact_{int(app_id)}"):
            if primary_email and not _is_valid_email(primary_email):
                st.error("Adresse destinataire invalide.")
            elif cc_email and not _is_valid_email(cc_email):
                st.error("Adresse CC invalide.")
            else:
                with session_scope() as s:
                    app = s.get(Application, int(app_id))
                    if app is not None:
                        if primary_email:
                            contact_row = add_contact(
                                s,
                                company=app.job.company if app.job else _text(r["company"]),
                                email=primary_email,
                                source_url="manual",
                                confidence=1.0,
                                decision_reason="manual_ui",
                            )
                            app.contact_id = contact_row.id
                        else:
                            app.contact_id = None
                        app.email_cc = cc_email or None
                        eml_path = _regenerate_eml(
                            app,
                            recipient=primary_email,
                            cc_recipient=cc_email or None,
                        )
                        if eml_path:
                            upsert_document(
                                s,
                                int(app_id),
                                doc_type="eml",
                                path=eml_path,
                            )
                st.success("Contact mis à jour.")
                st.rerun()

letter_body = _text(r["letter_body"])
letter_subject = _text(r["letter_subject"])
tab_letter, tab_email, tab_follow = st.tabs(["Lettre", "Email final", "Suivi"])
with tab_letter:
    if letter_body:
        if letter_subject:
            st.text_input("Sujet de la lettre", value=letter_subject, disabled=True)
        st.text_area(
            "Corps de la lettre",
            value=letter_body,
            height=220,
            disabled=True,
        )
    else:
        render_empty_state("Lettre non disponible", "Aucune lettre n'est attachée à cette candidature.")

with tab_email:
    if not contact_valid_now:
        render_info_panel(
            "Email non prêt à envoyer",
            "Le contenu peut être relu, mais le destinataire doit être corrigé avant export ou brouillon Gmail.",
            kind="warning",
        )
    st.text_input("Sujet", key=subject_key)
    st.text_area("Corps de l'email", key=body_key, height=220)
if st.button("Enregistrer l'email final"):
    with session_scope() as s:
        app = s.get(Application, int(app_id))
        if app is not None:
            app.email_subject = str(st.session_state[subject_key]).strip()
            app.email_body = str(st.session_state[body_key]).strip()
            upsert_document(
                s,
                int(app_id),
                doc_type="email",
                content=app.email_body,
                extra={"subject": app.email_subject},
            )
            eml_path = _regenerate_eml(
                app,
                recipient=contact,
                cc_recipient=email_cc,
            )
            if eml_path:
                upsert_document(s, int(app_id), doc_type="eml", path=eml_path)
    st.success("Email final enregistré.")
    st.rerun()

with tab_follow:
    row_status = _text(r["status"])
    current_status = row_status if row_status in APPLICATION_STATUSES else APPLICATION_STATUSES[0]
    new_status = st.selectbox(
        "Statut",
        options=APPLICATION_STATUSES,
        index=APPLICATION_STATUSES.index(current_status),
        format_func=status_label,
    )
    new_notes = st.text_area(
        "Notes / prochaines actions",
        value=_text(r["notes"]),
        height=120,
        placeholder="Ex: relancer le recruteur mardi, préparer 3 exemples de projets NLP, feedback reçu...",
    )
    if st.button("Enregistrer le suivi", type="primary"):
        try:
            with session_scope() as s:
                update_application_tracking(
                    s,
                    int(app_id),
                    status=new_status,
                    notes=new_notes,
                )
            st.success("Suivi mis a jour.")
            st.rerun()
        except Exception as e:
            st.error(f"Echec : {e}")

st.divider()
st.markdown("### 3. Actions et documents")
cols = st.columns(4)
cv_path = _optional_text(r["cv_path"])
if cv_path and Path(cv_path).exists():
    cols[0].download_button(
        "⬇️ Télécharger le CV (DOCX)",
        Path(cv_path).read_bytes(),
        file_name=Path(cv_path).name,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

cv_pdf_path = _optional_text(r["cv_pdf_path"])
if cv_pdf_path and Path(cv_pdf_path).exists():
    cols[1].download_button(
        "⬇️ Télécharger le CV (PDF)",
        Path(cv_pdf_path).read_bytes(),
        file_name=Path(cv_pdf_path).name,
        mime="application/pdf",
    )

letter_pdf_path = _optional_text(r["letter_pdf_path"])
if letter_pdf_path and Path(letter_pdf_path).exists():
    cols[2].download_button(
        "⬇️ Télécharger la lettre (PDF)",
        Path(letter_pdf_path).read_bytes(),
        file_name=Path(letter_pdf_path).name,
        mime="application/pdf",
    )

eml_path = _optional_text(r["eml_path"])
if eml_path and Path(eml_path).exists():
    if not contact_valid_now:
        cols[3].warning("EML à vérifier : destinataire manquant ou invalide.")
    else:
        cols[3].download_button(
            "⬇️ Télécharger l'email (.eml)",
            Path(eml_path).read_bytes(),
            file_name=Path(eml_path).name,
            mime="message/rfc822",
        )

st.divider()
if not contact:
    st.info("Ajoute ou trouve un contact avant de créer un brouillon Gmail.")

final_subject = str(st.session_state.get(subject_key, "")).strip()
final_body = str(st.session_state.get(body_key, "")).strip()
contact_valid = _is_valid_email(contact)
draft_disabled = not contact_valid or not final_subject or not final_body
if st.button("📧 Créer un brouillon Gmail", type="primary", disabled=draft_disabled):
    try:
        from smartapply.email_agent.gmail_draft import create_draft_result

        created_draft_id: str | None = None
        with session_scope() as s:
            app = s.get(Application, int(app_id))
            if app is None:
                raise RuntimeError("Candidature introuvable.")
            attachment_paths = [
                path
                for path in [cv_pdf_path, letter_pdf_path]
                if path and Path(path).exists()
            ]
            result = create_draft_result(
                subject=final_subject,
                body=final_body,
                recipient=contact or "",
                cc_recipient=email_cc,
                sender=pipeline_singleton().profile.identity.email,
                attachment_paths=attachment_paths,
            )
            if result.status != "draft_created" or not result.draft_id:
                st.error(result.error or "Gmail n'a pas renvoyé d'identifiant de brouillon.")
            else:
                app.email_subject = final_subject
                app.email_body = final_body
                app.email_cc = email_cc
                upsert_document(
                    s,
                    int(app_id),
                    doc_type="email",
                    content=final_body,
                    extra={"subject": final_subject},
                )
                eml_path = _regenerate_eml(
                    app,
                    recipient=contact,
                    cc_recipient=email_cc,
                )
                if eml_path:
                    upsert_document(s, int(app_id), doc_type="eml", path=eml_path)
                app.gmail_draft_id = result.draft_id
                app.status = JobStatus.DRAFT_CREATED
                if app.job is not None:
                    app.job.status = JobStatus.DRAFT_CREATED
                created_draft_id = result.draft_id
        if created_draft_id:
            st.success(f"Brouillon créé : {created_draft_id}")
    except Exception as e:
        st.error(f"Échec : {e}")
elif draft_disabled:
    if contact and not contact_valid:
        st.caption("Adresse contact invalide : corrige le destinataire avant Gmail.")
    else:
        st.caption("Contact, sujet et corps d'email sont obligatoires pour créer un brouillon.")
