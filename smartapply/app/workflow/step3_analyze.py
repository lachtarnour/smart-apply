"""Workflow step 3: LLM analysis."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import pipeline_singleton, render_section_header
from smartapply.app.workflow.state import _begin_run, _end_run, settings
from smartapply.app.workflow.step1_fetch import (
    _render_filter_rejected_picker,
    _restore_archived_jobs_for_manual_flow,
)
from smartapply.app.workflow.step2_score import (
    _ranked_jobs_df,
    _selected_analysis_ids_from_df,
    _sync_analysis_keep_state,
)
from smartapply.app.workflow.widgets import _filter_table, _render_action_strip
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus


def _analyzed_jobs_df(job_ids: list[int] | None = None) -> pd.DataFrame:
    """Jobs that already have an LLM analysis and can move to generation."""
    rows: list[dict[str, Any]] = []
    manual_contacts = st.session_state.get("wf_manual_contacts", {})
    with session_scope() as s:
        query = s.query(Job).filter(Job.status == JobStatus.ANALYZED)
        if job_ids:
            query = query.filter(Job.id.in_(job_ids))
        for job in query.all():
            if job.analysis is None:
                continue
            raw = job.analysis.raw_response or {}
            rows.append(
                {
                    "keep": True,
                    "id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "score": (
                        round(job.score.final_score, 3)
                        if job.score and job.score.final_score is not None
                        else None
                    ),
                    "seniority": job.analysis.seniority or "",
                    "company_size": raw.get("company_size", "unknown"),
                    "lang": raw.get("offer_language", ""),
                    "manual_contact": manual_contacts.get(int(job.id), ""),
                    "domain": job.analysis.domain or "",
                    "reasons": " · ".join((job.analysis.match_reasons or [])[:2]),
                    "risks": " · ".join((job.analysis.risks or [])[:2]),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty and "score" in df.columns:
        df = df.sort_values("score", ascending=False, na_position="last")
    return df



def _sync_manual_contacts(df: pd.DataFrame) -> None:
    contacts = dict(st.session_state.get("wf_manual_contacts", {}))
    if df.empty or "manual_contact" not in df.columns:
        st.session_state["wf_manual_contacts"] = contacts
        return
    for _, row in df[["id", "manual_contact"]].iterrows():
        job_id = int(row["id"])
        value = str(row.get("manual_contact") or "").strip()
        if value:
            contacts[job_id] = value
        else:
            contacts.pop(job_id, None)
    st.session_state["wf_manual_contacts"] = contacts


def _sync_contact_lookup_state(df: pd.DataFrame) -> None:
    lookup_map = {
        int(k): bool(v)
        for k, v in st.session_state.get("wf_contact_lookup_map", {}).items()
    }
    if df.empty or not {"id", "lookup_contact"}.issubset(df.columns):
        st.session_state["wf_contact_lookup_map"] = lookup_map
        return
    for _, row in df[["id", "lookup_contact"]].iterrows():
        lookup_map[int(row["id"])] = bool(row.get("lookup_contact", False))
    st.session_state["wf_contact_lookup_map"] = lookup_map


def _sync_keep_state(df: pd.DataFrame, *, state_key: str = "wf_keep_map") -> None:
    if df.empty or not {"id", "keep"}.issubset(df.columns):
        return
    keep_updates = {
        int(row["id"]): bool(row["keep"])
        for _, row in df[["id", "keep"]].iterrows()
    }
    st.session_state[state_key] = {
        **st.session_state.get(state_key, {}),
        **keep_updates,
    }


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



def step3_analyze() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 3 · Analyse IA</h3>
          <div class="sa-muted">Choisis dans les offres scorées disponibles, avec le top-K précoché et la possibilité de restaurer des offres filtrées.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ids_to_analyze: list[int] = []
    resume_mode = False
    analysis_attempted = False
    selected_rejected_analysis_ids = _render_filter_rejected_picker(
        state_key="wf_rejected_analysis_map",
        editor_key="wf_step3_rejected_analysis_editor",
        title="Offres rejetées par le filtre à ajouter à l'analyse",
        checkbox_label="Analyser",
        caption=(
            "Tu peux forcer l'analyse IA d'une offre rejetée par le filtre. "
            "Elle sera restaurée au lancement de l'analyse."
        ),
    )

    candidate_df = _ranked_jobs_df()
    if not candidate_df.empty:
        render_section_header(
            "Offres scorées disponibles",
            "Le top-K est précoché ; ajoute ou retire des offres avant l'appel IA.",
            badges=[
                (f"{len(candidate_df)} disponible(s)", "blue"),
                ("Top-K précoché", "purple"),
            ],
        )
        candidate_search = st.text_input(
            "Rechercher dans les offres disponibles pour analyse",
            placeholder="Entreprise, poste, ville, raison, score...",
            key="wf_step3_candidate_search",
        )
        visible_candidate_df = _filter_table(candidate_df, candidate_search)
        edited_candidates = st.data_editor(
            visible_candidate_df,
            column_config={
                "analyze": st.column_config.CheckboxColumn("Analyser", default=True),
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
            key="wf_step3_candidate_editor",
        )
        _sync_analysis_keep_state(edited_candidates)
        ids_to_analyze = _selected_analysis_ids_from_df(candidate_df)

    if selected_rejected_analysis_ids:
        ids_to_analyze = list(
            dict.fromkeys([*ids_to_analyze, *selected_rejected_analysis_ids])
        )

    st.session_state["wf_selected_for_analysis"] = ids_to_analyze

    if not ids_to_analyze:
        existing_df = _analyzed_jobs_df()
        if existing_df.empty:
            st.warning("Aucune offre sélectionnée pour analyse. Retourne au scoring pour choisir la shortlist.")
            col_score, col_fetch = st.columns(2)
            with col_score:
                if st.button("Retourner au scoring", key="wf_step3_empty_score"):
                    st.session_state["wf_step"] = 2
                    st.rerun()
            with col_fetch:
                if st.button("Retourner à la recherche", key="wf_step3_empty_fetch"):
                    st.session_state["wf_step"] = 1
                    st.rerun()
            return
        resume_mode = True
        ids_to_analyze = existing_df["id"].astype(int).tolist()
        st.info(
            "Mode reprise : aucune nouvelle sélection, donc j'affiche les offres déjà analysées en base."
        )

    a1, a2, a3 = st.columns(3)
    a1.metric("Sélection", len(ids_to_analyze))
    a2.metric("Parallélisme IA", settings.llm_max_concurrent)
    a3.metric("Analyse IA", settings.openai_model_cheap)

    if not resume_mode:
        _render_action_strip(
            kicker="Analyse IA",
            title=f"{len(ids_to_analyze)} offre(s) sélectionnée(s)",
            message=(
                "L'appel IA ne part que sur cette sélection. Les offres non cochées "
                "restent scorées et réutilisables."
            ),
            badges=[
                (f"{len(selected_rejected_analysis_ids)} restaurée(s)", "warn")
                if selected_rejected_analysis_ids
                else ("Aucune restauration", "neutral"),
                (f"Modèle {settings.openai_model_cheap}", "blue"),
            ],
        )

    run_analysis = False
    if not resume_mode:
        run_col, stop_col = st.columns([2, 1])
        with run_col:
            run_analysis = st.button(
                "Lancer l'analyse IA",
                type="primary",
                width="stretch",
                disabled=not ids_to_analyze,
            )
        with stop_col:
            if st.button("Arrêter", key="wf_stop_analysis", width="stretch"):
                st.session_state["wf_stop_requested"] = True
    else:
        if st.button("Analyser une nouvelle shortlist", key="wf_step3_new_score"):
            st.session_state["wf_step"] = 2
            st.rerun()

    if run_analysis:
        analysis_attempted = True
        restored_ids = _restore_archived_jobs_for_manual_flow(
            selected_rejected_analysis_ids
        )
        if restored_ids:
            ids_to_analyze = list(dict.fromkeys([*ids_to_analyze, *restored_ids]))
        st.session_state["wf_selected_for_analysis"] = ids_to_analyze
        _begin_run("analyse IA")
        progress = st.progress(0.0, text="Analyse IA...")
        with st.spinner("Analyse IA en cours sur la shortlist sélectionnée..."):
            try:
                progress.progress(0.35, text="Appels IA en parallèle...")
                report = pipeline_singleton().analyze_jobs(ids_to_analyze)
                progress.progress(1.0, text="Analyse terminée.")
                st.success("Traitement terminé")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Demandées", report.requested)
                col2.metric("Déjà analysées", report.already_analyzed)
                col3.metric("Ignorées", report.skipped_missing)
                col4.metric("Analysées", report.analyzed)
                _end_run(f"Analyse : {report.analyzed} offre(s) analysée(s).")
            except Exception as e:
                _end_run("Analyse interrompue par erreur.")
                st.error(f"Échec : {e}")
            finally:
                progress.empty()

    st.divider()

    # Show the analyzed jobs (status = ANALYZED) for the user to pick which ones to apply to
    with session_scope() as s:
        analyzed_jobs = (
            s.query(Job)
            .filter(Job.id.in_(ids_to_analyze))
            .filter(Job.status == JobStatus.ANALYZED)
            .all()
        )
        analyzed_ids = [j.id for j in analyzed_jobs]
        rejected_jobs = (
            s.query(Job)
            .filter(Job.id.in_(ids_to_analyze))
            .filter(Job.status == JobStatus.ARCHIVED)
            .all()
        )
        rejected_summary = [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "reasons": (
                    (j.score.components or {}).get("reasons", [])
                    if j.score
                    else []
                ),
            }
            for j in rejected_jobs
        ]

    if rejected_summary:
        with st.expander(f"❌ {len(rejected_summary)} offre(s) rejetée(s) par le filtre"):
            for r in rejected_summary:
                st.write(f"**[{r['id']}] {r['title']}** @ {r['company']}")
                if r["reasons"]:
                    st.caption(" · ".join(r["reasons"][:5]))

    if not analyzed_ids:
        if not analysis_attempted and not resume_mode:
            st.info(
                "Sélection prête. Clique sur **Lancer l'analyse IA** pour analyser ces offres."
            )
            return
        st.info("Aucune offre analysée. Retour au scoring pour ajuster la shortlist.")
        return

    # Build a richer view with LLM analysis data
    df = _analyzed_jobs_df(analyzed_ids)
    render_section_header(
        "Offres analysées",
        "Sélectionne les candidatures à générer, avec contact manuel optionnel.",
        badges=[
            (f"{len(analyzed_ids)} analysée(s)", "blue"),
            (f"{len(st.session_state.get('wf_selected_for_apply', []))} vers génération", "good"),
        ],
    )

    analyze_search = st.text_input(
        "Rechercher dans les offres analysées",
        placeholder="Entreprise, domaine, risque, compétence...",
        key="wf_step2_search",
    )
    visible_df = _filter_table(df.rename(columns={"reasons": "preview"}), analyze_search)
    if "preview" in visible_df.columns:
        visible_df = visible_df.rename(columns={"preview": "reasons"})

    edited = st.data_editor(
        visible_df,
        column_config={
            "keep": st.column_config.CheckboxColumn("Garder", default=True),
            "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
            "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
            "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
            "score": st.column_config.NumberColumn("Score", disabled=True, format="%.3f", width="small"),
            "seniority": st.column_config.TextColumn("Seniority", disabled=True, width="small"),
            "company_size": st.column_config.TextColumn("Taille", disabled=True, width="small"),
            "lang": st.column_config.TextColumn("Lang", disabled=True, width="small"),
            "manual_contact": st.column_config.TextColumn(
                "Contact manuel",
                width="medium",
                help="Optionnel. Email recruteur/RH à utiliser pour cette offre.",
            ),
            "domain": st.column_config.TextColumn("Domaine", disabled=True, width="medium"),
            "reasons": st.column_config.TextColumn("Pourquoi ça match", disabled=True, width="large"),
            "risks": st.column_config.TextColumn("Risques", disabled=True, width="medium"),
        },
        hide_index=True,
        width="stretch",
        key="wf_step2_editor",
    )
    _sync_manual_contacts(edited)
    _sync_keep_state(edited, state_key="wf_apply_keep_map")
    selected = _kept_ids_from_full_df(df, state_key="wf_apply_keep_map")

    st.write(f"→ **{len(selected)} offre(s) à transformer en candidature**")

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("⬅ Retour à l'étape 2 : scoring"):
            st.session_state["wf_step"] = 2
            st.rerun()
    with col_next:
        if st.button(
            "Passer à l'étape 4 : génération",
            type="primary",
            disabled=not selected,
        ):
            st.session_state["wf_selected_for_apply"] = selected
            st.session_state["wf_step"] = 4
            st.rerun()


# ============================================================
# STEP 4 — Generate (CV + email)
# ============================================================


