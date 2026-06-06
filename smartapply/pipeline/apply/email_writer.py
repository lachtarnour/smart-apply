"""Email/EML export and application persistence helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from smartapply.database import session_scope
from smartapply.database.models import Job
from smartapply.database.repository import (
    add_contact,
    create_or_get_application,
    update_status,
    upsert_document,
)
from smartapply.email_agent import ContactCandidate, export_eml
from smartapply.llm import EmailDraft, JobAnalysis, MotivationLetter
from smartapply.pipeline.reports import ApplyReport


class EmailWriterMixin:
    """Persist generated email/application artifacts."""

    def _export_eml(
        self,
        *,
        report: ApplyReport,
        email_draft: EmailDraft,
        recipient: str,
        cc_recipient: str | None = None,
    ) -> None:
        out_dir = self.settings.output_dir / f"job-{report.job_id}"
        eml_path = out_dir / "draft.eml"
        export_eml(
            subject=email_draft.subject,
            body=email_draft.body,
            sender=self.profile.identity.email,
            recipient=recipient,
            cc_recipient=cc_recipient,
            attachments=self.renderer.attachment_paths(report),
            out_path=eml_path,
        )
        report.eml_path = str(eml_path)

    def _build_audit(
        self,
        *,
        job_id: int,
        job: Job,
        analysis: JobAnalysis,
        score_components: dict[str, Any] | None,
        report: ApplyReport,
        contact: ContactCandidate | None,
        status: str,
    ) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "job_title": job.title,
            "job_company": job.company,
            "score": score_components,
            "quality_review": report.quality_review,
            "validation_warnings": report.validation_warnings,
            "validation_errors": report.validation_errors,
            "contact": asdict(contact) if contact else None,
            "contact_email": report.contact_email,
            "contact_cc_email": report.contact_cc_email,
            "contact_source": report.contact_source,
            "contact_form_url": report.contact_form_url,
            "contact_domain_kind": analysis.contact_domain_kind,
            "contact_domain_hint": analysis.contact_domain_hint,
            "contact_domain_reason": analysis.contact_domain_reason,
            "job_location": job.location,
            "extracted_location": analysis.extracted_location,
            "docx_path": report.docx_path,
            "cv_pdf_path": report.cv_pdf_path,
            "letter_pdf_path": report.letter_pdf_path,
            "eml_path": report.eml_path,
            "gmail_draft_id": report.gmail_draft_id,
            "status": status,
        }

    def _persist_application(
        self,
        *,
        report: ApplyReport,
        adapted,
        letter_draft: MotivationLetter,
        email_draft: EmailDraft,
        job_company: str,
        apply_url: str | None,
        status: str,
        contact_email: str | None = None,
        contact: ContactCandidate | None = None,
        quality_reason: str | None = None,
        audit: dict[str, Any] | None = None,
    ) -> None:
        with session_scope() as s:
            app = create_or_get_application(s, report.job_id)
            if contact and contact.email:
                contact_row = add_contact(
                    s,
                    company=job_company,
                    email=contact.email,
                    source_url=contact.source_url,
                    confidence=contact.confidence,
                    full_name=contact.full_name,
                    job_title=contact.job_title,
                    location_hint=contact.location_hint,
                    decision_reason=contact.decision_reason,
                )
                app.contact_id = contact_row.id
            elif contact_email:
                is_manual = report.contact_source == "manual"
                contact_row = add_contact(
                    s,
                    company=job_company,
                    email=contact_email,
                    source_url="manual" if is_manual else apply_url,
                    confidence=1.0 if is_manual else 0.7,
                )
                app.contact_id = contact_row.id
            app.cv_docx_path = report.docx_path
            app.cv_pdf_path = report.cv_pdf_path
            app.cv_json = adapted.model_dump()
            app.email_subject = email_draft.subject
            app.email_body = email_draft.body
            app.email_cc = report.contact_cc_email
            app.eml_path = report.eml_path
            app.gmail_draft_id = report.gmail_draft_id
            app.validation_warnings = report.validation_warnings
            app.status = status
            app.application_strategy = report.application_strategy
            if report.application_strategy in ("email_and_form", "form_only"):
                app.form_submission_url = report.contact_form_url or apply_url
            if quality_reason is not None:
                app.notes = (
                    f"{quality_reason}\nFormulaire: {report.contact_form_url}"
                    if report.contact_form_url and not report.contact_email
                    else quality_reason
                )
            self.renderer.add_document_rows(s, app.id, report)
            upsert_document(
                s,
                app.id,
                doc_type="cv_json",
                content=json.dumps(adapted.model_dump(), ensure_ascii=False),
            )
            upsert_document(
                s,
                app.id,
                doc_type="email",
                content=email_draft.body,
                extra={"subject": email_draft.subject},
            )
            upsert_document(
                s,
                app.id,
                doc_type="motivation_letter",
                content=letter_draft.body,
                extra={"subject": letter_draft.subject},
            )
            upsert_document(s, app.id, doc_type="eml", path=report.eml_path)
            if audit is not None:
                upsert_document(
                    s,
                    app.id,
                    doc_type="autopilot_audit",
                    content=json.dumps(audit, ensure_ascii=False, default=str),
                )
            update_status(s, report.job_id, status)
            report.application_id = app.id
