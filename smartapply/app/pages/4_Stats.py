"""Pipeline statistics — counts, costs, conversion rates."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy import select

from smartapply.app._helpers import (
    apply_app_style,
    cost_by_purpose,
    jobs_per_status,
    render_info_panel,
    render_page_header,
    render_status_funnel,
    total_cost_usd,
    total_jobs,
)
from smartapply.database import session_scope
from smartapply.database.models import JobStatus, LLMUsage

st.set_page_config(page_title="Stats | SmartApply", page_icon="📊", layout="wide")
apply_app_style()
render_page_header(
    "Statistiques du pipeline",
    "Comprendre le volume, la qualité du tri, les dossiers prêts et le coût des appels IA.",
    icon="📊",
    badges=[
        ("Santé pipeline", "blue"),
        ("Coûts IA audités", "neutral"),
        ("Historique disponible", "good"),
    ],
)

# ---- KPIs ----
status = jobs_per_status()
total_count = total_jobs()
denominator = total_count or 1
relevant_statuses = {
    JobStatus.SHORTLISTED,
    JobStatus.ANALYZED,
    JobStatus.CV_GENERATED,
    JobStatus.EMAIL_GENERATED,
    JobStatus.DRAFT_CREATED,
    JobStatus.READY_FOR_FORM_SUBMISSION,
    JobStatus.SENT,
    JobStatus.INTERVIEW,
}
ready_statuses = {
    JobStatus.EMAIL_GENERATED,
    JobStatus.DRAFT_CREATED,
    JobStatus.READY_FOR_FORM_SUBMISSION,
}
relevant_count = sum(status.get(value, 0) for value in relevant_statuses)
ready_count = sum(status.get(value, 0) for value in ready_statuses)
llm_cost = total_cost_usd()

st.markdown("### Santé du pipeline")
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total offres", total_count)
col2.metric("Taux pertinence", f"{relevant_count * 100 // denominator}%")
col3.metric("Candidatures prêtes", ready_count)
col4.metric("Coût IA", f"${llm_cost:.4f}")
col5.metric("Offres suivies", sum(status.values()))
render_info_panel(
    "Lecture rapide",
    "Le taux de pertinence compte les offres shortlistées, analysées ou transformées en dossier. Les coûts incluent les appels IA enregistrés en base.",
)

st.divider()

# ---- Funnel ----
render_status_funnel(status, title="Entonnoir logique du pipeline")

# ---- Cost breakdown ----
st.markdown("### Coût IA par usage")
costs = cost_by_purpose()
if costs:
    cost_df = pd.DataFrame(
        [{"usage": key, "cost_usd": float(value)} for key, value in costs.items()]
    ).sort_values("cost_usd", ascending=False)
    chart = (
        alt.Chart(cost_df)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color="#78A9FF")
        .encode(
            x=alt.X("usage:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-25)),
            y=alt.Y("cost_usd:Q", title="Coût USD"),
            tooltip=[
                alt.Tooltip("usage:N", title="Usage"),
                alt.Tooltip("cost_usd:Q", title="Coût USD", format="$.4f"),
            ],
        )
        .properties(height=260)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(chart, width="stretch", on_select="ignore")
else:
    st.info("Aucun appel IA enregistré pour le moment.")

# ---- Per-model usage ----
with session_scope() as s:
    rows = s.execute(select(LLMUsage)).scalars().all()
    usage_rows = [
        {
            "purpose": r.purpose,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "cost_usd": round(r.cost_usd, 4),
            "cached": r.cached,
            "created_at": r.created_at,
        }
        for r in rows
    ]

if usage_rows:
    df = pd.DataFrame(usage_rows).sort_values("created_at", ascending=False)
    display_df = df.rename(
        columns={
            "purpose": "usage",
            "prompt_tokens": "tokens_entree",
            "completion_tokens": "tokens_sortie",
            "cached": "cache",
            "created_at": "date",
        }
    )
    model_df = (
        df.groupby("model", as_index=False)["cost_usd"]
        .sum()
        .sort_values("cost_usd", ascending=False)
    )
    st.markdown("### Coût IA par modèle")
    mchart = (
        alt.Chart(model_df)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color="#A8A8A8")
        .encode(
            x=alt.X("model:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-20)),
            y=alt.Y("cost_usd:Q", title="Coût USD"),
            tooltip=[
                alt.Tooltip("model:N", title="Modèle"),
                alt.Tooltip("cost_usd:Q", title="Coût USD", format="$.4f"),
            ],
        )
        .properties(height=240)
        .configure_view(strokeWidth=0)
    )
    st.altair_chart(mchart, width="stretch", on_select="ignore")

    with st.expander("Historique détaillé des appels IA", expanded=False):
        st.dataframe(display_df, hide_index=True, width="stretch", height=380)
else:
    render_info_panel(
        "Aucun historique IA",
        "Les coûts et appels apparaîtront ici après les premières analyses ou générations.",
    )
