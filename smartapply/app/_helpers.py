"""Streamlit helpers — shared by every page."""

from __future__ import annotations

from functools import lru_cache
from html import escape
from typing import Any

import pandas as pd
import streamlit as st

from smartapply.database import init_db, session_scope
from smartapply.database.models import JobStatus
from smartapply.database.repository import list_jobs, total_cost

STATUS_FLOW: list[dict[str, Any]] = [
    {
        "status": JobStatus.SCRAPED,
        "label": "Collectée",
        "description": "Offre importée depuis une source, pas encore filtrée.",
        "group": "Pipeline principal",
        "color": "#2563EB",
    },
    {
        "status": JobStatus.FILTERED,
        "label": "Filtrée",
        "description": "Le filtre local a retiré stages, doublons et hors cible.",
        "group": "Pipeline principal",
        "color": "#0891B2",
    },
    {
        "status": JobStatus.SHORTLISTED,
        "label": "Shortlistée",
        "description": "Bon score local avant analyse détaillée.",
        "group": "Pipeline principal",
        "color": "#7C3AED",
    },
    {
        "status": JobStatus.ANALYZED,
        "label": "Analysée LLM",
        "description": "Le LLM a identifié rôle, compétences, risques et matching.",
        "group": "Pipeline principal",
        "color": "#4F46E5",
    },
    {
        "status": JobStatus.CV_GENERATED,
        "label": "CV généré",
        "description": "CV adapté produit, avant finalisation email/lettre.",
        "group": "Pipeline principal",
        "color": "#059669",
    },
    {
        "status": JobStatus.EMAIL_GENERATED,
        "label": "Dossier prêt",
        "description": "CV, lettre, email et pièces jointes sont prêts à relire.",
        "group": "Pipeline principal",
        "color": "#16A34A",
    },
    {
        "status": JobStatus.DRAFT_CREATED,
        "label": "Brouillon Gmail",
        "description": "Brouillon créé dans Gmail, rien n'est envoyé automatiquement.",
        "group": "Pipeline principal",
        "color": "#0D9488",
    },
    {
        "status": JobStatus.READY_FOR_FORM_SUBMISSION,
        "label": "Formulaire prêt",
        "description": "Pas d'email fiable, dossier prêt pour soumission ATS/formulaire.",
        "group": "Pipeline principal",
        "color": "#65A30D",
    },
    {
        "status": JobStatus.SENT,
        "label": "Envoyée",
        "description": "Email envoyé ou formulaire soumis.",
        "group": "Pipeline principal",
        "color": "#0284C7",
    },
    {
        "status": JobStatus.INTERVIEW,
        "label": "Entretien",
        "description": "Candidature convertie en échange recruteur.",
        "group": "Pipeline principal",
        "color": "#9333EA",
    },
    {
        "status": JobStatus.CONTACT_MISSING,
        "label": "Contact manquant",
        "description": "Le dossier existe, mais aucun contact fiable n'a été trouvé.",
        "group": "Blocages et rejets",
        "color": "#D97706",
    },
    {
        "status": JobStatus.QUALITY_REJECTED,
        "label": "Rejet qualité",
        "description": "Le quality gate bloque la candidature.",
        "group": "Blocages et rejets",
        "color": "#DC2626",
    },
    {
        "status": JobStatus.REJECTED,
        "label": "Refusée",
        "description": "Retour négatif reçu ou candidature à abandonner.",
        "group": "Blocages et rejets",
        "color": "#B91C1C",
    },
    {
        "status": JobStatus.ARCHIVED,
        "label": "Archivée",
        "description": "Offre retirée du pipeline actif.",
        "group": "Blocages et rejets",
        "color": "#6B7280",
    },
]

STATUS_LABEL_BY_KEY = {row["status"]: row["label"] for row in STATUS_FLOW}
SERPAPI_LANGUAGE_OPTIONS = {
    "Bilingue EN + FR": "en,fr",
    "Anglais uniquement": "en",
    "Français uniquement": "fr",
}


def ensure_db() -> None:
    """Idempotent — make sure tables exist before any query."""
    init_db()


