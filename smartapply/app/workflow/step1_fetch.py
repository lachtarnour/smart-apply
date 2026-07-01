"""Workflow step 1: fetch and local filtering."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    SERPAPI_LANGUAGE_OPTIONS,
    pipeline_singleton,
    render_section_header,
)
from smartapply.app.workflow.state import (
    _end_run,
    _force_clear_run_lock,
    _request_stop,
    _serpapi_effective_config,
    _stop_requested,
    _try_begin_run,
    settings,
)
from smartapply.app.workflow.step1_archive import (
    _archive_ids_from_df,
    _archive_jobs_for_workflow,
    _filter_override_ids,
    _filter_pending_for_step1,
    _scraped_job_ids_excluding,
)
from smartapply.app.workflow.step1_progress import _wttj_progress_callback
from smartapply.app.workflow.step1_rejections import (
    _render_job_detail,
    _render_rejected_offer_controls,
)
from smartapply.app.workflow.widgets import (
    _filter_table,
    _render_action_strip,
    _render_compact_job_cards,
    _sort_table,
)
from smartapply.database import session_scope
from smartapply.database.repository import list_pending_processing
from smartapply.logging_setup import get_logger
from smartapply.pipeline.pipeline import freshness_kwargs
from smartapply.scrapers import SERPAPI_DATE_POSTED_LABELS

logger = get_logger(__name__)


def _render_fetch_stop_control() -> None:
    if st.session_state.get("wf_running") != "recherche":
        return
    status_col, stop_col = st.columns([2, 1])
    with status_col:
        if _stop_requested():
            st.warning(
                "Arrêt demandé : la recherche se termine au prochain point sûr. "
                "Une requête réseau déjà partie peut encore prendre quelques secondes."
            )
        else:
            st.info(
                "Recherche en cours. L'arrêt coupe toutes les sources au prochain point sûr."
            )
    with stop_col:
        if st.button(
            "Arrêter toutes les sources",
            key="wf_stop_fetch_all_sources",
            type="secondary",
            width="stretch",
        ):
            _request_stop()
            st.warning("Arrêt demandé pour toutes les sources en cours.")


def _render_run_notice() -> None:
    notice = st.session_state.get("wf_run_notice")
    if not notice:
        return
    if str(notice).startswith("Recherche arrêtée") or "Arrêt demandé" in str(notice):
        st.warning(str(notice))
    else:
        st.info(str(notice))


def _render_blocked_search_controls() -> None:
    logger.warning(
        "Search launch blocked in step1 UI: running=%r stop_requested=%s",
        st.session_state.get("wf_running"),
        st.session_state.get("wf_stop_requested"),
    )
    st.warning(
        "Une recherche est encore verrouillée. Si tu viens de demander l'arrêt "
        "et que rien ne bouge, débloque le verrou puis relance la recherche."
    )
    if st.button("Débloquer la recherche", key="wf_force_unlock_search", type="secondary"):
        _force_clear_run_lock("manual unlock from step1 search")
        st.success("Recherche débloquée. Relance la recherche.")
        st.rerun()


def _pending_jobs_df(keep_map: dict[int, bool], recent_ids: list[int]) -> pd.DataFrame:
    """Return jobs still available before LLM analysis, with description preview.

    With per-phase timestamps, "pending" includes freshly scraped jobs and
    jobs already filtered locally but not yet analyzed by the LLM.
    """
    rows: list[dict[str, Any]] = []
    with session_scope() as s:
        for job in list_pending_processing(s):
            desc = (job.cleaned_description or job.description or "").strip()
            preview = desc[:180] + ("..." if len(desc) > 180 else "")
            rows.append(
                {
                    "keep": keep_map.get(job.id, True),
                    "archive": False,
                    "id": job.id,
                    "new": "🆕" if job.id in recent_ids else "",
                    "title": job.title,
                    "company": job.company,
                    "location": job.location or "",
                    "contract": job.contract_type or "",
                    "source": job.source,
                    "phase": "Filtrée" if job.filtered_at else "Nouvelle",
                    "preview": preview,
                    "url": job.application_url or "",
                }
            )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # New ones (this session) first, then by company
    df = df.sort_values(["new", "company"], ascending=[False, True])
    return df


def _job_editor(df: pd.DataFrame, key: str) -> list[int]:
    """Render a data_editor where only the 'keep' column is editable.

    Returns the list of job IDs the user wants to keep.
    """
    if df.empty:
        return []
    df = _sort_table(
        df,
        state_prefix=key,
        default_sort="score" if "score" in df.columns else "new",
        default_desc=True,
    )
    with st.form(f"{key}_form"):
        edited = st.data_editor(
            df,
            column_config={
                "keep": st.column_config.CheckboxColumn("Garder", default=True),
                "archive": st.column_config.CheckboxColumn("Archiver", default=False),
                "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                "new": st.column_config.TextColumn("New", disabled=True, width="small"),
                "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
                "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
                "location": st.column_config.TextColumn("Lieu", disabled=True, width="small"),
                "contract": st.column_config.TextColumn("Contrat", disabled=True, width="small"),
                "source": st.column_config.TextColumn("Source", disabled=True, width="small"),
                "phase": st.column_config.TextColumn("Phase", disabled=True, width="small"),
                "status": st.column_config.TextColumn("Statut", disabled=True, width="small"),
                "score": st.column_config.NumberColumn(
                    "Score", disabled=True, format="%.3f", width="small"
                ),
                "preview": st.column_config.TextColumn("Aperçu", disabled=True, width="large"),
                "url": st.column_config.LinkColumn("URL", disabled=True, width="small"),
            },
            width="stretch",
            hide_index=True,
            key=key,
        )
        col_apply, col_archive = st.columns(2)
        with col_apply:
            apply_clicked = st.form_submit_button(
                "Appliquer les coches",
                type="primary",
                width="stretch",
            )
        with col_archive:
            archive_clicked = st.form_submit_button(
                "Archiver les offres cochées",
                width="stretch",
            )
    if archive_clicked:
        archive_ids = _archive_ids_from_df(edited)
        if not archive_ids:
            st.warning("Coche au moins une offre dans la colonne Archiver.")
        else:
            count = _archive_jobs_for_workflow(archive_ids)
            st.success(f"{count} offre(s) archivée(s).")
            st.rerun()
    if apply_clicked:
        keep_map = {
            int(row["id"]): bool(row["keep"])
            for _, row in edited[["id", "keep"]].iterrows()
        }
        st.session_state["wf_keep_map"] = {
            **st.session_state.get("wf_keep_map", {}),
            **keep_map,
        }
        st.success("Sélection mise à jour.")
    all_keep_map = st.session_state.get("wf_keep_map", {})
    return [
        int(row["id"])
        for _, row in df.iterrows()
        if bool(all_keep_map.get(int(row["id"]), bool(row.get("keep", True))))
    ]
def step1_fetch() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <div style="display:flex;justify-content:space-between;gap:1rem;align-items:center;flex-wrap:wrap;">
            <div>
              <h3 style="margin:0;">Étape 1 · Recherche et filtre local</h3>
              <div class="sa-muted">Cherche des offres, applique le filtre local, puis garde uniquement ce qui mérite un scoring.</div>
            </div>
            <div>
              <span class="sa-pill sa-pill-blue">Filtre stages/alternances actif</span>
              <span class="sa-pill sa-pill-good">Dédoublonnage DB actif</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    date_options = list(SERPAPI_DATE_POSTED_LABELS)
    language_labels = list(SERPAPI_LANGUAGE_OPTIONS)
    default_date = (
        settings.serpapi_date_posted
        if settings.serpapi_date_posted in SERPAPI_DATE_POSTED_LABELS
        else "week"
    )
    with st.form("fetch_form"):
        col1, col2, col3 = st.columns([1.4, 1.1, 0.8])
        with col1:
            query = st.text_input(
                "Requête",
                value="Data Scientist OR Machine Learning Engineer OR IA Engineer",
            )
            location = st.text_input(
                "Localisation",
                value=settings.serpapi_default_location,
            )
        with col2:
            sources = st.multiselect(
                "Sources",
                options=["serpapi", "francetravail", "linkedin", "welcometothejungle"],
                default=["francetravail", "linkedin", "welcometothejungle"],
            )
            date_posted = st.selectbox(
                "Fraîcheur",
                options=date_options,
                index=date_options.index(default_date),
                format_func=lambda value: SERPAPI_DATE_POSTED_LABELS[value],
            )
        with col3:
            slider_max = (
                settings.linkedin_max_results if "linkedin" in sources else 300
            )
            slider_default = (
                settings.linkedin_max_results if "linkedin" in sources else 15
            )
            max_per_source = st.slider(
                "Résultats/source",
                1,
                int(slider_max),
                min(int(slider_default), int(slider_max)),
            )

        serpapi_language_label = language_labels[0]
        unlimited_sources: list[str] = []
        with st.expander("Options avancées", expanded=False):
            adv1, adv2 = st.columns(2)
            with adv1:
                serpapi_language_label = st.selectbox(
                    "Langue Google Jobs",
                    options=language_labels,
                    index=0,
                    help="Bilingue lance Google Jobs en contexte anglais puis français.",
                )
            with adv2:
                unlimited_source_options = [
                    src for src in sources if src not in {"linkedin", "serpapi"}
                ]
                unlimited_sources = (
                    st.multiselect(
                        "Sources sans limite",
                        options=unlimited_source_options,
                        default=[],
                        help="LinkedIn et SerpApi restent limités pour éviter les coûts API.",
                    )
                    if unlimited_source_options
                    else []
                )
            if "serpapi" in sources:
                st.caption(
                    _serpapi_effective_config(
                        max_results=int(max_per_source),
                        date_posted=date_posted,
                        location=location,
                    )
                )
            if "linkedin" in sources:
                st.caption(
                    "LinkedIn/Apify : "
                    f"limite globale {settings.linkedin_max_results} depuis .env."
                )
            if unlimited_sources:
                st.caption("Sans limite : " + ", ".join(unlimited_sources))

        submitted = st.form_submit_button("Lancer la recherche", type="primary")

    _render_run_notice()
    _render_fetch_stop_control()

    st.divider()

    if "submitted" not in locals():
        submitted = False

    if submitted:
        if not _try_begin_run("recherche"):
            _render_blocked_search_controls()
            return
        _render_fetch_stop_control()
        try:
            if not sources:
                st.error("Choisis au moins une source.")
            else:
                logger.info(
                    "Search run started: sources=%s query=%r location=%r max_per_source=%s",
                    sources,
                    query,
                    location,
                    max_per_source,
                )
                all_ids: list[int] = []
                stopped = False
                p = pipeline_singleton()
                progress = st.progress(0.0, text="Préparation de la recherche...")
                for i, src in enumerate(sources, start=1):
                    if _stop_requested():
                        stopped = True
                        logger.warning("Search run stop observed before source=%s", src)
                        st.warning("Recherche arrêtée avant la source suivante.")
                        break
                    progress.progress((i - 1) / len(sources), text=f"Recherche sur {src}...")
                    logger.info("Search source started: source=%s index=%s/%s", src, i, len(sources))
                    with st.spinner(f"Recherche sur {src}..."):
                        try:
                            kwargs = freshness_kwargs(
                                src,
                                date_posted=date_posted,
                                serpapi_hl=SERPAPI_LANGUAGE_OPTIONS[serpapi_language_label],
                            )
                            source_max_results = (
                                None if src in unlimited_sources else int(max_per_source)
                            )
                            if (
                                src == "linkedin"
                                and source_max_results is not None
                                and source_max_results > settings.linkedin_max_results
                            ):
                                source_max_results = settings.linkedin_max_results
                            source_progress = None
                            if src == "welcometothejungle":
                                source_progress = st.progress(
                                    0.0,
                                    text="WTTJ: préparation...",
                                )
                                kwargs["progress_callback"] = _wttj_progress_callback(
                                    source_progress
                                )
                                kwargs["progress_target"] = source_max_results
                            report = p.ingest(
                                src,
                                query,
                                location,
                                max_results=source_max_results,
                                stop_requested=_stop_requested,
                                **kwargs,
                            )
                            summary_bits = [f"{report.inserted} nouvelle(s)"]
                            logger.info(
                                "Search source finished: source=%s accepted_for_persist=%s "
                                "inserted=%s updated_pending=%s skipped_processed=%s "
                                "skipped_known_collect=%s skipped_existing_collect=%s "
                                "skipped_existing_persist=%s hit_raw_seen_cap=%s cancelled=%s",
                                src,
                                report.fetched,
                                report.inserted,
                                report.updated_pending,
                                report.skipped_processed,
                                report.skipped_known_during_collect,
                                report.skipped_existing_during_collect,
                                report.skipped_existing_during_persist,
                                report.hit_raw_seen_cap,
                                report.cancelled,
                            )
                            skipped_existing = (
                                report.skipped_existing_during_collect
                                + report.skipped_existing_during_persist
                            )
                            if skipped_existing:
                                summary_bits.append(
                                    f"{skipped_existing} déjà en base ignorée(s)"
                                )
                            if report.skipped_known_during_collect:
                                summary_bits.append(
                                    f"{report.skipped_known_during_collect} déjà connue(s) ignorée(s) en collecte"
                                )
                            if report.updated_pending:
                                summary_bits.append(
                                    f"{report.updated_pending} déjà en attente"
                                )
                            if report.skipped_processed:
                                summary_bits.append(
                                    f"{report.skipped_processed} déjà traitée(s)/ignorée(s)"
                                )
                            st.success(f"{src} : " + ", ".join(summary_bits) + ".")
                            if report.hit_raw_seen_cap and not report.inserted:
                                st.info(
                                    f"{src} : limite de scan atteinte avant de trouver de nouvelles offres. "
                                    "Augmente le slider 'Résultats/source' ou élargis la requête."
                                )
                            if report.cancelled:
                                stopped = True
                                logger.warning("Search source cancelled: source=%s", src)
                                st.warning(f"{src} : arrêt demandé, collecte interrompue.")
                            if source_progress is not None:
                                source_progress.progress(
                                    0.99 if report.cancelled else 1.0,
                                    text=(
                                        f"WTTJ: arrêt demandé · {report.fetched} offre(s) collectée(s)"
                                        if report.cancelled
                                        else f"WTTJ: terminé · {report.fetched} offre(s) collectée(s)"
                                    ),
                                )
                            all_ids.extend(report.job_ids)
                            if stopped or _stop_requested():
                                stopped = True
                                logger.warning("Search run stopping after source=%s", src)
                                break
                        except Exception as e:
                            logger.exception("Search source failed: source=%s", src)
                            st.error(f"{src} : {e}")
                progress.progress(
                    1.0,
                    text=(
                        "Recherche arrêtée · filtre local automatique..."
                        if stopped
                        else "Filtre local automatique..."
                    ),
                )
                st.session_state["wf_fetched_ids"] = all_ids
                with st.spinner("Filtre local automatique..."):
                    filter_report = _filter_pending_for_step1()
                if filter_report is not None:
                    st.session_state["wf_auto_filter_report"] = filter_report.__dict__
                    st.info(
                        f"Filtre local : {filter_report.kept} gardée(s), "
                        f"{filter_report.rejected} retirée(s)"
                        + (
                            f", dont {filter_report.duplicates_removed} doublon(s)."
                            if filter_report.duplicates_removed
                            else "."
                        )
                    )
                progress.empty()
                summary_prefix = "Recherche arrêtée" if stopped else "Recherche terminée"
                summary = f"{summary_prefix} : {len(all_ids)} offre(s) candidate(s)."
                logger.info("Search run ended: stopped=%s candidate_ids=%s", stopped, len(all_ids))
                _end_run(summary)
        finally:
            if st.session_state.get("wf_running") == "recherche":
                _end_run()

    fetched_ids = st.session_state["wf_fetched_ids"]
    auto_filter_report = st.session_state.get("wf_auto_filter_report")
    if auto_filter_report:
        st.caption(
            "Filtre automatique actif : stages, alternances, offres hors cible, "
            "doublons et postes trop senior sont retirés avant l'étape IA. "
            f"Dernier passage : {auto_filter_report.get('kept', 0)} gardée(s), "
            f"{auto_filter_report.get('rejected', 0)} retirée(s)."
        )
    if st.session_state.get("wf_filter_override_ids"):
        st.caption(
            f"{len(st.session_state['wf_filter_override_ids'])} offre(s) réactivée(s) "
            "manuellement seront autorisées à passer le filtre local."
        )
    if (
        not submitted
        and _scraped_job_ids_excluding(_filter_override_ids())
        and st.button(
            "Appliquer le filtre local aux nouvelles offres",
            key="wf_filter_pending_now",
        )
    ):
        with st.spinner("Filtre local automatique..."):
            filter_report = _filter_pending_for_step1()
        if filter_report is not None:
            st.session_state["wf_auto_filter_report"] = filter_report.__dict__
            st.success(
                f"Filtre local : {filter_report.kept} gardée(s), "
                f"{filter_report.rejected} retirée(s)."
            )
        st.rerun()
    keep_map = st.session_state.get("wf_keep_map", {})
    df = _pending_jobs_df(keep_map=keep_map, recent_ids=fetched_ids)
    if df.empty:
        _render_rejected_offer_controls()
        st.info(
            "Aucune offre en attente. Lance une recherche ci-dessus ou importe "
            "une offre depuis la CLI / une autre page."
        )
        return

    new_count = int((df["new"] == "🆕").sum()) if "new" in df.columns else 0
    filtered_count = int((df["phase"] == "Filtrée").sum()) if "phase" in df.columns else 0
    k1, k2, k3 = st.columns(3)
    k1.metric("Offres à décider", len(df))
    k2.metric("Nouvelles", new_count)
    k3.metric("Déjà filtrées", filtered_count)

    render_section_header(
        "Vivier de départ",
        "Construis le lot qui partira au scoring. Les offres non gardées ici restent disponibles.",
        badges=[
            (f"{len(df)} affichées", "blue"),
            (f"{filtered_count} déjà filtrées", "neutral" if filtered_count else "blue"),
        ],
    )
    st.markdown("<div class='sa-toolbar'>", unsafe_allow_html=True)
    search_text = st.text_input(
        "Rechercher dans les offres",
        value=st.session_state.get("wf_search_text", ""),
        placeholder="Entreprise, titre, ville, techno...",
        key="wf_search_text",
    )
    visible_df = _filter_table(df, search_text)
    csel, cdesel, cclear = st.columns([1, 1, 2])
    with csel:
        if st.button("Tout garder visible", disabled=visible_df.empty, key="wf_keep_visible"):
            keep_map = st.session_state.get("wf_keep_map", {})
            for jid in visible_df["id"].astype(int):
                keep_map[int(jid)] = True
            st.session_state["wf_keep_map"] = keep_map
            st.rerun()
    with cdesel:
        if st.button("Tout retirer visible", disabled=visible_df.empty, key="wf_drop_visible"):
            keep_map = st.session_state.get("wf_keep_map", {})
            for jid in visible_df["id"].astype(int):
                keep_map[int(jid)] = False
            st.session_state["wf_keep_map"] = keep_map
            st.rerun()
    with cclear:
        st.caption(f"{len(visible_df)} offre(s) affichée(s). Les cases restent mémorisées même si tu filtres la vue.")
    st.markdown("</div>", unsafe_allow_html=True)

    kept_ids = _job_editor(visible_df, key="wf_step1_editor")
    all_keep_map = st.session_state.get("wf_keep_map", {})
    full_kept_ids = [
        int(row["id"])
        for _, row in df.iterrows()
        if bool(all_keep_map.get(int(row["id"]), bool(row["keep"])))
    ]

    _render_action_strip(
        kicker="Sélection active",
        title=f"{len(full_kept_ids)} offre(s) prêtes pour le scoring",
        message=(
            "Les offres retirées de cette sélection ne sont pas supprimées ; "
            "elles peuvent revenir dans un autre lot."
        ),
        badges=[
            (f"{len(full_kept_ids)} gardée(s)", "good"),
            (f"{len(df) - len(full_kept_ids)} non cochée(s)", "warn"),
        ],
    )
    _render_compact_job_cards(df, full_kept_ids)

    detail_ids = visible_df["id"].astype(int).tolist()
    if not detail_ids:
        st.info("Aucune offre ne correspond à cette recherche.")
        _render_rejected_offer_controls()
        return
    detail_id = st.selectbox(
        "Checker une offre avant de passer au scoring",
        options=detail_ids,
        format_func=lambda jid: (
            f"[{jid}] "
            f"{visible_df.loc[visible_df['id'] == jid, 'company'].iloc[0]} — "
            f"{visible_df.loc[visible_df['id'] == jid, 'title'].iloc[0]}"
        ),
        key="wf_step1_detail_select",
    )
    _render_job_detail(int(detail_id))
    _render_rejected_offer_controls()

    if st.button(
        "Passer à l'étape 2 : scoring",
        type="primary",
        disabled=not full_kept_ids,
    ):
        st.session_state["wf_selected_for_scoring"] = full_kept_ids
        st.session_state["wf_ranked_ids"] = []
        st.session_state["wf_selected_for_analysis"] = []
        st.session_state["wf_analysis_keep_map"] = {}
        st.session_state["wf_step"] = 2
        st.rerun()


# ============================================================
# STEP 2 — Score + shortlist
# ============================================================
