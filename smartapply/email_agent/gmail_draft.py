"""Gmail draft creation (optional, never sends).

Requires Google OAuth credentials in ``secrets/credentials.json``. The first
call triggers a browser flow and persists a token. Subsequent calls are
non-interactive.

If ``google-api-python-client`` isn't installed, the module raises a clear
error and the pipeline falls back to ``eml_export``.

**Important contract**: this module is allowed to call exactly one Gmail
API endpoint: ``users().drafts().create``. It must never invoke
``send``, ``messages.send`` or ``drafts.send``. ``tests/test_email_agent``
contains a static guard that enforces this — do not add new call sites
without updating that guard.
"""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger

logger = get_logger(__name__)


SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

# Reasonable defensive limits before any I/O. Gmail rejects messages over
# 25 MB total. We cap a little under that to account for base64 overhead.
_ACCEPTED_ATTACHMENT_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".txt"})
_MAX_TOTAL_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20 MB
_MAX_ATTACHMENT_COUNT = 10
_BODY_PREVIEW_CHARS = 320


class GmailDraftError(RuntimeError):
    """Raised for any Gmail-related failure: missing libs, missing OAuth,
    invalid input, or upstream API error."""


@dataclass
class GmailDraftResult:
    """Outcome of a draft-creation attempt. The UI consumes this directly.

    ``status`` is ``"draft_created"`` on success and ``"error"`` on
    failure. The error message is sanitised (no recipient address, no
    body content, no credential paths).
    """

    status: str
    to: str
    subject: str
    attachment_names: list[str] = field(default_factory=list)
    draft_id: str | None = None
    message_id: str | None = None
    error: str | None = None


@dataclass
class GmailDraftDryRun:
    """MIME-only preview built without any Gmail network call."""

    to: str
    subject: str
    body_preview: str
    attachment_names: list[str]
    encoded_size_bytes: int


# ---- internal helpers --------------------------------------------------


def _ensure_libs() -> None:
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError as e:  # pragma: no cover - optional dep
        raise GmailDraftError(
            "Gmail integration requires the 'gmail' extras. "
            "Run: pip install -e '.[gmail]'"
        ) from e


def _validate_text_inputs(*, subject: str, body: str, recipient: str) -> None:
    if not (recipient and recipient.strip()):
        raise GmailDraftError("Recipient is empty — refusing to build a Gmail draft.")
    if not (subject and subject.strip()):
        raise GmailDraftError("Subject is empty — refusing to build a Gmail draft.")
    if not (body and body.strip()):
        raise GmailDraftError("Body is empty — refusing to build a Gmail draft.")


def _collect_attachments(
    *,
    cv_path: str | Path | None,
    attachment_paths: list[str | Path] | None,
) -> list[Path]:
    attachments = [Path(p) for p in (attachment_paths or [])]
    if cv_path:
        attachments.append(Path(cv_path))
    return attachments


def _validate_attachments(attachments: list[Path]) -> None:
    if len(attachments) > _MAX_ATTACHMENT_COUNT:
        raise GmailDraftError(
            f"Too many attachments ({len(attachments)} > {_MAX_ATTACHMENT_COUNT})."
        )
    total = 0
    for path in attachments:
        if not path.exists():
            # Never include any directory path beyond the file name in the
            # error to avoid leaking local layout in logs.
            raise GmailDraftError(f"Attachment missing: {path.name}")
        suffix = path.suffix.lower()
        if suffix not in _ACCEPTED_ATTACHMENT_EXTENSIONS:
            raise GmailDraftError(
                f"Attachment extension not accepted: {path.name} "
                f"(allowed: {', '.join(sorted(_ACCEPTED_ATTACHMENT_EXTENSIONS))})"
            )
        size = path.stat().st_size
        total += size
        if total > _MAX_TOTAL_ATTACHMENT_BYTES:
            raise GmailDraftError(
                f"Attachments total size exceeds {_MAX_TOTAL_ATTACHMENT_BYTES // (1024 * 1024)} MB."
            )


def build_mime_message(
    *,
    subject: str,
    body: str,
    recipient: str,
    cc_recipient: str | None = None,
    sender: str | None = None,
    cv_path: str | Path | None = None,
    attachment_paths: list[str | Path] | None = None,
) -> EmailMessage:
    """Build the RFC 5322 message that will be sent to Gmail.

    Performs every input check up front so callers get a clear
    ``GmailDraftError`` *before* any network or filesystem side-effect
    that depends on Gmail-specific state.
    """
    _validate_text_inputs(subject=subject, body=body, recipient=recipient)
    attachments = _collect_attachments(
        cv_path=cv_path, attachment_paths=attachment_paths
    )
    _validate_attachments(attachments)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = recipient
    if cc_recipient:
        msg["Cc"] = cc_recipient
    if sender:
        msg["From"] = sender
    msg.set_content(body)

    for attachment_path in attachments:
        ctype, _ = mimetypes.guess_type(attachment_path.name)
        maintype, subtype = (
            ctype.split("/", 1) if ctype else ("application", "octet-stream")
        )
        msg.add_attachment(
            attachment_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment_path.name,
        )
    return msg


def _encode_message(msg: EmailMessage) -> str:
    return base64.urlsafe_b64encode(bytes(msg)).decode("utf-8")


