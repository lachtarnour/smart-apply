"""Tests for the Snov.io contact provider."""

from __future__ import annotations

from unittest.mock import MagicMock

from smartapply.config import get_settings
from smartapply.email_agent.contact_providers import (
    SnovContactProvider,
    contact_lookup_key,
    default_contact_chain,
    domain_from_url,
    score_email,
)


def test_score_email_orders_recruitment_above_support() -> None:
    assert score_email("recrutement@acme.com") > score_email("contact@acme.com")
    assert score_email("contact@acme.com") > score_email("support@acme.com")
    assert score_email("jobs@acme.com") > score_email("hello@acme.com")


def test_score_email_blocks_noreply() -> None:
    assert score_email("noreply@acme.com") == 0.0
    assert score_email("no-reply@acme.com") == 0.0
    assert score_email("donotreply@acme.com") == 0.0


def test_score_email_neutral_for_personal_addresses() -> None:
    assert 0.4 <= score_email("john.doe@acme.com") <= 0.6


def test_domain_from_url_strips_common_job_subdomain() -> None:
    assert domain_from_url("https://jobs.acme.ai/roles/42") == "acme.ai"
    assert domain_from_url("https://www.example.com/jobs") == "example.com"


def test_contact_lookup_key_uses_company_for_ats_domains() -> None:
    assert (
        contact_lookup_key("Acme AI", "https://boards.greenhouse.io/acme/jobs/123")
        == "company:acme ai"
    )
    assert contact_lookup_key("Acme AI", "https://acme.ai/jobs/123") == "domain:acme.ai"


def test_snov_provider_uses_generic_contacts_with_free_preflight(mocker) -> None:
    token = MagicMock()
    token.json.return_value = {"access_token": "token", "expires_in": 3600}
    token.raise_for_status = MagicMock()
    count = MagicMock()
    count.json.return_value = {"success": True, "webmail": False, "result": 3}
    count.raise_for_status = MagicMock()
    start = MagicMock()
    start.json.return_value = {"data": {"task_hash": "abc"}}
    start.raise_for_status = MagicMock()
    result = MagicMock()
    result.json.return_value = {
        "data": [
            {"email": "jobs@acme.com"},
            {"email": "sales@acme.com"},
        ]
    }
    result.raise_for_status = MagicMock()
    requests_post = mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[token, count, start],
    )
    mocker.patch(
        "smartapply.email_agent.contact_providers.requests.get",
        return_value=result,
    )

    contacts = SnovContactProvider(client_id="id", client_secret="secret").find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
    )

    assert requests_post.call_args_list[2].args[0].endswith(
        "/domain-search/generic-contacts/start"
    )
    assert contacts[0].email == "jobs@acme.com"
    assert contacts[0].provider == "snov"


def test_snov_provider_skips_paid_lookup_when_preflight_is_empty(mocker) -> None:
    token = MagicMock()
    token.json.return_value = {"access_token": "token", "expires_in": 3600}
    token.raise_for_status = MagicMock()
    count = MagicMock()
    count.json.return_value = {"success": True, "webmail": False, "result": 0}
    count.raise_for_status = MagicMock()
    requests_post = mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[token, count],
    )
    requests_get = mocker.patch("smartapply.email_agent.contact_providers.requests.get")

    contacts = SnovContactProvider(client_id="id", client_secret="secret").find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
    )

    assert contacts == []
    assert requests_post.call_count == 2
    requests_get.assert_not_called()


def test_default_contact_chain_uses_snov_only(monkeypatch) -> None:
    monkeypatch.setenv("SNOV_CLIENT_ID", "id")
    monkeypatch.setenv("SNOV_CLIENT_SECRET", "secret")
    get_settings.cache_clear()

    try:
        chain = default_contact_chain()
        assert [provider.name for provider in chain.providers] == ["snov"]
    finally:
        get_settings.cache_clear()


# ============================================================
# ContactService._contact_lookup_url priority logic
# ============================================================


def test_contact_service_prefers_llm_hint_even_when_classified_ats() -> None:
    """If the LLM extracted a company domain from the text, we use it
    regardless of how it classified the application URL."""
    from smartapply.pipeline.contact_service import ContactService

    url = ContactService._contact_lookup_url(
        application_url="https://boards.greenhouse.io/acme/jobs/42",
        contact_domain_hint="acme.ai",
        contact_domain_kind="ats_or_job_board",
    )
    assert url == "https://acme.ai"


def test_contact_service_returns_none_for_ats_without_hint() -> None:
    """ATS URL + no LLM hint -> None so the provider falls back to
    name-based domain resolution. We never pass the ATS URL itself."""
    from smartapply.pipeline.contact_service import ContactService

    url = ContactService._contact_lookup_url(
        application_url="https://boards.greenhouse.io/acme/jobs/42",
        contact_domain_hint="",
        contact_domain_kind="ats_or_job_board",
    )
    assert url is None


def test_contact_service_uses_application_url_when_company_domain() -> None:
    from smartapply.pipeline.contact_service import ContactService

    url = ContactService._contact_lookup_url(
        application_url="https://acme.ai/jobs/42",
        contact_domain_hint="",
        contact_domain_kind="company_domain",
    )
    assert url == "https://acme.ai/jobs/42"


def test_contact_service_uses_local_contact_when_no_provider_configured(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import init_db, reset_engine_cache
    reset_engine_cache()
    init_db()

    from smartapply.database import session_scope
    from smartapply.database.repository import add_contact
    from smartapply.email_agent.contact_providers import ContactProviderChain
    from smartapply.pipeline.contact_service import ContactService

    with session_scope() as s:
        add_contact(
            s,
            company="Acme",
            email="jobs@acme.ai",
            source_url="manual",
            confidence=0.9,
        )

    contact = ContactService(ContactProviderChain([])).find(
        company="Acme",
        application_url="https://acme.ai/jobs/42",
    )

    assert contact is not None
    assert contact.email == "jobs@acme.ai"
    assert contact.provider == "db_cache"

    reset_engine_cache()
    get_settings.cache_clear()


def test_snov_falls_back_to_company_name_resolution(mocker) -> None:
    """End-to-end check: when only the company name is known, Snov hits the
    company-domain-by-name endpoint, then proceeds with email enrichment.
    """
    token = MagicMock()
    token.json.return_value = {"access_token": "token", "expires_in": 3600}
    token.raise_for_status = MagicMock()
    domain_start = MagicMock()
    domain_start.json.return_value = {"data": {"task_hash": "domain-hash"}}
    domain_start.raise_for_status = MagicMock()
    domain_result = MagicMock()
    domain_result.json.return_value = {
        "data": [{"result": {"domain": "acme.ai"}}]
    }
    domain_result.raise_for_status = MagicMock()
    count = MagicMock()
    count.json.return_value = {"success": True, "webmail": False, "result": 5}
    count.raise_for_status = MagicMock()
    contacts_start = MagicMock()
    contacts_start.json.return_value = {"data": {"task_hash": "contacts-hash"}}
    contacts_start.raise_for_status = MagicMock()
    contacts_result = MagicMock()
    contacts_result.json.return_value = {"data": [{"email": "jobs@acme.ai"}]}
    contacts_result.raise_for_status = MagicMock()

    mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[token, domain_start, count, contacts_start],
    )
    mocker.patch(
        "smartapply.email_agent.contact_providers.requests.get",
        side_effect=[domain_result, contacts_result],
    )

    contacts = SnovContactProvider(client_id="id", client_secret="secret").find(
        company="Acme",
        application_url=None,
    )

    assert len(contacts) == 1
    assert contacts[0].email == "jobs@acme.ai"
