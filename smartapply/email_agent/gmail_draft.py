"""Gmail draft creation (optional).

Requires Google OAuth credentials in ``secrets/credentials.json``. The first
call triggers a browser flow and persists a token. Subsequent calls are
non-interactive.

If google-api-python-client isn't installed, the module raises a clear
error and the pipeline falls back to ``eml_export``.
"""

from __future__ import annotations

import base64
import mimetypes
from email.message import EmailMessage
from pathlib import Path

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger

logger = get_logger(__name__)


SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


class GmailDraftError(RuntimeError):
    pass


def _ensure_libs():
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


def _get_credentials():
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
                raise GmailDraftError(
                    f"Missing OAuth credentials at {creds_path}. "
                    "Download credentials.json from Google Cloud Console "
                    "(OAuth Desktop client) and save it there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
    return creds


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
    """Create a Gmail draft. Returns the draft id."""
    _ensure_libs()
    from googleapiclient.discovery import build

    creds = _get_credentials()
    service = build("gmail", "v1", credentials=creds)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = recipient
    if cc_recipient:
        msg["Cc"] = cc_recipient
    if sender:
        msg["From"] = sender
    msg.set_content(body)

    attachments = [Path(p) for p in (attachment_paths or [])]
    if cv_path:
        attachments.append(Path(cv_path))

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

    raw = base64.urlsafe_b64encode(bytes(msg)).decode("utf-8")
    user_id = get_settings().gmail_user
    draft = (
        service.users()
        .drafts()
        .create(userId=user_id, body={"message": {"raw": raw}})
        .execute()
    )
    logger.info("Gmail draft created id=%s", draft.get("id"))
    return draft["id"]