def _get_credentials() -> Any:
    _ensure_libs()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    settings = get_settings()
    creds_path = Path(settings.gmail_credentials_path)
    token_path = Path(settings.gmail_token_path)
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not creds_path.exists():
                # Surface the configuration key, not the absolute path, so
                # logs do not leak machine layout.
                raise GmailDraftError(
                    "Gmail OAuth credentials file is missing. Configure "
                    "GMAIL_CREDENTIALS_PATH to point to your client secret "
                    "JSON (downloaded from Google Cloud Console, "
                    "OAuth Desktop client)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
    return creds


# ---- public API --------------------------------------------------------


def dry_run_draft(
    *,
    subject: str,
    body: str,
    recipient: str,
    cc_recipient: str | None = None,
    sender: str | None = None,
    cv_path: str | Path | None = None,
    attachment_paths: list[str | Path] | None = None,
) -> GmailDraftDryRun:
    """Build and validate the MIME message *without touching Gmail*.

    Use this from the UI to preview exactly what would be sent to
    ``drafts().create`` if the user clicked the real button. Raises
    ``GmailDraftError`` on validation failure so the caller can render
    a clear message without exposing internals.
    """
    msg = build_mime_message(
        subject=subject,
        body=body,
        recipient=recipient,
        cc_recipient=cc_recipient,
        sender=sender,
        cv_path=cv_path,
        attachment_paths=attachment_paths,
    )
    encoded = _encode_message(msg)
    attachments = _collect_attachments(
        cv_path=cv_path, attachment_paths=attachment_paths
    )
    return GmailDraftDryRun(
        to=recipient,
        subject=subject,
        body_preview=body[:_BODY_PREVIEW_CHARS]
        + ("…" if len(body) > _BODY_PREVIEW_CHARS else ""),
        attachment_names=[p.name for p in attachments],
        encoded_size_bytes=len(encoded),
    )


def create_draft(
    *,
    subject: str,
    body: str,
    recipient: str,
    cc_recipient: str | None = None,
    sender: str | None = None,
    cv_path: str | Path | None = None,
    attachment_paths: list[str | Path] | None = None,
) -> str:
    """Create a Gmail draft and return its id (legacy contract).

    Prefer :func:`create_draft_result` in new code — it returns a typed
    result that surfaces attachment names and the message id alongside
    the draft id. This function is kept stable for the existing
    Streamlit workflow callsite.
    """
    _ensure_libs()
    from googleapiclient.discovery import build

    msg = build_mime_message(
        subject=subject,
        body=body,
        recipient=recipient,
        cc_recipient=cc_recipient,
        sender=sender,
        cv_path=cv_path,
        attachment_paths=attachment_paths,
    )
    raw = _encode_message(msg)
    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)
    user_id = get_settings().gmail_user
    # The only Gmail endpoint this module is allowed to hit. See module
    # docstring. ``message`` is the raw RFC 5322 bytes, base64-url-safe.
    draft = (
        service.users()
        .drafts()
        .create(userId=user_id, body={"message": {"raw": raw}})
        .execute()
    )
    draft_id = draft.get("id") or ""
    # Log only metadata — never the recipient, subject, body or token.
    attachments = _collect_attachments(
        cv_path=cv_path, attachment_paths=attachment_paths
    )
    logger.info(
        "Gmail draft created id=%s attachments=%d encoded_bytes=%d",
        draft_id,
        len(attachments),
        len(raw),
    )
    return draft_id


def create_draft_result(
    *,
    subject: str,
    body: str,
    recipient: str,
    cc_recipient: str | None = None,
    sender: str | None = None,
    cv_path: str | Path | None = None,
    attachment_paths: list[str | Path] | None = None,
) -> GmailDraftResult:
    """Create a Gmail draft and return a typed result.

    The function never raises: validation errors and Gmail API failures
    are reported via ``GmailDraftResult.status == "error"`` so the UI
    can render a clear message without try/except plumbing.
    """
    attachments = _collect_attachments(
        cv_path=cv_path, attachment_paths=attachment_paths
    )
    attachment_names = [p.name for p in attachments]
    try:
        # Validate inputs first so users get the specific error
        # (missing subject / body / attachment) rather than a generic
        # "Gmail libs not installed" complaint when both apply.
        msg = build_mime_message(
            subject=subject,
            body=body,
            recipient=recipient,
            cc_recipient=cc_recipient,
            sender=sender,
            cv_path=cv_path,
            attachment_paths=attachment_paths,
        )
        raw = _encode_message(msg)
        _ensure_libs()
        from googleapiclient.discovery import build

        creds = _get_credentials()
        service = build("gmail", "v1", credentials=creds)
        user_id = get_settings().gmail_user
        draft = (
            service.users()
            .drafts()
            .create(userId=user_id, body={"message": {"raw": raw}})
            .execute()
        )
        draft_id = draft.get("id") or ""
        message_id = (draft.get("message") or {}).get("id")
        logger.info(
            "Gmail draft created id=%s attachments=%d encoded_bytes=%d",
            draft_id,
            len(attachments),
            len(raw),
        )
        return GmailDraftResult(
            status="draft_created",
            to=recipient,
            subject=subject,
            attachment_names=attachment_names,
            draft_id=draft_id,
            message_id=message_id,
        )
    except GmailDraftError as exc:
        return GmailDraftResult(
            status="error",
            to=recipient,
            subject=subject,
            attachment_names=attachment_names,
            error=str(exc),
        )
    except Exception as exc:  # pragma: no cover - upstream network errors
        # Sanitise to type+message only — never log the full traceback at
        # info level because it can include header values.
        logger.error("Gmail draft creation failed: %s", type(exc).__name__)
        return GmailDraftResult(
            status="error",
            to=recipient,
            subject=subject,
            attachment_names=attachment_names,
            error=f"{type(exc).__name__}: {exc}",
        )
