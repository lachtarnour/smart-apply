"""Workflow step 5: final review and Gmail draft creation."""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    render_html_open_button,
    status_label,
)
from smartapply.app.workflow.state import reset_workflow
from smartapply.app.workflow.step4_generate import _existing_generated_application_ids
from smartapply.app.workflow.step5_contacts import (
    _render_contact_lookup_controls,
    _save_manual_contact_for_application,
)
from smartapply.app.workflow.step5_forms import _render_form_questions_assistant
from smartapply.app.workflow.step5_gmail import (
    _create_gmail_draft,
    _render_gmail_dry_run_preview,
)
from smartapply.app.workflow.widgets import _sort_table, _status_pill
from smartapply.database import session_scope
from smartapply.database.models import Application, JobStatus
from smartapply.database.repository import mark_archived

CLOSED_STATUSES = (JobStatus.SENT, JobStatus.ARCHIVED)


def _html_document_path(document: Any | None, *sibling_paths: str | None) -> str | None:
    document_path = str(getattr(document, "path", "") or "").strip()
    if document_path and Path(document_path).exists():
        return document_path
    for sibling_path in sibling_paths:
        sibling = str(sibling_path or "").strip()
        if not sibling:
            continue
        try:
            html_path = Path(sibling).with_suffix(".html")
        except ValueError:
            continue
        if html_path.exists():
            return str(html_path)
    return document_path or None


def step5_send() -> None:
    _render_close_button_styles()
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 5 · Finalisation Gmail et formulaires</h3>
          <div class="sa-muted">Dernier contrôle avant action : ajuste l'email, vérifie les pièces jointes, crée les brouillons Gmail ou marque les formulaires soumis.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_step5_notice()
    app_ids = st.session_state["wf_generated_app_ids"]
    if not app_ids:
        if st.session_state.get("wf_step5_has_loaded_app_ids"):
            st.info("Pas de candidature à envoyer.")
            st.success("Toutes les candidatures générées pour cette étape sont clôturées.")
            _render_step5_navigation()
            return
        app_ids = _existing_generated_application_ids()
        if not app_ids:
            st.warning("Aucune candidature générée. Retourne à l'étape 4.")
            return
        st.session_state["wf_generated_app_ids"] = app_ids
        st.session_state["wf_step5_has_loaded_app_ids"] = True
        st.info(
            "Mode reprise : j'affiche les candidatures déjà générées en base."
        )
    else:
        st.session_state["wf_step5_has_loaded_app_ids"] = True

    with session_scope() as s:
        apps = s.query(Application).filter(Application.id.in_(app_ids)).all()
        # Pull out the data we need into plain dicts to avoid using detached
        # SQLAlchemy objects after the session closes.
        rows = []
        for app in apps:
            docs = {doc.doc_type: doc for doc in app.documents}
            cv_html = docs.get("cv_html")
            letter_pdf = docs.get("motivation_letter_pdf")
            letter_html = docs.get("motivation_letter_html")
            analysis_raw = (
                app.job.analysis.raw_response
                if app.job and app.job.analysis and isinstance(app.job.analysis.raw_response, dict)
                else {}
            )
            rows.append(
                {
                    "id": app.id,
                    "job_id": app.job_id,
                    "title": app.job.title,
                    "company": app.job.company,
                    "application_url": app.job.application_url,
                    "job_description": app.job.cleaned_description or app.job.description,
                    "job_location": app.job.location,
                    "source_data": app.job.source_data if app.job else None,
                    "analysis_raw": analysis_raw,
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
                    "cv_html_path": _html_document_path(
                        cv_html,
                        app.cv_pdf_path,
                        app.cv_docx_path,
                    ),
                    "cv_pdf_path": app.cv_pdf_path,
                    "cv_docx_path": app.cv_docx_path,
                    "eml_path": app.eml_path,
                    "letter_html_path": _html_document_path(
                        letter_html,
                        letter_pdf.path if letter_pdf else None,
                    ),
                    "letter_pdf_path": letter_pdf.path if letter_pdf else None,
                    "form_url": app.form_submission_url,
                    "gmail_draft_id": app.gmail_draft_id,
                    "email_sent_at": app.email_sent_at,
                    "form_submitted_at": app.form_submitted_at,
                    "validation_warnings": app.validation_warnings or [],
                }
            )

    rows = _sort_rows_by_app_ids(rows, app_ids)
    rows = _active_rows(rows)
    animation_target_ids = _consume_close_animation_target_ids(rows)
    _render_card_animation_styles(animation_target_ids)
    if not rows:
        st.info("Pas de candidature à envoyer.")
        st.success("Toutes les candidatures générées pour cette étape sont clôturées.")
        _render_step5_navigation()
        return

    drafts_done = sum(1 for row in rows if row["gmail_draft_id"])
    with_contact = sum(1 for row in rows if row["contact"])
    with_form = sum(1 for row in rows if row["form_url"])
    sent_done = sum(
        1
        for row in rows
        if row["email_sent_at"]
        or row["form_submitted_at"]
        or _is_closed_status(str(row["status"]))
    )
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
    summary_df = _sort_table(
        summary_df,
        state_prefix="wf_step5_summary",
        default_sort="id",
        default_desc=False,
    )
    st.dataframe(summary_df, hide_index=True, width="stretch")

    st.caption(
        "Rien n'est envoyé automatiquement. Le bouton Gmail crée seulement un brouillon, après validation manuelle."
    )
    for row in rows:
        with st.container(key=f"wf_send_card_{int(row['id'])}"):
            _render_send_card(row)

    _render_step5_navigation()
    st.divider()


