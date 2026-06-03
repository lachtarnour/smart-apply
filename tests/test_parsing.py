"""Tests for the parsing module."""

from __future__ import annotations

from smartapply.parsing import (
    clean_description,
    drop_boilerplate,
    extract_sections,
    normalize_whitespace,
    strip_html,
)


def test_strip_html_removes_tags_and_scripts() -> None:
    html = "<p>Hello <b>world</b><script>alert(1)</script></p>"
    out = strip_html(html)
    assert "alert" not in out
    assert "Hello" in out and "world" in out


def test_strip_html_passthrough_when_no_tags() -> None:
    assert strip_html("plain text") == "plain text"


def test_normalize_whitespace_collapses() -> None:
    raw = "Hello   world   here\n\n\n\nLine"
    assert "  " not in normalize_whitespace(raw)
    assert "\n\n\n" not in normalize_whitespace(raw)


def test_drop_boilerplate_removes_equal_opportunity_blocks() -> None:
    text = (
        "Job description\n"
        "Build pipelines.\n\n"
        "Equal opportunity employer\n"
        "Lorem ipsum dolor.\n\n"
        "Benefits\n"
        "- Free coffee\n"
        "- Health insurance\n\n"
        "Responsibilities\n"
        "- Ship features"
    )
    cleaned = drop_boilerplate(text)
    assert "Build pipelines" in cleaned
    assert "Ship features" in cleaned
    assert "Free coffee" not in cleaned
    assert "Equal opportunity" not in cleaned


def test_clean_description_reduces_size_meaningfully() -> None:
    noisy = (
        "<p>Looking for a <b>Data Scientist</b>.</p>\n"
        "Equal opportunity employer.\n"
        "Reasonable accommodation will be provided.\n"
        "Compensation: $100k\n"
        "About us\n"
        "We are an amazing company with great values.\n"
        "Responsibilities\n"
        "- Build ML pipelines"
    )
    cleaned = clean_description(noisy)
    assert "Data Scientist" in cleaned
    assert "Build ML pipelines" in cleaned
    assert "Equal opportunity" not in cleaned
    assert "great values" not in cleaned
    assert "<p>" not in cleaned


def test_extract_sections_finds_responsibilities_and_profile() -> None:
    text = (
        "Missions\n"
        "Build RAG pipelines\n"
        "Deploy to AWS\n\n"
        "Profil recherché\n"
        "3+ years Python\n"
        "PyTorch experience\n\n"
        "Avantages\n"
        "Mutuelle, tickets restau"
    )
    sections = extract_sections(text)
    assert "responsibilities" in sections
    assert "RAG" in sections["responsibilities"]
    assert "profile" in sections
    assert "Python" in sections["profile"]
    assert "benefits" in sections
    assert "Mutuelle" in sections["benefits"]


def test_extract_sections_empty_when_no_headings() -> None:
    out = extract_sections("Just some blob of text without structure.")
    assert out == {}


def test_full_pipeline_handles_french_noisy_offer() -> None:
    raw = (
        "<div>\n"
        "<h2>Vos missions</h2>\n"
        "Vous concevez des pipelines de Machine Learning.\n"
        "Vous deployez sur AWS.\n\n"
        "<h2>Profil recherché</h2>\n"
        "Bac+5 minimum.\n"
        "Maitrise de Python, PyTorch.\n\n"
        "<h2>Avantages</h2>\n"
        "Tickets restaurant, mutuelle, télétravail.\n\n"
        "Conformément au RGPD, vos données seront conservées 2 ans.\n"
        "</div>"
    )
    cleaned = clean_description(raw)
    sections = extract_sections(cleaned)
    assert "Vos missions" in cleaned or "missions" in sections
    assert "RGPD" not in cleaned
    assert "responsibilities" in sections
    assert "AWS" in sections["responsibilities"]
    assert "profile" in sections
    assert "Python" in sections["profile"]
