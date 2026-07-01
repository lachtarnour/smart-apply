"""CandiPilot production dashboard."""

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
from smartapply.database import session_scope
from smartapply.database.models import Application, Job, JobStatus
from smartapply.database.repository import list_pending_processing
from smartapply.jobsearch import next_action_for

st.set_page_config(
    page_title="CandiPilot",
    page_icon="CP",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_app_style()


READY_STATUSES = {
    JobStatus.EMAIL_GENERATED,
    JobStatus.DRAFT_CREATED,
    JobStatus.READY_FOR_FORM_SUBMISSION,
}


def _dashboard_snapshot() -> dict[str, Any]:
    with session_scope() as s:
        pending_jobs = list_pending_processing(s)
        apps = s.execute(select(Application)).scalars().all()
        latest_jobs = (
            s.execute(select(Job).order_by(Job.scraped_at.desc()).limit(5))
            .scalars()
            .all()
        )
        latest_apps = (
            s.execute(
                select(Application).order_by(Application.updated_at.desc()).limit(8)
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
        application_queue = [
            {
                "id": app.id,
                "entreprise": app.job.company if app.job else "",
                "poste": app.job.title if app.job else "",
                "statut": status_label(app.status),
                "prochaine action": next_action_for(
                    app.status,
                    app.updated_at,
                    has_contact=app.contact is not None,
                    has_gmail_draft=bool(app.gmail_draft_id),
                ),
            }
            for app in latest_apps
        ]

    needs_review = [
        app
        for app in apps
        if app.status in {JobStatus.CONTACT_MISSING, JobStatus.QUALITY_REJECTED}
        or (
            app.status in {JobStatus.EMAIL_GENERATED, JobStatus.DRAFT_CREATED}
            and not app.contact
        )
    ]
    return {
        "pending": len(pending_jobs),
        "applications": len(apps),
        "ready": sum(1 for app in apps if app.status in READY_STATUSES),
        "drafts": sum(1 for app in apps if app.gmail_draft_id),
        "needs_review": len(needs_review),
        "recent_jobs": recent_jobs,
        "application_queue": application_queue,
    }


def _recommended_action(
    status_counts: dict[str, int],
    snapshot: dict[str, Any],
) -> tuple[str, str, str, str]:
    if snapshot["pending"]:
        return (
            "Trier les offres",
            f"{snapshot['pending']} offre(s) attendent une décision avant scoring.",
            "pages/0_Workflow.py",
            ":material/account_tree:",
        )
    if status_counts.get(JobStatus.ANALYZED, 0):
        return (
            "Générer les dossiers",
            "Des offres analysées attendent CV, lettre, email et contact.",
            "pages/0_Workflow.py",
            ":material/auto_awesome:",
        )
    if snapshot["needs_review"]:
        return (
            "Corriger les dossiers",
            f"{snapshot['needs_review']} candidature(s) ont besoin d'un contact ou d'une revue.",
            "pages/2_Candidatures.py",
            ":material/rule:",
        )
    if snapshot["ready"]:
        return (
            "Finaliser les candidatures",
            f"{snapshot['ready']} dossier(s) sont prêts à relire ou déposer.",
            "pages/2_Candidatures.py",
            ":material/outgoing_mail:",
        )
    return (
        "Lancer une recherche",
        "Collecte quelques offres ciblées pour remplir la file de travail.",
        "pages/0_Workflow.py",
        ":material/search:",
    )


def _metric_card(label: str, value: int | str, note: str, tone: str) -> str:
    return f"""
      <div class="sa-custom-metric sa-tone-{escape(tone)}">
        <div class="sa-custom-metric-top">
          <div class="sa-custom-metric-label">{escape(label)}</div>
          <div class="sa-custom-metric-mark"></div>
        </div>
        <div class="sa-custom-metric-value">{escape(str(value))}</div>
        <div class="sa-custom-metric-note">{escape(note)}</div>
      </div>
    """


status_counts = jobs_per_status()
snapshot = _dashboard_snapshot()
next_title, next_caption, next_page, next_icon = _recommended_action(
    status_counts,
    snapshot,
)

st.markdown(
    f"""
    <div class="sa-home-layout">
      <div class="sa-home-hero">
        <div class="sa-home-eyebrow">Pilotage production</div>
        <div class="sa-home-title">Tableau de bord</div>
        <div class="sa-home-copy">
          Un espace de travail pour décider quoi traiter maintenant :
          collecte, génération, revue des contacts et finalisation.
        </div>
        <div class="sa-home-meta">
          <span>Revue manuelle</span>
          <span>Données locales</span>
          <span>Actions contrôlées</span>
        </div>
      </div>
      <div class="sa-home-panel">
        <div class="sa-home-panel-head">
          <div class="sa-focus-kicker">Action prioritaire</div>
          <div class="sa-home-panel-icon">1</div>
        </div>
        <div class="sa-home-next-title">{escape(next_title)}</div>
        <div class="sa-home-next-copy">{escape(next_caption)}</div>
        <div class="sa-home-panel-foot">Une seule prochaine décision mise en avant pour garder le flux simple.</div>
      </div>
    </div>
    <div class="sa-custom-metrics">
      {_metric_card("Offres", total_jobs(), "Total en base", "blue")}
      {_metric_card("A traiter", snapshot["pending"], "Avant scoring", "teal")}
      {_metric_card("A revoir", snapshot["needs_review"], "Contact ou qualité", "amber")}
      {_metric_card("Prêtes", snapshot["ready"], "Dépôt ou Gmail", "violet")}
    </div>
    """,
    unsafe_allow_html=True,
)

if st.button(
    next_title,
    icon=next_icon,
    type="primary",
    width="stretch",
    key="home_primary_action",
):
    st.switch_page(next_page)

secondary, tertiary = st.columns(2)
with secondary:
    if st.button(
        "Offre manuelle",
        icon=":material/edit_note:",
        width="stretch",
        key="home_manual_action",
    ):
        st.switch_page("pages/6_Candidature_manuelle.py")
with tertiary:
    if st.button(
        "Candidatures",
        icon=":material/outgoing_mail:",
        width="stretch",
        key="home_applications_action",
    ):
        st.switch_page("pages/2_Candidatures.py")

st.divider()

render_section_header(
    "File de travail",
    "Les dossiers récents avec leur prochaine action.",
)
if snapshot["application_queue"]:
    st.dataframe(
        pd.DataFrame(snapshot["application_queue"]),
        hide_index=True,
        width="stretch",
        height=300,
    )
else:
    st.info("Aucune candidature générée pour le moment.")

render_section_header(
    "Dernières offres",
    "Les dernières entrées collectées, pour vérifier la fraîcheur du vivier.",
)
if snapshot["recent_jobs"]:
    st.dataframe(
        pd.DataFrame(snapshot["recent_jobs"]),
        hide_index=True,
        width="stretch",
        height=300,
    )
else:
    st.info("Aucune offre collectée.")