def _render_close_button_styles() -> None:
    st.markdown(
        """
        <style>
        .sa-step5-card-top {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            gap: 1rem;
            align-items: start;
            padding: 0.58rem 0.72rem;
            border: 1px solid var(--sa-border);
            border-radius: 8px;
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FBFF 100%);
            box-shadow: var(--sa-shadow-xs);
            margin-bottom: 0.62rem;
        }
        .sa-step5-title-row {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            align-items: center;
            margin-bottom: 0.42rem;
        }
        .sa-step5-contact-line {
            display: flex;
            gap: 0.55rem;
            flex-wrap: wrap;
            align-items: center;
            color: var(--sa-muted);
            font-size: 0.88rem;
            line-height: 1.35;
        }
        .sa-step5-contact-line strong {
            color: var(--sa-ink);
        }
        .sa-step5-chip {
            display: inline-flex;
            align-items: center;
            border: 1px solid var(--sa-border);
            border-radius: 999px;
            background: #FFFFFF;
            color: #475467;
            font-size: 0.78rem;
            font-weight: 750;
            padding: 0.18rem 0.52rem;
        }
        .sa-step5-action-box {
            min-width: 17rem;
            display: grid;
            gap: 0.45rem;
        }
        .sa-step5-action-box [data-testid="stCheckbox"] {
            margin-bottom: 0 !important;
        }
        .sa-step5-action-box label {
            font-size: 0.88rem !important;
        }
        .sa-step5-mini-title {
            color: var(--sa-ink);
            font-size: 0.82rem;
            font-weight: 850;
            text-transform: uppercase;
            margin: 0 0 0.25rem 0;
        }
        .sa-step5-contact-missing {
            border: 1px solid #FEDF89;
            border-radius: 8px;
            background: #FFFAEB;
            color: #93370D;
            font-size: 0.86rem;
            line-height: 1.35;
            padding: 0.52rem 0.65rem;
            margin-bottom: 0.45rem;
        }
        .sa-step5-section-note {
            color: var(--sa-muted);
            font-size: 0.82rem;
            line-height: 1.38;
            margin-top: 0.32rem;
        }
        .sa-step5-compact-row {
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
            align-items: center;
            margin: 0.1rem 0 0.45rem;
        }
        div[class*="st-key-wf_email_body_box_"] textarea {
            min-height: 7.2rem !important;
        }
        div[class*="st-key-wf_contact_tools_"] button,
        div[class*="st-key-wf_gmail_preview_"] button {
            min-height: 2.35rem;
        }
        div[class*="st-key-wf_close_done_"] button {
            background: #1F7A4D !important;
            border-color: #35B66B !important;
            color: #FFFFFF !important;
        }
        div[class*="st-key-wf_close_done_"] button:hover {
            background: #24935C !important;
            border-color: #52C98A !important;
            color: #FFFFFF !important;
        }
        div[class*="st-key-wf_close_archive_"] button {
            background: #8F2F38 !important;
            border-color: #D65B66 !important;
            color: #FFFFFF !important;
        }
        div[class*="st-key-wf_close_archive_"] button:hover {
            background: #A63A44 !important;
            border-color: #FF7A84 !important;
            color: #FFFFFF !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_card_animation_styles(app_ids: list[int]) -> None:
    if not app_ids:
        return
    selectors = ",\n".join(
        f'div[class*="st-key-wf_send_card_{app_id}"]' for app_id in app_ids
    )
    st.markdown(
        f"""
        <style>
        @keyframes sa-wf-card-slide-up {{
            from {{
                transform: translateY(22px);
            }}
            to {{
                transform: translateY(0);
            }}
        }}
        {selectors} {{
            animation: sa-wf-card-slide-up 260ms cubic-bezier(0.2, 0.8, 0.2, 1) both;
            transform-origin: top center;
            will-change: transform;
        }}
        @media (prefers-reduced-motion: reduce) {{
            {selectors} {{
                animation: none !important;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_step5_navigation() -> None:
    col_back, col_reset = st.columns([1, 1])
    with col_back:
        if st.button("⬅ Retour à l'étape 4", key="wf_step5_back", width="stretch"):
            st.session_state["wf_step"] = 4
            st.rerun()
    with col_reset:
        if st.button("🔄 Nouveau workflow", key="wf_reset", width="stretch"):
            reset_workflow()
            st.rerun()


def _reset_final_email(subject_key: str, body_key: str, subject: str, body: str) -> None:
    st.session_state[subject_key] = subject
    st.session_state[body_key] = body


def _set_step5_notice(kind: str, message: str) -> None:
    st.session_state["wf_step5_notice"] = {"kind": kind, "message": message}


def _render_step5_notice() -> None:
    notice = st.session_state.pop("wf_step5_notice", None)
    if not isinstance(notice, dict):
        return
    message = str(notice.get("message") or "").strip()
    if not message:
        return
    kind = str(notice.get("kind") or "info")
    if kind == "success":
        st.success(message)
    elif kind == "warning":
        st.warning(message)
    elif kind == "error":
        st.error(message)
    else:
        st.info(message)


def _is_closed_status(status: str) -> bool:
    return status in CLOSED_STATUSES


def _active_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active = [row for row in rows if not _is_closed_status(str(row["status"]))]
    st.session_state["wf_generated_app_ids"] = [int(row["id"]) for row in active]
    return active


def _sort_rows_by_app_ids(
    rows: list[dict[str, Any]],
    app_ids: list[int],
) -> list[dict[str, Any]]:
    order = {int(app_id): index for index, app_id in enumerate(app_ids)}
    return sorted(rows, key=lambda row: order.get(int(row["id"]), len(order)))


def _drop_application_from_step5(app_id: int) -> None:
    current_ids = st.session_state.get("wf_generated_app_ids", [])
    remaining_ids, slide_target_ids = _drop_application_id(current_ids, int(app_id))
    st.session_state["wf_generated_app_ids"] = remaining_ids
    st.session_state["wf_closed_slide_target_ids"] = slide_target_ids


def _drop_application_id(
    current_ids: list[int],
    app_id: int,
) -> tuple[list[int], list[int]]:
    normalized_ids = [int(current_id) for current_id in current_ids]
    if app_id not in normalized_ids:
        return normalized_ids, []
    closed_index = normalized_ids.index(app_id)
    return (
        [current_id for current_id in normalized_ids if current_id != app_id],
        normalized_ids[closed_index + 1 :],
    )


def _consume_close_animation_target_ids(rows: list[dict[str, Any]]) -> list[int]:
    active_ids = {int(row["id"]) for row in rows}
    target_ids = st.session_state.pop("wf_closed_slide_target_ids", [])
    return [int(app_id) for app_id in target_ids if int(app_id) in active_ids]


def _close_application(app_id: int, action: str) -> bool:
    with session_scope() as s:
        app = s.get(Application, int(app_id))
        if app is None:
            return False

        if action == "done":
            _mark_application_done(app)
            return True

        if action == "archive":
            app.status = JobStatus.ARCHIVED
            if app.job is not None:
                mark_archived(s, app.job.id)
            return True

    return False


def _close_application_from_step5(app_id: int, action: str) -> None:
    if _close_application(app_id, action):
        _drop_application_from_step5(app_id)
        if action == "done":
            _set_step5_notice("success", "Candidature marquée comme faite.")
        else:
            _set_step5_notice("success", "Candidature archivée.")
    else:
        _set_step5_notice("error", "Impossible de clôturer cette candidature.")


def _track_application_action(
    app_id: int,
    *,
    email_sent: bool = False,
    form_submitted: bool = False,
) -> tuple[bool, bool]:
    with session_scope() as s:
        app = s.get(Application, int(app_id))
        if app is None:
            return False, False
        now = datetime.now(timezone.utc)
        if email_sent and app.email_sent_at is None:
            app.email_sent_at = now
        if form_submitted and app.form_submitted_at is None:
            app.form_submitted_at = now
        should_close = app.email_sent_at is not None and app.form_submitted_at is not None
        if should_close:
            app.status = JobStatus.SENT
            if app.job is not None:
                app.job.status = JobStatus.SENT
        return True, should_close


def _track_application_action_from_step5(
    app_id: int,
    *,
    email_sent: bool = False,
    form_submitted: bool = False,
) -> None:
    updated, closed = _track_application_action(
        app_id,
        email_sent=email_sent,
        form_submitted=form_submitted,
    )
    if not updated:
        _set_step5_notice("error", "Impossible de mettre à jour cette candidature.")
        return
    if closed:
        _drop_application_from_step5(app_id)
        _set_step5_notice(
            "success",
            "Email et formulaire enregistrés : candidature clôturée automatiquement.",
        )
    else:
        _set_step5_notice(
            "success",
            "Action enregistrée. La candidature reste visible tant que l'autre action n'est pas faite.",
        )


def _mark_application_done(app: Application) -> None:
    now = datetime.now(timezone.utc)
    strategy = app.application_strategy or "email_only"
    if strategy in ("email_only", "email_and_form") and app.email_sent_at is None:
        app.email_sent_at = now
    if strategy in ("form_only", "email_and_form") and app.form_submitted_at is None:
        app.form_submitted_at = now
    app.status = JobStatus.SENT
    if app.job is not None:
        app.job.status = JobStatus.SENT


def _render_send_card(row: dict[str, Any]) -> None:
    app_id = int(row["id"])
    strategy_icon = {
        "email_only": "📧",
        "email_and_form": "📧🗂",
        "form_only": "🗂",
    }.get(row["strategy"], "")
    expanded_default = row["status"] not in (JobStatus.SENT, JobStatus.ARCHIVED)
    with st.expander(
        f"{strategy_icon} [{app_id}] {row['title']} @ {row['company']}  ·  {row['status_label']}",
        expanded=expanded_default,
    ):
        subject_key = f"wf_final_subject_{app_id}"
        body_key = f"wf_final_body_{app_id}"
        st.session_state.setdefault(subject_key, row["subject"])
        st.session_state.setdefault(body_key, row["body"])

        _render_step5_card_summary(row)

        editor_col, action_col = st.columns([1.52, 1])
        with editor_col:
            _render_step5_email_workspace(row, app_id, subject_key, body_key)
        with action_col:
            final_subject = str(st.session_state.get(subject_key, "")).strip()
            final_body = str(st.session_state.get(body_key, "")).strip()
            reviewed = st.checkbox(
                "Revue finale OK",
                key=f"wf_reviewed_{app_id}",
                help="Contact, CV, lettre et email relus.",
            )
            _render_step5_actions(row, app_id, reviewed, final_subject, final_body)
            _render_step5_contact_workspace(row, app_id)
            _render_step5_secondary_tools(row, app_id, final_subject, final_body)


def _render_step5_card_summary(row: dict[str, Any]) -> None:
    status_kind = "good" if row["gmail_draft_id"] or row["email_sent_at"] else "warn"
    contact_text = row["contact"] or "Contact à trouver"
    form_text = "Formulaire disponible" if row["form_url"] else "Pas de formulaire"
    contact_detail = _contact_detail_line(row)
    cc_html = (
        f"<span class='sa-step5-chip'>CC {escape(str(row['email_cc']))}</span>"
        if row.get("email_cc")
        else ""
    )
    contact_detail_html = (
        f"<span>{escape(contact_detail)}</span>" if contact_detail else ""
    )
    html = (
        '<div class="sa-step5-card-top">'
        "<div>"
        '<div class="sa-step5-title-row">'
        f"{_status_pill(_strategy_label(row.get('strategy')), 'blue')}"
        f"{_status_pill(str(row['status_label']), status_kind)}"
        f'<span class="sa-step5-chip">{escape(form_text)}</span>'
        f"{cc_html}"
        "</div>"
        '<div class="sa-step5-contact-line">'
        "<strong>Contact</strong>"
        f"<span>{escape(contact_text)}</span>"
        f"{contact_detail_html}"
        "</div>"
        "</div>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_step5_email_workspace(
    row: dict[str, Any],
    app_id: int,
    subject_key: str,
    body_key: str,
) -> None:
    st.markdown("<div class='sa-step5-mini-title'>Email et documents</div>", unsafe_allow_html=True)

    doc_cols = st.columns([1, 1, 0.72])
    with doc_cols[0]:
        render_html_open_button(
            "CV HTML",
            row.get("cv_html_path"),
            key=f"wf_open_cv_html_{app_id}",
        )
    with doc_cols[1]:
        render_html_open_button(
            "Lettre HTML",
            row.get("letter_html_path"),
            key=f"wf_open_letter_html_{app_id}",
        )
    with doc_cols[2]:
        _render_validation_warnings_popover(row, app_id)

    st.text_input("Sujet final", key=subject_key)
    with st.container(key=f"wf_email_body_box_{app_id}"):
        st.text_area(
            "Email final",
            height=118,
            key=body_key,
        )

    st.button(
        "Recharger l'email généré",
        key=f"wf_reset_email_{app_id}",
        on_click=_reset_final_email,
        args=(subject_key, body_key, row["subject"], row["body"]),
    )


def _render_step5_actions(
    row: dict[str, Any],
    app_id: int,
    reviewed: bool,
    final_subject: str,
    final_body: str,
) -> None:
    st.markdown("<div class='sa-step5-mini-title'>Actions visibles</div>", unsafe_allow_html=True)

    if row["form_url"]:
        st.link_button("Ouvrir le formulaire ATS", row["form_url"], width="stretch")

    _render_gmail_action(row, app_id, reviewed, final_subject, final_body)
    _render_tracking_actions(row, app_id)
    _render_close_actions(app_id)


def _render_gmail_action(
    row: dict[str, Any],
    app_id: int,
    reviewed: bool,
    final_subject: str,
    final_body: str,
) -> None:
    if row["gmail_draft_id"]:
        st.success(f"Brouillon Gmail : `{row['gmail_draft_id']}`")
        return

    disabled = not row["contact"] or not reviewed or not final_subject or not final_body
    if st.button(
        "Créer le brouillon Gmail",
        disabled=disabled,
        key=f"wf_gmail_{app_id}",
        type="primary",
        width="stretch",
    ):
        _create_gmail_draft(
            {
                **row,
                "subject": final_subject,
                "body": final_body,
            }
        )
        st.rerun()
    _render_gmail_blocker_hint(row, reviewed, final_subject, final_body)


def _render_tracking_actions(row: dict[str, Any], app_id: int) -> None:
    track_cols = st.columns(2)
    with track_cols[0]:
        if row["email_sent_at"]:
            st.caption(f"Email envoyé {row['email_sent_at'].strftime('%d/%m %H:%M')}")
        else:
            st.button(
                "Email envoyé",
                key=f"wf_mark_email_{app_id}",
                disabled=not row["contact"],
                width="stretch",
                on_click=_track_application_action_from_step5,
                args=(app_id,),
                kwargs={"email_sent": True},
            )

    with track_cols[1]:
        if row["strategy"] not in ("email_and_form", "form_only"):
            st.button("Form soumis", key=f"wf_mark_form_hidden_{app_id}", disabled=True, width="stretch")
        elif row["form_submitted_at"]:
            st.caption(f"Form soumis {row['form_submitted_at'].strftime('%d/%m %H:%M')}")
        else:
            st.button(
                "Form soumis",
                key=f"wf_mark_form_{app_id}",
                width="stretch",
                on_click=_track_application_action_from_step5,
                args=(app_id,),
                kwargs={"form_submitted": True},
            )


def _render_close_actions(app_id: int) -> None:
    close_done, close_archive = st.columns(2)
    with close_done:
        st.button(
            "Candidature faite",
            key=f"wf_close_done_{app_id}",
            type="primary",
            width="stretch",
            on_click=_close_application_from_step5,
            args=(app_id, "done"),
        )
    with close_archive:
        st.button(
            "Archiver",
            key=f"wf_close_archive_{app_id}",
            width="stretch",
            on_click=_close_application_from_step5,
            args=(app_id, "archive"),
        )


def _render_step5_contact_workspace(row: dict[str, Any], app_id: int) -> None:
    st.markdown("<div class='sa-step5-mini-title'>Contact</div>", unsafe_allow_html=True)
    if row["contact"]:
        st.markdown(f"**{row['contact']}**")
        detail = _contact_detail_line(row)
        if detail:
            st.caption(detail)
        if row["strategy"] == "form_only":
            st.caption("Email possible si tu gardes ce contact.")
    else:
        st.markdown(
            '<div class="sa-step5-contact-missing">Aucun contact attaché.</div>',
            unsafe_allow_html=True,
        )

    contact_key = f"wf_manual_contact_{app_id}"
    st.session_state.setdefault(contact_key, row["contact"] or "")
    with st.popover(
        "Modifier / trouver un contact",
        key=f"wf_contact_tools_{app_id}",
        width="stretch",
    ):
        st.text_input(
            "Email contact",
            key=contact_key,
            placeholder="recrutement@entreprise.com",
        )
        if st.button(
            "Enregistrer le contact",
            key=f"wf_save_manual_contact_{app_id}",
            width="stretch",
        ):
            saved = _save_manual_contact_for_application(
                row,
                str(st.session_state.get(contact_key) or ""),
            )
            if saved:
                st.rerun()
        st.divider()
        _render_contact_lookup_controls(row)


def _render_step5_secondary_tools(
    row: dict[str, Any],
    app_id: int,
    final_subject: str,
    final_body: str,
) -> None:
    tools_cols = st.columns(2)
    with tools_cols[0]:
        _render_form_questions_assistant(row)
    with tools_cols[1], st.popover(
        "Aperçu Gmail",
        key=f"wf_gmail_preview_{app_id}",
        width="stretch",
        help="Valide localement le contenu du brouillon sans appel Gmail.",
    ):
        _render_gmail_dry_run_preview(
            {
                **row,
                "subject": final_subject,
                "body": final_body,
            }
        )


def _render_validation_warnings_popover(row: dict[str, Any], app_id: int) -> None:
    warnings = row.get("validation_warnings") or []
    if not warnings:
        st.button("Warnings", key=f"wf_warnings_empty_{app_id}", disabled=True, width="stretch")
        return

    with st.popover(
        f"Warnings ({len(warnings)})",
        key=f"wf_validation_warnings_{app_id}",
        width="stretch",
    ):
        for warning in warnings:
            st.write(f"- {warning}")


def _render_gmail_blocker_hint(
    row: dict[str, Any],
    reviewed: bool,
    final_subject: str,
    final_body: str,
) -> None:
    if row["strategy"] == "form_only":
        st.caption("Gmail possible si un contact est attaché.")
    elif not row["contact"]:
        st.caption("Gmail bloqué : trouve un contact ou soumets via formulaire.")
    elif not reviewed:
        st.caption("Gmail bloqué : coche la revue finale.")
    elif not final_subject or not final_body:
        st.caption("Gmail bloqué : sujet et email obligatoires.")


def _contact_detail_line(row: dict[str, Any]) -> str:
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
    return " · ".join(str(bit) for bit in contact_bits if bit)


def _strategy_label(strategy: Any) -> str:
    return {
        "email_only": "Email",
        "email_and_form": "Email + formulaire",
        "form_only": "Formulaire",
    }.get(str(strategy or ""), str(strategy or "Stratégie"))


# ============================================================
