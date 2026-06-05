"""Interactive workflow: Fetch → Score → Analyze → Generate → Send.

Streamlit single-page wizard that walks the user through one full
job-application loop. The state is held in ``st.session_state`` so each
interaction reruns cheaply.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    SERPAPI_LANGUAGE_OPTIONS,
    apply_app_style,
    pipeline_singleton,
    status_label,
)
from smartapply.config import get_settings
from smartapply.database import session_scope
from smartapply.database.models import Application, Job, JobStatus
from smartapply.database.repository import (
    list_pending_processing,
    update_application_tracking,
    upsert_document,
)
from smartapply.jobsearch import AutopilotRunner
from smartapply.pipeline.pipeline import freshness_kwargs
from smartapply.scrapers import SERPAPI_DATE_POSTED_LABELS

# ============================================================
# Page setup
# ============================================================


st.set_page_config(
    page_title="Workflow | SmartApply",
    page_icon="🧭",
    layout="wide",
)
apply_app_style()
settings = get_settings()

st.title("🧭 Workflow guidé")
st.caption(
    "Recherche → Scoring → Analyse IA → Génération CV/email → Envoi Gmail. "
    "À chaque étape tu peux désélectionner ce qui ne t'intéresse pas."
)

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
    "wf_generated_app_ids": [],
    "wf_running": None,
    "wf_stop_requested": False,
    "wf_last_run_summary": None,
    "wf_search_text": "",
    "wf_hide_low_signal": True,
    "wf_autopilot_report": None,
}
for key, default in DEFAULTS.items():
    st.session_state.setdefault(key, default)


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
    return {
        "pending": len(pending_jobs),
        "analyzed": sum(1 for j in jobs if j.status == JobStatus.ANALYZED),
        "archived": sum(1 for j in jobs if j.status == JobStatus.ARCHIVED),
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


def _status_pill(label: str, kind: str = "blue") -> str:
    cls = {
        "good": "sa-pill-good",
        "warn": "sa-pill-warn",
        "bad": "sa-pill-bad",
        "blue": "sa-pill-blue",
    }.get(kind, "sa-pill-blue")
    return f"<span class='sa-pill {cls}'>{label}</span>"


# ============================================================
# Stepper
# ============================================================


def render_stepper() -> None:
    counts = _workflow_counts()
    st.markdown(
        """
        <div class="sa-hero">
          <h2>SmartApply Command Center</h2>
          <div class="sa-muted">Un flux fluide pour chercher, scorer, analyser, générer, vérifier et préparer tes candidatures sans perdre le contrôle.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("À trier", counts["pending"])
    m2.metric("Analysées", counts["analyzed"])
    m3.metric("Prêtes", counts["ready"])
    m4.metric("Brouillons", counts["drafts"])
    m5.metric("Rejetées", counts["archived"])

    if st.session_state.get("wf_last_run_summary"):
        st.caption(f"Dernier résultat : {st.session_state['wf_last_run_summary']}")
    _request_stop_button("wf_global_stop")

    steps = [
        ("1", "Fetch", "Chercher et choisir"),
        ("2", "Scoring", "Ranker et shortlister"),
        ("3", "Analyse", "IA sur sélection"),
        ("4", "Génération", "CV, lettre, email"),
        ("5", "Finalisation", "Gmail ou formulaire"),
    ]
    cols = st.columns(len(steps))
    current = st.session_state["wf_step"]
    for col, (n, label, desc) in zip(cols, steps, strict=True):
        i = int(n)
        state_cls = "sa-step-active" if i == current else "sa-step-done" if i < current else ""
        with col:
            st.markdown(
                f"""
                <div class="sa-step {state_cls}">
                  <div class="sa-step-num">{'✓' if i < current else n}</div>
                  <div>
                    <div class="sa-step-title">{label}</div>
                    <div class="sa-step-caption">{desc}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                f"Aller étape {i}",
                key=f"wf_goto_{i}",
                width="stretch",
                type="primary" if i == current else "secondary",
            ):
                st.session_state["wf_step"] = i
                st.rerun()


render_stepper()
st.divider()


# ============================================================
# Helpers
# ============================================================


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


def _filter_table(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if df.empty or not query.strip():
        return df
    needle = query.strip().lower()
    searchable_cols = [
        "title",
        "company",
        "location",
        "contract",
        "source",
        "phase",
        "status",
        "preview",
        "reasons",
        "risks",
        "domain",
        "seniority",
        "company_size",
        "lang",
        "strategy",
        "contact",
    ]
    cols = [c for c in searchable_cols if c in df]
    mask = pd.Series(False, index=df.index)
    for col in cols:
        mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(
            needle,
            regex=False,
        )
    return df[mask]


def _render_compact_job_cards(df: pd.DataFrame, selected_ids: list[int]) -> None:
    if df.empty:
        return
    selected_set = set(selected_ids)
    with st.expander("Vue synthétique des offres sélectionnées", expanded=False):
        for _, row in df[df["id"].isin(selected_set)].head(8).iterrows():
            st.markdown(
                f"""
                <div class="sa-panel">
                  <div style="display:flex;justify-content:space-between;gap:.75rem;align-items:flex-start;">
                    <div>
                      <strong>{row['title']}</strong><br>
                      <span class="sa-muted">{row['company']} · {row['location'] or '—'}</span>
                    </div>
                    {_status_pill(str(row.get('phase') or row.get('source') or 'offre'), 'blue')}
                  </div>
                  <div class="sa-muted" style="margin-top:.45rem;">{row.get('preview', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


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


def _sync_keep_state(df: pd.DataFrame) -> None:
    if df.empty or not {"id", "keep"}.issubset(df.columns):
        return
    keep_updates = {
        int(row["id"]): bool(row["keep"])
        for _, row in df[["id", "keep"]].iterrows()
    }
    st.session_state["wf_keep_map"] = {
        **st.session_state.get("wf_keep_map", {}),
        **keep_updates,
    }


def _kept_ids_from_full_df(df: pd.DataFrame) -> list[int]:
    if df.empty or "id" not in df.columns:
        return []
    keep_map = st.session_state.get("wf_keep_map", {})
    return [
        int(row["id"])
        for _, row in df.iterrows()
        if bool(keep_map.get(int(row["id"]), bool(row.get("keep", True))))
    ]


def _existing_generated_application_ids(limit: int = 50) -> list[int]:
    with session_scope() as s:
        apps = s.query(Application).order_by(Application.updated_at.desc()).limit(limit).all()
        return [
            int(app.id)
            for app in apps
            if app.cv_pdf_path
            or app.cv_docx_path
            or app.email_body
            or app.status
            in {
                JobStatus.EMAIL_GENERATED,
                JobStatus.READY_FOR_FORM_SUBMISSION,
                JobStatus.DRAFT_CREATED,
                JobStatus.CONTACT_MISSING,
            }
        ]


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


def _render_pdf(pdf_path: str, height: int = 600) -> None:
    """Embed a PDF as a base64 iframe. Falls back gracefully if browser blocks it."""
    path = Path(pdf_path)
    if not path.exists():
        st.warning(f"PDF introuvable : {pdf_path}")
        return
    pdf_bytes = path.read_bytes()
    b64 = base64.b64encode(pdf_bytes).decode()
    st.markdown(
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}px" style="border: 1px solid #ddd; border-radius: 6px;">'
        f"</iframe>",
        unsafe_allow_html=True,
    )


def _download_button(label: str, path: str | None, mime: str, key: str) -> None:
    if not path:
        return
    p = Path(path)
    if not p.exists():
        return
    st.download_button(
        label,
        p.read_bytes(),
        file_name=p.name,
        mime=mime,
        key=key,
    )


# ============================================================
# STEP 1 — Fetch
# ============================================================


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
                    options=["serpapi", "francetravail"],
                    default=["serpapi", "francetravail"],
                    help="SerpApi consomme un crédit par page. France Travail est gratuit.",
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
                    options=["serpapi", "francetravail", "manual"],
                    default=["serpapi", "francetravail"],
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
                            report = p.ingest(
                                src,
                                query,
                                location,
                                max_results=max_per_source,
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

    st.markdown(
        f"{_status_pill(str(len(full_kept_ids)) + ' gardée(s)', 'good')} "
        f"{_status_pill(str(len(df) - len(full_kept_ids)) + ' retirée(s)', 'warn')}",
        unsafe_allow_html=True,
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
    if not ids_to_score:
        pending_df = _pending_jobs_df(
            keep_map=st.session_state.get("wf_keep_map", {}),
            recent_ids=st.session_state.get("wf_fetched_ids", []),
        )
        if pending_df.empty:
            ranked_resume = _ranked_jobs_df(st.session_state.get("wf_ranked_ids") or None)
            if ranked_resume.empty:
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

    if ids_to_score:
        s1, s2, s3 = st.columns(3)
        s1.metric("À scorer", len(ids_to_score))
        s2.metric("Top-K défaut", settings.top_k_ranked)
        s3.metric("Embeddings", settings.openai_model_embed)
        override_ids = sorted(_filter_override_ids().intersection(ids_to_score))
        if override_ids:
            st.caption(
                f"{len(override_ids)} offre(s) réactivée(s) manuellement peuvent passer le filtre local."
            )

        default_top = min(settings.top_k_ranked, len(ids_to_score))
        top_k_ranked = st.number_input(
            "Préselection automatique pour analyse",
            min_value=1,
            max_value=max(1, len(ids_to_score)),
            value=max(1, default_top),
            help="Après le scoring, ces top offres seront cochées par défaut. Tu peux ajuster manuellement avant l'analyse.",
            key="wf_step2_top_k_ranked",
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

    st.write("**Shortlist scorée.** Coche uniquement les offres à envoyer à l'analyse IA.")
    rank_search = st.text_input(
        "Rechercher dans la shortlist scorée",
        placeholder="Entreprise, poste, ville, raison, score...",
        key="wf_step2_rank_search",
    )
    visible_ranked_df = _filter_table(ranked_df, rank_search)
    edited = st.data_editor(
        visible_ranked_df,
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
        key="wf_step2_ranked_editor",
    )
    _sync_analysis_keep_state(edited)
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


def step3_analyze() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 3 · Analyse IA</h3>
          <div class="sa-muted">Analyse uniquement les offres cochées après le scoring. Rien n'est envoyé automatiquement.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ids_to_analyze = st.session_state["wf_selected_for_analysis"]
    resume_mode = False
    analysis_attempted = False
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

    run_analysis = False
    if not resume_mode:
        run_col, stop_col = st.columns([2, 1])
        with run_col:
            run_analysis = st.button("Lancer l'analyse IA", type="primary", width="stretch")
        with stop_col:
            if st.button("Arrêter", key="wf_stop_analysis", width="stretch"):
                st.session_state["wf_stop_requested"] = True
    else:
        if st.button("Analyser une nouvelle shortlist", key="wf_step3_new_score"):
            st.session_state["wf_step"] = 2
            st.rerun()

    if run_analysis:
        analysis_attempted = True
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

    st.write(f"**{len(analyzed_ids)} offre(s) analysée(s).** Sélectionne celles pour lesquelles tu veux générer une candidature :")

    # Build a richer view with LLM analysis data
    df = _analyzed_jobs_df(analyzed_ids)

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
    _sync_keep_state(edited)
    selected = _kept_ids_from_full_df(df)

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


def step4_generate() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 4 · Génération des candidatures</h3>
          <div class="sa-muted">Le système génère un CV PDF/DOCX, une lettre et un email. Tu peux ajouter un contact manuel et arrêter proprement entre deux offres.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    seed_ids = list(st.session_state["wf_selected_for_apply"])
    resume_df = _analyzed_jobs_df(seed_ids or None)
    if resume_df.empty:
        st.warning("Aucune offre sélectionnée et aucune offre analysée disponible pour génération.")
        col_back, col_analyze = st.columns(2)
        with col_back:
            if st.button("Retourner au scoring", key="wf_step4_empty_score"):
                st.session_state["wf_step"] = 2
                st.rerun()
        with col_analyze:
            if st.button("Voir l'analyse", key="wf_step4_empty_analyze"):
                st.session_state["wf_step"] = 3
                st.rerun()
        return

    st.info(
        "Sélectionne les offres à générer. Le contact manuel est optionnel : si tu le renseignes, l'EML/Gmail utilisera cet email."
    )
    resume_search = st.text_input(
        "Rechercher dans les offres analysées",
        placeholder="Entreprise, poste, domaine, compétence...",
        key="wf_step3_resume_search",
    )
    visible_resume_df = _filter_table(
        resume_df.rename(columns={"reasons": "preview"}),
        resume_search,
    )
    if "preview" in visible_resume_df.columns:
        visible_resume_df = visible_resume_df.rename(columns={"preview": "reasons"})
    edited_resume = st.data_editor(
        visible_resume_df,
        column_config={
            "keep": st.column_config.CheckboxColumn("Générer", default=True),
            "id": st.column_config.NumberColumn("id", disabled=True, width="small"),
            "title": st.column_config.TextColumn("Titre", disabled=True, width="large"),
            "company": st.column_config.TextColumn("Entreprise", disabled=True, width="medium"),
            "score": st.column_config.NumberColumn(
                "Score", disabled=True, format="%.3f", width="small"
            ),
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
        key="wf_step3_resume_editor",
    )
    _sync_manual_contacts(edited_resume)
    _sync_keep_state(edited_resume)
    ids = _kept_ids_from_full_df(resume_df)
    st.session_state["wf_selected_for_apply"] = ids
    if not ids:
        st.warning("Sélectionne au moins une offre analysée pour générer une candidature.")
        return

    g1, g2, g3 = st.columns(3)
    g1.metric("À générer", len(ids))
    g2.metric("Déjà générées", len(st.session_state.get("wf_generated_app_ids", [])))
    g3.metric("Mode", "Manuel contrôlé")

    c_run, c_stop = st.columns([2, 1])
    with c_run:
        run_generation = st.button("Générer les candidatures", type="primary", width="stretch")
    with c_stop:
        if st.button("Arrêter", key="wf_stop_generation", width="stretch"):
            st.session_state["wf_stop_requested"] = True

    if run_generation:
        _begin_run("génération")
        progress = st.progress(0.0, text="Démarrage...")
        generated_ids: list[int] = []
        p = pipeline_singleton()
        manual_contacts = st.session_state.get("wf_manual_contacts", {})
        for i, job_id in enumerate(ids, start=1):
            if _stop_requested():
                st.warning("Génération arrêtée avant la candidature suivante.")
                break
            progress.progress(
                i / len(ids),
                text=f"Candidature {i}/{len(ids)} (job_id={job_id})...",
            )
            try:
                report = p.apply_to(
                    job_id,
                    contact_email=manual_contacts.get(int(job_id)),
                    create_gmail_draft=False,
                )
                if report.application_id:
                    generated_ids.append(report.application_id)
            except Exception as e:
                st.error(f"Job {job_id} : {e}")
        progress.empty()
        st.success(f"{len(generated_ids)} candidature(s) générée(s)")
        st.session_state["wf_generated_app_ids"] = generated_ids
        _end_run(f"Génération : {len(generated_ids)} candidature(s).")

    st.divider()

    app_ids = st.session_state["wf_generated_app_ids"]
    if not app_ids:
        st.info("Lance la génération ci-dessus.")
        return

    # ---- Application picker ----
    st.markdown("### Prévisualisation et contrôle")
    with session_scope() as s:
        apps_rows = []
        for app in s.query(Application).filter(Application.id.in_(app_ids)).all():
            apps_rows.append(
                {
                    "id": app.id,
                    "status": status_label(app.status),
                    "strategy": app.application_strategy,
                    "contact": app.contact.email if app.contact else "—",
                    "label": (
                        f"[{app.id}] {app.job.company} — {app.job.title} "
                        f"({app.application_strategy})"
                    ),
                }
            )
    if not apps_rows:
        st.warning("Pas de candidature trouvée.")
        return

    apps_df = pd.DataFrame(apps_rows)
    st.dataframe(
        apps_df[["id", "status", "strategy", "contact"]],
        hide_index=True,
        width="stretch",
    )
    choice = st.selectbox(
        "Candidature",
        options=[r["id"] for r in apps_rows],
        format_func=lambda i: next(r["label"] for r in apps_rows if r["id"] == i),
    )

    _render_application_detail(choice)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("⬅ Retour à l'étape 3", key="wf_step4_back_analysis"):
            st.session_state["wf_step"] = 3
            st.rerun()
    with col_next:
        if st.button(
            "Passer à l'étape 5 : envoi Gmail",
            type="primary",
            key="wf_step4_next_send",
        ):
            st.session_state["wf_step"] = 5
            st.rerun()


def _render_application_detail(application_id: int) -> None:
    with session_scope() as s:
        app = s.get(Application, application_id)
        if app is None:
            st.error("Candidature introuvable.")
            return
        docs = {doc.doc_type: doc for doc in app.documents}
        letter_doc = docs.get("motivation_letter")
        letter_extra = letter_doc.extra if letter_doc and isinstance(letter_doc.extra, dict) else {}
        data = {
            "job_title": app.job.title,
            "job_company": app.job.company,
            "job_url": app.job.application_url or "",
            "status": app.status,
            "strategy": app.application_strategy,
            "contact_email": app.contact.email if app.contact else None,
            "contact_full_name": app.contact.full_name if app.contact else None,
            "contact_job_title": app.contact.job_title if app.contact else None,
            "contact_location_hint": app.contact.location_hint if app.contact else None,
            "contact_reason": app.contact.decision_reason if app.contact else None,
            "contact_confidence": app.contact.confidence if app.contact else None,
            "form_url": app.form_submission_url,
            "email_cc": app.email_cc,
            "email_subject": app.email_subject or "",
            "email_body": app.email_body or "",
            "motivation_letter_subject": letter_extra.get("subject", ""),
            "motivation_letter_body": letter_doc.content if letter_doc else "",
            "cv_pdf_path": app.cv_pdf_path,
            "cv_docx_path": app.cv_docx_path,
            "validation_warnings": app.validation_warnings or [],
            "notes": app.notes,
        }
        letter_pdf = docs.get("motivation_letter_pdf")
        letter_pdf_path = letter_pdf.path if letter_pdf else None

    # ---- Header ----
    st.markdown(f"### {data['job_title']} @ {data['job_company']}")
    strat_label = {
        "email_only": "📧 Email suffit",
        "email_and_form": "📧 + 🗂 Email **et** formulaire ATS",
        "form_only": "🗂 Formulaire ATS uniquement",
    }.get(data["strategy"], data["strategy"])
    st.markdown(f"**Stratégie** : {strat_label}")
    if data["contact_email"]:
        st.markdown(f"**Contact RH** : `{data['contact_email']}`")
        contact_bits = [
            data.get("contact_full_name"),
            data.get("contact_job_title"),
            f"raison={data.get('contact_reason')}" if data.get("contact_reason") else None,
            f"lieu={data.get('contact_location_hint')}" if data.get("contact_location_hint") else None,
            (
                f"score={float(data['contact_confidence']):.2f}"
                if data.get("contact_confidence") is not None
                else None
            ),
        ]
        contact_summary = " · ".join(str(bit) for bit in contact_bits if bit)
        if contact_summary:
            st.caption(contact_summary)
        if data.get("email_cc"):
            st.markdown(f"**CC** : `{data['email_cc']}`")
    else:
        st.warning("Pas de contact email trouvé.")
    if data["form_url"]:
        st.markdown(f"**URL formulaire** : {data['form_url']}")

    if data["validation_warnings"]:
        with st.expander(f"⚠️ {len(data['validation_warnings'])} warning(s) anti-hallucination"):
            for w in data["validation_warnings"]:
                st.write(f"- {w}")

    # ---- Tabs: CV PDF / Lettre PDF / Email ----
    tab_cv, tab_letter, tab_email = st.tabs(["📄 CV", "✉️ Lettre de motivation", "📧 Email"])

    with tab_cv:
        if data["cv_pdf_path"]:
            _render_pdf(data["cv_pdf_path"], height=700)
            col1, col2 = st.columns(2)
            with col1:
                _download_button(
                    "⬇ Télécharger PDF",
                    data["cv_pdf_path"],
                    "application/pdf",
                    f"cv_pdf_{application_id}",
                )
            with col2:
                _download_button(
                    "⬇ Télécharger DOCX",
                    data["cv_docx_path"],
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    f"cv_docx_{application_id}",
                )
        else:
            st.warning("PDF du CV introuvable.")

    with tab_letter:
        if letter_pdf_path:
            _render_pdf(letter_pdf_path, height=700)
            _download_button(
                "⬇ Télécharger PDF",
                letter_pdf_path,
                "application/pdf",
                f"letter_pdf_{application_id}",
            )
            if data["motivation_letter_body"]:
                with st.expander("Texte brut de la lettre"):
                    if data["motivation_letter_subject"]:
                        st.markdown(f"**Sujet** : {data['motivation_letter_subject']}")
                    st.text_area(
                        "Corps",
                        data["motivation_letter_body"],
                        height=300,
                        disabled=True,
                        key=f"wf_letter_body_{application_id}",
                    )
        else:
            st.info("Pas de PDF de lettre de motivation.")
            st.text_area(
                "Corps (texte brut)",
                data["motivation_letter_body"],
                height=300,
                disabled=True,
                key=f"wf_letter_fallback_{application_id}",
            )

    with tab_email:
        st.markdown(f"**Sujet** : {data['email_subject']}")
        st.text_area(
            "Corps de l'email",
            data["email_body"],
            height=420,
            disabled=True,
            key=f"wf_email_body_{application_id}",
        )


# ============================================================
# STEP 5 — Send
# ============================================================


def step5_send() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 5 · Finalisation Gmail et formulaires</h3>
          <div class="sa-muted">Dernier contrôle avant action : ajuste l'email, vérifie les pièces jointes, crée les brouillons Gmail ou marque les formulaires soumis.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    app_ids = st.session_state["wf_generated_app_ids"]
    if not app_ids:
        app_ids = _existing_generated_application_ids()
        if not app_ids:
            st.warning("Aucune candidature générée. Retourne à l'étape 4.")
            return
        st.session_state["wf_generated_app_ids"] = app_ids
        st.info(
            "Mode reprise : j'affiche les candidatures déjà générées en base."
        )

    with session_scope() as s:
        apps = s.query(Application).filter(Application.id.in_(app_ids)).all()
        # Pull out the data we need into plain dicts to avoid using detached
        # SQLAlchemy objects after the session closes.
        rows = []
        for app in apps:
            docs = {doc.doc_type: doc for doc in app.documents}
            letter_pdf = docs.get("motivation_letter_pdf")
            rows.append(
                {
                    "id": app.id,
                    "title": app.job.title,
                    "company": app.job.company,
                    "status": app.status,
                    "status_label": status_label(app.status),
                    "strategy": app.application_strategy,
                    "contact": app.contact.email if app.contact else None,
                    "contact_full_name": app.contact.full_name if app.contact else None,
                    "contact_job_title": app.contact.job_title if app.contact else None,
                    "contact_location_hint": app.contact.location_hint if app.contact else None,
                    "contact_reason": app.contact.decision_reason if app.contact else None,
                    "contact_confidence": app.contact.confidence if app.contact else None,
                    "email_cc": app.email_cc,
                    "subject": app.email_subject or "",
                    "body": app.email_body or "",
                    "cv_pdf_path": app.cv_pdf_path,
                    "cv_docx_path": app.cv_docx_path,
                    "eml_path": app.eml_path,
                    "letter_pdf_path": letter_pdf.path if letter_pdf else None,
                    "form_url": app.form_submission_url,
                    "gmail_draft_id": app.gmail_draft_id,
                    "email_sent_at": app.email_sent_at,
                    "form_submitted_at": app.form_submitted_at,
                    "validation_warnings": app.validation_warnings or [],
                }
            )

    if not rows:
        st.info("Pas de candidature à envoyer.")
        return

    drafts_done = sum(1 for row in rows if row["gmail_draft_id"])
    with_contact = sum(1 for row in rows if row["contact"])
    with_form = sum(1 for row in rows if row["form_url"])
    sent_done = sum(1 for row in rows if row["email_sent_at"] or row["form_submitted_at"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Candidatures", len(rows))
    m2.metric("Contacts trouvés", with_contact)
    m3.metric("Formulaires", with_form)
    m4.metric("Actions faites", drafts_done + sent_done)

    summary_df = pd.DataFrame(
        [
            {
                "id": row["id"],
                "company": row["company"],
                "title": row["title"],
                "strategy": row["strategy"],
                "contact": row["contact"] or "—",
                "gmail": "créé" if row["gmail_draft_id"] else "à faire",
                "form": "soumis" if row["form_submitted_at"] else ("à faire" if row["form_url"] else "—"),
                "status": row["status_label"],
            }
            for row in rows
        ]
    )
    st.dataframe(summary_df, hide_index=True, width="stretch")

    st.caption(
        "Rien n'est envoyé automatiquement. Le bouton Gmail crée seulement un brouillon, après validation manuelle."
    )
    for row in rows:
        _render_send_card(row)

    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("⬅ Retour à l'étape 4", key="wf_step5_back", width="stretch"):
            st.session_state["wf_step"] = 4
            st.rerun()
    with col_reset:
        if st.button("🔄 Nouveau workflow", key="wf_reset", width="stretch"):
            reset_workflow()
            st.rerun()

    st.divider()


def _render_send_card(row: dict[str, Any]) -> None:
    app_id = row["id"]
    strategy_icon = {
        "email_only": "📧",
        "email_and_form": "📧🗂",
        "form_only": "🗂",
    }.get(row["strategy"], "")
    expanded_default = row["status"] != JobStatus.SENT
    with st.expander(
        f"{strategy_icon} [{app_id}] {row['title']} @ {row['company']}  ·  {row['status_label']}",
        expanded=expanded_default,
    ):
        subject_key = f"wf_final_subject_{app_id}"
        body_key = f"wf_final_body_{app_id}"
        st.session_state.setdefault(subject_key, row["subject"])
        st.session_state.setdefault(body_key, row["body"])

        col1, col2 = st.columns([2, 1])
        with col1:
            status_kind = "good" if row["gmail_draft_id"] or row["email_sent_at"] else "warn"
            st.markdown(
                f"{_status_pill(str(row['strategy']), 'blue')} "
                f"{_status_pill(str(row['status_label']), status_kind)}",
                unsafe_allow_html=True,
            )
            st.markdown(f"**Contact** : `{row['contact'] or '— aucun —'}`")
            contact_bits = [
                row.get("contact_full_name"),
                row.get("contact_job_title"),
                f"raison={row.get('contact_reason')}" if row.get("contact_reason") else None,
                f"lieu={row.get('contact_location_hint')}" if row.get("contact_location_hint") else None,
                (
                    f"score={float(row['contact_confidence']):.2f}"
                    if row.get("contact_confidence") is not None
                    else None
                ),
            ]
            contact_summary = " · ".join(str(bit) for bit in contact_bits if bit)
            if contact_summary:
                st.caption(contact_summary)
            if row.get("email_cc"):
                st.markdown(f"**CC** : `{row['email_cc']}`")
            if row["form_url"]:
                st.link_button("Ouvrir le formulaire ATS", row["form_url"], width="stretch")
            if row["validation_warnings"]:
                with st.expander(
                    f"Warnings validation CV ({len(row['validation_warnings'])})",
                    expanded=False,
                ):
                    for warning in row["validation_warnings"]:
                        st.write(f"- {warning}")

            st.markdown("**Documents finaux**")
            doc_cols = st.columns(3)
            with doc_cols[0]:
                _download_button(
                    "CV PDF",
                    row.get("cv_pdf_path"),
                    "application/pdf",
                    f"wf_send_cv_pdf_{app_id}",
                )
            with doc_cols[1]:
                _download_button(
                    "CV DOCX",
                    row.get("cv_docx_path"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    f"wf_send_cv_docx_{app_id}",
                )
            with doc_cols[2]:
                _download_button(
                    "Lettre PDF",
                    row.get("letter_pdf_path"),
                    "application/pdf",
                    f"wf_send_letter_pdf_{app_id}",
                )

            st.text_input("Sujet final", key=subject_key)
            st.text_area(
                "Email final",
                height=240,
                key=body_key,
            )
            if st.button(
                "Recharger l'email généré",
                key=f"wf_reset_email_{app_id}",
            ):
                st.session_state[subject_key] = row["subject"]
                st.session_state[body_key] = row["body"]
                st.rerun()
        with col2:
            reviewed = st.checkbox(
                "J'ai vérifié le contact, le CV, la lettre et l'email",
                key=f"wf_reviewed_{app_id}",
            )
            final_subject = str(st.session_state.get(subject_key, "")).strip()
            final_body = str(st.session_state.get(body_key, "")).strip()

            # ---- Gmail draft button ----
            if row["gmail_draft_id"]:
                st.success(f"✓ Brouillon Gmail : `{row['gmail_draft_id']}`")
            else:
                disabled = (
                    not row["contact"]
                    or row["strategy"] == "form_only"
                    or not reviewed
                    or not final_subject
                    or not final_body
                )
                if st.button(
                    "📧 Créer le brouillon Gmail",
                    disabled=disabled,
                    key=f"wf_gmail_{app_id}",
                    type="primary",
                ):
                    _create_gmail_draft(
                        {
                            **row,
                            "subject": final_subject,
                            "body": final_body,
                        }
                    )
                    st.rerun()
                if row["strategy"] == "form_only":
                    st.caption("Stratégie formulaire uniquement.")
                elif not row["contact"]:
                    st.caption("Pas de contact → soumets via le formulaire.")
                elif not reviewed:
                    st.caption("Coche la validation finale avant Gmail.")
                elif not final_subject or not final_body:
                    st.caption("Sujet et email final obligatoires.")

            st.divider()

            # ---- Manual tracking buttons ----
            if row["email_sent_at"]:
                st.markdown(f"✓ Email envoyé : `{row['email_sent_at'].strftime('%d/%m %H:%M')}`")
            else:
                if st.button(
                    "✉ Marquer email envoyé",
                    key=f"wf_mark_email_{app_id}",
                    disabled=row["strategy"] == "form_only",
                ):
                    with session_scope() as s:
                        update_application_tracking(s, app_id, email_sent=True)
                    st.rerun()

            if row["strategy"] in ("email_and_form", "form_only"):
                if row["form_submitted_at"]:
                    st.markdown(
                        f"✓ Form soumis : `{row['form_submitted_at'].strftime('%d/%m %H:%M')}`"
                    )
                else:
                    if st.button(
                        "🗂 Marquer formulaire soumis",
                        key=f"wf_mark_form_{app_id}",
                    ):
                        with session_scope() as s:
                            update_application_tracking(s, app_id, form_submitted=True)
                        st.rerun()


def _create_gmail_draft(row: dict[str, Any]) -> None:
    from smartapply.email_agent import export_eml
    from smartapply.email_agent.gmail_draft import GmailDraftError, create_draft
    from smartapply.profile import get_profile

    subject = str(row.get("subject") or "").strip()
    body = str(row.get("body") or "").strip()
    recipient = str(row.get("contact") or "").strip()
    cc_recipient = str(row.get("email_cc") or "").strip() or None
    if not recipient:
        st.error("Contact email manquant.")
        return
    if not subject or not body:
        st.error("Sujet et corps de mail obligatoires.")
        return

    sender = get_profile().identity.email
    attachments = [
        p
        for p in (
            row.get("cv_pdf_path"),
            row.get("cv_docx_path"),
            row.get("letter_pdf_path"),
        )
        if p and Path(p).exists()
    ]

    eml_path = row.get("eml_path")
    if eml_path:
        try:
            export_eml(
                subject=subject,
                body=body,
                sender=sender,
                recipient=recipient,
                cc_recipient=cc_recipient,
                attachments=attachments,
                out_path=eml_path,
            )
        except Exception as e:
            st.warning(f"Email .eml non régénéré : {e}")

    with session_scope() as s:
        app = s.get(Application, row["id"])
        if app is not None:
            app.email_subject = subject
            app.email_body = body
            upsert_document(
                s,
                app.id,
                doc_type="email",
                content=body,
                extra={"subject": subject},
            )
            if eml_path:
                app.eml_path = eml_path
                upsert_document(s, app.id, doc_type="eml", path=eml_path)

    try:
        draft_id = create_draft(
            subject=subject,
            body=body,
            recipient=recipient,
            cc_recipient=cc_recipient,
            sender=sender,
            attachment_paths=attachments,
        )
    except GmailDraftError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Échec Gmail : {e}")
        return

    # Persist the draft_id and bump status
    with session_scope() as s:
        app = s.get(Application, row["id"])
        if app is not None:
            app.email_subject = subject
            app.email_body = body
            app.gmail_draft_id = draft_id
            app.status = JobStatus.DRAFT_CREATED
            if app.job is not None:
                app.job.status = JobStatus.DRAFT_CREATED
    st.success(f"✓ Brouillon Gmail créé : {draft_id}")


# ============================================================
# Dispatch
# ============================================================


step = st.session_state["wf_step"]
if step == 1:
    step1_fetch()
elif step == 2:
    step2_score()
elif step == 3:
    step3_analyze()
elif step == 4:
    step4_generate()
elif step == 5:
    step5_send()
