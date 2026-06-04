"""Offers list — searchable operational view."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    STATUS_FLOW,
    apply_app_style,
    pipeline_singleton,
    status_label,
)
from smartapply.database import session_scope
from smartapply.database.models import Job
from smartapply.database.repository import list_jobs


st.set_page_config(page_title="Offres | SmartApply", page_icon="📋", layout="wide")
apply_app_style()

st.markdown(
    """
    <div class="sa-hero">
      <h2>Offres collectées</h2>
      <div class="sa-muted">Une table de travail pour retrouver une offre, comprendre son état et lancer une candidature ciblée si besoin.</div>
    </div>
    """,
    unsafe_allow_html=True,
)


def _matches_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if df.empty or not query.strip():
        return df
    needle = query.strip().lower()
    cols = ["title", "company", "location", "source", "contract", "status", "preview"]
    mask = pd.Series(False, index=df.index)
    for col in [c for c in cols if c in df]:
        mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(
            needle,
            regex=False,
        )
    return df[mask]


status_options = ["(tous)"] + [row["status"] for row in STATUS_FLOW]
col_search, col_status, col_source, col_limit = st.columns([1.6, 1, 0.85, 0.7])
with col_search:
    search = st.text_input(
        "Rechercher",
        placeholder="Entreprise, poste, ville, compétence...",
    )
with col_status:
    status_filter = st.selectbox(
        "Statut",
        options=status_options,
        format_func=lambda value: "Tous les statuts" if value == "(tous)" else status_label(value),
    )
with col_source:
    source_filter = st.selectbox(
        "Source",
        options=["(tous)", "serpapi", "francetravail", "manual"],
        format_func=lambda value: "Toutes" if value == "(tous)" else value,
    )
with col_limit:
    limit = st.number_input("Limite", min_value=10, max_value=500, value=150)

with session_scope() as s:
    jobs = list_jobs(
        s,
        status=None if status_filter == "(tous)" else status_filter,
        source=None if source_filter == "(tous)" else source_filter,
        limit=int(limit),
    )
    rows: list[dict[str, Any]] = []
    for job in jobs:
        desc = (job.cleaned_description or job.description or "").strip()
        rows.append(
            {
                "id": job.id,
                "score": (
                    round(job.score.final_score, 3)
                    if job.score and job.score.final_score is not None
                    else None
                ),
                "title": job.title,
                "company": job.company,
                "location": job.location or "",
                "source": job.source,
                "status": status_label(job.status),
                "status_code": job.status,
                "contract": job.contract_type or "",
                "preview": desc[:160] + ("..." if len(desc) > 160 else ""),
                "url": job.application_url or "",
            }
        )

df = pd.DataFrame(rows)
if df.empty:
    st.info("Aucune offre trouvée. Lance une recherche depuis le Workflow ou l'accueil.")
    st.stop()

df = _matches_search(df, search)
if df.empty:
    st.warning("Aucune offre ne correspond à cette recherche.")
    st.stop()

if "score" in df.columns:
    df = df.sort_values("score", ascending=False, na_position="last")

m1, m2, m3 = st.columns(3)
m1.metric("Offres affichées", len(df))
m2.metric("Avec score", int(df["score"].notna().sum()) if "score" in df else 0)
m3.metric("Sources", df["source"].nunique())

table_df = df.drop(columns=["status_code"]).reset_index(drop=True)
backing_df = df.reset_index(drop=True)
selection = st.dataframe(
    table_df,
    hide_index=True,
    width="stretch",
    height=430,
    on_select="rerun",
    selection_mode="single-row",
    key="offers_table",
    column_config={
        "url": st.column_config.LinkColumn("URL", width="small"),
        "score": st.column_config.NumberColumn("Score", format="%.3f", width="small"),
    },
)

st.divider()
st.markdown("### Inspection rapide")
st.caption("Sélectionne une ligne directement dans le tableau ci-dessus pour inspecter l'offre.")

selected_rows = list(selection.selection.rows) if selection and selection.selection else []
if selected_rows:
    selected_job_id = int(backing_df.iloc[selected_rows[0]]["id"])
    st.session_state["offers_selected_job_id"] = selected_job_id
else:
    previous_id = st.session_state.get("offers_selected_job_id")
    selected_job_id = (
        int(previous_id)
        if previous_id in set(backing_df["id"].astype(int).tolist())
        else None
    )

if selected_job_id is None:
    st.info("Aucune offre sélectionnée. Clique une ligne du tableau pour afficher son détail.")
    st.stop()

with session_scope() as s:
    job = s.get(Job, int(selected_job_id))
    if job is None:
        st.warning("Offre introuvable.")
        st.stop()
    detail = {
        "title": job.title,
        "company": job.company,
        "status": job.status,
        "location": job.location or "",
        "contract": job.contract_type or "",
        "remote": job.remote_policy or "",
        "source": job.source,
        "url": job.application_url or "",
        "score": job.score.final_score if job.score else None,
        "analysis": job.analysis,
        "description": job.cleaned_description or job.description or "",
    }

left, right = st.columns([1.35, 1])
with left:
    st.markdown(
        f"""
        <div class="sa-panel">
          <h3 style="margin:0;">{detail['title']}</h3>
          <div class="sa-muted">{detail['company']} · {detail['location'] or 'Lieu non indiqué'} · {detail['source']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if detail["url"]:
        st.link_button("Ouvrir l'offre", detail["url"])
    manual_contact = st.text_input(
        "Contact manuel",
        placeholder="recrutement@entreprise.com",
        help="Optionnel. Aucun contact n'est cherché automatiquement en mode manuel.",
        key=f"offer_manual_contact_{selected_job_id}",
    )
    if st.button("Générer une candidature pour cette offre", type="primary"):
        with st.spinner("Génération CV + lettre + email..."):
            try:
                report = pipeline_singleton().apply_to(
                    int(selected_job_id),
                    contact_email=manual_contact,
                )
                st.success(f"Candidature #{report.application_id} créée.")
                st.json(report.__dict__)
            except Exception as e:
                st.error(str(e))

with right:
    st.markdown("**État**")
    st.write(f"Statut : **{status_label(detail['status'])}**")
    if detail["score"] is not None:
        st.write(f"Score : **{detail['score']:.3f}**")
    st.write(f"Contrat : `{detail['contract'] or '—'}`")
    st.write(f"Remote : `{detail['remote'] or '—'}`")

if detail["analysis"]:
    analysis = detail["analysis"]
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**Analyse LLM**")
        st.write(f"Rôle : `{analysis.role_type or '—'}`")
        st.write(f"Domaine : `{analysis.domain or '—'}`")
        st.write(f"Seniorité : `{analysis.seniority or '—'}`")
    with a2:
        st.markdown("**Match / risques**")
        st.write("Match : " + (" · ".join((analysis.match_reasons or [])[:4]) or "—"))
        st.write("Risques : " + (" · ".join((analysis.risks or [])[:4]) or "—"))

with st.expander("Description complète", expanded=False):
    st.text_area(
        "Description",
        detail["description"] or "(description vide)",
        height=360,
        disabled=True,
        label_visibility="collapsed",
    )
