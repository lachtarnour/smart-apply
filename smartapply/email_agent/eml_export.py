"""Export an email as an .eml file the user can drag into any client.

This is the zero-OAuth alternative to Gmail drafts. The .eml format is a
standard RFC 5322 message and is supported by Mail.app, Outlook, Thunderbird,
Spark, Apple Mail, etc.
"""

from __future__ import annotations

import mimetypes
from email.message import EmailMessage
from pathlib import Path


def export_eml(
    *,
    subject: str,
    body: str,
    sender: str,
    recipient: str,
    out_path: str | Path,
    cv_path: str | Path | None = None,
    attachments: list[str | Path] | None = None,
) -> Path:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    attachment_paths = [Path(p) for p in (attachments or [])]
    if cv_path:
        attachment_paths.append(Path(cv_path))

    for attachment_path in attachment_paths:
        ctype, _ = mimetypes.guess_type(attachment_path.name)
        maintype, subtype = (
            ctype.split("/", 1)
            if ctype
            else ("application", "octet-stream")
        )
        msg.add_attachment(
            attachment_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=attachment_path.name,
        )

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(msg))
    return out_path
