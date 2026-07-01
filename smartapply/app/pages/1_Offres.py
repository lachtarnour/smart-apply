"""Offers list — searchable operational view."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from smartapply.app._helpers import (
    STATUS_FLOW,
    apply_app_style,
    pipeline_singleton,
    render_badge_row,
    render_empty_state,
    render_info_panel,
    render_page_header,
    status_label,
)
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import list_jobs

st.set_page_config(page_title="Offres | SmartApply", page_icon="📋", layout="wide")
apply_app_style()

render_page_header(
    "Offres",
    "Explorer le vivier, comprendre les rejets et relancer une offre utile.",
    icon="📋",
    badges=[
        ("Filtre local actif", "good"),
        ("Analyse IA contrôlée", "blue"),
        ("Aucune action automatique", "neutral"),
    ],
)


def _matches_search(df: pd.DataFrame, query: str) -> pd.DataFrame:
    if df.empty or not query.strip():
        return df
    needle = query.strip().lower()
    cols = [
        "title",
        "company",
        "location",
        "source",
        "contract",
        "status",
        "rejection",
        "preview",
    ]
    mask = pd.Series(False, index=df.index)
    for col in [c for c in cols if c in df]:
        mask = mask | df[col].fillna("").astype(str).str.lower().str.contains(
            needle,
            regex=False,
        )
    return df[mask]


def _components_dict(job: Job) -> dict[str, Any]:
    if job.score is None or not isinstance(job.score.components, dict):
        return {}
    return dict(job.score.components)


def _rejection_reasons(components: dict[str, Any]) -> list[str]:
    raw = components.get("rejection_reasons") or components.get("reasons") or []
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(reason) for reason in raw if str(reason).strip()]
    return []


def _rejection_stage_label(stage: str | None) -> str:
    labels = {
        "local_filter": "Filtre local",
        "deduplication": "Dédoublonnage",
    }
    return labels.get(stage or "", "Non renseignée")


status_options = ["(tous)"] + [row["status"] for row in STATUS_FLOW]
col_search, col_status, col_source, col_score, col_limit = st.columns(
    [1.7, 1, 0.85, 0.75, 0.65]
)
with col_search:
    search = st.text_input(
        "Rechercher",
        placeholder="Entreprise, poste, ville, compétence...",
    )
with col_status:
    status_filter = st.selectbox(
        "Statut",
        options=status_options,
        format_func=lambda value: "Tous les statuts" if value == "(tous)" else status_label(value),
    )
with col_source:
    source_filter = st.selectbox(
        "Source",
        options=[
            "(tous)",
            "serpapi",
            "francetravail",
            "linkedin",
            "welcometothejungle",
            "manual",
        ],
        format_func=lambda value: "Toutes" if value == "(tous)" else value,
    )
with col_score:
    min_score = st.slider(
        "Score min.",
        min_value=0.0,
        max_value=1.0,
        value=0.0,
        step=0.05,
        help="Filtre uniquement les offres qui ont déjà un score final.",
    )
with col_limit:
    limit = st.number_input("Limite", min_value=10, max_value=500, value=150)

with session_scope() as s:
    jobs = list_jobs(
        s,
        status=None if status_filter == "(tous)" else status_filter,
        source=None if source_filter == "(tous)" else source_filter,
        limit=int(limit),
    )
    rows: list[dict[str, Any]] = []
    for job in jobs:
        desc = (job.cleaned_description or job.description or "").strip()
        components = _components_dict(job)
        rejection_reasons = _rejection_reasons(components)
        rejection_summary = (
            str(components.get("rejection_summary") or "")
            or " · ".join(rejection_reasons[:2])
        )
        rows.append(
            {
                "id": job.id,
                "score": (
                    round(job.score.final_score, 3)
                    if job.score and job.score.final_score is not None
                    else None
                ),
                "title": job.title,
                "company": job.company,
                "location": job.location or "",
                "source": job.source,
                "status": status_label(job.status),
                "status_code": job.status,
                "contract": job.contract_type or "",
                "rejection": rejection_summary if job.status == JobStatus.ARCHIVED else "",
                "preview": desc[:160] + ("..." if len(desc) > 160 else ""),
                "url": job.application_url or "",
            }
        )

df = pd.DataFrame(rows)
if df.empty:
    render_empty_state(
        "Aucune offre trouvée",
        "Lance une recherche depuis le Workflow pour remplir cette table.",
    )
    st.stop()

df = _matches_search(df, search)
if min_score > 0 and "score" in df:
    df = df[df["score"].fillna(-1) >= min_score]
if df.empty:
    render_empty_state(
        "Aucune offre ne correspond aux filtres",
        "Essaie une recherche plus large, baisse le score minimum ou change le statut.",
    )
    st.stop()

if "score" in df.columns:
    df = df.sort_values("score", ascending=False, na_position="last")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Offres affichées", len(df))
m2.metric("Avec score", int(df["score"].notna().sum()) if "score" in df else 0)
m3.metric("Sources", df["source"].nunique())
m4.metric("Analysées", int((df["status_code"] == JobStatus.ANALYZED).sum()))
m5.metric(
    "Shortlist/prêtes",
    int(
        df["status_code"].isin(
            [
                JobStatus.SHORTLISTED,
                JobStatus.EMAIL_GENERATED,
                JobStatus.READY_FOR_FORM_SUBMISSION,
                JobStatus.DRAFT_CREATED,
            ]
        ).sum()
    ),
)

table_df = df.drop(columns=["status_code"]).reset_index(drop=True)
backing_df = df.reset_index(drop=True)
selection = st.dataframe(
    table_df,
    hide_index=True,
    width="stretch",
    height=430,
    on_select="rerun",
    selection_mode="single-row",
    key="offers_table",
    column_config={
        "url": st.column_config.LinkColumn("URL", width="small"),
        "score": st.column_config.NumberColumn("Score", format="%.3f", width="small"),
    },
)

st.divider()
st.markdown("### Inspection rapide")
st.caption("Sélectionne une ligne directement dans le tableau ci-dessus pour inspecter l'offre.")

selected_rows = list(selection.selection.rows) if selection and selection.selection else []
if selected_rows:
    selected_job_id = int(backing_df.iloc[selected_rows[0]]["id"])
    st.session_state["offers_selected_job_id"] = selected_job_id
else:
    previous_id = st.session_state.get("offers_selected_job_id")
    selected_job_id = (
        int(previous_id)
        if previous_id in set(backing_df["id"].astype(int).tolist())
        else None
    )

if selected_job_id is None:
    render_info_panel(
        "Sélectionne une offre",
        "Clique une ligne du tableau pour afficher son analyse, son score et les actions disponibles.",
    )
    st.stop()

with session_scope() as s:
    job = s.get(Job, int(selected_job_id))
    if job is None:
        st.warning("Offre introuvable.")
        st.stop()
    detail = {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "status": job.status,
        "location": job.location or "",
        "contract": job.contract_type or "",
        "remote": job.remote_policy or "",
        "source": job.source,
        "url": job.application_url or "",
        "score": job.score.final_score if job.score else None,
        "score_components": _components_dict(job),
        "analysis": job.analysis,
        "description": job.cleaned_description or job.description or "",
    }

left, right = st.columns([1.35, 1])
with left:
    st.markdown(
        f"""
        <div class="sa-panel">
          <h3 style="margin:0;">{detail['title']}</h3>
          <div class="sa-muted">{detail['company']} · {detail['location'] or 'Lieu non indiqué'}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    badges = [
        (status_label(detail["status"]), "good" if detail["status"] == JobStatus.ANALYZED else "blue"),
        (detail["source"], "neutral"),
    ]
    if detail["contract"]:
        badges.append((detail["contract"], "purple"))
    if detail["remote"]:
        badges.append((detail["remote"], "neutral"))
    render_badge_row(badges)
    if detail["url"]:
        st.link_button("Ouvrir l'offre", detail["url"])
    manual_contact = st.text_input(
        "Contact manuel",
        placeholder="recrutement@entreprise.com",
        help="Optionnel. Aucun contact n'est cherché automatiquement en mode manuel.",
        key=f"offer_manual_contact_{selected_job_id}",
    )
    can_generate = detail["status"] == JobStatus.ANALYZED and detail["analysis"] is not None
    if not can_generate:
        render_info_panel(
            "Analyse IA requise avant génération",
            "Passe cette offre par le Workflow pour produire rôle, compétences, risques et matching avant de générer le dossier.",
            kind="warning",
        )
    if st.button(
        "Générer une candidature pour cette offre",
        type="primary",
        disabled=not can_generate,
    ):
        with st.spinner("Génération CV + lettre + email..."):
            try:
                report = pipeline_singleton().apply_to(
                    int(selected_job_id),
                    contact_email=manual_contact,
                )
                st.success(f"Candidature #{report.application_id} créée.")
                st.write(f"Statut : **{status_label(report.status or '')}**")
                if report.contact_email:
                    st.write(f"Destinataire : `{report.contact_email}`")
                if getattr(report, "contact_cc_email", None):
                    st.write(f"CC : `{report.contact_cc_email}`")
                if report.validation_warnings:
                    st.warning(
                        "Points à vérifier : "
                        + " · ".join(report.validation_warnings[:5])
                    )
                if report.cv_pdf_path:
                    st.write(f"CV PDF : `{report.cv_pdf_path}`")
                if report.eml_path:
                    st.write(f"Email EML : `{report.eml_path}`")
            except Exception as e:
                st.error(str(e))

