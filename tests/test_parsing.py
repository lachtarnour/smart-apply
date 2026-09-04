"""Tests for the parsing module."""

from __future__ import annotations

from smartapply.parsing import (
    clean_description,
    extract_sections,
    strip_html,
)


def test_strip_html_removes_tags_and_scripts() -> None:
    html = "<p>Hello <b>world</b><script>alert(1)</script></p>"
    out = strip_html(html)
    assert "alert" not in out
    assert "Hello" in out and "world" in out


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
