"""Tests for the email_agent module."""

from __future__ import annotations

import ast
import base64
from email import message_from_bytes, policy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from smartapply.email_agent import (
    export_eml,
)
from smartapply.email_agent.gmail_draft import (
    GmailDraftError,
    GmailDraftResult,
    build_mime_message,
    check_gmail_setup,
    create_draft,
    create_draft_result,
    dry_run_draft,
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


# ---------------- Gmail draft: MIME construction ----------------
# These tests exercise ``build_mime_message`` and ``dry_run_draft`` only —
# never the real ``google-api-python-client`` chain. The mock-based tests
# below cover the network path.


def test_gmail_build_mime_without_attachments_keeps_headers_and_body() -> None:
    """Test #1: MIME sans pièce jointe — headers + body simples."""
    msg = build_mime_message(
        subject="Application Data Scientist",
        body="Bonjour, je vous adresse ma candidature.",
        recipient="recrutement@acme.com",
        sender="nour.lachtar@dauphine.eu",
    )
    rendered = message_from_bytes(bytes(msg), policy=policy.default)
    assert rendered["Subject"] == "Application Data Scientist"
    assert rendered["To"] == "recrutement@acme.com"
    assert rendered["From"] == "nour.lachtar@dauphine.eu"
    assert list(rendered.iter_attachments()) == []


def test_gmail_build_mime_with_cv_and_letter_preserves_filenames(tmp_path: Path) -> None:
    """Test #2: MIME avec CV + lettre — les deux apparaissent en attachments."""
    cv = tmp_path / "cv.pdf"
    letter = tmp_path / "letter.pdf"
    cv.write_bytes(b"%PDF-1.4 cv bytes")
    letter.write_bytes(b"%PDF-1.4 letter bytes")
    msg = build_mime_message(
        subject="Candidature",
        body="Bonjour",
        recipient="contact@acme.com",
        cv_path=cv,
        attachment_paths=[letter],
    )
    rendered = message_from_bytes(bytes(msg), policy=policy.default)
    filenames = [p.get_filename() for p in rendered.iter_attachments()]
    # Order: explicit attachment_paths first, then cv_path (per implementation).
    assert sorted(filenames) == sorted(["cv.pdf", "letter.pdf"])


def test_gmail_build_mime_keeps_body_content_intact() -> None:
    """Test #3: le body est bien présent dans le MIME final, intact."""
    body = "Ligne 1\n\nLigne 2 avec accent é à ù.\n\nCordialement."
    msg = build_mime_message(
        subject="Sujet",
        body=body,
        recipient="contact@acme.com",
    )
    rendered = message_from_bytes(bytes(msg), policy=policy.default)
    text_part = rendered.get_body(preferencelist=("plain",))
    assert text_part is not None
    payload = text_part.get_content().rstrip("\n")
    assert payload == body


def test_gmail_build_mime_raises_when_attachment_is_missing(tmp_path: Path) -> None:
    """Test #4: une pièce jointe inexistante lève une erreur propre, pas
    une IOError brute. Le nom du fichier est dans le message mais pas son
    chemin absolu (anti-leak)."""
    ghost = tmp_path / "ghost.pdf"
    with pytest.raises(GmailDraftError) as ctx:
        build_mime_message(
            subject="Sujet",
            body="body",
            recipient="contact@acme.com",
            attachment_paths=[ghost],
        )
    assert "ghost.pdf" in str(ctx.value)
    assert str(tmp_path) not in str(ctx.value), "must not leak parent path"


@pytest.mark.parametrize(
    "missing_kwarg,error_marker",
    [
        ({"recipient": ""}, "Recipient"),
        ({"subject": "   "}, "Subject"),
        ({"body": ""}, "Body"),
    ],
)
def test_gmail_build_mime_rejects_empty_required_fields(
    missing_kwarg: dict[str, str], error_marker: str
) -> None:
    base = {
        "subject": "ok",
        "body": "ok",
        "recipient": "contact@acme.com",
    }
    base.update(missing_kwarg)
    with pytest.raises(GmailDraftError) as ctx:
        build_mime_message(**base)
    assert error_marker in str(ctx.value)


def test_gmail_build_mime_rejects_unsupported_attachment_extension(
    tmp_path: Path,
) -> None:
    binary = tmp_path / "payload.exe"
    binary.write_bytes(b"MZ")
    with pytest.raises(GmailDraftError):
        build_mime_message(
            subject="Sujet",
            body="body",
            recipient="contact@acme.com",
            attachment_paths=[binary],
        )


# ---------------- Gmail draft: dry-run (no network) ----------------


def test_gmail_dry_run_returns_preview_without_touching_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tests #5 + #8: dry-run renvoie un encodage base64URL valide *et*
    ne touche jamais le module ``googleapiclient.discovery``."""

    def _explode(*args, **kwargs):  # noqa: ANN001, ANN201, ARG001
        raise AssertionError("dry_run_draft must not import or call googleapiclient")

    # Patch the module the gmail_draft pulls on real-call paths. The
    # name is imported lazily inside ``_ensure_libs`` so monkeypatching
    # at the lazy-import site catches any accidental access.
    import sys

    if "googleapiclient" in sys.modules:  # pragma: no cover - cosmetic
        monkeypatch.delitem(sys.modules, "googleapiclient", raising=False)
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft._get_credentials",
        _explode,
    )
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft._ensure_libs",
        _explode,
    )

    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 cv")

    preview = dry_run_draft(
        subject="Application Data",
        body="Body content with enough characters to verify the preview.",
        recipient="contact@acme.com",
        cv_path=cv,
    )

    assert preview.to == "contact@acme.com"
    assert preview.subject == "Application Data"
    assert preview.attachment_names == ["cv.pdf"]
    assert preview.encoded_size_bytes > 0
    # base64url alphabet check on a reconstructed raw payload:
    # encoded_size_bytes is the encoded MIME size; rebuild the
    # message and confirm it round-trips through urlsafe base64.
    msg_bytes = bytes(
        build_mime_message(
            subject="Application Data",
            body="Body content with enough characters to verify the preview.",
            recipient="contact@acme.com",
            cv_path=cv,
        )
    )
    encoded = base64.urlsafe_b64encode(msg_bytes).decode("utf-8")
    # urlsafe_b64encode uses ``-`` and ``_`` instead of ``+`` and ``/``.
    assert "+" not in encoded
    assert "/" not in encoded
    # Decoding back must round-trip without raising.
    assert base64.urlsafe_b64decode(encoded.encode("utf-8")) == msg_bytes


# ---------------- Gmail draft: real-call path with mock ----------------


def _make_fake_gmail_service(captured: dict[str, object]) -> MagicMock:
    """Build a MagicMock that records the kwargs passed to ``drafts.create``."""
    service = MagicMock(name="gmail_service")
    create_mock = MagicMock(name="drafts.create")
    create_mock.return_value.execute.return_value = {
        "id": "draft_abc123",
        "message": {"id": "msg_xyz789"},
    }
    drafts_mock = MagicMock(name="drafts")
    drafts_mock.create = create_mock
    users_mock = MagicMock(name="users")
    users_mock.return_value.drafts.return_value = drafts_mock
    service.users = users_mock
    captured["create"] = create_mock
    return service


def test_gmail_create_draft_calls_drafts_create_with_userId_me(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test #6: le seul endpoint touché est ``drafts.create``, et
    ``userId`` est bien ``"me"``."""
    captured: dict[str, object] = {}
    fake_service = _make_fake_gmail_service(captured)

    # Skip OAuth entirely — return a sentinel creds object.
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft._ensure_libs", lambda: None
    )
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft._get_credentials",
        lambda: MagicMock(name="creds"),
    )
    import googleapiclient.discovery as discovery

    monkeypatch.setattr(discovery, "build", lambda *a, **k: fake_service)

    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 cv")

    draft_id = create_draft(
        subject="Sujet test",
        body="Body content.",
        recipient="contact@acme.com",
        cv_path=cv,
    )
    assert draft_id == "draft_abc123"
    create_mock = captured["create"]
    assert create_mock.call_count == 1
    kwargs = create_mock.call_args.kwargs
    assert kwargs["userId"] == "me"
    raw = kwargs["body"]["message"]["raw"]
    # ``raw`` must be url-safe base64 and decodable back to a MIME blob.
    decoded = base64.urlsafe_b64decode(raw.encode("utf-8"))
    assert b"Subject: Sujet test" in decoded
    assert b"To: contact@acme.com" in decoded