with right:
    st.markdown("### État de l'offre")
    k1, k2 = st.columns(2)
    k1.metric("Statut", status_label(detail["status"]))
    k2.metric("Score", f"{detail['score']:.3f}" if detail["score"] is not None else "—")
    st.markdown(
        f"""
        <div class="sa-kv">
          <div class="sa-kv-label">Contrat</div><div class="sa-kv-value">{detail['contract'] or '—'}</div>
          <div class="sa-kv-label">Remote</div><div class="sa-kv-value">{detail['remote'] or '—'}</div>
          <div class="sa-kv-label">Source</div><div class="sa-kv-value">{detail['source']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

if detail["status"] == JobStatus.ARCHIVED:
    components = detail["score_components"]
    rejection_reasons = _rejection_reasons(components)
    stage = _rejection_stage_label(components.get("rejection_stage"))
    render_info_panel(
        "Cause de rejet",
        f"Cette offre a été archivée à l'étape : {stage}.",
        kind="warning",
    )
    if rejection_reasons:
        st.markdown("**Points qui ont causé le rejet**")
        for reason in rejection_reasons:
            st.markdown(f"- `{reason}`")
    else:
        st.caption(
            "Aucune cause détaillée n'est enregistrée pour cette ancienne archive."
        )
    with st.expander("Détails techniques du rejet"):
        st.json(components or {"status": "archived", "rejection_reasons": []})

    # ---- Manual rescue ------------------------------------------------
    # When the local filter rejects something it should not have (e.g.
    # an ML role flagged for "apprentissage automatique"), the user can
    # forcefully re-inject the offer with maximum synthetic scores so it
    # leapfrogs straight to the analysis phase. The action is reversible
    # only by re-archiving manually — keep it explicit and require a one-
    # line justification for the audit trail.
    st.markdown("---")
    st.markdown("**Récupérer cette offre manuellement**")
    st.caption(
        "L'offre sera réintroduite dans le workflow comme si elle avait été "
        "scorée en tête (toutes les composantes à 1.0). Direction l'étape 3 "
        "(Analyse IA) ensuite."
    )
    with st.form(f"rescue_form_{detail['job_id']}", clear_on_submit=False):
        rescue_justification = st.text_input(
            "Pourquoi tu veux la garder ? (optionnel mais conservé en audit)",
            placeholder=(
                "Ex : faux rejet du filtre — 'apprentissage automatique' "
                "≠ contrat d'apprentissage"
            ),
            key=f"rescue_justification_{detail['job_id']}",
        )
        rescue_submitted = st.form_submit_button(
            "Réinjecter avec score maximal",
            type="primary",
        )
    if rescue_submitted:
        from smartapply.database.repository import rescue_archived_job

        with session_scope() as s:
            rescued = rescue_archived_job(
                s,
                int(detail["job_id"]),
                justification=rescue_justification,
            )
        if rescued is None:
            st.error("Offre introuvable, impossible de la réinjecter.")
        else:
            st.success(
                "Offre réinjectée avec un score maximal. Statut = "
                "`shortlisted`. Va sur le Workflow → étape 3 (Analyse IA) "
                "pour lancer l'analyse LLM dessus."
            )
            st.rerun()

if detail["analysis"]:
    analysis = detail["analysis"]
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("### Analyse IA")
        st.write(f"Rôle : `{analysis.role_type or '—'}`")
        st.write(f"Domaine : `{analysis.domain or '—'}`")
        st.write(f"Seniorité : `{analysis.seniority or '—'}`")
    with a2:
        st.markdown("### Match / risques")
        if analysis.match_reasons:
            render_badge_row([(reason, "good") for reason in analysis.match_reasons[:4]])
        else:
            st.caption("Aucune raison de match détaillée.")
        if analysis.risks:
            render_badge_row([(risk, "warn") for risk in analysis.risks[:4]])
        else:
            st.caption("Aucun risque majeur renseigné.")

with st.expander("Description complète", expanded=False):
    st.text_area(
        "Description",
        detail["description"] or "(description vide)",
        height=360,
        disabled=True,
        label_visibility="collapsed",
    )
