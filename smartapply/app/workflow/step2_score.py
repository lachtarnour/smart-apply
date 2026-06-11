"""Workflow step 2: local scoring and shortlist."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import pipeline_singleton, render_section_header, status_label
from smartapply.app.workflow.state import _begin_run, _end_run, settings
from smartapply.app.workflow.step1_fetch import (
    _archive_jobs_for_workflow,
    _filter_override_ids,
    _job_editor,
    _pending_jobs_df,
    _render_filter_rejected_picker,
    _render_job_detail,
    _restore_archived_jobs_for_manual_flow,
)
from smartapply.app.workflow.widgets import (
    _filter_table,
    _render_action_strip,
    _sort_table,
    _status_pill,
)
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus


def _ranked_jobs_df(job_ids: list[int] | None = None) -> pd.DataFrame:
    """Ranked jobs that can be manually selected for LLM analysis."""
    rows: list[dict[str, Any]] = []
    analysis_keep_map = {
        int(k): bool(v)
        for k, v in st.session_state.get("wf_analysis_keep_map", {}).items()
    }
    with session_scope() as s:
        query = (
            s.query(Job)
            .filter(Job.archived_at.is_(None))
            .filter(Job.analyzed_at.is_(None))
        )
        if job_ids:
            query = query.filter(Job.id.in_(job_ids))
        for job in query.all():
            if job.score is None or job.score.final_score is None:
                continue
            components = job.score.components or {}
            desc = (job.cleaned_description or job.description or "").strip()
            default_keep = job.status == JobStatus.SHORTLISTED
            rows.append(
                {
                    "analyze": analysis_keep_map.get(int(job.id), default_keep),
                    "archive": False,
                    "id": int(job.id),
                    "title": job.title,
                    "company": job.company,
                    "location": job.location or "",
                    "contract": job.contract_type or "",
                    "source": job.source,
                    "status": status_label(job.status),
                    "score": round(float(job.score.final_score), 3),
                    "semantic": (
                        round(float(job.score.semantic_score), 3)
                        if job.score.semantic_score is not None
                        else None
                    ),
                    "skills": (
                        round(float(job.score.skill_score), 3)
                        if job.score.skill_score is not None
                        else None
                    ),
                    "seniority_score": (
                        round(float(job.score.seniority_score), 3)
                        if job.score.seniority_score is not None
                        else None
                    ),
                    "location_score": (
                        round(float(job.score.location_score), 3)
                        if job.score.location_score is not None
                        else None
                    ),
                    "reasons": " · ".join(str(r) for r in (components.get("reasons") or [])[:4]),
                    "preview": desc[:180] + ("..." if len(desc) > 180 else ""),
                    "url": job.application_url or "",
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty and "score" in df.columns:
        df = df.sort_values("score", ascending=False, na_position="last")
    return df


def _sync_analysis_keep_state(df: pd.DataFrame) -> None:
    if df.empty or not {"id", "analyze"}.issubset(df.columns):
        return
    updates = {
        int(row["id"]): bool(row["analyze"])
        for _, row in df[["id", "analyze"]].iterrows()
    }
    st.session_state["wf_analysis_keep_map"] = {
        **st.session_state.get("wf_analysis_keep_map", {}),
        **updates,
    }


def _selected_analysis_ids_from_df(df: pd.DataFrame) -> list[int]:
    if df.empty or "id" not in df.columns:
        return []
    keep_map = {
        int(k): bool(v)
        for k, v in st.session_state.get("wf_analysis_keep_map", {}).items()
    }
    return [
        int(row["id"])
        for _, row in df.iterrows()
        if bool(keep_map.get(int(row["id"]), bool(row.get("analyze", True))))
    ]



def _kept_ids_from_full_df(
    df: pd.DataFrame,
    *,
    state_key: str = "wf_keep_map",
) -> list[int]:
    if df.empty or "id" not in df.columns:
        return []
    keep_map = st.session_state.get(state_key, {})
    return [
        int(row["id"])
        for _, row in df.iterrows()
        if bool(keep_map.get(int(row["id"]), bool(row.get("keep", True))))
    ]



def step2_score() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 2 · Scoring et shortlist</h3>
          <div class="sa-muted">Calcule le ranking local/embedding, puis choisis exactement les offres qui auront droit à l'analyse IA.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    ids_to_score = list(st.session_state.get("wf_selected_for_scoring", []))
    selected_rejected_score_ids = _render_filter_rejected_picker(
        state_key="wf_rejected_score_map",
        editor_key="wf_step2_rejected_score_editor",
        title="Offres rejetées par le filtre à ajouter au scoring",
        checkbox_label="Scorer",
        caption=(
            "Ces offres avaient été archivées par le filtre local ou le dédoublonnage. "
            "Coche celles que tu veux réinjecter dans ce run de scoring."
        ),
    )
    if not ids_to_score:
        pending_df = _pending_jobs_df(
            keep_map=st.session_state.get("wf_keep_map", {}),
            recent_ids=st.session_state.get("wf_fetched_ids", []),
        )
        if pending_df.empty:
            ranked_resume = _ranked_jobs_df(st.session_state.get("wf_ranked_ids") or None)
            if ranked_resume.empty and not selected_rejected_score_ids:
                st.warning("Aucune offre à scorer. Retourne à la recherche.")
                if st.button("Retourner à la recherche", key="wf_step2_empty_back"):
                    st.session_state["wf_step"] = 1
                    st.rerun()
                return
        else:
            st.info(
                "Mode reprise : des offres sont en attente. Sélectionne celles à scorer."
            )
            pending_search = st.text_input(
                "Rechercher dans les offres à scorer",
                placeholder="Entreprise, poste, ville, source...",
                key="wf_step2_score_pending_search",
            )
            visible_pending_df = _filter_table(pending_df, pending_search)
            if visible_pending_df.empty:
                st.warning("Aucune offre en attente ne correspond à cette recherche.")
                return
            _job_editor(visible_pending_df, key="wf_step2_score_pending_editor")
            ids_to_score = _kept_ids_from_full_df(pending_df)
            st.session_state["wf_selected_for_scoring"] = ids_to_score

    if selected_rejected_score_ids:
        ids_to_score = list(dict.fromkeys([*ids_to_score, *selected_rejected_score_ids]))
        st.session_state["wf_selected_for_scoring"] = ids_to_score

    if ids_to_score:
        s1, s2 = st.columns(2)
        s1.metric("À scorer", len(ids_to_score))
        s2.metric("Embeddings", settings.openai_model_embed)
        override_ids = sorted(
            _filter_override_ids()
            .union(selected_rejected_score_ids)
            .intersection(ids_to_score)
        )
        if override_ids:
            st.caption(
                f"{len(override_ids)} offre(s) réactivée(s) manuellement peuvent passer le filtre local."
            )

        # Top-K présélection — paramétrable par run. Le défaut vient de
        # ``settings.top_k_ranked`` (env var ``TOP_K_RANKED``) mais l'utilisateur
        # peut le surcharger ici. Un slider est plus visible que number_input
        # pour ce genre de réglage et permet le drag.
        default_top = min(max(1, settings.top_k_ranked), len(ids_to_score))
        if len(ids_to_score) > 1:
            top_k_ranked = st.slider(
                "Top-K présélection pour l'analyse IA",
                min_value=1,
                max_value=len(ids_to_score),
                value=default_top,
                help=(
                    f"Après le scoring, ce nombre d'offres sera coché par défaut "
                    f"pour l'analyse LLM. Défaut global (env TOP_K_RANKED) : "
                    f"{settings.top_k_ranked}. Tu peux ajuster manuellement la "
                    f"shortlist après scoring avant d'enchaîner sur l'analyse."
                ),
                key="wf_step2_top_k_ranked",
            )
        else:
            # st.slider exige max > min : pas de slider si une seule offre.
            top_k_ranked = 1
            st.caption("Une seule offre à scorer — Top-K = 1.")

        _render_action_strip(
            kicker="Scoring",
            title=f"{len(ids_to_score)} offre(s) dans le run",
            message=(
                f"Le top-K précochera {int(top_k_ranked)} offre(s) pour l'analyse. "
                "Les autres restent scorées et disponibles pour une autre sélection."
            ),
            badges=[
                (f"Top-K {int(top_k_ranked)}", "purple"),
                (f"{len(selected_rejected_score_ids)} restaurée(s)", "warn")
                if selected_rejected_score_ids
                else ("Aucune restauration", "neutral"),
            ],
        )

        run_col, back_col = st.columns([2, 1])
        with run_col:
            run_ranking = st.button(
                "Calculer le scoring",
                type="primary",
                width="stretch",
                key="wf_run_scoring",
            )
        with back_col:
            if st.button("Retour recherche", key="wf_step2_back_fetch", width="stretch"):
                st.session_state["wf_step"] = 1
                st.rerun()

        if run_ranking:
            _begin_run("scoring")
            progress = st.progress(0.0, text="Filtrage et ranking...")
            with st.spinner("Filtrage local + scoring sémantique en cours..."):
                try:
                    restored_ids = _restore_archived_jobs_for_manual_flow(
                        selected_rejected_score_ids
                    )
                    if restored_ids:
                        ids_to_score = list(dict.fromkeys([*ids_to_score, *restored_ids]))
                        st.session_state["wf_selected_for_scoring"] = ids_to_score
                        override_ids = sorted(
                            _filter_override_ids().intersection(ids_to_score)
                        )
                    progress.progress(0.35, text="Filtrage local...")
                    report = pipeline_singleton().rank_pending(
                        top_k_ranked=int(top_k_ranked),
                        job_ids=ids_to_score,
                        local_filter_override_ids=override_ids,
                    )
                    progress.progress(1.0, text="Scoring terminé.")
                    st.session_state["wf_ranked_ids"] = report.ranked_ids
                    st.session_state["wf_selected_for_analysis"] = report.shortlisted_ids
                    st.session_state["wf_analysis_keep_map"] = {
                        int(job_id): int(job_id) in set(report.shortlisted_ids)
                        for job_id in report.ranked_ids
                    }
                    _end_run(
                        f"Scoring : {report.ranked} offre(s) scorée(s), "
                        f"{report.shortlisted} présélectionnée(s)."
                    )
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total", report.total)
                    c2.metric("Filtre OK", report.kept_after_filter)
                    c3.metric("Doublons", report.duplicates_removed)
                    c4.metric("Scorées", report.ranked)
                    st.success(st.session_state["wf_last_run_summary"])
                except Exception as e:
                    _end_run("Scoring interrompu par erreur.")
                    st.error(f"Échec scoring : {e}")
                finally:
                    progress.empty()

    st.divider()

    ranked_ids = st.session_state.get("wf_ranked_ids") or ids_to_score
    ranked_df = _ranked_jobs_df(ranked_ids)
    if ranked_df.empty:
        st.info("Lance le scoring pour afficher la shortlist triée.")
        return

    render_section_header(
        "Shortlist scorée",
        "Le top-K est précoché, mais tu gardes la main sur chaque offre à envoyer à l'analyse.",
        badges=[
            (f"{len(ranked_df)} scorée(s)", "blue"),
            (f"{len(st.session_state.get('wf_selected_for_analysis', []))} sélectionnée(s)", "good"),
        ],
    )
    rank_search = st.text_input(
        "Rechercher dans la shortlist scorée",
        placeholder="Entreprise, poste, ville, raison, score...",
        key="wf_step2_rank_search",
    )
    visible_ranked_df = _filter_table(ranked_df, rank_search)
    visible_ranked_df = _sort_table(
        visible_ranked_df,
        state_prefix="wf_step2_ranked_editor",
        default_sort="score",
        default_desc=True,
    )
    with st.form("wf_step2_ranked_editor_form"):
        edited = st.data_editor(
            visible_ranked_df,
            column_config={
                "analyze": st.column_config.CheckboxColumn("Analyser", default=True),
                "archive": st.column_config.CheckboxColumn("Archiver", default=False),
                "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
                "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
                "location": st.column_config.TextColumn("Lieu", disabled=True, width="small"),
                "contract": st.column_config.TextColumn("Contrat", disabled=True, width="small"),
                "source": st.column_config.TextColumn("Source", disabled=True, width="small"),
                "status": st.column_config.TextColumn("Statut", disabled=True, width="small"),
                "score": st.column_config.NumberColumn("Score final", disabled=True, format="%.3f", width="small"),
                "semantic": st.column_config.NumberColumn("Sémantique", disabled=True, format="%.3f", width="small"),
                "skills": st.column_config.NumberColumn("Skills", disabled=True, format="%.3f", width="small"),
                "seniority_score": st.column_config.NumberColumn("Seniorité", disabled=True, format="%.3f", width="small"),
                "location_score": st.column_config.NumberColumn("Lieu score", disabled=True, format="%.3f", width="small"),
                "reasons": st.column_config.TextColumn("Raisons", disabled=True, width="large"),
                "preview": st.column_config.TextColumn("Aperçu", disabled=True, width="large"),
                "url": st.column_config.LinkColumn("URL", disabled=True, width="small"),
            },
            hide_index=True,
            width="stretch",
            key="wf_step2_ranked_editor",
        )
        col_apply, col_archive = st.columns(2)
        with col_apply:
            apply_ranked = st.form_submit_button(
                "Appliquer les coches",
                type="primary",
                width="stretch",
            )
        with col_archive:
            archive_ranked = st.form_submit_button(
                "Archiver les offres cochées",
                width="stretch",
            )
    if archive_ranked:
        archive_ids = edited.loc[edited["archive"], "id"].astype(int).tolist()
        if not archive_ids:
            st.warning("Coche au moins une offre dans la colonne Archiver.")
        else:
            count = _archive_jobs_for_workflow(archive_ids)
            st.success(f"{count} offre(s) archivée(s).")
            st.rerun()
    if apply_ranked:
        _sync_analysis_keep_state(edited)
        st.success("Sélection mise à jour.")
    selected = _selected_analysis_ids_from_df(ranked_df)
    st.session_state["wf_selected_for_analysis"] = selected
    st.markdown(
        f"{_status_pill(str(len(selected)) + ' à analyser', 'good')} "
        f"{_status_pill(str(len(ranked_df) - len(selected)) + ' non analysée(s)', 'warn')}",
        unsafe_allow_html=True,
    )

    detail_ids = visible_ranked_df["id"].astype(int).tolist()
    if detail_ids:
        detail_id = st.selectbox(
            "Checker une offre scorée",
            options=detail_ids,
            format_func=lambda jid: (
                f"[{jid}] "
                f"{visible_ranked_df.loc[visible_ranked_df['id'] == jid, 'company'].iloc[0]} — "
                f"{visible_ranked_df.loc[visible_ranked_df['id'] == jid, 'title'].iloc[0]}"
            ),
            key="wf_step2_rank_detail_select",
        )
        _render_job_detail(int(detail_id))

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("Retour à l'étape 1", key="wf_step2_back_bottom"):
            st.session_state["wf_step"] = 1
            st.rerun()
    with col_next:
        if st.button(
            "Passer à l'étape 3 : analyse IA",
            type="primary",
            disabled=not selected,
            key="wf_step2_next_analysis",
        ):
            st.session_state["wf_selected_for_analysis"] = selected
            st.session_state["wf_step"] = 3
            st.rerun()


# ============================================================
# STEP 3 — Analyze (LLM)
# ============================================================
