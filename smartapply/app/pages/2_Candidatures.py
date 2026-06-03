"""Generated applications — downloads and Gmail draft action."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from smartapply.app._helpers import apply_app_style, pipeline_singleton, status_label
from smartapply.database import session_scope
from smartapply.database.repository import (
    list_applications,
    update_application_tracking,
    upsert_document,
)
from smartapply.jobsearch import APPLICATION_STATUSES, next_action_for


st.set_page_config(page_title="Candidatures | SmartApply", page_icon="📝", layout="wide")
apply_app_style()
st.markdown(
    """
    <div class="sa-hero">
      <h2>Candidatures générées</h2>
      <div class="sa-muted">Suivi opérationnel des dossiers prêts, brouillons Gmail, formulaires et relances.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

with session_scope() as s:
    apps = list_applications(s)
    rows = []
    for a in apps:
        docs = {doc.doc_type: doc.path for doc in a.documents if doc.path}
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
                "subject": a.email_subject,
                "body": a.email_body or "",
                "contact": a.contact.email if a.contact else None,
                "strategy": a.application_strategy,
                "form_url": a.form_submission_url,
                "cv_path": a.cv_docx_path,
                "cv_pdf_path": a.cv_pdf_path or docs.get("cv_pdf"),
                "letter_pdf_path": docs.get("motivation_letter_pdf"),
                "eml_path": a.eml_path,
                "notes": a.notes,
                "updated_at": a.updated_at,
            }
        )

df = pd.DataFrame(rows)
if df.empty:
    st.info("Pas encore de candidature générée. Va dans la page Offres pour en créer.")
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
    st.warning("Aucune candidature ne correspond à ce filtre.")
    st.stop()

st.dataframe(
    visible_df.drop(
        columns=[
            "status",
            "body",
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

st.subheader("Téléchargement & relance")
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
st.write(f"**{r['title']}** — {r['company']}")
st.write(f"Statut : **{status_label(r['status'])}**")
st.write(f"Prochaine action : **{r['next_action']}**")
st.write(f"Contact : `{r['contact']}`")
st.write(f"Stratégie : `{r['strategy']}`")
if r["form_url"]:
    st.link_button("Ouvrir le formulaire", r["form_url"])

st.subheader("Email final")
subject_key = f"applications_subject_{int(app_id)}"
body_key = f"applications_body_{int(app_id)}"
st.session_state.setdefault(subject_key, r["subject"] or "")
st.session_state.setdefault(body_key, r["body"] or "")
st.text_input("Sujet", key=subject_key)
st.text_area("Corps de l'email", key=body_key, height=220)
if st.button("Enregistrer l'email final"):
    with session_scope() as s:
        from smartapply.database.models import Application

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
    st.success("Email final enregistré.")
    st.rerun()

st.subheader("Suivi")
current_status = r["status"] if r["status"] in APPLICATION_STATUSES else APPLICATION_STATUSES[0]
new_status = st.selectbox(
    "Statut",
    options=APPLICATION_STATUSES,
    index=APPLICATION_STATUSES.index(current_status),
    format_func=status_label,
)
new_notes = st.text_area(
    "Notes / prochaines actions",
    value=r["notes"] or "",
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
st.subheader("Documents")
cols = st.columns(4)
cv_path = r["cv_path"]
if cv_path and Path(cv_path).exists():
    cols[0].download_button(
        "⬇️ Télécharger le CV (DOCX)",
        Path(cv_path).read_bytes(),
        file_name=Path(cv_path).name,
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

cv_pdf_path = r["cv_pdf_path"]
if cv_pdf_path and Path(cv_pdf_path).exists():
    cols[1].download_button(
        "⬇️ Télécharger le CV (PDF)",
        Path(cv_pdf_path).read_bytes(),
        file_name=Path(cv_pdf_path).name,
        mime="application/pdf",
    )

letter_pdf_path = r["letter_pdf_path"]
if letter_pdf_path and Path(letter_pdf_path).exists():
    cols[2].download_button(
        "⬇️ Télécharger la lettre (PDF)",
        Path(letter_pdf_path).read_bytes(),
        file_name=Path(letter_pdf_path).name,
        mime="application/pdf",
    )

eml_path = r["eml_path"]
if eml_path and Path(eml_path).exists():
    cols[3].download_button(
        "⬇️ Télécharger l'email (.eml)",
        Path(eml_path).read_bytes(),
        file_name=Path(eml_path).name,
        mime="message/rfc822",
    )

st.divider()
if not r["contact"]:
    st.info("Ajoute ou trouve un contact avant de créer un brouillon Gmail.")

final_subject = str(st.session_state.get(subject_key, "")).strip()
final_body = str(st.session_state.get(body_key, "")).strip()
draft_disabled = not r["contact"] or not final_subject or not final_body
if st.button("📧 Créer un brouillon Gmail", type="primary", disabled=draft_disabled):
    try:
        from smartapply.email_agent.gmail_draft import create_draft

        with session_scope() as s:
            from smartapply.database.models import Application

            app = s.get(Application, int(app_id))
            attachment_paths = [
                path
                for path in [cv_pdf_path or cv_path, letter_pdf_path]
                if path and Path(path).exists()
            ]
            draft_id = create_draft(
                subject=final_subject,
                body=final_body,
                recipient=r["contact"] or "",
                sender=pipeline_singleton().profile.identity.email,
                attachment_paths=attachment_paths,
            )
            app.email_subject = final_subject
            app.email_body = final_body
            upsert_document(
                s,
                int(app_id),
                doc_type="email",
                content=final_body,
                extra={"subject": final_subject},
            )
            app.gmail_draft_id = draft_id
            app.status = "draft_created"
        st.success(f"Brouillon créé : {draft_id}")
    except Exception as e:
        st.error(f"Échec : {e}")
elif draft_disabled:
    st.caption("Contact, sujet et corps d'email sont obligatoires pour créer un brouillon.")
