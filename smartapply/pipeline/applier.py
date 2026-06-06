"""Phase 3 - generate one application (CV + email + contact + drafts)."""

from __future__ import annotations

import dataclasses
import re
from typing import Any

from smartapply.config import get_settings
from smartapply.cv import CvAdapter, CvValidator
from smartapply.cv.motivation_validator import MotivationLetterValidator
from smartapply.database.models import Job, JobStatus
from smartapply.email_agent import ContactCandidate
from smartapply.email_agent import gmail_draft as _gmail_draft
from smartapply.email_agent.eml_export import MISSING_RECIPIENT_PLACEHOLDER
from smartapply.llm import (
    ApplicationQualityReview,
    EmailDraft,
    JobAnalysis,
    LLMProvider,
    MotivationLetter,
)
from smartapply.llm.prompts import application_quality_review as quality_prompts
from smartapply.pipeline.application_renderer import ApplicationDocumentRenderer
from smartapply.pipeline.apply.cv_writer import CvWriterMixin, _document_company_label
from smartapply.pipeline.apply.email_writer import EmailWriterMixin
from smartapply.pipeline.apply.gmail_dispatcher import GmailDispatcherMixin
from smartapply.pipeline.apply_specs import (
    ApplyMode,
    ApplySpec,
    ContactProviderKind,
    apply_spec_for,
)
from smartapply.pipeline.contact_service import ContactService
from smartapply.pipeline.reports import ApplyReport
from smartapply.profile import Profile
from smartapply.utils.strategy import decide_strategy

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
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
        manual_contact_email = self._normalize_manual_contact_email(contact_email)
        manual_contact_form_url = (contact_form_url or "").strip() or None

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
        if approved and manual_contact_email:
            if self._manual_contact_passes_optional_verification(
                manual_contact_email,
                report,
            ):
                report.contact_email = manual_contact_email
                report.contact_source = "manual"
                report.contact_form_url = manual_contact_form_url
            else:
                manual_contact_email = None
        elif approved:
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
        if approved and manual_contact_form_url and not report.contact_form_url:
            report.contact_form_url = manual_contact_form_url

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
            return None, not report.validation_errors
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
        candidate = self.contact_service.find(
            company=job.company,
            application_url=job.application_url,
            contact_domain_hint=analysis.contact_domain_hint,
            contact_domain_kind=analysis.contact_domain_kind,
            job_description=job.cleaned_description or job.description,
            analysis=analysis,
            job_location=analysis.extracted_location or job.location,
        )
        return (candidate.email if candidate else None), candidate

    @staticmethod
    def _normalize_manual_contact_email(email: str | None) -> str | None:
        value = (email or "").strip().lower()
        if not value:
            return None
        if not _EMAIL_RE.match(value):
            raise ValueError(f"Invalid contact email: {email}")
        return value

    def _manual_contact_passes_optional_verification(
        self,
        email: str,
        report: ApplyReport,
    ) -> bool:
        if not self.settings.anymailfinder_verify_manual_contacts:
            return True
        verified = self.contact_service.verify_email(email)
        if verified is False:
            report.validation_warnings.append("manual_contact_email_not_verified")
            return False
        if verified is None:
            report.validation_warnings.append("manual_contact_email_verification_unavailable")
        return True

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
            "letter_self_deprecation",
            "french_elision_missing_apostrophe",
            "unsupported_term_in_letter",
            "unsupported_tech_in_letter",
            "unselected_project_in_letter",
            "cv_title_not_offer_anchored",
            "summary_not_offer_anchored",
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
