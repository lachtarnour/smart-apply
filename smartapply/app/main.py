"""SmartApply AI — compact Streamlit home."""

from __future__ import annotations

from html import escape
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import select

from smartapply.app._helpers import (
    apply_app_style,
    jobs_per_status,
    render_section_header,
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

total_job_count = total_jobs()
st.markdown(
    f"""
    <div class="sa-home-layout">
      <div class="sa-home-hero">
        <div class="sa-home-eyebrow">Mode manuel contrôlé</div>
        <div class="sa-home-title">SmartApply</div>
        <div class="sa-home-copy">
          Un cockpit sobre pour collecter les offres, choisir les bons lots,
          générer des dossiers propres et garder le contrôle sur chaque envoi.
        </div>
        <div class="sa-pill-row">
          <span class="sa-pill sa-pill-good">Aucun envoi automatique</span>
          <span class="sa-pill sa-pill-blue">Analyse IA {escape(settings.openai_model_cheap)}</span>
          <span class="sa-pill sa-pill-neutral">Contacts contrôlés</span>
        </div>
      </div>
      <div class="sa-home-panel">
        <div class="sa-focus-kicker">Prochaine action</div>
        <div class="sa-home-next-title">{escape(next_title)}</div>
        <div class="sa-home-next-copy">{escape(next_caption)}</div>
      </div>
    </div>
    <div class="sa-custom-metrics">
      <div class="sa-custom-metric" style="--metric-accent:#78A9FF;">
        <div class="sa-custom-metric-label">Offres</div>
        <div class="sa-custom-metric-value">{total_job_count}</div>
        <div class="sa-custom-metric-note">Total collecté</div>
      </div>
      <div class="sa-custom-metric" style="--metric-accent:#A8A8A8;">
        <div class="sa-custom-metric-label">A traiter</div>
        <div class="sa-custom-metric-value">{snapshot["pending"]}</div>
        <div class="sa-custom-metric-note">Dans le vivier actif</div>
      </div>
      <div class="sa-custom-metric" style="--metric-accent:#D0E2FF;">
        <div class="sa-custom-metric-label">Dossiers prêts</div>
        <div class="sa-custom-metric-value">{snapshot["ready"]}</div>
        <div class="sa-custom-metric-note">A relire ou finaliser</div>
      </div>
      <div class="sa-custom-metric" style="--metric-accent:#FFB3B8;">
        <div class="sa-custom-metric-label">Brouillons Gmail</div>
        <div class="sa-custom-metric-value">{snapshot["drafts"]}</div>
        <div class="sa-custom-metric-note">Créés, jamais envoyés</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

_, continue_col = st.columns([3.2, 1])
with continue_col:
    if st.button(
        "Continuer",
        icon=":material/arrow_forward:",
        type="primary",
        use_container_width=True,
        key="home_continue",
    ):
        st.switch_page(next_page)

render_section_header(
    "Accès rapide",
    "Les six vues utiles pour piloter sans chercher dans les menus.",
)

quick_actions = [
    (
        "Workflow",
        "Collecter, scorer, analyser et générer depuis un flux guidé.",
        "pages/0_Workflow.py",
        ":material/account_tree:",
    ),
    (
        "Offres",
        "Inspecter les offres, scores, filtres et rejets.",
        "pages/1_Offres.py",
        ":material/view_list:",
    ),
    (
        "Candidatures",
        "Relire les emails, brouillons et dossiers prêts.",
        "pages/2_Candidatures.py",
        ":material/outgoing_mail:",
    ),
    (
        "Autopilot",
        "Lancer un run haut volume avec garde-fous.",
        "pages/5_Autopilot.py",
        ":material/rocket_launch:",
    ),
    (
        "Stats",
        "Suivre volume, pipeline, statuts et coûts.",
        "pages/4_Stats.py",
        ":material/monitoring:",
    ),
    (
        "Profil",
        "Vérifier les paramètres utilisés pour générer les dossiers.",
        "pages/3_Profil.py",
        ":material/manage_accounts:",
    ),
]
quick_cols = st.columns(3)
nav_accents = [
    ("01", "#78A9FF", "#28384E"),
    ("02", "#C6C6C6", "#393939"),
    ("03", "#D2B36A", "#3A321F"),
    ("04", "#82CFFF", "#253946"),
    ("05", "#A8A8A8", "#393939"),
    ("06", "#FFB3B8", "#3A2425"),
]
for idx, (label, copy, page, icon) in enumerate(quick_actions):
    number, accent, soft = nav_accents[idx]
    with quick_cols[idx % 3]:
        st.markdown(
            f"""
            <div class="sa-nav-card" style="--nav-accent:{accent};--nav-soft:{soft};">
              <div class="sa-nav-top">
                <div>
                  <h4>{escape(label)}</h4>
                </div>
                <div class="sa-nav-icon">{number}</div>
              </div>
              <p>{escape(copy)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button(
            f"Ouvrir {label}",
            icon=icon,
            use_container_width=True,
            key=f"home_open_{label.lower()}",
        ):
            st.switch_page(page)

st.divider()

col_jobs, col_apps = st.columns(2)
with col_jobs:
    render_section_header("Offres récentes", "Dernières entrées collectées.")
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
    render_section_header("Candidatures à suivre", "Dossiers récents et prochaine action.")
    if snapshot["recent_apps"]:
        st.dataframe(
            pd.DataFrame(snapshot["recent_apps"]),
            hide_index=True,
            width="stretch",
            height=260,
        )
    else:
        st.info("Aucune candidature générée.")
