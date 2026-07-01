"""CV and motivation-letter generation/validation helpers."""

from __future__ import annotations

import re
from typing import Any

from smartapply.database import session_scope
from smartapply.database.models import Job
from smartapply.email_agent import build_application_email
from smartapply.llm import EmailDraft, JobAnalysis, MotivationLetter
from smartapply.pipeline.language import detect_offer_language
from smartapply.pipeline.reports import ApplyReport

_ANCHOR_STOPWORDS = {
    "and",
    "avec",
    "chez",
    "data",
    "donnée",
    "données",
    "donnee",
    "donnees",
    "engineer",
    "engineering",
    "for",
    "from",
    "h/f",
    "ingénieur",
    "ingenieur",
    "junior",
    "mid",
    "pour",
    "role",
    "scientist",
    "the",
    "with",
}

_ROLE_PHRASES = (
    "ai engineer",
    "analytics engineer",
    "business analyst",
    "computer vision",
    "data analyst",
    "data engineer",
    "data scientist",
    "deep learning",
    "devops",
    "full stack",
    "fullstack",
    "generative ai",
    "ia engineer",
    "ingénieur data",
    "machine learning",
    "ml engineer",
    "mlops",
    "nlp",
    "product analyst",
    "product data analyst",
    "rag",
    "software engineer",
    "speech",
    "time series",
)

_ANONYMOUS_COMPANY_MARKERS = (
    "confidentiel",
    "non communiqu",
    "anonyme",
)


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().replace("’", "'").split())


def _is_anonymous_company(name: str | None) -> bool:
    lowered = _norm(name)
    return not lowered or any(marker in lowered for marker in _ANONYMOUS_COMPANY_MARKERS)


def _document_company_label(company: str | None, language: str) -> str:
    if not _is_anonymous_company(company):
        return (company or "").strip()
    return "l'entreprise recruteuse" if language == "fr" else "the hiring company"


def _word_anchors(text: str) -> set[str]:
    words = {
        word
        for word in re.findall(r"[a-zA-ZÀ-ÿ0-9+#.]{3,}", _norm(text))
        if word not in _ANCHOR_STOPWORDS
    }
    return words


def _offer_anchors(analysis: JobAnalysis, job_title: str) -> set[str]:
    role_text = " ".join(
        [
            job_title or "",
            analysis.role_type or "",
            " ".join(analysis.main_tasks[:4]),
            " ".join(analysis.required_skills),
            " ".join(analysis.cv_keywords_to_include),
        ]
    )
    haystack = _norm(role_text)
    anchors = _word_anchors(role_text)
    for phrase in _ROLE_PHRASES:
        if phrase in haystack:
            anchors.add(phrase)
    return {anchor for anchor in anchors if len(anchor) >= 3}


class CvWriterMixin:
    """Generate and validate CV/motivation-letter content."""

    def _generate_draft(
        self,
        *,
        job: Job,
        analysis: JobAnalysis,
        offer_language: str,
        document_company: str,
    ) -> tuple[Any, MotivationLetter, EmailDraft]:
        """Generate CV + motivation letter, then build the sending email."""
        adapted, letter_draft, _selection = self.adapter.adapt_application(
            analysis,
            job_title=job.title,
            job_company=document_company,
            language=offer_language,
            job_id=job.id,
        )
        email_draft = build_application_email(
            candidate_name=self.profile.identity.full_name,
            job_title=job.title,
            job_company=document_company,
            language=offer_language,
        )
        return adapted, letter_draft, email_draft

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

    def _validate_cv_offer_alignment(
        self,
        adapted,
        analysis: JobAnalysis,
        job_title: str,
        report: ApplyReport,
    ) -> None:
        anchors = _offer_anchors(analysis, job_title)
        if not anchors:
            return
        title = _norm(adapted.cv_title)
        summary = _norm(adapted.professional_summary)
        if not any(anchor in title for anchor in anchors):
            report.validation_warnings.append("cv_title_not_offer_anchored")
        if not any(anchor in summary for anchor in anchors):
            report.validation_warnings.append("summary_not_offer_anchored")

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
                extracted_company_name=raw.get("extracted_company_name") or "",
                extracted_location=raw.get("extracted_location") or "",
                company_context=raw.get("company_context") or "",
                offer_interest_points=list(raw.get("offer_interest_points") or []),
            )
            if job.score is not None:
                _ = job.score.components
            return job, analysis
