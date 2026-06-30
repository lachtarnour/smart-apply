"""Gmail draft creation glue for application generation."""

from __future__ import annotations

from smartapply.email_agent.gmail_draft import GmailDraftError
from smartapply.llm import EmailDraft
from smartapply.logging_setup import get_logger
from smartapply.pipeline.reports import ApplyReport

logger = get_logger(__name__)


class GmailDispatcherMixin:
    """Create Gmail drafts from generated application artifacts."""

    def _create_gmail_draft(
        self,
        *,
        report: ApplyReport,
        email_draft: EmailDraft,
        recipient: str,
        cc_recipient: str | None = None,
    ) -> None:
        try:
            report.gmail_draft_id = self.create_draft(
                subject=email_draft.subject,
                body=email_draft.body,
                recipient=recipient,
                cc_recipient=cc_recipient,
                sender=self.profile.identity.email,
                attachment_paths=self.renderer.attachment_paths(report),
            )
        except GmailDraftError as e:
            logger.warning("Gmail draft skipped: %s", e)
