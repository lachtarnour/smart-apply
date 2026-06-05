"""SmartApply AI — compact Streamlit home."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import select

from smartapply.app._helpers import (
    apply_app_style,
    jobs_per_status,
    status_label,
    total_jobs,
)
from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.models import Application, Job, JobStatus
from smartapply.database.repository import list_pending_processing
from smartapply.jobsearch import next_action_for

st.set_page_config(
    page_title="SmartApply AI",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_app_style()


def _dashboard_snapshot() -> dict[str, Any]:
    with session_scope() as s:
        pending_jobs = list_pending_processing(s)
        apps = s.execute(select(Application)).scalars().all()
        latest_jobs = (
            s.execute(select(Job).order_by(Job.scraped_at.desc()).limit(6))
            .scalars()
            .all()
        )
        latest_apps = (
            s.execute(
                select(Application).order_by(Application.updated_at.desc()).limit(6)
            )
            .scalars()
            .all()
        )
        recent_jobs = [
            {
                "id": job.id,
                "entreprise": job.company,
                "poste": job.title,
                "statut": status_label(job.status),
                "source": job.source,
            }
            for job in latest_jobs
        ]
        recent_apps = [
            {
                "id": app.id,
                "entreprise": app.job.company if app.job else "",
                "poste": app.job.title if app.job else "",
                "statut": status_label(app.status),
                "action": next_action_for(
                    app.status,
                    app.updated_at,
                    has_contact=app.contact is not None,
                    has_gmail_draft=bool(app.gmail_draft_id),
                ),
            }
            for app in latest_apps
        ]

    ready_statuses = {
        JobStatus.EMAIL_GENERATED,
        JobStatus.DRAFT_CREATED,
        JobStatus.READY_FOR_FORM_SUBMISSION,
    }
    return {
        "pending": len(pending_jobs),
        "applications": len(apps),
        "ready": sum(1 for app in apps if app.status in ready_statuses),
        "drafts": sum(1 for app in apps if app.gmail_draft_id),
        "recent_jobs": recent_jobs,
        "recent_apps": recent_apps,
    }


def _recommended_action(status_counts: dict[str, int], snapshot: dict[str, Any]) -> tuple[str, str, str]:
    if snapshot["pending"]:
        return (
            "Trier les offres en attente",
            "Ouvre le workflow pour sélectionner, scorer, shortlister puis lancer l'analyse IA.",
            "pages/0_Workflow.py",
        )
    if status_counts.get(JobStatus.ANALYZED, 0):
        return (
            "Générer les candidatures",
            "Des offres analysées attendent un CV, une lettre, un email et un contact.",
            "pages/0_Workflow.py",
        )
    if snapshot["ready"]:
        return (
            "Finaliser les dossiers prêts",
            "Relis les emails, crée les brouillons Gmail ou soumets les formulaires.",
            "pages/2_Candidatures.py",
        )
    return (
        "Lancer une recherche",
        "Commence par le workflow pour collecter des offres fraîches et garder le contrôle.",
        "pages/0_Workflow.py",
    )


status_counts = jobs_per_status()
snapshot = _dashboard_snapshot()
next_title, next_caption, next_page = _recommended_action(status_counts, snapshot)
settings = get_settings()

st.title("SmartApply")
st.caption("Cockpit minimal pour savoir quoi faire maintenant et accéder vite aux bons outils.")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Offres", total_jobs())
m2.metric("À traiter", snapshot["pending"])
m3.metric("Dossiers prêts", snapshot["ready"])
m4.metric("Brouillons Gmail", snapshot["drafts"])
st.caption(
    f"Analyse IA : `{settings.openai_model_cheap}`"
)

st.divider()

left, right = st.columns([1.25, 1])
with left, st.container(border=True):
    st.caption("Prochaine action")
    st.subheader(next_title)
    st.write(next_caption)
    st.page_link(next_page, label="Continuer", icon="➡️")

with right, st.container(border=True):
    st.caption("Raccourcis")
    c1, c2 = st.columns(2)
    with c1:
        st.page_link("pages/0_Workflow.py", label="Workflow", icon="🧭")
        st.page_link("pages/1_Offres.py", label="Offres", icon="📋")
        st.page_link("pages/2_Candidatures.py", label="Candidatures", icon="📝")
    with c2:
        st.page_link("pages/5_Autopilot.py", label="Autopilot", icon="🚀")
        st.page_link("pages/4_Stats.py", label="Stats", icon="📊")
        st.page_link("pages/3_Profil.py", label="Profil", icon="👤")

st.divider()

col_jobs, col_apps = st.columns(2)
with col_jobs:
    st.subheader("Offres récentes")
    if snapshot["recent_jobs"]:
        st.dataframe(
            pd.DataFrame(snapshot["recent_jobs"]),
            hide_index=True,
            width="stretch",
            height=260,
        )
    else:
        st.info("Aucune offre collectée.")

with col_apps:
    st.subheader("Candidatures à suivre")
    if snapshot["recent_apps"]:
        st.dataframe(
            pd.DataFrame(snapshot["recent_apps"]),
            hide_index=True,
            width="stretch",
            height=260,
        )
    else:
        st.info("Aucune candidature générée.")
