"""Streamlit helpers — shared by every page."""

from __future__ import annotations

import subprocess
import sys
from functools import lru_cache
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from smartapply.app.metrics import cost_by_purpose as cost_by_purpose
from smartapply.app.metrics import jobs_per_status as jobs_per_status
from smartapply.app.metrics import total_cost_usd as total_cost_usd
from smartapply.app.metrics import total_jobs as total_jobs
from smartapply.app.source_options import (
    SERPAPI_LANGUAGE_OPTIONS as SERPAPI_LANGUAGE_OPTIONS,
)
from smartapply.app.status import STATUS_FLOW as STATUS_FLOW
from smartapply.app.status import ordered_status_rows as ordered_status_rows
from smartapply.app.status import status_label as status_label
from smartapply.app.theme import render_app_style
from smartapply.database import init_db


def ensure_db() -> None:
    """Idempotent — make sure tables exist before any query."""
    init_db()


def apply_app_style() -> None:
    ensure_db()
    render_app_style()


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


def render_section_header(
    title: str,
    subtitle: str | None = None,
    *,
    badges: list[tuple[str, str]] | None = None,
) -> None:
    badge_html = ""
    if badges:
        badge_html = (
            "<div class='sa-pill-row'>"
            + "".join(render_status_badge(label, kind) for label, kind in badges)
            + "</div>"
        )
    subtitle_html = (
        f"<div class='sa-section-subtitle'>{escape(subtitle)}</div>"
        if subtitle
        else ""
    )
    st.markdown(
        f"""
        <div class="sa-section-header">
          <div>
            <h3>{escape(title)}</h3>
            {subtitle_html}
          </div>
          {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def html_file_path(path: str | None) -> Path | None:
    if not path:
        return None
    html_path = Path(path)
    if not html_path.exists() or not html_path.is_file():
        return None
    return html_path


def render_html_open_button(
    label: str,
    path: str | None,
    *,
    key: str,
) -> None:
    html_path = html_file_path(path)
    if st.button(label, key=key, disabled=html_path is None, width="stretch"):
        open_html_file_in_browser(html_path)


def open_html_file_in_browser(html_path: Path | None) -> bool:
    if html_path is None:
        st.warning("Document HTML introuvable.")
        return False

    commands = open_html_commands(html_path)
    last_error = ""
    for command in commands:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=5,
            )
        except Exception as exc:
            last_error = str(exc)
            continue
        if result.returncode == 0:
            st.success(f"Ouvert dans le navigateur : {html_path.name}")
            return True
        last_error = (result.stderr or result.stdout or "").strip()

    st.error(f"Impossible d'ouvrir le document HTML. {last_error}".strip())
    return False


def open_html_commands(html_path: Path) -> list[list[str]]:
    if sys.platform == "darwin":
        return [
            ["open", "-a", "Google Chrome", str(html_path)],
            ["open", str(html_path)],
        ]
    if sys.platform.startswith("win"):
        return [["cmd", "/c", "start", "", str(html_path)]]
    return [["xdg-open", str(html_path)]]


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
            .mark_text(dy=-8, fontWeight="bold", color="#F4F4F4")
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
