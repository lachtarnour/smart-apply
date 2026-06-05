"""Decide how a generated application should reach the recruiter.

We have three strategies, all driven by the LLM-extracted ``company_size``
plus the presence of an email contact:

- ``email_only``    : small/medium company + email contact found.
                      The email is enough — no ATS form to chase.
- ``email_and_form``: large company + email contact found.
                      Send the email AND submit the formal ATS application
                      (large companies usually require it).
- ``form_only``     : no email contact found — must go through the ATS form.

The user is the one who actually clicks "Send" / "Submit". We just label
the application so the dashboard and CLI know what's pending.
"""

from __future__ import annotations

from typing import Literal

ApplicationStrategy = Literal["email_only", "email_and_form", "form_only"]


def decide_strategy(
    *,
    company_size: str,
    has_contact_email: bool,
    has_application_url: bool,
) -> ApplicationStrategy:
    """Pick the strategy from the LLM signal and the discovered artifacts."""
    if not has_contact_email:
        return "form_only"
    if company_size == "large" and has_application_url:
        return "email_and_form"
    return "email_only"
