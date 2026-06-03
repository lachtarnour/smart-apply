"""Tests for the scrapers module — manual, SerpApi, France Travail.

Real HTTP calls are forbidden in tests. Everything goes through mocks of
``requests.get`` / ``requests.post`` to keep tests offline and free.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from smartapply.scrapers import (
    FranceTravailScraper,
    ManualScraper,
    RawJob,
    ScraperConfigError,
    SerpApiGoogleJobsScraper,
    available_scrapers,
    get_scraper,
    make_external_id,
)


# ============================ Helpers ============================

def _mock_response(payload: dict[str, Any], status_code: int = 200) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.text = ""
    response.raise_for_status = MagicMock()
    return response


# ============================ make_external_id ============================

def test_external_id_is_deterministic_and_namespaced() -> None:
    a = make_external_id("serpapi", "Data Scientist", "Acme", "Paris")
    b = make_external_id("serpapi", "data scientist", "ACME ", "Paris")
    c = make_external_id("francetravail", "Data Scientist", "Acme", "Paris")
    assert a == b  # case + whitespace insensitive
    assert a != c  # namespace matters
    assert a.startswith("serpapi:")


# ============================ Registry ============================

def test_registry_lists_available_scrapers() -> None:
    names = available_scrapers()
    assert "serpapi" in names
    assert "francetravail" in names


def test_get_scraper_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_scraper("linkedin")


# ============================ ManualScraper ============================

def test_manual_scraper_from_text() -> None:
    s = ManualScraper()
    job = s.from_text(
        "We are looking for a Data Scientist with PyTorch experience.",
        title="Data Scientist",
        company="Acme AI",
        location="Paris",
    )
    assert job.title == "Data Scientist"
    assert job.company == "Acme AI"
    assert job.location == "Paris"
    assert job.source == "manual"
    assert job.external_id.startswith("manual:")


def test_manual_scraper_empty_text_rejected() -> None:
    s = ManualScraper()
    with pytest.raises(ValueError):
        s.from_text("   ", title="X", company="Y")


def test_manual_scraper_from_url_extracts_title_and_text(mocker) -> None:
    html = """
    <html>
      <head><title>Senior NLP Engineer — Acme AI</title>
            <meta property="og:site_name" content="Acme AI" />
      </head>
      <body>
        <h1>Senior NLP Engineer</h1>
        <p>We build RAG pipelines at scale.</p>
        <script>console.log('noise')</script>
      </body>
    </html>
    """
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    mocker.patch("smartapply.scrapers.manual.requests.get", return_value=response)

    job = ManualScraper().from_url("https://jobs.acme.ai/123")
    assert "Acme AI" in job.company
    assert "RAG pipelines" in job.description
    assert "console.log" not in job.description
    assert job.application_url == "https://jobs.acme.ai/123"


def test_manual_scraper_rejects_non_http_urls() -> None:
    with pytest.raises(ValueError):
        ManualScraper().from_url("file:///etc/passwd")


# ============================ SerpApi ============================

def _sample_serpapi_page(jobs: list[dict[str, Any]], next_token: str | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"jobs_results": jobs}
    if next_token:
        payload["serpapi_pagination"] = {"next_page_token": next_token}
    return payload


def test_serpapi_requires_api_key() -> None:
    s = SerpApiGoogleJobsScraper(api_key="")
    assert s.is_available() is False
    with pytest.raises(ScraperConfigError):
        next(s.search("data scientist"))


def test_serpapi_maps_jobs_and_paginates(mocker) -> None:
    page1_jobs = [
        {
            "title": "Data Scientist",
            "company_name": "Acme",
            "location": "Paris, France",
            "description": "Build pipelines.",
            "detected_extensions": {"schedule_type": "Full-time", "work_from_home": True},
            "apply_options": [{"title": "LinkedIn", "link": "https://linkedin.com/jobs/1"}],
            "job_id": "abc123",
            "job_highlights": [
                {"title": "Qualifications", "items": ["PyTorch", "5+ years"]},
            ],
        }
    ]
    page2_jobs = [
        {
            "title": "ML Engineer",
            "company_name": "Beta",
            "location": "Remote",
            "description": "Work on RAG.",
            "detected_extensions": {"schedule_type": "Contract"},
            "apply_options": [],
            "share_link": "https://google.com/search?...",
            "job_id": "xyz789",
        }
    ]
    pages = [
        _mock_response(_sample_serpapi_page(page1_jobs, next_token="tok-2")),
        _mock_response(_sample_serpapi_page(page2_jobs, next_token=None)),
    ]
    mocker.patch("smartapply.scrapers.serpapi.requests.get", side_effect=pages)

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    jobs = list(s.search("data scientist"))
    assert len(jobs) == 2
    first, second = jobs
    assert isinstance(first, RawJob)
    assert first.title == "Data Scientist"
    assert first.company == "Acme"
    assert first.contract_type == "Full-time"
    assert first.remote_policy == "remote"
    assert first.application_url == "https://linkedin.com/jobs/1"
    assert "PyTorch" in first.description  # highlights appended
    assert first.external_id.startswith("serpapi:")
    assert second.contract_type == "Contract"
    assert second.application_url.startswith("https://google.com")


def test_serpapi_external_id_uses_application_url_when_job_id_missing() -> None:
    scraper = SerpApiGoogleJobsScraper(api_key="fake")
    first = scraper._to_raw_job(
        {
            "title": "Data Scientist",
            "company_name": "Acme",
            "location": "Paris, France",
            "description": "Build ML pipelines.",
            "apply_options": [{"title": "ATS", "link": "https://acme.com/jobs/1"}],
        }
    )
    second = scraper._to_raw_job(
        {
            "title": "Data Scientist",
            "company_name": "Acme",
            "location": "Paris, France",
            "description": "Build ML pipelines.",
            "apply_options": [{"title": "ATS", "link": "https://acme.com/jobs/2"}],
        }
    )

    assert first is not None
    assert second is not None
    assert first.external_id != second.external_id


def test_serpapi_respects_max_results(mocker) -> None:
    jobs_page = [
        {"title": f"Role {i}", "company_name": "Acme", "description": "x", "job_id": str(i)}
        for i in range(10)
    ]
    mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response(_sample_serpapi_page(jobs_page, "tok")),
    )
    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    out = list(s.search("data", max_results=3))
    assert len(out) == 3


def test_serpapi_max_results_drives_page_count(mocker) -> None:
    def make_page(page: int, next_token: str | None):
        jobs_page = [
            {
                "title": f"Role {page}-{i}",
                "company_name": "Acme",
                "description": "x",
                "job_id": f"{page}-{i}",
            }
            for i in range(10)
        ]
        return _mock_response(_sample_serpapi_page(jobs_page, next_token))

    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            make_page(1, "tok-2"),
            make_page(2, "tok-3"),
            make_page(3, None),
        ],
    )
    s = SerpApiGoogleJobsScraper(api_key="fake", max_pages=1, hl="fr")
    out = list(s.search("data", max_results=25))
    assert len(out) == 25
    assert get_mock.call_count == 3


def test_serpapi_defaults_to_last_week_filter(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response({"jobs_results": []}),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    list(s.search("data scientist"))

    params = get_mock.call_args.kwargs["params"]
    assert params["q"] == "data scientist in the last week"
    assert "uds" not in params


def test_serpapi_can_search_multiple_languages(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(
                _sample_serpapi_page(
                    [
                        {
                            "title": "Machine Learning Engineer",
                            "company_name": "Acme",
                            "description": "Build ML systems.",
                            "job_id": "en-1",
                        }
                    ],
                    None,
                )
            ),
            _mock_response(
                _sample_serpapi_page(
                    [
                        {
                            "title": "Ingénieur Machine Learning",
                            "company_name": "Beta",
                            "description": "Construire des systèmes ML.",
                            "job_id": "fr-1",
                        }
                    ],
                    None,
                )
            ),
        ],
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="en,fr")
    jobs = list(s.search("Machine Learning Engineer", max_results=10, date_posted="any"))

    assert [call.kwargs["params"]["hl"] for call in get_mock.mock_calls] == ["en", "fr"]
    assert [job.title for job in jobs] == [
        "Machine Learning Engineer",
        "Ingénieur Machine Learning",
    ]


def test_serpapi_date_filter_can_be_disabled_or_combined_with_uds(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response({"jobs_results": []}),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    list(s.search("data scientist", date_posted="any", uds="raw-filter"))

    params = get_mock.call_args.kwargs["params"]
    assert params["q"] == "data scientist"
    assert params["uds"] == "raw-filter"


def test_serpapi_stops_when_no_results(mocker) -> None:
    mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response({"jobs_results": []}),
    )
    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    assert list(s.search("data")) == []


# ============================ France Travail ============================

def test_francetravail_requires_credentials() -> None:
    s = FranceTravailScraper(client_id="", client_secret="")
    assert s.is_available() is False
    with pytest.raises(ScraperConfigError):
        next(s.search("data"))


def test_francetravail_authenticates_and_maps(mocker) -> None:
    token_response = _mock_response({"access_token": "T0K3N", "expires_in": 1500})
    search_response = _mock_response(
        {
            "resultats": [
                {
                    "id": "OFR-001",
                    "intitule": "Data Scientist H/F",
                    "entreprise": {"nom": "Acme SA"},
                    "lieuTravail": {"libelle": "75 - Paris"},
                    "description": "Construire des pipelines ML.",
                    "competences": [
                        {"libelle": "Python", "exigence": "E"},
                        {"libelle": "PyTorch", "exigence": "S"},
                    ],
                    "typeContratLibelle": "CDI",
                    "dateCreation": "2026-05-01T12:00:00.000Z",
                    "origineOffre": {"urlOrigine": "https://candidat.francetravail.fr/offres/OFR-001"},
                }
            ]
        }
    )
    empty_response = _mock_response({"resultats": []})

    mocker.patch(
        "smartapply.scrapers.francetravail.requests.post",
        return_value=token_response,
    )
    mocker.patch(
        "smartapply.scrapers.francetravail.requests.get",
        side_effect=[search_response, empty_response],
    )

    s = FranceTravailScraper(client_id="cid", client_secret="csec")
    jobs = list(s.search("data scientist", location="Paris"))
    assert len(jobs) == 1
    j = jobs[0]
    assert j.title == "Data Scientist H/F"
    assert j.company == "Acme SA"
    assert j.contract_type == "CDI"
    assert j.location == "75 - Paris"
    assert "PyTorch" in j.description
    assert j.published_date is not None
    assert j.application_url and "OFR-001" in j.application_url


def test_francetravail_token_caching(mocker) -> None:
    token_response = _mock_response({"access_token": "T0K3N", "expires_in": 1500})
    empty_response = _mock_response({"resultats": []})
    post_mock = mocker.patch(
        "smartapply.scrapers.francetravail.requests.post", return_value=token_response
    )
    mocker.patch(
        "smartapply.scrapers.francetravail.requests.get", return_value=empty_response
    )

    s = FranceTravailScraper(client_id="cid", client_secret="csec")
    list(s.search("a"))
    list(s.search("b"))
    # token endpoint should only be hit once thanks to caching
    assert post_mock.call_count == 1
