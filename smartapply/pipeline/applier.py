"""Phase 3 - generate one application (CV + email + contact + drafts)."""

from __future__ import annotations

import dataclasses

from smartapply.config import get_settings
from smartapply.contacts.service import ContactService
from smartapply.cv import CvAdapter, CvValidator
from smartapply.cv.motivation_validator import MotivationLetterValidator
from smartapply.database.models import JobStatus
from smartapply.email_agent import gmail_draft as _gmail_draft
from smartapply.email_agent.eml_export import MISSING_RECIPIENT_PLACEHOLDER
from smartapply.llm import LLMProvider
from smartapply.pipeline.application_renderer import ApplicationDocumentRenderer
from smartapply.pipeline.apply.contact_resolution import ContactResolutionService
from smartapply.pipeline.apply.cv_writer import CvWriterMixin, _document_company_label
from smartapply.pipeline.apply.email_writer import EmailWriterMixin
from smartapply.pipeline.apply.gmail_dispatcher import GmailDispatcherMixin
from smartapply.pipeline.apply.quality_gate import QualityGateService
from smartapply.pipeline.apply_specs import (
    ApplyMode,
    ApplySpec,
    apply_spec_for,
)
from smartapply.pipeline.reports import ApplyReport
from smartapply.profile import Profile
from smartapply.utils.strategy import decide_strategy

create_draft = _gmail_draft.create_draft


class Applier(GmailDispatcherMixin, EmailWriterMixin, CvWriterMixin):
    """Compose the CV adapter, validator, renderer and contact service."""

    def __init__(
        self,
        *,
        profile: Profile,
        llm: LLMProvider,
        adapter: CvAdapter,
        validator: CvValidator,
        renderer: ApplicationDocumentRenderer,
        contact_service: ContactService,
    ):
        self.profile = profile
        self.llm = llm
        self.adapter = adapter
        self.validator = validator
        self.renderer = renderer
        self.contact_service = contact_service
        self.create_draft = create_draft
        self.letter_validator = MotivationLetterValidator(profile)
        self.settings = get_settings()
        self.contact_resolver = ContactResolutionService(
            contact_service=contact_service,
            settings=self.settings,
        )
        self.quality_gate = QualityGateService(
            profile=profile,
            llm=llm,
            settings=self.settings,
        )

    # ============================================================
    # Public API
    # ============================================================

    def apply(
        self,
        job_id: int,
        *,
        mode: ApplyMode = "manual",
        create_gmail_draft: bool | None = None,
        require_quality_gate: bool | None = None,
        contact_email: str | None = None,
        contact_form_url: str | None = None,
    ) -> ApplyReport:
        """Generate one application using the preset for ``mode``.

        Per-call overrides:
        - ``create_gmail_draft`` overrides the preset's default.
        - ``require_quality_gate`` overrides the preset's quality_gate flag
          (autopilot reads ``settings.autopilot_require_quality_gate`` when
          left as ``None``).
        - ``contact_email`` manually sets the recipient and bypasses provider
          lookup for that application.
        """
        spec = apply_spec_for(mode)
        if create_gmail_draft is None:
            create_gmail_draft = spec.default_gmail_draft
        if mode == "autopilot" and require_quality_gate is None:
            require_quality_gate = self.settings.autopilot_require_quality_gate
        if require_quality_gate is not None:
            spec = dataclasses.replace(spec, quality_gate=require_quality_gate)
        return self._do_apply(
            job_id,
            spec=spec,
            create_gmail_draft=create_gmail_draft,
            contact_email=contact_email,
            contact_form_url=contact_form_url,
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
        contact_email: str | None = None,
        contact_form_url: str | None = None,
    ) -> ApplyReport:
        report = ApplyReport(job_id=job_id, application_id=None)
        job, analysis = self._load_job_analysis(job_id)
        offer_language = analysis.offer_language or "fr"
        document_company = _document_company_label(job.company, offer_language)

        adapted, letter_draft, email_draft = self._generate_draft(
            job=job,
            analysis=analysis,
            offer_language=offer_language,
            document_company=document_company,
        )
        adapted = self._validate_with_auto_fix(adapted, report)
        self._validate_letter(letter_draft, adapted, analysis, report)
        self._validate_cv_offer_alignment(adapted, analysis, job.title, report)

        score_components = job.score.components if job.score else None
        quality, approved = self.quality_gate.maybe_review(
            spec=spec,
            job=job,
            analysis=analysis,
            adapted=adapted,
            letter_draft=letter_draft,
            email_draft=email_draft,
            report=report,
            score_components=score_components,
        )

        contact_resolution = self.contact_resolver.resolve(
            approved=approved,
            provider=spec.contact_provider,
            job=job,
            analysis=analysis,
            report=report,
            contact_email=contact_email,
            contact_form_url=contact_form_url,
        )
        contact = contact_resolution.contact
        report.contact_email = contact_resolution.email
        report.contact_source = contact_resolution.source
        report.contact_form_url = contact_resolution.form_url

        report.company_size = analysis.company_size
        report.application_strategy = decide_strategy(
            company_size=analysis.company_size,
            has_contact_email=bool(report.contact_email),
            has_application_url=bool(job.application_url),
        )
        self._reserve_application_id(report)

        self.renderer.render_all(
            report=report,
            adapted=adapted,
            letter_draft=letter_draft,
            job_title=job.title,
            job_company=document_company,
            contact_email=report.contact_email,
            language=offer_language,
        )

        self._export_eml(
            report=report,
            email_draft=email_draft,
            recipient=report.contact_email or MISSING_RECIPIENT_PLACEHOLDER,
            cc_recipient=report.contact_cc_email,
        )

        if approved and create_gmail_draft and report.contact_email:
            self._create_gmail_draft(
                report=report,
                email_draft=email_draft,
                recipient=report.contact_email,
                cc_recipient=report.contact_cc_email,
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
