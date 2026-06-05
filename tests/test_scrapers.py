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


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8000/jobs",
        "http://127.0.0.1:8000/jobs",
        "http://10.0.0.5/jobs",
        "http://[::1]/jobs",
    ],
)
def test_manual_scraper_rejects_local_or_private_urls(url: str, mocker) -> None:  # noqa: ANN001
    get_mock = mocker.patch("smartapply.scrapers.manual.requests.get")

    with pytest.raises(ValueError):
        ManualScraper().from_url(url)

    assert get_mock.call_count == 0


def test_manual_scraper_rejects_host_resolving_to_private_ip(mocker) -> None:  # noqa: ANN001
    mocker.patch(
        "smartapply.scrapers.manual.socket.getaddrinfo",
        return_value=[(None, None, None, None, ("192.168.1.10", 0))],
    )
    get_mock = mocker.patch("smartapply.scrapers.manual.requests.get")

    with pytest.raises(ValueError):
        ManualScraper().from_url("https://jobs.example.test/42")

    assert get_mock.call_count == 0


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

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr", low_result_fallback_target=10)
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
    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr", low_result_fallback_target=10)
    out = list(s.search("data", max_results=3))
    assert len(out) == 3


def test_serpapi_respects_max_pages_even_with_max_results(mocker) -> None:
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
    s = SerpApiGoogleJobsScraper(
        api_key="fake",
        max_pages=1,
        hl="fr",
        low_result_fallback_target=10,
    )
    out = list(s.search("data", max_results=25))
    assert len(out) == 10
    assert get_mock.call_count == 1


def test_serpapi_does_not_low_result_fallback_without_max_results(mocker) -> None:
    jobs_page = [
        {
            "title": f"Data Scientist {i}",
            "company_name": "Acme",
            "description": "Build ML.",
            "job_id": f"strict-{i}",
        }
        for i in range(2)
    ]
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response(_sample_serpapi_page(jobs_page, None)),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr", low_result_fallback_target=10)
    jobs = list(
        s.search(
            "Data Scientist",
            chips="employment_type:FULLTIME",
            date_posted="week",
        )
    )

    assert len(jobs) == 2
    assert get_mock.call_count == 1


def test_serpapi_defaults_to_last_week_filter(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response({"jobs_results": []}),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    list(s.search("data scientist"))

    params = get_mock.call_args_list[0].kwargs["params"]
    assert params["q"] == "data scientist"
    assert params["chips"] == "date_posted:week"
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

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="en,fr", gl="us")
    jobs = list(
        s.search(
            "Machine Learning Engineer",
            location="New York",
            max_results=10,
            date_posted="any",
        )
    )

    assert [call.kwargs["params"]["hl"] for call in get_mock.mock_calls] == ["en", "fr"]
    assert [job.title for job in jobs] == [
        "Machine Learning Engineer",
        "Ingénieur Machine Learning",
    ]


def test_serpapi_does_not_split_quota_across_languages(mocker) -> None:
    fr_page1 = [
        {
            "title": f"Data Scientist {i}",
            "company_name": "Acme",
            "description": "Construire des modèles ML.",
            "job_id": f"fr-{i}",
        }
        for i in range(10)
    ]
    fr_page2 = [
        {
            "title": f"Data Scientist extra {i}",
            "company_name": "Beta",
            "description": "Construire des modèles ML.",
            "job_id": f"fr-extra-{i}",
        }
        for i in range(5)
    ]
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(_sample_serpapi_page([], None)),  # hl=en has no results
            _mock_response(_sample_serpapi_page([], None)),  # hl=en contextual fallback
            _mock_response(_sample_serpapi_page(fr_page1, "fr-page-2")),
            _mock_response(_sample_serpapi_page(fr_page2, None)),
        ],
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", max_pages=3, hl="en,fr", gl="us")
    jobs = list(
        s.search(
            "Data Scientist",
            location="New York",
            max_results=15,
            date_posted="any",
        )
    )

    assert len(jobs) == 15
    assert [call.kwargs["params"]["hl"] for call in get_mock.mock_calls] == [
        "en",
        "en",
        "fr",
        "fr",
    ]


