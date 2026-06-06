"""Pipeline orchestration — thin facade composing the phase modules.

Phases:
- Phase 1: ``Ingestor``  → scrape and persist raw jobs.
- Phase 2: ``Processor`` → dedup + filter + rank + LLM analysis on top-K.
- Phase 3: ``Applier``   → adapt CV + email + contact + drafts. Supports
                            ``mode='manual'`` and ``mode='autopilot'``.

The public API of ``Pipeline`` is intentionally identical to the previous
monolithic version so the CLI, the Streamlit app and tests don't need to
change.
"""

from __future__ import annotations

from typing import Any

from smartapply.config import get_settings
from smartapply.cv import CvAdapter, CvValidator
from smartapply.database import session_scope
from smartapply.database.repository import top_jobs_by_score
from smartapply.dedup import Deduplicator
from smartapply.email_agent import (
    ContactProviderChain,
    default_contact_chain,
)
from smartapply.filtering import JobFilter, ruleset_from_preferences
from smartapply.llm import get_llm_provider
from smartapply.logging_setup import get_logger
from smartapply.pipeline.application_renderer import ApplicationDocumentRenderer
from smartapply.pipeline.applier import Applier
from smartapply.pipeline.contact_service import ContactService
from smartapply.pipeline.ingestor import Ingestor, IngestReport
from smartapply.pipeline.processor import Processor
from smartapply.pipeline.reports import (
    AnalyzeReport,
    ApplyReport,
    ProcessReport,
    RankingReport,
)
from smartapply.profile import get_profile
from smartapply.ranking import JobScorer, get_embeddings_provider
from smartapply.utils.contracts import (
    should_filter_france_travail_to_cdi,
    should_filter_serpapi_to_fulltime,
)

logger = get_logger(__name__)


def freshness_kwargs(
    source: str,
    *,
    date_posted: str | None,
    serpapi_hl: str | None = None,
) -> dict[str, Any]:
    """Build per-source ingest kwargs for the freshness filter and SerpApi locale.

    ``date_posted`` is meaningful for both SerpApi (Google Jobs chip) and France
    Travail (``minCreationDate`` ISO). ``serpapi_hl`` is SerpApi-only — France
    Travail has no UI language to switch.
    """
    kwargs: dict[str, Any] = {}
    if date_posted and source in {"serpapi", "francetravail"}:
        kwargs["date_posted"] = date_posted
    if serpapi_hl and source == "serpapi":
        kwargs["hl"] = serpapi_hl
    return kwargs


