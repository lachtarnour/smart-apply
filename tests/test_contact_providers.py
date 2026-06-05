"""Tests for the Anymail Finder contact provider."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from smartapply.config import get_settings
from smartapply.email_agent.contact_providers import (
    AnymailFinderContactProvider,
    ContactCandidate,
    ContactProvider,
    ContactProviderChain,
    contact_lookup_key,
    default_contact_chain,
    domain_from_url,
    is_company_domain,
    is_job_board_domain,
    is_recruitment_generic_email,
    is_reliable_company_domain,
    is_suspicious_contact_domain,
    score_email,
)
from smartapply.utils.location import canonical_french_city, french_city_mismatch


class RejectingVerifierProvider(ContactProvider):
    name = "rejecting_verifier"

    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        return []

    def verify_email(self, email: str) -> bool | None:
        return False


class RecordingContactProvider(ContactProvider):
    name = "recording"

    def __init__(self) -> None:
        self.calls: list[dict[str, str | None]] = []

    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        self.calls.append(
            {
                "company": company,
                "application_url": application_url,
                "job_location": job_location,
            }
        )
        return [
            ContactCandidate(
                email="jobs@example.com",
                source_url="recording",
                confidence=0.95,
                provider=self.name,
            )
        ]


@pytest.fixture
def contact_service_factory(tmp_path, monkeypatch):
    def factory(provider: ContactProvider):
        db_path = tmp_path / "contact_strategy.db"
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
        monkeypatch.setenv("CONTACT_CACHE_ENABLED", "false")
        get_settings.cache_clear()
        from smartapply.database.session import init_db, reset_engine_cache

        reset_engine_cache()
        init_db()

        from smartapply.email_agent.contact_providers import ContactProviderChain
        from smartapply.pipeline.contact_service import ContactService

        return ContactService(ContactProviderChain([provider], min_confidence=0.0))

    yield factory

    from smartapply.database.session import reset_engine_cache

    reset_engine_cache()
    get_settings.cache_clear()


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
    assert domain_from_url("https://jobs.acme.co.uk/roles/42") == "acme.co.uk"
    assert domain_from_url("https://espace-emploi.agefiph.asso.fr/jobs/42") == (
        "agefiph.asso.fr"
    )


def test_non_company_domains_include_french_job_boards() -> None:
    assert is_job_board_domain("welcometothejungle.com")
    assert not is_company_domain("agefiph.asso.fr")
    assert not is_company_domain("espace-emploi.agefiph.asso.fr")
    assert not is_company_domain("cadremploi.fr")
    assert is_company_domain("acme.ai")
    assert is_suspicious_contact_domain("unknown-ats-platform.com")
    assert not is_reliable_company_domain("unknown-ats-platform.com")
    assert is_reliable_company_domain("acme.ai")


def test_recruitment_generic_detection() -> None:
    assert is_recruitment_generic_email("jobs@acme.com")
    assert is_recruitment_generic_email("recrutement@acme.com")
    assert not is_recruitment_generic_email("support@acme.com")


def test_contact_lookup_key_uses_company_for_ats_domains() -> None:
    assert (
        contact_lookup_key("Acme AI", "https://boards.greenhouse.io/acme/jobs/123")
        == "company:acme ai"
    )
    assert (
        contact_lookup_key("Acme AI", "https://apply.unknown-ats-platform.com/acme/123")
        == "company:acme ai"
    )
    assert contact_lookup_key("Acme AI", "https://acme.ai/jobs/123") == "domain:acme.ai"


def test_anymailfinder_stops_after_recruitment_generic_email(mocker) -> None:
    company = MagicMock()
    company.json.return_value = {
        "email_status": "valid",
        "valid_emails": ["jobs@acme.com", "support@acme.com"],
    }
    company.raise_for_status = MagicMock()
    requests_post = mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        return_value=company,
    )

    contacts = AnymailFinderContactProvider(api_key="key", timeout=5).find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
    )

    assert requests_post.call_count == 1
    assert requests_post.call_args_list[0].args[0].endswith("/find-email/company")
    assert requests_post.call_args_list[0].kwargs["headers"]["Authorization"] == "key"
    assert requests_post.call_args_list[0].kwargs["json"] == {
        "domain": "acme.com",
        "email_type": "generic",
    }
    assert contacts[0].email == "jobs@acme.com"
    assert contacts[0].provider == "anymailfinder"
    assert contacts[0].verified is True
    assert contacts[0].kind == "anymailfinder_company"
    assert contacts[0].decision_reason == "generic_recruitment_email"


def test_anymailfinder_uses_named_decision_maker_when_generic_is_weak(mocker) -> None:
    decision = MagicMock()
    decision.json.return_value = {
        "decision_maker_category": "hr",
        "email_status": "valid",
        "valid_email": "jane.hr@acme.com",
        "person_full_name": "Jane HR",
    }
    decision.raise_for_status = MagicMock()
    company = MagicMock()
    company.json.return_value = {
        "email_status": "valid",
        "valid_emails": ["support@acme.com"],
    }
    company.raise_for_status = MagicMock()
    mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[company, decision],
    )

    contacts = AnymailFinderContactProvider(api_key="key", timeout=5).find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
    )

    assert contacts[0].email == "jane.hr@acme.com"
    assert contacts[0].kind == "anymailfinder_decision_maker"


def test_anymailfinder_demotes_decision_maker_from_different_city(mocker) -> None:
    decision = MagicMock()
    decision.json.return_value = {
        "decision_maker_category": "hr",
        "email_status": "valid",
        "valid_email": "jane.hr@acme.com",
        "person_full_name": "Jane HR",
        "person_job_title": "Responsable RH Montpellier",
    }
    decision.raise_for_status = MagicMock()
    company = MagicMock()
    company.json.return_value = {
        "email_status": "valid",
        "valid_emails": ["contact@acme.com"],
    }
    company.raise_for_status = MagicMock()
    mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[company, decision],
    )

    chain = ContactProviderChain(
        [AnymailFinderContactProvider(api_key="key", timeout=5)],
        min_confidence=0.6,
    )
    contacts = chain.find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
        job_location="Paris, France",
    )

    assert [c.email for c in contacts] == ["contact@acme.com"]


def test_french_city_mismatch_only_when_both_cities_are_known() -> None:
    assert canonical_french_city("Paris, France") == "paris"
    assert canonical_french_city("Responsable RH Montpellier") == "montpellier"
    assert french_city_mismatch("Paris", "Talent Acquisition Montpellier")
    assert not french_city_mismatch("Paris", "DRH France")


def test_anymailfinder_uses_only_valid_company_emails(mocker) -> None:
    decision = MagicMock()
    decision.json.return_value = {
        "email_status": "not_found",
        "valid_email": None,
    }
    decision.raise_for_status = MagicMock()
    company = MagicMock()
    company.json.return_value = {
        "email_status": "valid",
        "emails": ["risky@acme.com"],
        "valid_emails": ["support@acme.com", "jobs@acme.com", "noreply@acme.com"],
    }
    company.raise_for_status = MagicMock()
    requests_post = mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[company],
    )

    contacts = AnymailFinderContactProvider(api_key="key", timeout=5).find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
    )

    assert contacts[0].email == "jobs@acme.com"
    assert "risky@acme.com" not in {c.email for c in contacts}
    assert "noreply@acme.com" not in {c.email for c in contacts}
    assert requests_post.call_count == 1


def test_anymailfinder_verify_email_endpoint(mocker) -> None:
    response = MagicMock()
    response.json.return_value = {
        "credits_charged": 0.2,
        "email_status": "valid",
    }
    response.raise_for_status = MagicMock()
    requests_post = mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        return_value=response,
    )

    result = AnymailFinderContactProvider(api_key="key", timeout=5).verify_email(
        "manual@acme.com"
    )

    assert result is True
    assert requests_post.call_args_list[0].args[0].endswith("/verify-email")
    assert requests_post.call_args_list[0].kwargs["json"] == {"email": "manual@acme.com"}


def test_default_contact_chain_uses_anymailfinder_only(monkeypatch) -> None:
    monkeypatch.setenv("ANYMAILFINDER_API_KEY", "key")
    get_settings.cache_clear()

    try:
        chain = default_contact_chain()
        assert [provider.name for provider in chain.providers] == ["anymailfinder"]
    finally:
        get_settings.cache_clear()


# ============================================================
# ContactService._contact_lookup_url priority logic
# ============================================================


def test_contact_service_ignores_llm_hint_when_classified_ats() -> None:
    """ATS URL + ATS-classified hint -> None so the provider falls back to
    name-based domain resolution. We never pass the platform domain."""
    from smartapply.pipeline.contact_service import ContactService

    url = ContactService._contact_lookup_url(
        application_url="https://boards.greenhouse.io/acme/jobs/42",
        contact_domain_hint="acme.ai",
        contact_domain_kind="ats_or_job_board",
    )
    assert url is None


def test_contact_service_uses_company_hint_when_classified_company_domain() -> None:
    from smartapply.pipeline.contact_service import ContactService

    url = ContactService._contact_lookup_url(
        application_url="https://boards.greenhouse.io/acme/jobs/42",
        contact_domain_hint="acme.ai",
        contact_domain_kind="company_domain",
        job_description="Pour postuler, consultez www.acme.ai.",
    )
    assert url == "https://acme.ai"


def test_contact_service_blocks_known_job_board_even_if_misclassified() -> None:
    from smartapply.pipeline.contact_service import ContactService

    url = ContactService._contact_lookup_url(
        application_url="https://espace-emploi.agefiph.asso.fr/jobs/42",
        contact_domain_hint="",
        contact_domain_kind="company_domain",
    )
    assert url is None


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


def test_contact_service_scopes_cache_key_by_job_city() -> None:
    from smartapply.pipeline.contact_service import ContactService

    assert (
        ContactService._location_scoped_lookup_key("domain:acme.ai", "Paris, France")
        == "domain:acme.ai|loc:paris"
    )
    assert (
        ContactService._location_scoped_lookup_key("domain:acme.ai", "Remote France")
        == "domain:acme.ai"
    )


def test_contact_strategy_uses_direct_company_url(contact_service_factory) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Acme",
        application_url="https://acme.ai/jobs/123",
        job_description="Build ML products.",
        analysis={},
        job_location="Paris, France",
    )

    assert provider.calls == [
        {
            "company": "Acme",
            "application_url": "https://acme.ai/jobs/123",
            "job_location": "Paris, France",
        }
    ]
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "domain_from_company_url"
    assert service.last_lookup_decision.lookup_domain == "acme.ai"


@pytest.mark.parametrize(
    "url",
    [
        "https://welcometothejungle.com/fr/companies/acme/jobs/ml-engineer",
        "https://www.linkedin.com/jobs/view/123",
        "https://www.indeed.com/viewjob?jk=123",
        "https://candidat.francetravail.fr/offres/recherche/detail/123",
        "https://jobs.lever.co/acme/123",
        "https://boards.greenhouse.io/acme/jobs/123",
        "https://apply.unknown-ats-platform.com/acme/123",
    ],
)
def test_contact_strategy_falls_back_to_company_for_job_boards_and_ats(
    contact_service_factory,
    url: str,
) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Acme",
        application_url=url,
        job_description="Build data products.",
        analysis={},
        job_location="Lyon, France",
    )

    assert provider.calls == [
        {
            "company": "Acme",
            "application_url": None,
            "job_location": "Lyon, France",
        }
    ]
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "company_name_fallback"


def test_contact_strategy_uses_company_domain_visible_in_offer_body(
    contact_service_factory,
) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Acme",
        application_url="https://candidat.francetravail.fr/offres/recherche/detail/123",
        job_description="Contact: recrutement@acme.fr. Site: www.acme.fr.",
        analysis={},
        job_location="Remote France",
    )

    assert provider.calls[0]["application_url"] == "https://acme.fr"
    assert provider.calls[0]["company"] == "Acme"
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "domain_from_offer_body"
    assert service.last_lookup_decision.lookup_domain == "acme.fr"


def test_contact_strategy_uses_validated_llm_hint_only_when_visible(
    contact_service_factory,
) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Acme",
        application_url="https://welcometothejungle.com/fr/companies/acme/jobs/123",
        job_description="Notre site entreprise est www.acme.fr.",
        analysis={
            "contact_domain_kind": "company_domain",
            "contact_domain_hint": "acme.fr",
        },
        job_location="Paris",
    )

    assert provider.calls[0]["application_url"] == "https://acme.fr"
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "domain_from_llm_hint_validated"


def test_contact_strategy_rejects_invented_llm_hint(contact_service_factory) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Skapa",
        application_url="https://welcometothejungle.com/fr/companies/skapa/jobs/123",
        job_description="Nous recrutons un Data Scientist.",
        analysis={
            "contact_domain_kind": "company_domain",
            "contact_domain_hint": "skapa.fr",
        },
        job_location="Paris",
    )

    assert provider.calls[0]["company"] == "Skapa"
    assert provider.calls[0]["application_url"] is None
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "company_name_fallback"
    assert "llm_domain_hint_not_visible" in service.last_lookup_decision.warnings


def test_contact_strategy_rejects_blacklisted_llm_hint(contact_service_factory) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Acme",
        application_url="https://welcometothejungle.com/fr/companies/acme/jobs/123",
        job_description="Nous recrutons.",
        analysis={
            "contact_domain_kind": "company_domain",
            "contact_domain_hint": "welcometothejungle.com",
        },
        job_location="Paris",
    )

    assert provider.calls[0]["application_url"] is None
    assert service.last_lookup_decision is not None
    assert "llm_domain_is_job_board" in service.last_lookup_decision.warnings


def test_contact_strategy_uses_extracted_company_when_company_is_generic(
    contact_service_factory,
) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Entreprise non communiquée",
        application_url="https://www.apec.fr/candidat/recherche-emploi.html",
        job_description="Le CEA recrute un ingénieur IA.",
        analysis={"extracted_company_name": "CEA"},
        job_location="Bruyères-le-Châtel",
    )

    assert provider.calls == [
        {
            "company": "CEA",
            "application_url": None,
            "job_location": "Bruyères-le-Châtel",
        }
    ]
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "company_name_from_extracted_company"


def test_contact_strategy_manual_review_when_company_is_generic_without_extracted_name(
    contact_service_factory,
) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    contact = service.find(
        company="France Travail",
        application_url="https://candidat.francetravail.fr/offres/recherche/detail/123",
        job_description="Offre anonyme.",
        analysis={},
        job_location="Paris",
    )

    assert contact is None
    assert provider.calls == []
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "manual_review_no_reliable_company"


def test_contact_strategy_prefers_company_url_over_unconfirmed_llm_conflict(
    contact_service_factory,
) -> None:
    provider = RecordingContactProvider()
    service = contact_service_factory(provider)

    service.find(
        company="Acme",
        application_url="https://acme.ai/jobs/123",
        job_description="Build ML products.",
        analysis={
            "contact_domain_kind": "company_domain",
            "contact_domain_hint": "other-company.fr",
        },
        job_location="Paris",
    )

    assert provider.calls[0]["application_url"] == "https://acme.ai/jobs/123"
    assert service.last_lookup_decision is not None
    assert service.last_lookup_decision.strategy == "domain_from_company_url"
    assert "llm_domain_hint_not_visible" in service.last_lookup_decision.warnings
    assert "llm_domain_hint_conflicts_with_application_domain" in (
        service.last_lookup_decision.warnings
    )


def test_domains_visible_in_text_avoids_regular_sentence_false_domains() -> None:
    from smartapply.pipeline.contact_service import domains_visible_in_text

    text = "Missions: analyses automatisées. Missions alignement métier. www.acme.fr"

    assert domains_visible_in_text(text) == ["acme.fr"]


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


def test_contact_service_does_not_reuse_external_job_board_contact(
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
            company="Manpower",
            email="c-metais@agefiph.asso.fr",
            source_url="anymailfinder:decision-maker:agefiph.fr",
            confidence=0.96,
        )

    contact = ContactService(ContactProviderChain([])).find(
        company="Manpower",
        application_url="https://manpower.fr/jobs/42",
        job_location="Paris",
    )

    assert contact is None

    reset_engine_cache()
    get_settings.cache_clear()


def test_contact_service_rejects_manual_contact_when_optional_verification_fails(
    tmp_path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANYMAILFINDER_VERIFY_MANUAL_CONTACTS", "true")
    from smartapply.config import get_settings
    get_settings.cache_clear()
    from smartapply.database.session import init_db, reset_engine_cache
    reset_engine_cache()
    init_db()

    from smartapply.database import session_scope
    from smartapply.database.repository import add_contact
    from smartapply.pipeline.contact_service import ContactService

    with session_scope() as s:
        add_contact(
            s,
            company="Acme",
            email="manual@acme.ai",
            source_url="manual",
            confidence=1.0,
        )

    contact = ContactService(ContactProviderChain([RejectingVerifierProvider()])).find(
        company="Acme",
        application_url="https://acme.ai/jobs/42",
    )

    assert contact is None

    reset_engine_cache()
    get_settings.cache_clear()


def test_contact_service_does_not_reuse_local_decision_maker_from_other_city(
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
            email="jane.hr@acme.ai",
            source_url="anymailfinder:decision-maker:acme.ai",
            confidence=0.96,
            full_name="Jane HR",
            job_title="Responsable RH Montpellier",
            location_hint="montpellier",
        )

    contact = ContactService(ContactProviderChain([])).find(
        company="Acme",
        application_url="https://acme.ai/jobs/42",
        job_location="Paris, France",
    )

    assert contact is None

    reset_engine_cache()
    get_settings.cache_clear()


def test_anymailfinder_uses_company_name_when_url_is_ats(mocker) -> None:
    decision = MagicMock()
    decision.json.return_value = {
        "email_status": "not_found",
        "valid_email": None,
    }
    decision.raise_for_status = MagicMock()
    company = MagicMock()
    company.json.return_value = {
        "email_status": "valid",
        "valid_emails": ["jobs@acme.ai"],
    }
    company.raise_for_status = MagicMock()

    requests_post = mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[company],
    )

    contacts = AnymailFinderContactProvider(api_key="key", timeout=5).find(
        company="Acme",
        application_url=None,
    )

    assert len(contacts) == 1
    assert contacts[0].email == "jobs@acme.ai"
    assert requests_post.call_args_list[0].kwargs["json"]["company_name"] == "Acme"


def test_anymailfinder_keeps_company_result_when_decision_maker_fails(mocker) -> None:
    import requests

    company = MagicMock()
    company.json.return_value = {
        "email_status": "valid",
        "valid_emails": ["contact@acme.com"],
    }
    company.raise_for_status = MagicMock()
    mocker.patch(
        "smartapply.email_agent.contact_providers.requests.post",
        side_effect=[company, requests.RequestException("boom")],
    )

    contacts = AnymailFinderContactProvider(api_key="key", timeout=5).find(
        company="Acme",
        application_url="https://acme.com/jobs/42",
    )

    assert [c.email for c in contacts] == ["contact@acme.com"]
