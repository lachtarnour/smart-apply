"""Contact resolution for generated applications."""

from __future__ import annotations

import re
from dataclasses import dataclass

from smartapply.config import Settings
from smartapply.contacts import ContactCandidate
from smartapply.contacts.service import ContactService
from smartapply.database.models import Job
from smartapply.llm import JobAnalysis
from smartapply.pipeline.apply_specs import ContactProviderKind
from smartapply.pipeline.reports import ApplyReport

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class ContactResolution:
    email: str | None = None
    source: str | None = None
    form_url: str | None = None
    contact: ContactCandidate | None = None


class ContactResolutionService:
    """Resolve the best recipient/form target for an application."""

    def __init__(
        self,
        *,
        contact_service: ContactService,
        settings: Settings,
    ) -> None:
        self.contact_service = contact_service
        self.settings = settings

    def resolve(
        self,
        *,
        approved: bool,
        provider: ContactProviderKind,
        job: Job,
        analysis: JobAnalysis,
        report: ApplyReport,
        contact_email: str | None = None,
        contact_form_url: str | None = None,
    ) -> ContactResolution:
        manual_email = self._normalize_manual_contact_email(contact_email)
        manual_form_url = (contact_form_url or "").strip() or None
        if not approved:
            return ContactResolution()
        if manual_email:
            if self._manual_contact_passes_optional_verification(manual_email, report):
                return ContactResolution(
                    email=manual_email,
                    source="manual",
                    form_url=manual_form_url,
                )
            return ContactResolution(form_url=manual_form_url)

        contact = self._find_contact(provider, job=job, analysis=analysis)
        if contact is None:
            return ContactResolution(form_url=manual_form_url)
        return ContactResolution(
            email=contact.email,
            source=contact.provider,
            form_url=contact.form_url or manual_form_url,
            contact=contact,
        )

    def _find_contact(
        self,
        provider: ContactProviderKind,
        *,
        job: Job,
        analysis: JobAnalysis,
    ) -> ContactCandidate | None:
        if provider == "none":
            return None
        return self.contact_service.find(
            company=job.company,
            application_url=job.application_url,
            contact_domain_hint=analysis.contact_domain_hint,
            contact_domain_kind=analysis.contact_domain_kind,
            job_description=job.cleaned_description or job.description,
            analysis=analysis,
            job_location=analysis.extracted_location or job.location,
            source_data=job.source_data,
        )

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
            report.validation_warnings.append(
                "manual_contact_email_verification_unavailable"
            )
        return True