class Pipeline:
    """Facade exposing the same surface as the monolithic Pipeline used to."""

    def __init__(
        self,
        profile=None,
        llm=None,
        embeddings=None,
        contact_chain: ContactProviderChain | None = None,
    ):
        self.profile = profile or get_profile()
        self.llm = llm or get_llm_provider()
        self.embeddings = embeddings or get_embeddings_provider()
        self.settings = get_settings()

        # Shared building blocks
        self.deduplicator = Deduplicator()
        self.filter = JobFilter(ruleset_from_preferences(self.profile.preferences))
        self.scorer = JobScorer(self.profile, embeddings=self.embeddings)
        self.adapter = CvAdapter(self.profile, llm=self.llm, embeddings=self.embeddings)
        self.validator = CvValidator(self.profile)
        self.contact_chain = contact_chain or default_contact_chain()

        # Renderers and services
        self.renderer = ApplicationDocumentRenderer(self.profile)
        self.contact_service = ContactService(self.contact_chain)

        # Phase modules
        self._ingestor = Ingestor()
        self._processor = Processor(
            profile=self.profile,
            deduplicator=self.deduplicator,
            job_filter=self.filter,
            scorer=self.scorer,
            llm=self.llm,
        )
        self._applier = Applier(
            profile=self.profile,
            llm=self.llm,
            adapter=self.adapter,
            validator=self.validator,
            renderer=self.renderer,
            contact_service=self.contact_service,
        )

    # =================================================================
    # Phase 1: Ingest
    # =================================================================

    def ingest(
        self,
        source: str,
        query: str,
        location: str | None = None,
        *,
        max_results: int = 20,
        **search_kwargs: Any,
    ) -> IngestReport:
        accepted = self.profile.preferences.accepted_contract_types or []
        if (
            source == "francetravail"
            and "type_contrat" not in search_kwargs
            and should_filter_france_travail_to_cdi(accepted)
        ):
            search_kwargs["type_contrat"] = "CDI"
        if source == "serpapi" and should_filter_serpapi_to_fulltime(accepted):
            existing_chips = search_kwargs.get("chips", "")
            fulltime_chip = "employment_type:FULLTIME"
            chips = [
                chip.strip()
                for chip in str(existing_chips).split(",")
                if chip.strip()
            ]
            if fulltime_chip.lower() not in {chip.lower() for chip in chips}:
                chips.append(fulltime_chip)
            search_kwargs["chips"] = ",".join(chips)
        return self._ingestor.from_source(
            source,
            query,
            location,
            max_results=max_results,
            **search_kwargs,
        )

    def ingest_url(self, url: str) -> IngestReport:
        return self._ingestor.from_url(url)

    def ingest_text(
        self,
        text: str,
        *,
        title: str,
        company: str,
        location: str | None = None,
        application_url: str | None = None,
    ) -> IngestReport:
        return self._ingestor.from_text(
            text,
            title=title,
            company=company,
            location=location,
            application_url=application_url,
        )

    # =================================================================
    # Phase 2: Process
    # =================================================================

    def process_pending(
        self,
        top_k_analyze: int | None = None,
        *,
        job_ids: list[int] | None = None,
        local_filter_override_ids: list[int] | None = None,
    ) -> ProcessReport:
        return self._processor.process_pending(
            top_k_analyze=top_k_analyze,
            job_ids=job_ids,
            local_filter_override_ids=local_filter_override_ids,
        )

    def rank_pending(
        self,
        top_k_ranked: int | None = None,
        *,
        job_ids: list[int] | None = None,
        local_filter_override_ids: list[int] | None = None,
    ) -> RankingReport:
        return self._processor.rank_pending(
            top_k_ranked=top_k_ranked,
            job_ids=job_ids,
            local_filter_override_ids=local_filter_override_ids,
        )

    def analyze_jobs(self, job_ids: list[int]) -> AnalyzeReport:
        return self._processor.analyze_jobs(job_ids)

    def filter_pending(self, *, job_ids: list[int] | None = None):
        return self._processor.filter_pending(job_ids=job_ids)

    # =================================================================
    # Phase 3: Apply
    # =================================================================

    def apply_to(
        self,
        job_id: int,
        *,
        contact_email: str | None = None,
        contact_form_url: str | None = None,
        create_gmail_draft: bool = False,
    ) -> ApplyReport:
        """Manual path: combined CV + letter draft, optional manual contact."""
        return self._applier.apply(
            job_id,
            mode="manual",
            contact_email=contact_email,
            contact_form_url=contact_form_url,
            create_gmail_draft=create_gmail_draft,
        )

    def apply_to_autopilot(
        self,
        job_id: int,
        *,
        create_gmail_draft: bool = True,
        require_quality_gate: bool | None = None,
    ) -> ApplyReport:
        """Autopilot path: combined LLM draft + quality gate + cached chain."""
        return self._applier.apply(
            job_id,
            mode="autopilot",
            create_gmail_draft=create_gmail_draft,
            require_quality_gate=require_quality_gate,
        )

    # =================================================================
    # Phase 4: End-to-end
    # =================================================================

    def run_end_to_end(
        self,
        *,
        sources: list[tuple[str, str, str | None]],
        max_per_source: int = 20,
        top_k_apply: int = 5,
        create_gmail_drafts: bool = False,
        date_posted: str | None = None,
        serpapi_hl: str | None = None,
    ) -> dict[str, Any]:
        ingest_reports = [
            self.ingest(
                name,
                query,
                location,
                max_results=max_per_source,
                **freshness_kwargs(name, date_posted=date_posted, serpapi_hl=serpapi_hl),
            )
            for name, query, location in sources
        ]
        process = self.process_pending()

        with session_scope() as s:
            top_jobs = list(top_jobs_by_score(s, top_k_apply))
            top_ids = [j.id for j in top_jobs]

        applies: list[ApplyReport] = []
        for jid in top_ids:
            try:
                applies.append(
                    self.apply_to(jid, create_gmail_draft=create_gmail_drafts)
                )
            except Exception as e:
                logger.exception("apply_to(%s) failed: %s", jid, e)

        return {
            "ingest": [r.__dict__ for r in ingest_reports],
            "process": process.__dict__,
            "applications": [a.__dict__ for a in applies],
        }
