"""Workflow step 1: fetch and local filtering."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    SERPAPI_LANGUAGE_OPTIONS,
    pipeline_singleton,
    render_section_header,
)
from smartapply.app.workflow.state import (
    _begin_run,
    _end_run,
    _serpapi_effective_config,
    _stop_requested,
    settings,
)
from smartapply.app.workflow.widgets import (
    _filter_table,
    _render_action_strip,
    _render_compact_job_cards,
)
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import list_pending_processing
from smartapply.jobsearch import AutopilotRunner
from smartapply.pipeline.pipeline import freshness_kwargs
from smartapply.scrapers import SERPAPI_DATE_POSTED_LABELS


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


def _event_int(event: dict[str, Any], key: str) -> int | None:
    value = event.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _wttj_progress_fraction(event: dict[str, Any]) -> float:
    event_name = str(event.get("event") or "")
    yielded = _event_int(event, "yielded") or 0
    target = _event_int(event, "progress_target") or _event_int(event, "max_jobs")
    if event_name == "done":
        return 1.0
    if target and target > 0:
        partial = {
            "page_fetch_start": 0.05,
            "page_links": 0.15,
            "job_detail_start": 0.35,
            "company_profile_start": 0.7,
        }.get(event_name, 0.0)
        return max(0.0, min(0.99, (yielded + partial) / target))

    page = _event_int(event, "page")
    pages_total = _event_int(event, "page_count") or _event_int(event, "pages_total")
    if not page or not pages_total:
        return 0.0
    partial = {
        "page_fetch_start": 0.05,
        "page_links": 0.25,
        "job_detail_start": 0.55,
        "company_profile_start": 0.75,
        "job_yielded": 0.9,
    }.get(event_name, 0.15)
    return max(0.0, min(0.99, ((page - 1) + partial) / pages_total))


def _wttj_progress_text(event: dict[str, Any]) -> str:
    event_name = str(event.get("event") or "")
    yielded = _event_int(event, "yielded") or 0
    target = _event_int(event, "progress_target") or _event_int(event, "max_jobs")
    page = _event_int(event, "page")
    pages_total = _event_int(event, "page_count") or _event_int(event, "pages_total")
    page_text = f"page {page}/{pages_total}" if page and pages_total else "préparation"
    count_text = f"{yielded}/{target} récupérée(s)" if target else f"{yielded} récupérée(s)"

    if event_name == "start":
        return f"WTTJ: préparation · objectif {target} offre(s)" if target else "WTTJ: préparation"
    if event_name == "page_fetch_start":
        return f"WTTJ: {page_text} · chargement des matches · {count_text}"
    if event_name == "page_links":
        links = _event_int(event, "links") or 0
        return f"WTTJ: {page_text} · {links} lien(s) trouvé(s) · {count_text}"
    if event_name == "page_empty":
        return f"WTTJ: {page_text} vide · arrêt de la recherche"
    if event_name == "page_duplicate":
        return f"WTTJ: {page_text} déjà lue · arrêt de la recherche"
    if event_name == "job_detail_start":
        page_job_index = _event_int(event, "page_job_index") or 0
        page_jobs = _event_int(event, "page_jobs") or 0
        return f"WTTJ: {page_text} · lecture offre {page_job_index}/{page_jobs} · {count_text}"
    if event_name == "company_profile_start":
        company = str(event.get("company") or "entreprise")
        return f"WTTJ: enrichissement {company[:40]} · {count_text}"
    if event_name == "job_yielded":
        title = str(event.get("title") or "offre")
        return f"WTTJ: {count_text} · {title[:50]}"
    if event_name == "done":
        return f"WTTJ: terminé · {count_text}"
    return f"WTTJ: {page_text} · {count_text}"


def _wttj_progress_callback(progress_widget: Any):
    def _callback(event: dict[str, Any]) -> None:
        progress_widget.progress(
            _wttj_progress_fraction(event),
            text=_wttj_progress_text(event),
        )

    return _callback


def _reason_text(job: Job) -> str:
    reasons = []
    if job.score and job.score.components:
        reasons = job.score.components.get("reasons", []) or []
    return " · ".join(str(reason) for reason in reasons[:5]) or "Raison non renseignée"


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
                "reason": st.column_config.TextColumn("Raison", disabled=True, width="large"),
                "preview": st.column_config.TextColumn("Aperçu", disabled=True, width="large"),
                "url": st.column_config.LinkColumn("URL", disabled=True, width="small"),
            },
            hide_index=True,
            width="stretch",
            key=editor_key,
        )
        if not edited.empty and {"id", "include"}.issubset(edited.columns):
            for _, row in edited[["id", "include"]].iterrows():
                selection_map[int(row["id"])] = bool(row["include"])
            st.session_state[state_key] = selection_map
        selected_ids = [
            int(row["id"])
            for _, row in df.iterrows()
            if bool(selection_map.get(int(row["id"]), bool(row.get("include", False))))
        ]
        st.caption(f"{len(selected_ids)} offre(s) ajoutée(s) par sélection manuelle.")
        return selected_ids


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
        edited = st.data_editor(
            df,
            column_config={
                "restore": st.column_config.CheckboxColumn("Réactiver", default=False),
                "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
                "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
                "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
                "reason": st.column_config.TextColumn("Raison", disabled=True, width="large"),
                "url": st.column_config.LinkColumn("URL", disabled=True, width="small"),
            },
            hide_index=True,
            width="stretch",
            key="wf_rejected_editor",
        )
        restore_ids = edited.loc[edited["restore"], "id"].astype(int).tolist()
        col_restore, col_reset = st.columns([2, 1])
        with col_restore:
            if st.button(
                "Réactiver les offres sélectionnées",
                disabled=not restore_ids,
                key="wf_restore_rejected",
                type="primary",
            ):
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
        with col_reset:
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

    st.markdown("**Description**")
    st.text_area(
        "Description (lecture seule)",
        data["desc"] or "(description vide)",
        height=300,
        disabled=True,
        label_visibility="collapsed",
        key=f"wf_step1_detail_{job_id}",
    )


def _job_editor(df: pd.DataFrame, key: str) -> list[int]:
    """Render a data_editor where only the 'keep' column is editable.

    Returns the list of job IDs the user wants to keep.
    """
    if df.empty:
        return []
    edited = st.data_editor(
        df,
        column_config={
            "keep": st.column_config.CheckboxColumn("Garder", default=True),
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
    keep_map = {
        int(row["id"]): bool(row["keep"])
        for _, row in edited[["id", "keep"]].iterrows()
    }
    st.session_state["wf_keep_map"] = {
        **st.session_state.get("wf_keep_map", {}),
        **keep_map,
    }
    return edited.loc[edited["keep"], "id"].astype(int).tolist()



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
    tab_manual, tab_auto = st.tabs(["Recherche contrôlée", "Autopilot express"])

    with tab_manual, st.form("fetch_form"):
            col1, col2, col3 = st.columns([1.5, 1.1, 1])
            with col1:
                query = st.text_input("Requête", value="Data Scientist OR Machine Learning Engineer")
                st.caption("Astuce : `A OR B OR C` lance plusieurs recherches. Les titres anglais sont conservés, avec alias FR en plus si utile.")
                location = st.text_input("Localisation", value=settings.serpapi_default_location)
            with col2:
                sources = st.multiselect(
                    "Sources",
                    options=["serpapi", "francetravail", "welcometothejungle"],
                    default=["serpapi", "francetravail", "welcometothejungle"],
                    help="SerpApi consomme un crédit par page. France Travail est gratuit. WTTJ lit tes matches personnalisés.",
                )
                date_posted = st.selectbox(
                    "Fraîcheur des offres",
                    options=date_options,
                    index=date_options.index(default_date),
                    format_func=lambda value: SERPAPI_DATE_POSTED_LABELS[value],
                    help="Appliqué à Google Jobs (chip date_posted) et à France Travail (minCreationDate).",
                )
                serpapi_language_label = st.selectbox(
                    "Langue Google Jobs",
                    options=language_labels,
                    index=0,
                    help="Bilingue lance Google Jobs en contexte anglais puis français, toujours sur le pays/localisation demandés.",
                )
            with col3:
                max_per_source = st.slider("Résultats/source", 5, 300, 15)
                unlimited_source_options = [
                    src for src in sources if src != "serpapi"
                ]
                unlimited_sources = (
                    st.multiselect(
                        "Sources sans limite",
                        options=unlimited_source_options,
                        default=[],
                        help=(
                            "Passe max_results=None aux sources sélectionnées. "
                            "SerpApi est volontairement exclu pour éviter des "
                            "coûts de pagination."
                        ),
                    )
                    if unlimited_source_options
                    else []
                )
                if unlimited_sources:
                    unlimited_caption = "Sans limite: " + ", ".join(unlimited_sources)
                    if "welcometothejungle" in unlimited_sources:
                        unlimited_caption += (
                            ". WTTJ utilise "
                            f"{settings.wttj_pages} page(s) / "
                            f"{settings.wttj_per_page} offre(s)/page."
                        )
                    st.caption(unlimited_caption)
                if "serpapi" in sources:
                    st.caption(
                        _serpapi_effective_config(
                            max_results=int(max_per_source),
                            date_posted=date_posted,
                            location=location,
                        )
                    )
            submitted = st.form_submit_button("Lancer la recherche", type="primary")

    with tab_auto:
        st.caption("Mode rapide : cherche, analyse, génère et prépare les meilleurs dossiers. Rien n'est envoyé automatiquement.")
        with st.form("autopilot_form"):
            a1, a2, a3 = st.columns([1.4, 1, 1])
            with a1:
                auto_query = st.text_input(
                    "Requête autopilot",
                    value="Data Scientist OR Machine Learning Engineer OR AI Engineer",
                    key="wf_auto_query",
                )
                st.caption("Les parties séparées par `OR` sont recherchées une par une, anglais conservé, alias FR ajouté si utile.")
                auto_location = st.text_input(
                    "Localisation autopilot",
                    value=settings.serpapi_default_location,
                    key="wf_auto_location",
                )
            with a2:
                auto_sources = st.multiselect(
                    "Sources autopilot",
                    options=["serpapi", "francetravail", "welcometothejungle", "manual"],
                    default=["serpapi", "francetravail", "welcometothejungle"],
                    key="wf_auto_sources",
                )
                auto_date = st.selectbox(
                    "Fraîcheur des offres autopilot",
                    options=date_options,
                    index=date_options.index(default_date),
                    format_func=lambda value: SERPAPI_DATE_POSTED_LABELS[value],
                    key="wf_auto_date",
                    help="Appliqué à Google Jobs (chip date_posted) et à France Travail (minCreationDate).",
                )
                auto_language_label = st.selectbox(
                    "Langue Google Jobs autopilot",
                    options=language_labels,
                    index=0,
                    key="wf_auto_language",
                    help="Bilingue augmente le rappel mais peut consommer plus de pages SerpApi.",
                )
            with a3:
                auto_target = st.number_input("Objectif", min_value=1, max_value=50, value=8)
                auto_max = st.number_input("Résultats/source", min_value=5, max_value=300, value=25)
                if "serpapi" in auto_sources:
                    st.caption(
                        _serpapi_effective_config(
                            max_results=int(auto_max),
                            date_posted=auto_date,
                            location=auto_location,
                        )
                    )
                auto_gmail = st.toggle("Créer brouillons Gmail", value=False)
            auto_submitted = st.form_submit_button("Lancer autopilot", type="primary")

        if auto_submitted:
            _begin_run("autopilot")
            with st.spinner("Autopilot en cours..."):
                try:
                    report = AutopilotRunner().run(
                        query=auto_query,
                        location=auto_location or None,
                        sources=auto_sources,
                        max_per_source=int(auto_max),
                        target_drafts=int(auto_target),
                        create_gmail_drafts=auto_gmail,
                        require_quality_gate=True,
                        date_posted=auto_date,
                        serpapi_hl=SERPAPI_LANGUAGE_OPTIONS[auto_language_label],
                    )
                    data = report.to_dict()
                    st.session_state["wf_autopilot_report"] = data
                    generated = [
                        int(a["application_id"])
                        for a in data.get("applications", [])
                        if a.get("application_id")
                    ]
                    if generated:
                        st.session_state["wf_generated_app_ids"] = generated
                    _end_run(
                        f"Autopilot : {data['productive_outputs']} sortie(s), "
                        f"{data['draft_created']} brouillon(s), "
                        f"{data['quality_rejected']} rejet(s) qualité."
                    )
                    st.success(st.session_state["wf_last_run_summary"])
                    if generated:
                        st.session_state["wf_step"] = 5
                        st.rerun()
                except Exception as e:
                    _end_run("Autopilot interrompu par erreur.")
                    st.error(f"Autopilot : {e}")

        if st.session_state.get("wf_autopilot_report"):
            with st.expander("Dernier rapport autopilot", expanded=False):
                st.json(st.session_state["wf_autopilot_report"])

    st.divider()

    if "submitted" not in locals():
        submitted = False

    if submitted:
        _begin_run("recherche")
        try:
            if not sources:
                st.error("Choisis au moins une source.")
            else:
                all_ids: list[int] = []
                p = pipeline_singleton()
                progress = st.progress(0.0, text="Préparation de la recherche...")
                for i, src in enumerate(sources, start=1):
                    if _stop_requested():
                        st.warning("Recherche arrêtée avant la source suivante.")
                        break
                    progress.progress((i - 1) / len(sources), text=f"Recherche sur {src}...")
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
                                **kwargs,
                            )
                            summary_bits = [f"{report.inserted} nouvelle(s)"]
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
                            if source_progress is not None:
                                source_progress.progress(
                                    1.0,
                                    text=f"WTTJ: terminé · {report.fetched} offre(s) collectée(s)",
                                )
                            all_ids.extend(report.job_ids)
                        except Exception as e:
                            st.error(f"{src} : {e}")
                progress.progress(1.0, text="Filtre local automatique...")
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
                _end_run(f"Recherche terminée : {len(all_ids)} offre(s) candidate(s).")
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
