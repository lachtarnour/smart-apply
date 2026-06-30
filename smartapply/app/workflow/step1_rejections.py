"""Rejected-offer review helpers for workflow step 1."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app.workflow.step1_archive import _filter_override_ids
from smartapply.app.workflow.widgets import _filter_table, _sort_table
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus


def _reason_text(job: Job) -> str:
    reasons = []
    if job.score and job.score.components:
        reasons = job.score.components.get("reasons", []) or []
    return " · ".join(str(reason) for reason in reasons[:5]) or "Raison non renseignée"


def _rejection_reasons(job: Job) -> list[str]:
    if not job.score or not isinstance(job.score.components, dict):
        return []
    components = job.score.components
    raw = components.get("rejection_reasons") or []
    if not isinstance(raw, list):
        return []
    return [str(reason) for reason in raw if str(reason).strip()]


def _terminal_rejection_reason(job: Job) -> str:
    reasons = _rejection_reasons(job)
    if not reasons:
        return ""
    return reasons[-1]


def _clean_reason_value(value: str) -> str:
    return value.replace("_", " ").strip()


def _short_rejection_label(job: Job) -> str:
    """Human-readable rejection reason for compact dashboard tables."""
    if not job.score or not isinstance(job.score.components, dict):
        return "Raison non renseignée"
    components = job.score.components
    stage = str(components.get("rejection_stage") or "")
    reason = _terminal_rejection_reason(job)

    if stage == "deduplication":
        duplicate_ref = next(
            (
                item.split(":", 1)[1].strip()
                for item in _rejection_reasons(job)
                if item.startswith("duplicate_reference:")
            ),
            "",
        )
        return f"Doublon: {duplicate_ref[:80]}" if duplicate_ref else "Doublon"

    label_map = {
        "missing_role_relevance": "Pas de signal Data/ML cible",
        "seniority_or_leadership_in_description": "Seniorité/leadership en description",
        "reporting_bi_without_analytical_ownership": "Reporting/BI sans ownership analytique",
        "finance_reporting_bi_without_core_data_tech": "BI finance sans data tech",
        "reporting_without_core_data_tech": "Reporting sans data tech",
        "web_analytics_tracking_focus": "Tracking web analytics",
        "pure_data_engineering_role": "Data engineering trop plateforme",
        "mep_data_center_focus": "MEP/Data center hors cible",
    }
    if reason in label_map:
        return label_map[reason]

    prefix_labels = {
        "description_hard_reject:": "Techno bloquée",
        "experience_required_too_high:": "Expérience trop élevée",
        "title_hard_reject:": "Titre hors cible",
        "seniority_in_title:": "Seniorité dans le titre",
        "seniority_blocked:": "Seniorité bloquée",
        "blocked_contract_visible_text:": "Contrat bloqué",
        "blocked_contract_type:": "Contrat bloqué",
        "blocked_contract_structured:": "Contrat bloqué",
        "blocked_work_time_structured:": "Temps de travail bloqué",
        "deal_breaker_in_title:": "Deal-breaker dans le titre",
        "deal_breaker_in_description:": "Deal-breaker en description",
        "location_rejected_foreign:": "Localisation hors France",
        "location_rejected_foreign_text:": "Localisation étrangère détectée",
        "below_min_score:": "Score local trop bas",
        "negative_desc_token:": "Signal négatif en description",
    }
    for prefix, label in prefix_labels.items():
        if reason.startswith(prefix):
            return f"{label}: {_clean_reason_value(reason.removeprefix(prefix))}"
    return _clean_reason_value(reason) if reason else "Raison non renseignée"


def _rejection_signal(job: Job) -> str:
    reason = _terminal_rejection_reason(job)
    if not reason:
        return ""
    if reason.startswith("description_hard_reject:"):
        return reason.removeprefix("description_hard_reject:").replace("_", " ")
    if ":" in reason:
        return reason.split(":", 1)[1].replace("_", " ")[:80]
    return reason.replace("_", " ")[:80]


def _rejected_jobs_df(job_ids: list[int]) -> pd.DataFrame:
    if not job_ids:
        return pd.DataFrame()
    rows: list[dict[str, Any]] = []
    with session_scope() as s:
        for job in s.query(Job).filter(Job.id.in_(job_ids)).all():
            rows.append(
                {
                    "restore": False,
                    "id": int(job.id),
                    "title": job.title,
                    "company": job.company,
                    "motif": _short_rejection_label(job),
                    "signal": _rejection_signal(job),
                    "reason": _reason_text(job),
                    "url": job.application_url or "",
                }
            )
    return pd.DataFrame(rows).sort_values(["company", "title"]) if rows else pd.DataFrame()


def _filter_rejected_jobs_df(
    selection_map: dict[int, bool],
    *,
    selection_col: str = "include",
    limit: int = 300,
) -> pd.DataFrame:
    """Filter/dedup archived jobs that can be manually brought back."""
    rows: list[dict[str, Any]] = []
    with session_scope() as s:
        jobs = (
            s.query(Job)
            .filter(Job.archived_at.is_not(None))
            .order_by(Job.scraped_at.desc())
            .limit(limit)
            .all()
        )
        for job in jobs:
            components = job.score.components if job.score and job.score.components else {}
            stage = str(components.get("rejection_stage") or "")
            if stage not in {"local_filter", "deduplication"}:
                continue
            desc = (job.cleaned_description or job.description or "").strip()
            rows.append(
                {
                    selection_col: bool(selection_map.get(int(job.id), False)),
                    "id": int(job.id),
                    "title": job.title,
                    "company": job.company,
                    "location": job.location or "",
                    "source": job.source,
                    "phase": "Filtre local" if stage == "local_filter" else "Doublon",
                    "motif": _short_rejection_label(job),
                    "signal": _rejection_signal(job),
                    "reason": _reason_text(job),
                    "preview": desc[:180] + ("..." if len(desc) > 180 else ""),
                    "url": job.application_url or "",
                }
            )
    return pd.DataFrame(rows).sort_values(["company", "title"]) if rows else pd.DataFrame()


def _render_filter_rejected_picker(
    *,
    state_key: str,
    editor_key: str,
    title: str,
    checkbox_label: str,
    caption: str,
) -> list[int]:
    selection_map = {
        int(k): bool(v)
        for k, v in st.session_state.get(state_key, {}).items()
    }
    df = _filter_rejected_jobs_df(selection_map, selection_col="include")
    if df.empty:
        return []

    with st.expander(f"{title} ({len(df)})", expanded=False):
        st.caption(caption)
        rejected_search = st.text_input(
            "Rechercher dans les offres rejetées",
            placeholder="Entreprise, poste, raison, source...",
            key=f"{editor_key}_search",
        )
        visible_df = _filter_table(df, rejected_search)
        visible_df = _sort_table(
            visible_df,
            state_prefix=editor_key,
            default_sort="company",
            default_desc=False,
        )
        with st.form(f"{editor_key}_form"):
            edited = st.data_editor(
                visible_df,
                column_config={
                    "include": st.column_config.CheckboxColumn(checkbox_label, default=False),
                    "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                    "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
                    "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
                    "location": st.column_config.TextColumn("Lieu", disabled=True, width="small"),
                    "source": st.column_config.TextColumn("Source", disabled=True, width="small"),
                    "phase": st.column_config.TextColumn("Origine", disabled=True, width="small"),
                    "motif": st.column_config.TextColumn("Motif", disabled=True, width="medium"),
                    "signal": st.column_config.TextColumn("Signal", disabled=True, width="small"),
                    "reason": st.column_config.TextColumn("Détail brut", disabled=True, width="large"),
                    "preview": st.column_config.TextColumn("Aperçu", disabled=True, width="large"),
                    "url": st.column_config.LinkColumn("URL", disabled=True, width="small"),
                },
                column_order=[
                    "include",
                    "id",
                    "phase",
                    "company",
                    "title",
                    "motif",
                    "signal",
                    "source",
                    "location",
                    "url",
                ],
                hide_index=True,
                width="stretch",
                key=editor_key,
            )
            apply_selection = st.form_submit_button(
                "Appliquer la sélection",
                type="primary",
                width="stretch",
            )
        if apply_selection and not edited.empty and {"id", "include"}.issubset(edited.columns):
            for _, row in edited[["id", "include"]].iterrows():
                selection_map[int(row["id"])] = bool(row["include"])
            st.session_state[state_key] = selection_map
            st.success("Sélection mise à jour.")
        if not visible_df.empty:
            detail_id = st.selectbox(
                "Checker une offre rejetée",
                options=visible_df["id"].astype(int).tolist(),
                format_func=lambda jid: (
                    f"[{jid}] "
                    f"{visible_df.loc[visible_df['id'] == jid, 'company'].iloc[0]} — "
                    f"{visible_df.loc[visible_df['id'] == jid, 'title'].iloc[0]}"
                ),
                key=f"{editor_key}_detail_select",
            )
            _render_job_detail(int(detail_id))
        selected_ids = [
            int(row["id"])
            for _, row in df.iterrows()
            if bool(selection_map.get(int(row["id"]), bool(row.get("include", False))))
        ]
        st.caption(f"{len(selected_ids)} offre(s) ajoutée(s) par sélection manuelle.")
        return selected_ids


def _render_rejected_offer_controls() -> None:
    report = st.session_state.get("wf_auto_filter_report") or {}
    rejected_ids = [int(jid) for jid in report.get("rejected_ids", [])]
    df = _rejected_jobs_df(rejected_ids)
    if df.empty:
        return

    with st.expander(f"Offres retirées par le filtre local ({len(df)})"):
        st.caption(
            "Ces offres ont été retirées automatiquement avant l'analyse IA. "
            "Si le filtre est trop strict pour une offre précise, réactive-la ici."
        )
        sorted_df = _sort_table(
            df,
            state_prefix="wf_rejected_editor",
            default_sort="company",
            default_desc=False,
        )
        with st.form("wf_rejected_editor_form"):
            edited = st.data_editor(
                sorted_df,
                column_config={
                    "restore": st.column_config.CheckboxColumn("Réactiver", default=False),
                    "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                    "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
                    "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
                    "motif": st.column_config.TextColumn("Motif", disabled=True, width="medium"),
                    "signal": st.column_config.TextColumn("Signal", disabled=True, width="small"),
                    "reason": st.column_config.TextColumn("Détail brut", disabled=True, width="large"),
                    "url": st.column_config.LinkColumn("URL", disabled=True, width="small"),
                },
                column_order=["restore", "id", "company", "title", "motif", "signal", "url"],
                hide_index=True,
                width="stretch",
                key="wf_rejected_editor",
            )
            restore_selected = st.form_submit_button(
                "Réactiver les offres sélectionnées",
                type="primary",
                width="stretch",
            )
        if restore_selected:
            restore_ids = edited.loc[edited["restore"], "id"].astype(int).tolist()
            if not restore_ids:
                st.warning("Coche au moins une offre à réactiver.")
            else:
                overrides = _filter_override_ids()
                overrides.update(restore_ids)
                with session_scope() as s:
                    for job_id in restore_ids:
                        job = s.get(Job, int(job_id))
                        if job is not None:
                            job.archived_at = None
                            job.analyzed_at = None
                            job.status = JobStatus.SCRAPED
                keep_map = st.session_state.get("wf_keep_map", {})
                for job_id in restore_ids:
                    keep_map[int(job_id)] = True
                st.session_state["wf_keep_map"] = keep_map
                st.session_state["wf_filter_override_ids"] = sorted(overrides)
                st.success(f"{len(restore_ids)} offre(s) réactivée(s).")
                st.rerun()
        if st.button(
            "Réinitialiser les réactivations",
            disabled=not st.session_state.get("wf_filter_override_ids"),
            key="wf_clear_overrides",
        ):
            st.session_state["wf_filter_override_ids"] = []
            st.rerun()



def _render_job_detail(job_id: int) -> None:
    """Show the full description and key fields for a single job."""
    with session_scope() as s:
        job = s.get(Job, job_id)
        if job is None:
            st.warning("Offre introuvable.")
            return
        desc = job.cleaned_description or job.description or ""
        data = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "contract": job.contract_type,
            "remote": job.remote_policy,
            "source": job.source,
            "url": job.application_url,
            "desc": desc,
            "status": job.status,
            "rejection_stage": (
                str(job.score.components.get("rejection_stage") or "")
                if job.score is not None and isinstance(job.score.components, dict)
                else ""
            ),
            "rejection_reasons": _rejection_reasons(job),
            "rejection_label": _short_rejection_label(job),
        }

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(f"### {data['title']}")
        st.markdown(f"**{data['company']}** · {data['location'] or '—'}")
    with col2:
        if data["url"]:
            st.markdown(f"🔗 [Voir l'offre]({data['url']})")
        st.caption(f"Source : `{data['source']}`")

    bits = []
    if data["contract"]:
        bits.append(f"Contrat : **{data['contract']}**")
    if data["remote"]:
        bits.append(f"Remote : **{data['remote']}**")
    if bits:
        st.markdown(" · ".join(bits))

    if data["rejection_reasons"] and data["rejection_stage"] in {
        "local_filter",
        "deduplication",
    }:
        st.markdown("**Décision filtre**")
        stage_label = (
            "Filtre local"
            if data["rejection_stage"] == "local_filter"
            else "Dédoublonnage"
        )
        st.caption(f"{stage_label} · {data['rejection_label']}")
        with st.expander("Voir toutes les raisons techniques", expanded=False):
            for reason in data["rejection_reasons"]:
                st.markdown(f"- `{reason}`")

    st.markdown("**Description**")
    st.text_area(
        "Description (lecture seule)",
        data["desc"] or "(description vide)",
        height=300,
        disabled=True,
        label_visibility="collapsed",
        key=f"wf_step1_detail_{job_id}",
    )
