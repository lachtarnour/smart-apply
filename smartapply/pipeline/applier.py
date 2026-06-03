"""Phase 3 — generate one application (CV + email + contact + drafts).

A single ``apply`` path driven by an ``ApplySpec`` preset. The two presets
``MANUAL`` and ``AUTOPILOT`` configure which LLM strategy, contact provider,
quality gate and audit behavior to use. They preserve the historical
semantics of the legacy ``apply_to`` and ``apply_to_autopilot``.

The differences between presets:

- ``MANUAL``    : two LLM calls (CV smart + letter/email legacy), no quality gate,
                  ContactFinder regex on the application URL, no audit blob.
- ``AUTOPILOT`` : one combined LLM call (CV + motivation letter), quality gate,
                  ContactProviderChain (Snov.io + persistent cache), audit
                  blob persisted as a generated_document.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from smartapply.config import get_settings
from smartapply.cv import CvAdapter, CvValidator
from smartapply.cv.motivation_validator import MotivationLetterValidator
from smartapply.database import session_scope
from smartapply.database.models import Job, JobStatus
from smartapply.database.repository import (
    add_contact,
    create_or_get_application,
    upsert_document,
    update_status,
)
from smartapply.email_agent import (
    ContactCandidate,
    ContactFinder,
    EmailWriter,
    build_application_email,
    export_eml,
)
from smartapply.email_agent.gmail_draft import GmailDraftError, create_draft
from smartapply.utils.strategy import decide_strategy
from smartapply.llm import (
    ApplicationQualityReview,
    EmailDraft,
    JobAnalysis,
    LLMProvider,
    MotivationLetter,
)
from smartapply.llm.prompts import application_quality_review as quality_prompts
from smartapply.logging_setup import get_logger
from smartapply.pipeline.application_renderer import ApplicationDocumentRenderer
from smartapply.pipeline.contact_service import ContactService
from smartapply.pipeline.language import detect_offer_language
from smartapply.profile import Profile

logger = get_logger(__name__)


ApplyMode = Literal["manual", "autopilot"]
ContactProviderKind = Literal["finder", "chain", "none"]


@dataclass(frozen=True)
class ApplySpec:
    """The knobs that distinguish manual from autopilot apply."""

    combined_call: bool
    quality_gate: bool
    contact_provider: ContactProviderKind
    build_audit: bool
    default_gmail_draft: bool


_PRESETS: dict[ApplyMode, ApplySpec] = {
    "manual": ApplySpec(
        combined_call=False,
        quality_gate=False,
        contact_provider="finder",
        build_audit=False,
        default_gmail_draft=False,
    ),
    "autopilot": ApplySpec(
        combined_call=True,
        quality_gate=True,
        contact_provider="chain",
        build_audit=True,
        default_gmail_draft=True,
    ),
}


@dataclass
class ApplyReport:
    job_id: int
    application_id: int | None
    docx_path: str | None = None
    cv_html_path: str | None = None
    cv_pdf_path: str | None = None
    letter_html_path: str | None = None
    letter_pdf_path: str | None = None
    eml_path: str | None = None
    contact_email: str | None = None
    contact_source: str | None = None
    contact_form_url: str | None = None
    gmail_draft_id: str | None = None
    status: str | None = None
    application_strategy: str = "email_only"
    company_size: str = "unknown"
    quality_review: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    validation_warnings: list[str] = field(default_factory=list)
    validation_errors: list[str] = field(default_factory=list)


class Applier:
    """Compose the CV adapter, validator, renderer and contact service."""

    def __init__(
        self,
        *,
        profile: Profile,
        llm: LLMProvider,
        adapter: CvAdapter,
        validator: CvValidator,
        email_writer: EmailWriter,
        renderer: ApplicationDocumentRenderer,
        contact_service: ContactService,
        contact_finder: ContactFinder,
    ):
        self.profile = profile
        self.llm = llm
        self.adapter = adapter
        self.validator = validator
        self.email_writer = email_writer
        self.renderer = renderer
        self.contact_service = contact_service
        self.contact_finder = contact_finder
        self.letter_validator = MotivationLetterValidator(profile)
        self.settings = get_settings()

    # ============================================================
    # Public API
    # ============================================================

    def apply(
        self,
        job_id: int,
        *,
        mode: ApplyMode = "manual",
        find_contact: bool = True,
        create_gmail_draft: bool | None = None,
        require_quality_gate: bool | None = None,
    ) -> ApplyReport:
        """Generate one application using the preset for ``mode``.

        Per-call overrides:
        - ``find_contact=False`` forces ``contact_provider="none"``.
        - ``create_gmail_draft`` overrides the preset's default.
        - ``require_quality_gate`` overrides the preset's quality_gate flag
          (autopilot reads ``settings.autopilot_require_quality_gate`` when
          left as ``None``).
        """
        spec = _PRESETS[mode]
        if create_gmail_draft is None:
            create_gmail_draft = spec.default_gmail_draft
        if mode == "autopilot" and require_quality_gate is None:
            require_quality_gate = self.settings.autopilot_require_quality_gate
        if require_quality_gate is not None:
            spec = dataclasses.replace(spec, quality_gate=require_quality_gate)
        if not find_contact:
            spec = dataclasses.replace(spec, contact_provider="none")
        return self._do_apply(
            job_id,
            spec=spec,
            create_gmail_draft=create_gmail_draft,
        )

    # ============================================================
    # Unified apply path
    # ============================================================

    def _do_apply(
        self,
        job_id: int,
        *,
        spec: ApplySpec,
        create_gmail_draft: bool,
    ) -> ApplyReport:
        report = ApplyReport(job_id=job_id, application_id=None)
        job, analysis = self._load_job_analysis(job_id)
        offer_language = analysis.offer_language or "fr"

        adapted, letter_draft, email_draft = self._generate_draft(
            spec=spec,
            job=job,
            analysis=analysis,
            offer_language=offer_language,
        )
        adapted = self._validate_with_auto_fix(adapted, report)
        self._validate_letter(letter_draft, adapted, analysis, report)

        score_components = job.score.components if job.score else None
        quality, approved = self._maybe_quality_gate(
            spec=spec,
            job=job,
            analysis=analysis,
            adapted=adapted,
            letter_draft=letter_draft,
            email_draft=email_draft,
            report=report,
            score_components=score_components,
        )

        contact: ContactCandidate | None = None
        if approved:
            contact_email, contact = self._find_contact(
                spec.contact_provider,
                job=job,
                analysis=analysis,
            )
            if contact:
                report.contact_email = contact.email
                report.contact_source = contact.provider
                report.contact_form_url = contact.form_url
            elif contact_email:
                report.contact_email = contact_email

        report.company_size = analysis.company_size
        report.application_strategy = decide_strategy(
            company_size=analysis.company_size,
            has_contact_email=bool(report.contact_email),
            has_application_url=bool(job.application_url),
        )

        self.renderer.render_all(
            report=report,
            adapted=adapted,
            letter_draft=letter_draft,
            job_title=job.title,
            job_company=job.company,
            contact_email=report.contact_email,
            language=offer_language,
        )

        self._export_eml(
            report=report,
            email_draft=email_draft,
            recipient=report.contact_email or "TODO@example.com",
        )

        if approved and create_gmail_draft and report.contact_email:
            self._create_gmail_draft(
                report=report,
                email_draft=email_draft,
                recipient=report.contact_email,
            )

        status = self._derive_status(approved=approved, report=report)
        report.status = status

        audit = None
        if spec.build_audit:
            audit = self._build_audit(
                job_id=job_id,
                job=job,
                analysis=analysis,
                score_components=score_components,
                report=report,
                contact=contact,
                status=status,
            )
            report.audit = audit

        quality_reason = (
            quality.decision_reason if spec.quality_gate and quality is not None else None
        )
        self._persist_application(
            report=report,
            adapted=adapted,
            letter_draft=letter_draft,
            email_draft=email_draft,
            job_company=job.company,
            apply_url=job.application_url,
            status=status,
            contact_email=report.contact_email,
            contact=contact,
            quality_reason=quality_reason,
            audit=audit,
        )
        return report

    # ============================================================
    # Step helpers — branching kept narrow and explicit
    # ============================================================

    def _generate_draft(
        self,
        *,
        spec: ApplySpec,
        job: Job,
        analysis: JobAnalysis,
        offer_language: str,
    ) -> tuple[Any, MotivationLetter, EmailDraft]:
        """Run either the combined ApplicationDraft call or the two-call legacy path."""
        if spec.combined_call:
            adapted, letter_draft, _selection = self.adapter.adapt_application(
                analysis,
                job_title=job.title,
                job_company=job.company,
                language=offer_language,
                job_id=job.id,
            )
            email_draft = build_application_email(
                candidate_name=self.profile.identity.full_name,
                job_title=job.title,
                job_company=job.company,
                language=offer_language,
            )
            return adapted, letter_draft, email_draft
        adapted, _selection = self.adapter.adapt(
            analysis,
            job_title=job.title,
            job_company=job.company,
            job_id=job.id,
        )
        email_draft = self.email_writer.write(
            analysis=analysis,
            job_title=job.title,
            job_company=job.company,
            language=offer_language,
            job_id=job.id,
        )
        letter_draft = MotivationLetter(
            subject=email_draft.subject,
            body=email_draft.body,
        )
        email_draft = build_application_email(
            candidate_name=self.profile.identity.full_name,
            job_title=job.title,
            job_company=job.company,
            language=offer_language,
        )
        return adapted, letter_draft, email_draft

    def _maybe_quality_gate(
        self,
        *,
        spec: ApplySpec,
        job: Job,
        analysis: JobAnalysis,
        adapted,
        letter_draft: MotivationLetter,
        email_draft: EmailDraft,
        report: ApplyReport,
        score_components: dict[str, Any] | None,
    ) -> tuple[ApplicationQualityReview | None, bool]:
        """When the gate is off, skip the LLM call entirely and approve."""
        if not spec.quality_gate:
            return None, True
        quality = self._review_quality(
            job=job,
            analysis=analysis,
            adapted=adapted,
            letter_draft=letter_draft,
            email_draft=email_draft,
            report=report,
            score_components=score_components,
        )
        report.quality_review = quality.model_dump()
        approved = self._quality_gate_approved(quality, report)
        return quality, approved

    def _find_contact(
        self,
        provider: ContactProviderKind,
        *,
        job: Job,
        analysis: JobAnalysis,
    ) -> tuple[str | None, ContactCandidate | None]:
        """Resolve a contact email using the configured provider."""
        if provider == "none":
            return None, None
        if provider == "finder":
            if not job.application_url:
                return None, None
            best = self.contact_finder.best(job.application_url)
            return (best.email if best else None), None
        candidate = self.contact_service.find(
            company=job.company,
            application_url=job.application_url,
            contact_domain_hint=analysis.contact_domain_hint,
            contact_domain_kind=analysis.contact_domain_kind,
        )
        return (candidate.email if candidate else None), candidate

    def _derive_status(self, *, approved: bool, report: ApplyReport) -> str:
        """Unified status logic.

        ``QUALITY_REJECTED`` is autopilot-only in practice (manual mode keeps
        ``approved=True``). ``READY_FOR_FORM_SUBMISSION`` was previously
        autopilot-only too; in the unified path it also surfaces in manual
        mode when no contact email is found — which is strictly more
        informative than the legacy "EMAIL_GENERATED without recipient".
        """
        if not approved:
            return JobStatus.QUALITY_REJECTED
        if report.gmail_draft_id:
            return JobStatus.DRAFT_CREATED
        if report.contact_email:
            return JobStatus.EMAIL_GENERATED
        return JobStatus.READY_FOR_FORM_SUBMISSION

    # ============================================================
    # Shared building blocks (unchanged from the previous version)
    # ============================================================

    def _validate_with_auto_fix(self, adapted, report: ApplyReport):
        result = self.validator.validate(adapted)
        if not result.ok:
            adapted, removed = self.validator.auto_fix(adapted)
            result = self.validator.validate(adapted)
            report.validation_warnings.extend(f"auto_fixed:{r}" for r in removed)
        report.validation_warnings.extend(result.warnings)
        report.validation_errors.extend(result.errors)
        return adapted

    def _validate_letter(
        self,
        letter_draft: MotivationLetter,
        adapted,
        analysis: JobAnalysis,
        report: ApplyReport,
    ) -> None:
        result = self.letter_validator.validate(
            letter_draft,
            cv=adapted,
            analysis=analysis,
        )
        report.validation_warnings.extend(result.warnings)
        report.validation_errors.extend(result.errors)

    def _load_job_analysis(self, job_id: int) -> tuple[Job, JobAnalysis]:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if job is None or job.analysis is None:
                raise ValueError(
                    f"Job {job_id} not analyzed. Run process_pending first."
                )
            raw = job.analysis.raw_response or {}
            offer_language = raw.get("offer_language") or detect_offer_language(
                f"{job.title}\n{job.cleaned_description or job.description}"
            )
            analysis = JobAnalysis(
                role_type=job.analysis.role_type or "",
                seniority=job.analysis.seniority or "",
                domain=job.analysis.domain or "",
                main_tasks=list(job.analysis.main_tasks or []),
                required_skills=list(job.analysis.required_skills or []),
                nice_to_have=list(job.analysis.nice_to_have or []),
                match_reasons=list(job.analysis.match_reasons or []),
                risks=list(job.analysis.risks or []),
                cv_keywords_to_include=list(job.analysis.cv_keywords_to_include or []),
                contact_domain_kind=raw.get("contact_domain_kind") or "unknown",
                contact_domain_hint=raw.get("contact_domain_hint") or "",
                contact_domain_reason=raw.get("contact_domain_reason") or "",
                offer_language=offer_language,
                company_size=raw.get("company_size") or "unknown",
                company_size_reason=raw.get("company_size_reason") or "",
            )
            if job.score is not None:
                _ = job.score.components
            return job, analysis

    def _export_eml(
        self,
        *,
        report: ApplyReport,
        email_draft: EmailDraft,
        recipient: str,
    ) -> None:
        out_dir = self.settings.output_dir / f"job-{report.job_id}"
        eml_path = out_dir / "draft.eml"
        export_eml(
            subject=email_draft.subject,
            body=email_draft.body,
            sender=self.profile.identity.email,
            recipient=recipient,
            attachments=self.renderer.attachment_paths(report),
            out_path=eml_path,
        )
        report.eml_path = str(eml_path)

    def _create_gmail_draft(
        self,
        *,
        report: ApplyReport,
        email_draft: EmailDraft,
        recipient: str,
    ) -> None:
        try:
            report.gmail_draft_id = create_draft(
                subject=email_draft.subject,
                body=email_draft.body,
                recipient=recipient,
                sender=self.profile.identity.email,
                attachment_paths=self.renderer.attachment_paths(report),
            )
        except GmailDraftError as e:
            logger.warning("Gmail draft skipped: %s", e)

    def _review_quality(
        self,
        *,
        job: Job,
        analysis: JobAnalysis,
        adapted,
        letter_draft: MotivationLetter,
        email_draft: EmailDraft,
        report: ApplyReport,
        score_components: dict[str, Any] | None,
    ) -> ApplicationQualityReview:
        prompt = quality_prompts.build_user_prompt(
            profile=self.profile,
            job_title=job.title,
            job_company=job.company,
            job_description=job.cleaned_description or job.description,
            score_components=score_components,
            analysis=analysis,
            adapted_cv=adapted,
            motivation_letter=letter_draft,
            email_draft=email_draft,
            validation_warnings=report.validation_warnings,
            validation_errors=report.validation_errors,
        )
        return self.llm.complete_json(
            system=quality_prompts.SYSTEM,
            user=prompt,
            schema=ApplicationQualityReview,
            model=self.llm.cheap_model,
            temperature=0.1,
            purpose="application_quality_review",
            job_id=job.id,
        )

    def _quality_gate_approved(
        self,
        quality: ApplicationQualityReview,
        report: ApplyReport,
    ) -> bool:
        severe_prefixes = (
            "hallucinated_number",
            "off_allowed_claims",
            "low_text_overlap",
            "summary_too_long",
            "bullet_too_long",
            "letter_too_short",
            "letter_too_long",
            "unsupported_term_in_letter",
        )
        severe_warnings = [
            w for w in report.validation_warnings if w.startswith(severe_prefixes)
        ]
        scores_ok = min(
            quality.match_score,
            quality.cv_score,
            quality.email_score,
        ) >= self.settings.autopilot_min_score
        return (
            quality.approved
            and scores_ok
            and not report.validation_errors
            and not severe_warnings
        )

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
            "contact_form_url": report.contact_form_url,
            "contact_domain_kind": analysis.contact_domain_kind,
            "contact_domain_hint": analysis.contact_domain_hint,
            "contact_domain_reason": analysis.contact_domain_reason,
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
                )
                app.contact_id = contact_row.id
            elif contact_email:
                contact_row = add_contact(
                    s,
                    company=job_company,
                    email=contact_email,
                    source_url=apply_url,
                    confidence=0.7,
                )
                app.contact_id = contact_row.id
            app.cv_docx_path = report.docx_path
            app.cv_pdf_path = report.cv_pdf_path
            app.cv_json = adapted.model_dump()
            app.email_subject = email_draft.subject
            app.email_body = email_draft.body
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
