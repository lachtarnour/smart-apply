"""Tests for the email_agent module."""

from __future__ import annotations

from email import message_from_bytes, policy
from pathlib import Path

from smartapply.email_agent import (
    export_eml,
)


# ---------------- .eml export ----------------


def test_export_eml_creates_valid_message(tmp_path: Path) -> None:
    out = tmp_path / "draft.eml"
    export_eml(
        subject="Application",
        body="Hello,\n\nPlease find attached.",
        sender="nour.lachtar@dauphine.eu",
        recipient="recrutement@acme.com",
        out_path=out,
    )
    raw = out.read_bytes()
    msg = message_from_bytes(raw)
    assert msg["Subject"] == "Application"
    assert msg["From"] == "nour.lachtar@dauphine.eu"
    assert msg["To"] == "recrutement@acme.com"


def test_export_eml_can_include_cc(tmp_path: Path) -> None:
    out = tmp_path / "draft.eml"
    export_eml(
        subject="Application",
        body="Hello",
        sender="nour.lachtar@dauphine.eu",
        recipient="recrutement@acme.com",
        cc_recipient="head.data@acme.com",
        out_path=out,
    )

    msg = message_from_bytes(out.read_bytes())
    assert msg["To"] == "recrutement@acme.com"
    assert msg["Cc"] == "head.data@acme.com"


def test_export_eml_attaches_cv(tmp_path: Path) -> None:
    cv = tmp_path / "cv.docx"
    cv.write_bytes(b"PK\x03\x04 fake docx")
    out = tmp_path / "draft.eml"
    export_eml(
        subject="App",
        body="hi",
        sender="a@b.com",
        recipient="c@d.com",
        cv_path=cv,
        out_path=out,
    )
    msg = message_from_bytes(out.read_bytes(), policy=policy.default)
    attachments = [p for p in msg.iter_attachments()]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "cv.docx"


def test_export_eml_attaches_multiple_documents(tmp_path: Path) -> None:
    cv = tmp_path / "cv.pdf"
    letter = tmp_path / "letter.pdf"
    cv.write_bytes(b"%PDF-1.4 cv")
    letter.write_bytes(b"%PDF-1.4 letter")
    out = tmp_path / "draft.eml"
    export_eml(
        subject="App",
        body="hi",
        sender="a@b.com",
        recipient="c@d.com",
        attachments=[cv, letter],
        out_path=out,
    )
    msg = message_from_bytes(out.read_bytes(), policy=policy.default)
    filenames = [p.get_filename() for p in msg.iter_attachments()]
    assert filenames == ["cv.pdf", "letter.pdf"]