def test_gmail_create_draft_result_returns_typed_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}
    fake_service = _make_fake_gmail_service(captured)
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft._ensure_libs", lambda: None
    )
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft._get_credentials",
        lambda: MagicMock(name="creds"),
    )
    import googleapiclient.discovery as discovery

    monkeypatch.setattr(discovery, "build", lambda *a, **k: fake_service)

    cv = tmp_path / "cv.pdf"
    cv.write_bytes(b"%PDF-1.4 cv")

    result = create_draft_result(
        subject="Sujet",
        body="Body content.",
        recipient="contact@acme.com",
        cv_path=cv,
    )
    assert isinstance(result, GmailDraftResult)
    assert result.status == "draft_created"
    assert result.draft_id == "draft_abc123"
    assert result.message_id == "msg_xyz789"
    assert result.to == "contact@acme.com"
    assert result.subject == "Sujet"
    assert result.attachment_names == ["cv.pdf"]
    assert result.error is None


def test_gmail_create_draft_result_reports_validation_failures_without_raising() -> None:
    """``create_draft_result`` must never raise — UI consumes the dict."""
    result = create_draft_result(
        subject="",  # invalid
        body="ok",
        recipient="contact@acme.com",
    )
    assert result.status == "error"
    assert result.error is not None
    assert "Subject" in result.error
    assert result.draft_id is None
    assert result.message_id is None


