"""Job archive and restore helpers shared by workflow steps."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import pipeline_singleton
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import list_pending_processing, mark_archived


def _remove_ids_from_session_list(key: str, job_ids: set[int]) -> None:
    values = st.session_state.get(key, [])
    st.session_state[key] = [
        int(value)
        for value in values
        if int(value) not in job_ids
    ]


def _remove_ids_from_session_map(key: str, job_ids: set[int]) -> None:
    values = dict(st.session_state.get(key, {}))
    for job_id in job_ids:
        values.pop(job_id, None)
        values.pop(str(job_id), None)
    st.session_state[key] = values


def _forget_archived_jobs_in_workflow(job_ids: set[int], app_ids: set[int]) -> None:
    for key in (
        "wf_fetched_ids",
        "wf_filter_override_ids",
        "wf_selected_for_scoring",
        "wf_ranked_ids",
        "wf_selected_for_analysis",
        "wf_selected_for_apply",
    ):
        _remove_ids_from_session_list(key, job_ids)
    for key in (
        "wf_keep_map",
        "wf_analysis_keep_map",
        "wf_apply_keep_map",
        "wf_generate_keep_map",
        "wf_manual_contacts",
        "wf_contact_lookup_map",
    ):
        _remove_ids_from_session_map(key, job_ids)
    if app_ids:
        values = st.session_state.get("wf_generated_app_ids", [])
        st.session_state["wf_generated_app_ids"] = [
            int(value)
            for value in values
            if int(value) not in app_ids
        ]


def _archive_jobs_for_workflow(job_ids: list[int]) -> int:
    unique_ids = {int(job_id) for job_id in job_ids}
    if not unique_ids:
        return 0
    archived_ids: set[int] = set()
    app_ids: set[int] = set()
    with session_scope() as s:
        for job_id in sorted(unique_ids):
            job = s.get(Job, job_id)
            if job is None:
                continue
            if job.application is not None:
                app_ids.add(int(job.application.id))
                if job.application.status != JobStatus.SENT:
                    job.application.status = JobStatus.ARCHIVED
            mark_archived(s, job_id)
            archived_ids.add(job_id)
    if archived_ids:
        _forget_archived_jobs_in_workflow(archived_ids, app_ids)
    return len(archived_ids)


def _archive_ids_from_df(df: pd.DataFrame) -> list[int]:
    if df.empty or not {"id", "archive"}.issubset(df.columns):
        return []
    return df.loc[df["archive"], "id"].astype(int).tolist()


def _filter_override_ids() -> set[int]:
    return {int(jid) for jid in st.session_state.get("wf_filter_override_ids", [])}


def _scraped_job_ids_excluding(overrides: set[int]) -> list[int]:
    with session_scope() as s:
        return [
            int(job.id)
            for job in list_pending_processing(s)
            if job.filtered_at is None and job.id not in overrides
        ]


def _filter_pending_for_step1() -> Any | None:
    """Run the automatic local filter while respecting manual restorations."""
    filter_ids = _scraped_job_ids_excluding(_filter_override_ids())
    if not filter_ids:
        return None
    return pipeline_singleton().filter_pending(job_ids=filter_ids)


def _restore_archived_jobs_for_manual_flow(job_ids: list[int]) -> list[int]:
    """Make manually selected archived jobs available again without max-score rescue."""
    unique_ids = list(dict.fromkeys(int(job_id) for job_id in job_ids))
    if not unique_ids:
        return []
    now = datetime.now(timezone.utc)
    restored: list[int] = []
    with session_scope() as s:
        for job_id in unique_ids:
            job = s.get(Job, int(job_id))
            if job is None:
                continue
            job.archived_at = None
            job.analyzed_at = None
            if job.filtered_at is None:
                job.filtered_at = now
            job.status = JobStatus.FILTERED
            restored.append(int(job_id))

    if restored:
        overrides = _filter_override_ids()
        overrides.update(restored)
        st.session_state["wf_filter_override_ids"] = sorted(overrides)
        keep_map = st.session_state.get("wf_keep_map", {})
        for job_id in restored:
            keep_map[int(job_id)] = True
        st.session_state["wf_keep_map"] = keep_map
    return restored
