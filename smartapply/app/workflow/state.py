"""Workflow session state and run helpers."""

from __future__ import annotations

import streamlit as st

from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.models import Application, Job, JobStatus
from smartapply.database.repository import list_pending_processing
from smartapply.scrapers import SERPAPI_DATE_POSTED_LABELS

settings = get_settings()

# ============================================================
# Session state
# ============================================================

DEFAULTS = {
    "wf_step": 1,
    "wf_fetched_ids": [],      # IDs from the last fetch
    "wf_keep_map": {},         # Manual keep/deselect state in step 1
    "wf_analysis_keep_map": {},  # Manual keep/deselect state after ranking
    "wf_auto_filter_report": None,
    "wf_filter_override_ids": [],  # Jobs manually restored after local rejection
    "wf_selected_for_scoring": [],
    "wf_ranked_ids": [],
    "wf_selected_for_analysis": [],
    "wf_selected_for_apply": [],
    "wf_manual_contacts": {},
    "wf_rejected_score_map": {},
    "wf_rejected_analysis_map": {},
    "wf_step1_editor_sort_by": "score",
    "wf_step1_editor_sort_desc": True,
    "wf_rejected_editor_sort_by": "company",
    "wf_rejected_editor_sort_desc": False,
    "wf_step2_rejected_score_editor_sort_by": "company",
    "wf_step2_rejected_score_editor_sort_desc": False,
    "wf_step2_score_pending_editor_sort_by": "score",
    "wf_step2_score_pending_editor_sort_desc": True,
    "wf_step2_ranked_editor_sort_by": "score",
    "wf_step2_ranked_editor_sort_desc": True,
    "wf_step3_rejected_analysis_editor_sort_by": "company",
    "wf_step3_rejected_analysis_editor_sort_desc": False,
    "wf_step3_candidate_editor_sort_by": "score",
    "wf_step3_candidate_editor_sort_desc": True,
    "wf_step3_analyzed_editor_sort_by": "score",
    "wf_step3_analyzed_editor_sort_desc": True,
    "wf_apply_keep_map": {},
    "wf_generate_keep_map": {},
    "wf_generate_seed_ids": [],
    "wf_step4_sort_by": "score",
    "wf_step4_sort_desc": True,
    "wf_step4_apps_sort_by": "id",
    "wf_step4_apps_sort_desc": False,
    "wf_step5_summary_sort_by": "id",
    "wf_step5_summary_sort_desc": False,
    "wf_contact_lookup_map": {},
    "wf_contact_lookup_bulk_value": False,
    "wf_generated_app_ids": [],
    "wf_step5_has_loaded_app_ids": False,
    "wf_use_contact_lookup": False,
    "wf_running": None,
    "wf_stop_requested": False,
    "wf_last_run_summary": None,
    "wf_search_text": "",
    "wf_hide_low_signal": True,
    "wf_autopilot_report": None,
}
def _serpapi_effective_config(
    *,
    max_results: int,
    date_posted: str,
    location: str | None,
) -> str:
    fallback_target = settings.serpapi_low_result_fallback_target
    effective_fallback = min(max_results, fallback_target) if fallback_target > 0 else 0
    freshness = SERPAPI_DATE_POSTED_LABELS.get(date_posted, date_posted)
    return (
        "SerpApi config effective : "
        f"lieu {location or settings.serpapi_default_location} · "
        f"fraîcheur {freshness} · "
        f"résultats/source {max_results} · "
        f"fallback {effective_fallback} · "
        f"pages max {settings.serpapi_max_pages}"
    )


def reset_workflow() -> None:
    for key, default in DEFAULTS.items():
        st.session_state[key] = default


def _begin_run(name: str) -> None:
    st.session_state["wf_running"] = name
    st.session_state["wf_stop_requested"] = False


def _end_run(summary: str | None = None) -> None:
    st.session_state["wf_running"] = None
    st.session_state["wf_stop_requested"] = False
    if summary:
        st.session_state["wf_last_run_summary"] = summary


def _stop_requested() -> bool:
    return bool(st.session_state.get("wf_stop_requested"))


def _request_stop_button(key: str) -> None:
    running = st.session_state.get("wf_running")
    if not running:
        return
    st.markdown(
        f"<div class='sa-runbar'><strong>Processus en cours</strong> : {running}. "
        "L'arrêt est coopératif : il coupe proprement entre deux offres/sources.</div>",
        unsafe_allow_html=True,
    )
    if st.button("Arrêter au prochain point sûr", key=key, type="secondary"):
        st.session_state["wf_stop_requested"] = True
        st.warning("Arrêt demandé. Le traitement s'arrêtera entre deux éléments.")


def _workflow_counts() -> dict[str, int]:
    with session_scope() as s:
        pending_jobs = list_pending_processing(s)
        jobs = s.query(Job).all()
        apps = s.query(Application).all()
        archived_filter_or_duplicate = 0
        for job in jobs:
            components = (
                job.score.components
                if job.score is not None and isinstance(job.score.components, dict)
                else {}
            )
            if (
                job.archived_at is not None
                and components.get("rejection_stage") in {"local_filter", "deduplication"}
            ):
                archived_filter_or_duplicate += 1
    return {
        "pending": len(pending_jobs),
        "analyzed": sum(1 for j in jobs if j.status == JobStatus.ANALYZED),
        "archived": sum(1 for j in jobs if j.status == JobStatus.ARCHIVED),
        "filter_rejected": archived_filter_or_duplicate,
        "ready": sum(
            1
            for a in apps
            if a.status
            in {
                JobStatus.EMAIL_GENERATED,
                JobStatus.READY_FOR_FORM_SUBMISSION,
                JobStatus.DRAFT_CREATED,
            }
        ),
        "drafts": sum(1 for a in apps if a.gmail_draft_id),
    }




def init_workflow_state() -> None:
    for key, default in DEFAULTS.items():
        st.session_state.setdefault(key, default)