def test_serpapi_uses_french_market_language_for_france(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response(
            _sample_serpapi_page(
                [
                    {
                        "title": "Machine Learning Engineer",
                        "company_name": "Acme",
                        "description": "Build ML systems.",
                        "job_id": "fr-market-1",
                    }
                ],
                None,
            )
        ),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="en,fr", gl="fr")
    jobs = list(
        s.search(
            "Machine Learning Engineer",
            location="Paris, France",
            max_results=10,
            date_posted="any",
        )
    )

    assert [job.title for job in jobs] == ["Machine Learning Engineer"]
    assert get_mock.call_count == 1
    assert get_mock.call_args.kwargs["params"]["hl"] == "fr"


def test_serpapi_fallback_contextualizes_empty_location_search(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(_sample_serpapi_page([], None)),
            _mock_response(
                _sample_serpapi_page(
                    [
                        {
                            "title": "Machine Learning Engineer",
                            "company_name": "Acme",
                            "description": "Build ML systems.",
                            "job_id": "fallback-1",
                        }
                    ],
                    None,
                )
            ),
        ],
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr", gl="fr")
    jobs = list(
        s.search(
            "Machine Learning Engineer",
            location="Paris, France",
            max_results=10,
            date_posted="any",
        )
    )

    assert [job.title for job in jobs] == ["Machine Learning Engineer"]
    first_params = get_mock.call_args_list[0].kwargs["params"]
    fallback_params = get_mock.call_args_list[1].kwargs["params"]
    assert first_params["q"] == "Machine Learning Engineer"
    assert first_params["location"] == "Paris, France"
    assert fallback_params["q"] == "Machine Learning Engineer jobs in Paris, France"
    assert "location" not in fallback_params


def test_serpapi_continues_empty_page_when_next_token_exists(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(_sample_serpapi_page([], "tok-2")),
            _mock_response(
                _sample_serpapi_page(
                    [
                        {
                            "title": "Data Scientist",
                            "company_name": "Acme",
                            "description": "Build ML.",
                            "job_id": "job-1",
                        }
                    ],
                    None,
                )
            ),
        ],
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", max_pages=2, hl="fr")
    jobs = list(s.search("Data Scientist", max_results=10, date_posted="any"))

    assert [job.title for job in jobs] == ["Data Scientist"]
    assert get_mock.call_count == 2
    assert get_mock.call_args_list[1].kwargs["params"]["next_page_token"] == "tok-2"


def test_serpapi_date_filter_can_be_disabled_or_combined_with_uds(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response({"jobs_results": []}),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    list(s.search("data scientist", date_posted="any", uds="raw-filter"))

    params = get_mock.call_args_list[0].kwargs["params"]
    assert params["q"] == "data scientist"
    assert "chips" not in params
    assert params["uds"] == "raw-filter"


def test_serpapi_date_filter_combines_with_existing_chips(mocker) -> None:
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        return_value=_mock_response({"jobs_results": []}),
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    list(
        s.search(
            "data scientist",
            chips="employment_type:FULLTIME",
            date_posted="3days",
        )
    )

    params = get_mock.call_args_list[0].kwargs["params"]
    assert params["q"] == "data scientist"
    assert params["chips"] == "employment_type:FULLTIME,date_posted:3days"


def test_serpapi_widens_zero_result_date_filter_before_giving_up(mocker) -> None:
    page_jobs = [
        {
            "title": "Machine Learning Engineer",
            "company_name": "Acme",
            "location": "Paris",
            "description": "Build ML models.",
            "apply_options": [{"link": "https://acme.test/jobs/ml"}],
            "detected_extensions": {"schedule_type": "Full-time"},
        }
    ]
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(_sample_serpapi_page([], None)),
            _mock_response(_sample_serpapi_page(page_jobs, None)),
        ],
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr")
    jobs = list(
        s.search(
            "Machine Learning Engineer",
            chips="employment_type:FULLTIME",
            date_posted="week",
            max_results=5,
        )
    )

    assert [job.title for job in jobs] == ["Machine Learning Engineer"]
    assert get_mock.call_args_list[0].kwargs["params"]["chips"] == (
        "employment_type:FULLTIME,date_posted:week"
    )
    assert get_mock.call_args_list[1].kwargs["params"]["chips"] == (
        "employment_type:FULLTIME,date_posted:month"
    )