def test_gmail_check_setup_reports_missing_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("smartapply.email_agent.gmail_draft._ensure_libs", lambda: None)
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft.get_settings",
        lambda: SimpleNamespace(
            gmail_credentials_path=tmp_path / "credentials.json",
            gmail_token_path=tmp_path / "token.json",
            gmail_user="me",
        ),
    )

    status = check_gmail_setup()

    assert status.dependencies_installed is True
    assert status.credentials_exists is False
    assert status.token_exists is False
    assert status.ready_for_auth is False
    assert status.issues


def test_gmail_check_setup_ready_for_first_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    credentials = tmp_path / "credentials.json"
    credentials.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("smartapply.email_agent.gmail_draft._ensure_libs", lambda: None)
    monkeypatch.setattr(
        "smartapply.email_agent.gmail_draft.get_settings",
        lambda: SimpleNamespace(
            gmail_credentials_path=credentials,
            gmail_token_path=tmp_path / "token.json",
            gmail_user="me",
        ),
    )

    status = check_gmail_setup()

    assert status.credentials_exists is True
    assert status.token_exists is False
    assert status.ready_for_auth is True
    assert status.issues == []


# ---------------- Gmail draft: anti-send static guard ----------------


def test_gmail_draft_module_has_no_send_calls() -> None:
    """Test #7: walking the ``gmail_draft`` AST, no method named
    ``send`` (or ``messages.send`` / ``drafts.send``) is ever called.

    This guard is the contract that lets us guarantee SmartApply never
    sends an email automatically: if a future edit adds such a call,
    this test fails before the change can be merged.
    """
    import smartapply.email_agent.gmail_draft as gmail_draft_module

    source = Path(gmail_draft_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_attribute_names = {"send"}
    forbidden_chains = {
        ("messages", "send"),
        ("drafts", "send"),
    }

    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        # Reject any ``.send(...)`` call regardless of receiver: this
        # blocks ``service.users().messages().send(...)`` and friends.
        if func.attr in forbidden_attribute_names:
            bad.append(ast.unparse(node))
            continue
        # Detect chained ``.messages.send`` / ``.drafts.send`` even when
        # the AST is split across attribute nodes.
        if isinstance(func.value, ast.Attribute):
            chain = (func.value.attr, func.attr)
            if chain in forbidden_chains:
                bad.append(ast.unparse(node))

    assert not bad, (
        "gmail_draft.py must never call .send / .messages.send / .drafts.send. "
        f"Found: {bad}"
    )


# ---------------- UI / workflow label contract ----------------


def test_workflow_step5_uses_creer_brouillon_label_not_envoyer() -> None:
    """Test #9: the only Gmail-creating button is labelled "Créer le
    brouillon Gmail" (no ``"Envoyer"`` button anywhere in step 5)."""
    workflow_path = (
        Path(__file__).resolve().parent.parent
        / "smartapply"
        / "app"
        / "pages"
        / "0_Workflow.py"
    )
    source = workflow_path.read_text(encoding="utf-8")
    assert "Créer le brouillon Gmail" in source, (
        "Step 5 must expose a button labelled exactly 'Créer le brouillon Gmail'."
    )
    # Tokenize to ignore the "envoi" / "envoyer" mentions in headings or
    # navigation breadcrumbs; we only care about button labels.
    tree = ast.parse(source)
    button_labels: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "button"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            button_labels.append(node.args[0].value)
    forbidden = [
        label
        for label in button_labels
        if "envoyer" in label.lower().replace("é", "e")
        and "marquer" not in label.lower()
    ]
    assert not forbidden, (
        f"Workflow must not expose a 'Envoyer' button; found: {forbidden}"
    )
