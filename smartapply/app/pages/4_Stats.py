"""Pipeline statistics — counts, costs, conversion rates."""

from __future__ import annotations

import pandas as pd
import streamlit as st
import altair as alt
from sqlalchemy import select

from smartapply.app._helpers import (
    apply_app_style,
    cost_by_purpose,
    jobs_per_status,
    render_status_funnel,
    total_cost_usd,
    total_jobs,
)
from smartapply.database import session_scope
from smartapply.database.models import JobStatus, LLMUsage


st.set_page_config(page_title="Stats | SmartApply", page_icon="📊", layout="wide")
apply_app_style()
st.title("📊 Statistiques du pipeline")

# ---- KPIs ----
status = jobs_per_status()
total_count = total_jobs()
denominator = total_count or 1
col1, col2, col3, col4 = st.columns(4)
col1.metric("Offres", total_count)
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
col2.metric("Taux pertinence", f"{relevant_count * 100 // denominator}%")
ready_count = sum(status.get(value, 0) for value in ready_statuses)
col3.metric("Candidatures prêtes", ready_count)
col4.metric("Coût LLM", f"${total_cost_usd():.4f}")

st.divider()

# ---- Funnel ----
render_status_funnel(status, title="Entonnoir logique du pipeline")

# ---- Cost breakdown ----
st.subheader("Coût LLM par usage")
costs = cost_by_purpose()
if costs:
    cost_df = pd.DataFrame(
        [{"usage": key, "cost_usd": float(value)} for key, value in costs.items()]
    ).sort_values("cost_usd", ascending=False)
    chart = (
        alt.Chart(cost_df)
        .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5, color="#2563EB")
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
    st.info("Aucun appel LLM enregistré pour le moment.")

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
    st.subheader("Historique des appels LLM")
    df = pd.DataFrame(usage_rows).sort_values("created_at", ascending=False)
    st.dataframe(df, hide_index=True, width="stretch", height=380)
else:
    st.caption("L'historique apparaîtra ici dès le premier appel LLM réel.")
