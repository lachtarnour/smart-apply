"""Workflow step 4: generate application documents."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from smartapply.app._helpers import pipeline_singleton, render_section_header, status_label
from smartapply.app.workflow.state import _begin_run, _end_run, _stop_requested, settings
from smartapply.app.workflow.step1_fetch import _archive_jobs_for_workflow
from smartapply.app.workflow.step3_analyze import (
    _analyzed_jobs_df,
    _kept_ids_from_full_df,
    _sync_contact_lookup_state,
    _sync_keep_state,
    _sync_manual_contacts,
)
from smartapply.app.workflow.widgets import (
    _download_button,
    _filter_table,
    _render_action_strip,
    _render_pdf,
    _sort_table,
)
from smartapply.database import session_scope
from smartapply.database.models import Application, JobStatus


def _existing_generated_application_ids(limit: int = 50) -> list[int]:
    with session_scope() as s:
        apps = s.query(Application).order_by(Application.updated_at.desc()).limit(limit).all()
        return [
            int(app.id)
            for app in apps
            if app.status not in {JobStatus.SENT, JobStatus.ARCHIVED}
            and (
                app.cv_pdf_path
                or app.cv_docx_path
                or app.email_body
                or app.status in {
                    JobStatus.EMAIL_GENERATED,
                    JobStatus.READY_FOR_FORM_SUBMISSION,
                    JobStatus.DRAFT_CREATED,
                    JobStatus.CONTACT_MISSING,
                }
            )
        ]



def step4_generate() -> None:
    st.markdown(
        """
        <div class="sa-panel">
          <h3 style="margin:0;">Étape 4 · Génération des candidatures</h3>
          <div class="sa-muted">Le système génère un CV PDF/DOCX, une lettre, un email et peut rechercher un contact fiable si Anymail est configuré.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    seed_ids = list(st.session_state["wf_selected_for_apply"])
    resume_df = _analyzed_jobs_df()
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
        "Sélectionne les offres à générer. Le contact manuel est prioritaire ; "
        "coche ensuite les offres pour lesquelles Anymail doit chercher un email."
    )
    seed_signature = sorted(int(job_id) for job_id in seed_ids)
    if seed_signature and st.session_state.get("wf_generate_seed_ids") != seed_signature:
        seed_set = set(seed_signature)
        st.session_state["wf_generate_keep_map"] = {
            int(job_id): int(job_id) in seed_set
            for job_id in resume_df["id"]
        }
        st.session_state["wf_generate_seed_ids"] = seed_signature
    generate_keep_map = {
        int(k): bool(v)
        for k, v in st.session_state.get("wf_generate_keep_map", {}).items()
    }
    if generate_keep_map:
        resume_df = resume_df.copy()
        resume_df["keep"] = [
            bool(generate_keep_map.get(int(job_id), bool(row_keep)))
            for job_id, row_keep in zip(resume_df["id"], resume_df["keep"], strict=True)
        ]
    contact_lookup_default = st.checkbox(
        "Précocher la recherche contact pour les offres affichées",
        disabled=not bool(settings.anymailfinder_api_key),
        key="wf_use_contact_lookup",
        help=(
            "Cette option ne lance rien toute seule. Elle préremplit la colonne "
            "'Chercher contact' ; le contact manuel reste prioritaire."
        ),
    )
    if not settings.anymailfinder_api_key:
        st.caption("ANYMAILFINDER_API_KEY non configurée : recherche automatique désactivée.")

    lookup_map = {
        int(k): bool(v)
        for k, v in st.session_state.get("wf_contact_lookup_map", {}).items()
    }
    previous_bulk_value = st.session_state.get("wf_contact_lookup_bulk_value")
    if previous_bulk_value is None or bool(previous_bulk_value) != bool(contact_lookup_default):
        lookup_map.update(
            {
                int(job_id): bool(contact_lookup_default)
                for job_id in resume_df["id"]
            }
        )
        st.session_state["wf_contact_lookup_map"] = lookup_map
        st.session_state["wf_contact_lookup_bulk_value"] = bool(contact_lookup_default)
    resume_df = resume_df.copy()
    resume_df["lookup_contact"] = [
        bool(settings.anymailfinder_api_key)
        and lookup_map.get(int(job_id), bool(contact_lookup_default))
        for job_id in resume_df["id"]
    ]
    render_section_header(
        "Dossiers à générer",
        "Toutes les offres analysées restent accessibles ; la sélection précédente est seulement précochée.",
        badges=[
            (f"{len(resume_df)} analysée(s)", "blue"),
            ("Contact manuel prioritaire", "good"),
        ],
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
    visible_resume_df = _sort_table(
        visible_resume_df,
        state_prefix="wf_step4",
        default_sort="score",
        default_desc=True,
    )
    with st.form("wf_step4_resume_editor_form"):
        edited_resume = st.data_editor(
            visible_resume_df,
            column_config={
                "keep": st.column_config.CheckboxColumn("Générer", default=True),
                "archive": st.column_config.CheckboxColumn("Archiver", default=False),
                "lookup_contact": st.column_config.CheckboxColumn(
                    "Chercher contact",
                    default=bool(contact_lookup_default),
                    help=(
                        "Appelle Anymail uniquement pour cette offre si aucun contact "
                        "manuel n'est renseigné."
                    ),
                    disabled=not bool(settings.anymailfinder_api_key),
                ),
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
        col_apply, col_archive = st.columns(2)
        with col_apply:
            apply_resume = st.form_submit_button(
                "Appliquer les coches",
                type="primary",
                width="stretch",
            )
        with col_archive:
            archive_resume = st.form_submit_button(
                "Archiver les offres cochées",
                width="stretch",
            )
    if archive_resume:
        archive_ids = edited_resume.loc[edited_resume["archive"], "id"].astype(int).tolist()
        if not archive_ids:
            st.warning("Coche au moins une offre dans la colonne Archiver.")
        else:
            count = _archive_jobs_for_workflow(archive_ids)
            st.success(f"{count} offre(s) archivée(s).")
            st.rerun()
    if apply_resume:
        _sync_manual_contacts(edited_resume)
        _sync_contact_lookup_state(edited_resume)
        _sync_keep_state(edited_resume, state_key="wf_generate_keep_map")
        st.success("Sélection mise à jour.")
    ids = _kept_ids_from_full_df(resume_df, state_key="wf_generate_keep_map")
    st.session_state["wf_selected_for_apply"] = ids
    if not ids:
        st.warning("Sélectionne au moins une offre analysée pour générer une candidature.")
        return

    manual_contacts = st.session_state.get("wf_manual_contacts", {})
    lookup_map = {
        int(k): bool(v)
        for k, v in st.session_state.get("wf_contact_lookup_map", {}).items()
    }
    selected_lookup_count = sum(
        1
        for job_id in ids
        if bool(settings.anymailfinder_api_key)
        and bool(lookup_map.get(int(job_id), bool(contact_lookup_default)))
        and not manual_contacts.get(int(job_id))
    )
    g1, g2, g3 = st.columns(3)
    g1.metric("À générer", len(ids))
    g2.metric("Déjà générées", len(st.session_state.get("wf_generated_app_ids", [])))
    g3.metric("Contacts à chercher", selected_lookup_count)

    _render_action_strip(
        kicker="Génération",
        title=f"{len(ids)} dossier(s) dans le lot",
        message=(
            "Le bouton génère CV, lettre, email et EML pour les offres cochées. "
            "Anymail ne part que sur les lignes marquées 'Chercher contact'."
        ),
        badges=[
            (f"{selected_lookup_count} contact(s)", "purple")
            if selected_lookup_count
            else ("Recherche contact désactivée", "neutral"),
            ("Brouillon Gmail non créé ici", "blue"),
        ],
    )

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
        lookup_map = {
            int(k): bool(v)
            for k, v in st.session_state.get("wf_contact_lookup_map", {}).items()
        }
        for i, job_id in enumerate(ids, start=1):
            if _stop_requested():
                st.warning("Génération arrêtée avant la candidature suivante.")
                break
            progress.progress(
                i / len(ids),
                text=f"Candidature {i}/{len(ids)} (job_id={job_id})...",
            )
            try:
                manual_contact = manual_contacts.get(int(job_id))
                should_lookup_contact = (
                    bool(lookup_map.get(int(job_id), bool(contact_lookup_default)))
                    and not manual_contact
                    and bool(settings.anymailfinder_api_key)
                )
                if should_lookup_contact:
                    report = p.apply_to_autopilot(
                        job_id,
                        create_gmail_draft=False,
                        require_quality_gate=False,
                    )
                else:
                    report = p.apply_to(
                        job_id,
                        contact_email=manual_contact,
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
    apps_df = _sort_table(
        apps_df,
        state_prefix="wf_step4_apps",
        default_sort="id",
        default_desc=False,
    )
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
