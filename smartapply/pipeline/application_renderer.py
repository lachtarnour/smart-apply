"""Render the CV and motivation letter for one application.

DOCX is generated for the candidate (editable). HTML and PDF are the
canonical recruiter-facing artifacts. The renderer never raises on PDF
failure — it logs a warning and lets the .eml fall back to DOCX.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from smartapply.config import get_settings
from smartapply.cv import CvDocxRenderer, HtmlApplicationRenderer
from smartapply.database.repository import upsert_document
from smartapply.llm import MotivationLetter
from smartapply.logging_setup import get_logger
from smartapply.profile import Profile

if TYPE_CHECKING:
    from smartapply.pipeline.reports import ApplyReport

logger = get_logger(__name__)


class ApplicationDocumentRenderer:
    """Render every artifact (DOCX, HTML, PDF) for one application."""

    def __init__(self, profile: Profile):
        self.profile = profile
        self.docx = CvDocxRenderer(profile)
        self.html = HtmlApplicationRenderer(profile)
        self.settings = get_settings()

    def render_all(
        self,
        *,
        report: ApplyReport,
        adapted,
        letter_draft: MotivationLetter,
        job_title: str,
        job_company: str,
        contact_email: str | None,
        language: str,
    ) -> None:
        """Generate every artifact and populate the corresponding report fields."""
        out_dir = self.settings.output_dir / f"job-{report.job_id}"
        safe_name = self.profile.identity.full_name.replace(" ", "_")

        # ---- DOCX (always — candidate fallback) ----
        docx_path = out_dir / f"CV_{safe_name}.docx"
        self.docx.save(adapted, docx_path)
        report.docx_path = str(docx_path)

        # ---- HTML sources ----
        cv_html_path = out_dir / f"CV_{safe_name}.html"
        letter_html_path = out_dir / f"Lettre_motivation_{safe_name}.html"
        self.html.save_cv_html(adapted, cv_html_path)
        self.html.save_letter_html(
            email_draft=letter_draft,
            job_title=job_title,
            job_company=job_company,
            contact_email=contact_email,
            path=letter_html_path,
            language=language,
        )
        report.cv_html_path = str(cv_html_path)
        report.letter_html_path = str(letter_html_path)

        # ---- PDF (best effort — DOCX is the fallback) ----
        try:
            cv_pdf_path = out_dir / f"CV_{safe_name}.pdf"
            letter_pdf_path = out_dir / f"Lettre_motivation_{safe_name}.pdf"
            self.html.save_cv_pdf(adapted, cv_pdf_path)
            self.html.save_letter_pdf(
                email_draft=letter_draft,
                job_title=job_title,
                job_company=job_company,
                contact_email=contact_email,
                path=letter_pdf_path,
                language=language,
            )
            report.cv_pdf_path = str(cv_pdf_path)
            report.letter_pdf_path = str(letter_pdf_path)
        except Exception as exc:
            logger.warning("HTML PDF rendering skipped: %s", exc)
            report.validation_warnings.append(f"pdf_generation_skipped:{exc}")

    @staticmethod
    def attachment_paths(report: ApplyReport) -> list[str]:
        """Return email-safe PDF attachments only.

        The DOCX CV remains downloadable in the UI, but it must not be sent as
        an email/Gmail attachment.
        """
        paths: list[str] = []
        if report.cv_pdf_path:
            paths.append(report.cv_pdf_path)
        if report.letter_pdf_path:
            paths.append(report.letter_pdf_path)
        return paths

    @staticmethod
    def add_document_rows(session, application_id: int, report: ApplyReport) -> None:
        """Persist every generated artifact in ``generated_documents``."""
        if report.docx_path:
            upsert_document(session, application_id, doc_type="cv_docx", path=report.docx_path)
        for doc_type, path in [
            ("cv_html", report.cv_html_path),
            ("cv_pdf", report.cv_pdf_path),
            ("motivation_letter_html", report.letter_html_path),
            ("motivation_letter_pdf", report.letter_pdf_path),
        ]:
            if path:
                upsert_document(session, application_id, doc_type=doc_type, path=path)