def test_serpapi_widens_low_result_strict_chips(mocker) -> None:
    first_page_jobs = [
        {
            "title": f"Machine Learning Engineer {i}",
            "company_name": "Acme",
            "location": "Paris",
            "description": "Build ML models.",
            "job_id": f"strict-{i}",
            "detected_extensions": {"schedule_type": "Full-time"},
        }
        for i in range(2)
    ]
    wider_page_jobs = [
        {
            "title": f"Data Scientist {i}",
            "company_name": "Beta",
            "location": "Paris",
            "description": "Build data products.",
            "job_id": f"wider-{i}",
            "detected_extensions": {"schedule_type": "Full-time"},
        }
        for i in range(8)
    ]
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(_sample_serpapi_page(first_page_jobs, None)),
            _mock_response(_sample_serpapi_page(wider_page_jobs, None)),
        ],
    )

    s = SerpApiGoogleJobsScraper(api_key="fake", hl="fr", low_result_fallback_target=10)
    jobs = list(
        s.search(
            "Machine Learning Engineer",
            chips="employment_type:FULLTIME",
            date_posted="week",
            max_results=20,
        )
    )

    assert len(jobs) == 10
    assert get_mock.call_count == 2
    assert jobs[0].source_data["_smartapply_search"]["result_origin"] == "strict"
    assert jobs[-1].source_data["_smartapply_search"] == {
        "query": "Machine Learning Engineer",
        "location": "Paris, France",
        "google_domain": "google.com",
        "hl": "fr",
        "gl": "fr",
        "result_origin": "fallback",
        "strict_chips": "employment_type:FULLTIME,date_posted:week",
        "fallback_reason": "low_result_strict_filters",
        "fallback_chips": "employment_type:FULLTIME,date_posted:month",
        "fallback_query": "Machine Learning Engineer",
    }
    assert get_mock.call_args_list[0].kwargs["params"]["chips"] == (
        "employment_type:FULLTIME,date_posted:week"
    )
    assert get_mock.call_args_list[1].kwargs["params"]["chips"] == (
        "employment_type:FULLTIME,date_posted:month"
    )


def test_serpapi_low_result_target_can_exceed_one_page(mocker) -> None:
    first_page_jobs = [
        {
            "title": f"Machine Learning Engineer {i}",
            "company_name": "Acme",
            "location": "Paris",
            "description": "Build ML models.",
            "job_id": f"strict-{i}",
            "detected_extensions": {"schedule_type": "Full-time"},
        }
        for i in range(2)
    ]
    fallback_page1 = [
        {
            "title": f"Data Scientist fallback p1 {i}",
            "company_name": "Beta",
            "location": "Paris",
            "description": "Build data products.",
            "job_id": f"fallback-p1-{i}",
            "detected_extensions": {"schedule_type": "Full-time"},
        }
        for i in range(10)
    ]
    fallback_page2 = [
        {
            "title": f"Data Scientist fallback p2 {i}",
            "company_name": "Gamma",
            "location": "Paris",
            "description": "Build data products.",
            "job_id": f"fallback-p2-{i}",
            "detected_extensions": {"schedule_type": "Full-time"},
        }
        for i in range(8)
    ]
    get_mock = mocker.patch(
        "smartapply.scrapers.serpapi.requests.get",
        side_effect=[
            _mock_response(_sample_serpapi_page(first_page_jobs, None)),
            _mock_response(_sample_serpapi_page(fallback_page1, "fallback-page-2")),
            _mock_response(_sample_serpapi_page(fallback_page2, None)),
        ],
    )

    s = SerpApiGoogleJobsScraper(
        api_key="fake",
        max_pages=3,
        hl="fr",
        low_result_fallback_target=20,
    )
    jobs = list(
        s.search(
            "Machine Learning Engineer",
            chips="employment_type:FULLTIME",
            date_posted="week",
            max_results=20,
        )
    )

    assert len(jobs) == 20
    assert get_mock.call_count == 3
    assert get_mock.call_args_list[1].kwargs["params"]["chips"] == (
        "employment_type:FULLTIME,date_posted:month"
    )
    assert get_mock.call_args_list[2].kwargs["params"]["next_page_token"] == (
        "fallback-page-2"
    )


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


