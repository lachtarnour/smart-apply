"""Tests for the email_agent module."""

from __future__ import annotations

from email import message_from_bytes, policy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from smartapply.email_agent import (
    ContactFinder,
    EmailWriter,
    FoundContact,
    export_eml,
    score_email,
)
from smartapply.llm import EmailDraft, JobAnalysis, MockLLMProvider
from smartapply.profile import get_profile


# ---------------- Score email ----------------


def test_score_email_orders_recruitment_above_support() -> None:
    assert score_email("recrutement@acme.com") > score_email("contact@acme.com")
    assert score_email("contact@acme.com") > score_email("support@acme.com")
    assert score_email("jobs@acme.com") > score_email("hello@acme.com")


def test_score_email_blocks_noreply() -> None:
    assert score_email("noreply@acme.com") == 0.0
    assert score_email("no-reply@acme.com") == 0.0
    assert score_email("donotreply@acme.com") == 0.0


def test_score_email_neutral_for_personal_addresses() -> None:
    # firstname.lastname@ — neutral score
    assert 0.4 <= score_email("john.doe@acme.com") <= 0.6


# ---------------- ContactFinder ----------------


def test_contact_finder_extracts_and_ranks(mocker) -> None:
    pages = {
        "https://acme.com": "<html>Welcome</html>",
        "https://acme.com/careers": "<p>Apply at recrutement@acme.com or contact@acme.com</p>",
        "https://acme.com/contact": "<p>Support: support@acme.com, press: press@acme.com</p>",
    }

    def fake_get(url, headers=None, timeout=None):
        response = MagicMock()
        response.status_code = 200
        response.text = pages.get(url, "")
        return response

    mocker.patch("smartapply.email_agent.contact_finder.requests.get", side_effect=fake_get)
    finder = ContactFinder(max_pages=10, min_confidence=0.3)
    contacts = finder.find("https://acme.com/jobs/42")
    assert any(c.email == "recrutement@acme.com" for c in contacts)
    # Highest scoring contact comes first
    assert contacts[0].email == "recrutement@acme.com"
    # noreply, postmaster filtered
    assert all("noreply" not in c.email for c in contacts)


def test_contact_finder_returns_empty_on_404(mocker) -> None:
    response = MagicMock()
    response.status_code = 404
    response.text = ""
    mocker.patch("smartapply.email_agent.contact_finder.requests.get", return_value=response)
    finder = ContactFinder()
    assert finder.find("https://nothing.example") == []


def test_contact_finder_best_returns_top(mocker) -> None:
    mocker.patch(
        "smartapply.email_agent.contact_finder.requests.get",
        return_value=MagicMock(
            status_code=200,
            text="<p>hello@acme.com</p><p>recrutement@acme.com</p>",
        ),
    )
    best = ContactFinder(max_pages=1).best("https://acme.com")
    assert isinstance(best, FoundContact)
    assert best.email == "recrutement@acme.com"


# ---------------- EmailWriter ----------------


def _analysis() -> JobAnalysis:
    return JobAnalysis(
        role_type="Data Scientist",
        seniority="mid",
        domain="HealthTech",
        main_tasks=["RAG pipelines"],
        required_skills=["Python"],
        nice_to_have=[],
        match_reasons=["NLP background"],
        risks=[],
        cv_keywords_to_include=["RAG"],
    )


def test_email_writer_returns_draft() -> None:
    MockLLMProvider.clear()
    MockLLMProvider.register(
        "email_writer",
        EmailDraft(
            subject="Application: Data Scientist NLP",
            body="Hello,\n\nI am writing to express my interest..." + " word" * 25,
        ),
    )
    writer = EmailWriter(get_profile())
    draft = writer.write(
        analysis=_analysis(),
        job_title="Data Scientist NLP",
        job_company="Acme",
    )
    assert draft.subject.startswith("Application")
    assert "interest" in draft.body


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
