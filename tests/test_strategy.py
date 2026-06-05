"""Tests for the application-strategy decision logic."""

from __future__ import annotations

from smartapply.utils.strategy import decide_strategy


def test_small_company_with_contact_is_email_only() -> None:
    assert (
        decide_strategy(
            company_size="small",
            has_contact_email=True,
            has_application_url=True,
        )
        == "email_only"
    )


def test_large_company_with_contact_is_email_and_form() -> None:
    """The whole point of company_size: large = always submit via ATS too."""
    assert (
        decide_strategy(
            company_size="large",
            has_contact_email=True,
            has_application_url=True,
        )
        == "email_and_form"
    )


def test_large_company_without_application_url_is_email_only() -> None:
    assert (
        decide_strategy(
            company_size="large",
            has_contact_email=True,
            has_application_url=False,
        )
        == "email_only"
    )


def test_no_contact_falls_back_to_form_only() -> None:
    """If we couldn't find an email contact, the ATS form is the only path."""
    for size in ("large", "small", "unknown"):
        for has_application_url in (True, False):
            assert (
                decide_strategy(
                    company_size=size,
                    has_contact_email=False,
                    has_application_url=has_application_url,
                )
                == "form_only"
            )


def test_unknown_company_with_contact_defaults_to_email_only() -> None:
    """When the LLM cannot classify the company, we don't force a form."""
    assert (
        decide_strategy(
            company_size="unknown",
            has_contact_email=True,
            has_application_url=True,
        )
        == "email_only"
    )