def test_francetravail_date_posted_week_sends_creation_window(mocker) -> None:
    """FT API rejects minCreationDate alone — both bounds must be sent together."""
    from datetime import datetime, timezone

    from smartapply.scrapers.francetravail import _date_posted_to_creation_window

    fixed_now = datetime(2026, 6, 4, 12, 0, 0, tzinfo=timezone.utc)
    assert _date_posted_to_creation_window("week", now=fixed_now) == (
        "2026-05-28T12:00:00Z",
        "2026-06-04T12:00:00Z",
    )

    token_response = _mock_response({"access_token": "T0K3N", "expires_in": 1500})
    empty_response = _mock_response({"resultats": []})
    mocker.patch(
        "smartapply.scrapers.francetravail.requests.post", return_value=token_response
    )
    get_mock = mocker.patch(
        "smartapply.scrapers.francetravail.requests.get", return_value=empty_response
    )
    mocker.patch(
        "smartapply.scrapers.francetravail.datetime",
        wraps=datetime,
        now=lambda tz=None: fixed_now.astimezone(tz) if tz else fixed_now,
    )

    s = FranceTravailScraper(client_id="cid", client_secret="csec")
    list(s.search("data scientist", date_posted="week"))

    params = get_mock.call_args.kwargs["params"]
    assert params["minCreationDate"] == "2026-05-28T12:00:00Z"
    assert params["maxCreationDate"] == "2026-06-04T12:00:00Z"
    assert params["motsCles"] == "data scientist"


def test_francetravail_date_posted_any_omits_creation_window(mocker) -> None:
    token_response = _mock_response({"access_token": "T0K3N", "expires_in": 1500})
    empty_response = _mock_response({"resultats": []})
    mocker.patch(
        "smartapply.scrapers.francetravail.requests.post", return_value=token_response
    )
    get_mock = mocker.patch(
        "smartapply.scrapers.francetravail.requests.get", return_value=empty_response
    )

    s = FranceTravailScraper(client_id="cid", client_secret="csec")
    list(s.search("data", date_posted="any"))
    params = get_mock.call_args.kwargs["params"]
    assert "minCreationDate" not in params
    assert "maxCreationDate" not in params

    list(s.search("data"))  # no date_posted passed at all
    params = get_mock.call_args.kwargs["params"]
    assert "minCreationDate" not in params
    assert "maxCreationDate" not in params


def test_francetravail_date_posted_today_uses_one_day_window(mocker) -> None:
    from datetime import datetime, timezone

    token_response = _mock_response({"access_token": "T0K3N", "expires_in": 1500})
    empty_response = _mock_response({"resultats": []})
    mocker.patch(
        "smartapply.scrapers.francetravail.requests.post", return_value=token_response
    )
    get_mock = mocker.patch(
        "smartapply.scrapers.francetravail.requests.get", return_value=empty_response
    )
    fixed_now = datetime(2026, 6, 4, 10, 30, 0, tzinfo=timezone.utc)
    mocker.patch(
        "smartapply.scrapers.francetravail.datetime",
        wraps=datetime,
        now=lambda tz=None: fixed_now.astimezone(tz) if tz else fixed_now,
    )

    s = FranceTravailScraper(client_id="cid", client_secret="csec")
    list(s.search("data", date_posted="today"))
    params = get_mock.call_args.kwargs["params"]
    assert params["minCreationDate"] == "2026-06-03T10:30:00Z"
    assert params["maxCreationDate"] == "2026-06-04T10:30:00Z"
