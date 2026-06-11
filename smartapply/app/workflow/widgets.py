"""Shared Streamlit widgets for the workflow page."""

from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from smartapply.app.workflow.state import _request_stop_button, _workflow_counts


def _status_pill(label: str, kind: str = "blue") -> str:
    cls = {
        "good": "sa-pill-good",
        "warn": "sa-pill-warn",
        "bad": "sa-pill-bad",
        "blue": "sa-pill-blue",
        "neutral": "sa-pill-neutral",
        "purple": "sa-pill-purple",
    }.get(kind, "sa-pill-blue")
    return f"<span class='sa-pill {cls}'>{escape(str(label))}</span>"


def _render_action_strip(
    *,
    kicker: str,
    title: str,
    message: str,
    badges: list[tuple[str, str]] | None = None,
) -> None:
    badge_html = ""
    if badges:
        badge_html = (
            "<div class='sa-pill-row'>"
            + "".join(_status_pill(label, kind) for label, kind in badges)
            + "</div>"
        )
    st.markdown(
        f"""
        <div class="sa-action-strip">
          <div>
            <div class="sa-focus-kicker">{escape(kicker)}</div>
            <strong>{escape(title)}</strong>
            <div class="sa-section-subtitle">{escape(message)}</div>
          </div>
          {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Stepper
# ============================================================


def render_stepper() -> None:
    counts = _workflow_counts()
    st.markdown(
        """
        <div class="sa-hero">
          <h2>Workflow guidé</h2>
          <div class="sa-muted">Recherche, scoring, analyse IA, génération et finalisation depuis un seul écran de contrôle.</div>
          <div class="sa-pill-row">
            <span class="sa-pill sa-pill-good">Chaque étape est indépendante</span>
            <span class="sa-pill sa-pill-blue">Sélections modifiables</span>
            <span class="sa-pill sa-pill-neutral">Aucun envoi automatique</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("À trier", counts["pending"])
    m2.metric("Analysées", counts["analyzed"])
    m3.metric("Prêtes", counts["ready"])
    m4.metric("Brouillons", counts["drafts"])
    m5.metric("Filtre/Doublons", counts["filter_rejected"])

    if st.session_state.get("wf_last_run_summary"):
        st.caption(f"Dernier résultat : {st.session_state['wf_last_run_summary']}")
    _request_stop_button("wf_global_stop")

    steps = [
        ("1", "Fetch", "Chercher et choisir"),
        ("2", "Scoring", "Ranker et shortlister"),
        ("3", "Analyse", "IA sur sélection"),
        ("4", "Génération", "CV, lettre, email, contact"),
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

# ============================================================
# Helpers
# ============================================================


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
        "reason",
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


_SORTABLE_COLUMN_LABELS = {
    "include": "Sélection",
    "restore": "Réactiver",
    "keep": "Garder",
    "analyze": "Analyser",
    "lookup_contact": "Chercher contact",
    "id": "id",
    "new": "New",
    "title": "Titre",
    "company": "Entreprise",
    "location": "Lieu",
    "contract": "Contrat",
    "source": "Source",
    "phase": "Phase",
    "status": "Statut",
    "score": "Score",
    "semantic": "Sémantique",
    "skills": "Skills",
    "seniority_score": "Seniorité score",
    "location_score": "Lieu score",
    "seniority": "Seniority",
    "company_size": "Taille entreprise",
    "lang": "Langue",
    "manual_contact": "Contact manuel",
    "domain": "Domaine",
    "strategy": "Stratégie",
    "contact": "Contact",
    "gmail": "Gmail",
    "form": "Formulaire",
    "reason": "Raison",
    "reasons": "Raisons",
    "risks": "Risques",
}


def _sort_table(
    df: pd.DataFrame,
    *,
    state_prefix: str,
    default_sort: str = "score",
    default_desc: bool = True,
) -> pd.DataFrame:
    if df.empty:
        return df

    options = {
        column: _SORTABLE_COLUMN_LABELS[column]
        for column in _SORTABLE_COLUMN_LABELS
        if column in df.columns
    }
    if not options:
        return df

    sort_key = f"{state_prefix}_sort_by"
    desc_key = f"{state_prefix}_sort_desc"
    default_column = default_sort if default_sort in options else next(iter(options))
    st.session_state.setdefault(sort_key, default_column)
    st.session_state.setdefault(desc_key, default_desc)
    if st.session_state.get(sort_key) not in options:
        st.session_state[sort_key] = default_column

    sort_col, order_col = st.columns([2, 1])
    with sort_col:
        selected_column = st.selectbox(
            "Trier le tableau par",
            options=list(options),
            format_func=lambda column: options[column],
            key=sort_key,
        )
    with order_col:
        descending = st.toggle("Ordre décroissant", key=desc_key)

    return df.sort_values(
        by=str(selected_column),
        ascending=not bool(descending),
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)


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
