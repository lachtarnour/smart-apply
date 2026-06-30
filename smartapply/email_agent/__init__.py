"""Email draft and export helpers."""

from smartapply.email_agent.eml_export import export_eml
from smartapply.email_agent.gmail_draft import (
    GmailDraftDryRun,
    GmailDraftError,
    GmailDraftResult,
    GmailSetupStatus,
    build_mime_message,
    check_gmail_setup,
    create_draft,
    create_draft_result,
    dry_run_draft,
)
from smartapply.email_agent.template import build_application_email

__all__ = [
    "GmailDraftDryRun",
    "GmailDraftError",
    "GmailDraftResult",
    "GmailSetupStatus",
    "build_application_email",
    "build_mime_message",
    "check_gmail_setup",
    "create_draft",
    "create_draft_result",
    "dry_run_draft",
    "export_eml",
]