def apply_app_style() -> None:
    ensure_db()
    st.markdown(
        """
        <style>
        :root {
            --sa-bg: #F6F7FB;
            --sa-surface: #FFFFFF;
            --sa-surface-2: #F9FAFB;
            --sa-text: #111827;
            --sa-muted: #6B7280;
            --sa-border: #E5E7EB;
            --sa-primary: #2563EB;
            --sa-primary-soft: #DBEAFE;
            --sa-good: #059669;
            --sa-warn: #D97706;
            --sa-bad: #DC2626;
            --sa-ink: #172033;
        }
        .stApp,
        [data-testid="stAppViewContainer"] {
            background-color: var(--sa-bg) !important;
            color: var(--sa-text) !important;
            font-family: 'Inter', -apple-system, sans-serif;
        }
        [data-testid="stHeader"] {
            background-color: rgba(246, 247, 251, 0.88) !important;
            backdrop-filter: blur(8px);
        }
        .main .block-container {
            max-width: 1440px;
            padding-top: 1.25rem;
            padding-bottom: 3rem;
        }
        section[data-testid="stSidebar"] {
            background-color: var(--sa-surface) !important;
            color: var(--sa-text) !important;
            border-right: 1px solid var(--sa-border);
        }
        section[data-testid="stSidebar"] > div,
        section[data-testid="stSidebar"] [data-testid="stSidebarContent"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {
            background-color: var(--sa-surface) !important;
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] * {
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] a,
        section[data-testid="stSidebar"] a *,
        section[data-testid="stSidebar"] button,
        section[data-testid="stSidebar"] button *,
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] * {
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] a:hover,
        section[data-testid="stSidebar"] button:hover {
            background-color: #EEF2FF !important;
            color: var(--sa-text) !important;
        }
        section[data-testid="stSidebar"] [aria-current="page"],
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
            background-color: var(--sa-primary-soft) !important;
            color: #1D4ED8 !important;
            font-weight: 700;
        }
        section[data-testid="stSidebar"] [aria-current="page"] *,
        section[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] * {
            color: #1D4ED8 !important;
        }
        section[data-testid="stSidebar"] svg,
        section[data-testid="stSidebar"] svg path {
            fill: currentColor !important;
            color: var(--sa-text) !important;
        }
        h1, h2, h3 { color: var(--sa-ink) !important; letter-spacing: 0 !important; }
        p, li, label, span { letter-spacing: 0 !important; }
        [data-testid="stMetric"],
        .stMetric {
            background-color: var(--sa-surface) !important;
            color: var(--sa-text) !important;
            padding: 0.95rem;
            border-radius: 8px;
            border: 1px solid var(--sa-border);
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        [data-testid="stMetric"] *,
        .stMetric * {
            color: var(--sa-text) !important;
        }
        div[data-testid="stDataFrame"],
        div[data-testid="stDataEditor"] {
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            overflow: hidden;
            background: var(--sa-surface);
        }
        div[data-testid="stVegaLiteChart"] [data-testid="stElementToolbar"],
        div[data-testid="stAltairChart"] [data-testid="stElementToolbar"] {
            display: none !important;
        }
        .sa-hero {
            background: var(--sa-surface);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1.15rem 1.2rem;
            box-shadow: 0 8px 22px rgba(15, 23, 42, 0.05);
            margin-bottom: 0.85rem;
        }
        .sa-hero h1, .sa-hero h2, .sa-hero h3 {
            margin: 0 0 0.25rem 0 !important;
        }
        .sa-muted {
            color: var(--sa-muted);
            font-size: 0.92rem;
        }
        .sa-panel {
            background: var(--sa-surface);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
            margin-bottom: 0.85rem;
        }
        .sa-toolbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
            background: var(--sa-surface);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            margin: 0.65rem 0;
        }
        .sa-step {
            display: flex;
            gap: 0.65rem;
            align-items: center;
            background: var(--sa-surface);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 0.65rem 0.75rem;
            min-height: 74px;
        }
        .sa-step-active {
            border-color: #93C5FD;
            background: #EFF6FF;
        }
        .sa-step-done {
            border-color: #A7F3D0;
            background: #ECFDF5;
        }
        .sa-step-num {
            width: 2rem;
            height: 2rem;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 999px;
            background: var(--sa-primary-soft);
            color: var(--sa-primary);
            font-weight: 800;
            flex-shrink: 0;
        }
        .sa-step-title {
            font-weight: 800;
            color: var(--sa-ink);
            line-height: 1.2;
        }
        .sa-step-caption {
            color: var(--sa-muted);
            font-size: 0.82rem;
            line-height: 1.25;
        }
        .sa-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            border: 1px solid var(--sa-border);
            border-radius: 999px;
            padding: 0.18rem 0.55rem;
            font-size: 0.78rem;
            font-weight: 700;
            color: var(--sa-muted);
            background: var(--sa-surface-2);
            white-space: nowrap;
        }
        .sa-pill-good { color: #047857; background: #ECFDF5; border-color: #A7F3D0; }
        .sa-pill-warn { color: #B45309; background: #FFFBEB; border-color: #FDE68A; }
        .sa-pill-bad { color: #B91C1C; background: #FEF2F2; border-color: #FECACA; }
        .sa-pill-blue { color: #1D4ED8; background: #EFF6FF; border-color: #BFDBFE; }
        .sa-pill-neutral { color: #475569; background: #F8FAFC; border-color: #CBD5E1; }
        .sa-pill-purple { color: #6D28D9; background: #F5F3FF; border-color: #DDD6FE; }
        .sa-pill-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            align-items: center;
            margin: 0.45rem 0 0.1rem 0;
        }
        .sa-kv {
            display: grid;
            grid-template-columns: 8.5rem 1fr;
            gap: 0.35rem 0.75rem;
            font-size: 0.92rem;
        }
        .sa-kv-label { color: var(--sa-muted); }
        .sa-kv-value { color: var(--sa-text); font-weight: 650; }
        .sa-box-title {
            margin: 0 0 0.25rem 0;
            color: var(--sa-ink);
            font-weight: 800;
            font-size: 0.98rem;
        }
        .sa-box-message {
            color: var(--sa-muted);
            font-size: 0.9rem;
            line-height: 1.42;
        }
        .sa-runbar {
            border: 1px solid #BFDBFE;
            background: #EFF6FF;
            color: #1E3A8A;
            border-radius: 8px;
            padding: 0.75rem 0.9rem;
            margin: 0.75rem 0;
        }
        .sa-danger {
            border-color: #FECACA;
            background: #FEF2F2;
            color: #991B1B;
        }
        .sa-warning {
            border-color: #FDE68A;
            background: #FFFBEB;
            color: #92400E;
        }
        .sa-success {
            border-color: #A7F3D0;
            background: #ECFDF5;
            color: #065F46;
        }
        .sa-command-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 0.85rem;
            margin: 0.85rem 0;
        }
        .sa-action-card {
            background: var(--sa-surface);
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            padding: 1rem;
            min-height: 138px;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
        }
        .sa-action-card h4 {
            margin: 0 0 0.35rem 0;
            color: var(--sa-ink);
            font-size: 1rem;
        }
        .sa-action-card p {
            margin: 0;
            color: var(--sa-muted);
            font-size: 0.9rem;
            line-height: 1.35;
        }
        .sa-inline-actions {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            align-items: center;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_status_badge(label: str, kind: str = "blue") -> str:
    """Return a compact safe HTML badge."""
    cls = {
        "good": "sa-pill-good",
        "success": "sa-pill-good",
        "warn": "sa-pill-warn",
        "warning": "sa-pill-warn",
        "bad": "sa-pill-bad",
        "danger": "sa-pill-bad",
        "blue": "sa-pill-blue",
        "info": "sa-pill-blue",
        "purple": "sa-pill-purple",
        "neutral": "sa-pill-neutral",
    }.get(kind, "sa-pill-blue")
    return f"<span class='sa-pill {cls}'>{escape(str(label))}</span>"


def render_badge_row(badges: list[tuple[str, str]]) -> None:
    if not badges:
        return
    html = "".join(render_status_badge(label, kind) for label, kind in badges)
    st.markdown(f"<div class='sa-pill-row'>{html}</div>", unsafe_allow_html=True)


def render_page_header(
    title: str,
    subtitle: str,
    *,
    icon: str | None = None,
    badges: list[tuple[str, str]] | None = None,
) -> None:
    heading = f"{escape(icon)} {escape(title)}" if icon else escape(title)
    badge_html = ""
    if badges:
        badge_html = (
            "<div class='sa-pill-row'>"
            + "".join(render_status_badge(label, kind) for label, kind in badges)
            + "</div>"
        )
    st.markdown(
        f"""
        <div class="sa-hero">
          <h2>{heading}</h2>
          <div class="sa-muted">{escape(subtitle)}</div>
          {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_info_panel(title: str, message: str, *, kind: str = "info") -> None:
    cls = {
        "info": "sa-runbar",
        "warning": "sa-runbar sa-warning",
        "danger": "sa-runbar sa-danger",
        "success": "sa-runbar sa-success",
    }.get(kind, "sa-runbar")
    st.markdown(
        f"""
        <div class="{cls}">
          <div class="sa-box-title">{escape(title)}</div>
          <div class="sa-box-message">{escape(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state(title: str, message: str) -> None:
    st.markdown(
        f"""
        <div class="sa-panel">
          <div class="sa-box-title">{escape(title)}</div>
          <div class="sa-box-message">{escape(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


@lru_cache(maxsize=1)
def pipeline_singleton():
    """Hold one Pipeline instance across reruns (Streamlit reruns the file)."""
    from smartapply.pipeline import Pipeline

    return Pipeline()


def total_jobs() -> int:
    with session_scope() as s:
        return len(list(list_jobs(s)))


def jobs_per_status() -> dict[str, int]:
    with session_scope() as s:
        counts: dict[str, int] = {}
        for job in list_jobs(s):
            counts[job.status] = counts.get(job.status, 0) + 1
    return counts


def status_label(status: str) -> str:
    return STATUS_LABEL_BY_KEY.get(status, status.replace("_", " ").title())


def ordered_status_rows(
    counts: dict[str, int],
    *,
    include_zero: bool = True,
    group: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    known = {row["status"] for row in STATUS_FLOW}
    for order, meta in enumerate(STATUS_FLOW, start=1):
        if group and meta["group"] != group:
            continue
        count = int(counts.get(meta["status"], 0))
        if count == 0 and not include_zero:
            continue
        rows.append(
            {
                **meta,
                "order": order,
                "count": count,
                "axis_label": f"{order}. {meta['label']}",
            }
        )
    for status, count in sorted(counts.items()):
        if status in known or (count == 0 and not include_zero):
            continue
        rows.append(
            {
                "status": status,
                "label": status_label(status),
                "description": "Statut non documenté dans le pipeline.",
                "group": "Autres",
                "color": "#64748B",
                "order": len(rows) + 1,
                "count": int(count),
                "axis_label": f"{len(rows) + 1}. {status_label(status)}",
            }
        )
    return rows


def render_status_funnel(
    counts: dict[str, int],
    *,
    title: str = "Entonnoir logique",
    show_dictionary: bool = True,
) -> None:
    import altair as alt

    pipeline_rows = ordered_status_rows(
        counts,
        include_zero=True,
        group="Pipeline principal",
    )
    exception_rows = ordered_status_rows(
        counts,
        include_zero=False,
        group="Blocages et rejets",
    )
    st.markdown(f"### {title}")
    st.caption(
        "Les statuts sont affichés dans l'ordre métier : collecte, filtrage, analyse, génération, action, puis suivi."
    )

    for start in range(0, len(pipeline_rows), 5):
        cols = st.columns(5)
        for col, row in zip(cols, pipeline_rows[start : start + 5], strict=False):
            with col, st.container(border=True):
                st.caption(f"Étape {row['order']}")
                st.metric(row["label"], row["count"])
                st.caption(row["description"])

    df = pd.DataFrame(pipeline_rows)
    if not df.empty:
        domain = df["axis_label"].tolist()
        color_range = df["color"].tolist()
        chart = (
            alt.Chart(df)
            .mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5)
            .encode(
                x=alt.X(
                    "axis_label:N",
                    sort=domain,
                    title=None,
                    axis=alt.Axis(labelAngle=-28, labelLimit=130),
                ),
                y=alt.Y("count:Q", title="Nombre d'offres", axis=alt.Axis(format="d")),
                color=alt.Color(
                    "axis_label:N",
                    scale=alt.Scale(domain=domain, range=color_range),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("label:N", title="Statut"),
                    alt.Tooltip("status:N", title="Code"),
                    alt.Tooltip("count:Q", title="Nombre", format="d"),
                    alt.Tooltip("description:N", title="Définition"),
                ],
            )
            .properties(height=250)
        )
        labels = (
            alt.Chart(df)
            .mark_text(dy=-8, fontWeight="bold", color="#172033")
            .encode(
                x=alt.X("axis_label:N", sort=domain),
                y=alt.Y("count:Q"),
                text=alt.Text("count:Q", format="d"),
            )
        )
        static_chart = (chart + labels).configure_view(strokeWidth=0)
        st.altair_chart(static_chart, width="stretch", on_select="ignore")

    if exception_rows:
        st.markdown("**Blocages et rejets à surveiller**")
        exception_df = pd.DataFrame(
            [
                {
                    "statut": row["label"],
                    "nombre": row["count"],
                    "à comprendre": row["description"],
                }
                for row in exception_rows
            ]
        )
        st.dataframe(exception_df, hide_index=True, width="stretch")

    if show_dictionary:
        with st.expander("Comprendre tous les statuts"):
            dictionary_df = pd.DataFrame(
                [
                    {
                        "ordre": row["order"],
                        "statut": row["label"],
                        "code": row["status"],
                        "famille": row["group"],
                        "définition": row["description"],
                    }
                    for row in ordered_status_rows(counts, include_zero=True)
                ]
            )
            st.dataframe(dictionary_df, hide_index=True, width="stretch")


def total_cost_usd() -> float:
    with session_scope() as s:
        return float(total_cost(s))


def cost_by_purpose() -> dict[str, float]:
    from sqlalchemy import select

    from smartapply.database.models import LLMUsage

    with session_scope() as s:
        rows = s.execute(select(LLMUsage)).scalars().all()
        out: dict[str, float] = {}
        for r in rows:
            out[r.purpose] = out.get(r.purpose, 0.0) + r.cost_usd
    return out
