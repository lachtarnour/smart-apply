"""Tests for the Welcome to the Jungle scraper prototype."""

from __future__ import annotations

from smartapply.scrapers.welcometothejungle import (
    WTTJ_SOURCE,
    WelcomeToTheJungleScraper,
    WTTJScraperError,
    matches_page_url,
    parse_company_html,
    parse_detail_api_job,
    parse_detail_html,
    parse_listing_links,
    parse_matches_api_links,
    scrape_matches_requests,
)


def test_matches_page_url_is_1_indexed() -> None:
    assert matches_page_url(1) == "https://www.welcometothejungle.com/fr/jobs-matches?page=1"


def test_wttj_scraper_requires_cookie() -> None:
    scraper = WelcomeToTheJungleScraper(cookie_header="")

    assert scraper.is_available() is False


def test_wttj_scraper_uses_large_default_pagination() -> None:
    scraper = WelcomeToTheJungleScraper(cookie_header="wttj_session=abc")

    assert scraper.max_pages == 150
    assert scraper.pages == 150
    assert scraper.per_page == 50


def test_wttj_scraper_search_adds_audit_metadata(mocker) -> None:  # noqa: ANN001
    raw = mocker.MagicMock()
    raw.source_data = {"company_domain": "acme.com"}
    scrape = mocker.patch(
        "smartapply.scrapers.welcometothejungle.scrape_matches_requests",
        return_value=iter([raw]),
    )

    scraper = WelcomeToTheJungleScraper(
        cookie_header="wttj_session=abc",
        pages=5,
        per_page=10,
        include_company_profile=True,
        delay_seconds=0,
    )
    jobs = list(scraper.search("Data Scientist", location="Paris", max_results=20))

    scrape.assert_called_once_with(
        pages=range(1, 6),
        cookie_header="wttj_session=abc",
        max_jobs=20,
        per_page=10,
        include_company_profile=True,
        skip_failed_jobs=True,
        timeout=30,
        delay_seconds=0.0,
    )
    assert jobs == [raw]
    assert raw.source_data["_smartapply_search"] == {
        "source_mode": "personalized_matches",
        "query": "Data Scientist",
        "location": "Paris",
        "pages": 5,
        "per_page": 10,
        "include_company_profile": True,
    }


def test_wttj_scraper_search_caps_pages_to_supported_max(mocker) -> None:  # noqa: ANN001
    max_pages = 12
    raw = mocker.MagicMock()
    raw.source_data = {}
    scrape = mocker.patch(
        "smartapply.scrapers.welcometothejungle.scrape_matches_requests",
        return_value=iter([raw]),
    )

    scraper = WelcomeToTheJungleScraper(
        cookie_header="wttj_session=abc",
        max_pages=max_pages,
        pages=max_pages + 50,
        delay_seconds=0,
    )
    jobs = list(scraper.search("Data Scientist"))

    assert jobs == [raw]
    assert scrape.call_args.kwargs["pages"] == range(1, max_pages + 1)
    assert raw.source_data["_smartapply_search"]["pages"] == max_pages


def test_wttj_zero_max_results_returns_no_jobs(mocker) -> None:  # noqa: ANN001
    scrape = mocker.patch(
        "smartapply.scrapers.welcometothejungle.scrape_matches_requests"
    )
    scraper = WelcomeToTheJungleScraper(
        cookie_header="wttj_session=abc",
        delay_seconds=0,
    )

    assert list(scraper.search("Data Scientist", max_results=0)) == []
    scrape.assert_not_called()


def test_parse_listing_links_deduplicates_job_urls() -> None:
    html = """
    <html><body>
      <a href="/fr/companies/acme/jobs/ml-engineer_paris">ML Engineer</a>
      <a href="https://www.welcometothejungle.com/fr/companies/acme/jobs/ml-engineer_paris?x=1">
        Duplicate
      </a>
      <a href="/fr/companies/acme">Company page</a>
      <a href="https://example.com/fr/companies/acme/jobs/nope">External</a>
      <a href="/fr/companies/beta/jobs/data-scientist_lyon">Data Scientist</a>
    </body></html>
    """
    links = parse_listing_links(html)

    assert [link.title_hint for link in links] == ["ML Engineer", "Data Scientist"]
    assert [link.url for link in links] == [
        "https://www.welcometothejungle.com/fr/companies/acme/jobs/ml-engineer_paris",
        "https://www.welcometothejungle.com/fr/companies/beta/jobs/data-scientist_lyon",
    ]


def test_parse_matches_api_links_builds_public_job_urls() -> None:
    payload = {
        "data": [
            {
                "name": "Senior Python Developer / Data Engineer",
                "slug": "senior-python-developer-data-engineer_paris_OKEIR_kApmoRW",
                "organization": {"slug": "cibiltech", "name": "Okeiro"},
            },
            {
                "name": "Duplicate",
                "slug": "senior-python-developer-data-engineer_paris_OKEIR_kApmoRW",
                "organization": {"slug": "cibiltech", "name": "Okeiro"},
            },
            {"name": "Missing organization", "slug": "missing-org_paris"},
        ]
    }

    links = parse_matches_api_links(payload)

    assert len(links) == 1
    assert links[0].title_hint == "Senior Python Developer / Data Engineer"
    assert links[0].url == (
        "https://www.welcometothejungle.com/fr/companies/cibiltech/jobs/"
        "senior-python-developer-data-engineer_paris_OKEIR_kApmoRW"
    )
    assert links[0].api_data is payload["data"][0]


def test_parse_detail_html_reads_json_ld_and_metadata() -> None:
    html = """
    <html>
      <head>
        <title>Senior ML Engineer - Doctolib - CDI à Paris</title>
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "JobPosting",
          "datePosted": "2026-05-27T22:01:01Z",
          "description": "<h2>What you'll do</h2><p>Build reliable AI evaluation systems.</p>",
          "employmentType": "FULL_TIME",
          "hiringOrganization": {
            "@type": "Organization",
            "name": "Doctolib"
          },
          "industry": "Santé",
          "jobLocation": [{
            "@type": "Place",
            "address": {
              "@type": "PostalAddress",
              "addressLocality": "Paris",
              "addressRegion": "Paris",
              "addressCountry": "FR"
            }
          }],
          "title": "Senior ML Engineer",
          "validThrough": "2026-08-25T22:01:01.000Z"
        }
        </script>
      </head>
      <body>
        <div data-testid="job-metadata-block">
          Doctolib Senior ML Engineer Résumé du poste CDI Paris Télétravail fréquent
          Salaire : Non spécifié
          <div>
            <div><span><span>Compétences & expertises</span></span></div>
            <div>
              <div><span>Python</span></div>
              <div><span>Communication</span></div>
              <div><span>+3</span></div>
            </div>
          </div>
        </div>
        <aside>
          <a href="/fr/companies/doctolib">Explorer l’entreprise</a>
          <a href="https://about.doctolib.com/">Voir le site</a>
          <h4><span>Qui sont-ils ?</span></h4>
          <p>Doctolib builds healthcare software.</p>
          <h4><span>Le lieu de travail</span></h4>
          <a>Paris, France</a>
          <div data-testid="job-company-tag">3000 collaborateurs</div>
          <div data-testid="job-company-tag">Créée en 2013</div>
        </aside>
      </body>
    </html>
    """

    job = parse_detail_html(
        html,
        url="https://www.welcometothejungle.com/fr/companies/doctolib/jobs/senior-ml_paris",
    )

    assert job.source == WTTJ_SOURCE
    assert job.title == "Senior ML Engineer"
    assert job.company == "Doctolib"
    assert job.location == "Paris, FR"
    assert job.contract_type == "CDI"
    assert job.remote_policy == "hybrid"
    assert "Build reliable AI evaluation systems." in job.description
    assert job.published_date is not None
    assert job.source_data is not None
    assert job.source_data["company_profile_url"] == (
        "https://www.welcometothejungle.com/fr/companies/doctolib"
    )
    assert job.source_data["company_website"] == "https://about.doctolib.com/"
    assert job.source_data["company_summary"] == "Doctolib builds healthcare software."
    assert job.source_data["workplace"] == "Paris, France"
    assert job.source_data["skills"] == ["Python", "Communication"]
    assert job.source_data["skills_more_count"] == 3
    assert job.source_data["company_stats"] == {
        "employees": "3000 collaborateurs",
        "founded": "Créée en 2013",
    }
    assert job.application_url == (
        "https://www.welcometothejungle.com/fr/companies/doctolib/jobs/senior-ml_paris"
    )
    assert job.external_id.startswith("welcometothejungle:")


def test_parse_detail_api_job_reads_public_api_payload() -> None:
    job = parse_detail_api_job(
        {
            "name": "Business data analyst",
            "slug": "business-data-analyst_paris",
            "contract_type": "full_time",
            "remote": "partial",
            "published_at": "2026-05-22T07:35:43Z",
            "experience_level": "3_TO_4_YEARS",
            "description": "<p>Build business data products.</p>",
            "looking_for_candidate_description": "<p>Python and communication.</p>",
            "salary_min": 45000,
            "salary_max": 50000,
            "salary_currency": "EUR",
            "salary_period": "yearly",
            "offices": [{"city": "Paris", "country_code": "FR"}],
            "organization": {
                "name": "Phagos",
                "slug": "phagos-1",
                "description": "<p>Phagos builds biotech products.</p>",
                "nb_employees": 70,
                "creation_year": 2021,
            },
            "profession": {"category_name": "Data"},
        },
        url="https://www.welcometothejungle.com/fr/companies/phagos-1/jobs/business-data-analyst_paris",
    )

    assert job.title == "Business data analyst"
    assert job.company == "Phagos"
    assert job.location == "Paris, FR"
    assert job.contract_type == "Full-time"
    assert job.remote_policy == "hybrid"
    assert job.published_date is not None
    assert job.experience == {
        "level": "3_TO_4_YEARS",
        "min_years": 3.0,
        "required": True,
    }
    assert "Build business data products." in job.description
    assert job.source_data is not None
    assert job.source_data["salary"]["min"] == 45000
    assert job.source_data["company_profile"]["presentation"] == "Phagos builds biotech products."


def test_parse_company_html_reads_profile_fields() -> None:
    html = """
    <html>
      <head>
        <title>WeWard: pictures, videos and careers</title>
        <link rel="canonical" href="https://www.welcometothejungle.com/en/companies/weward" />
      </head>
      <body>
        <main data-testid="page-organization-profile">
          <header data-testid="showcase-header">
            WeWard Follow
            <div data-testid="showcase-header-sector">Application mobile, Santé</div>
            <div data-testid="showcase-header-office">Paris, New York</div>
            <a data-testid="showcase-header-website-link" href="https://www.weward.fr/">View website</a>
          </header>
          <span data-testid="stats-creation-year">2019</span>
          <span data-testid="stats-nb-employees">50</span>
          <span data-testid="stats-parity-women">45%</span>
          <span data-testid="stats-parity-men">55%</span>
          <span data-testid="stats-average-age">28 years old</span>
          <span data-testid="stats-turnover">0%</span>
          <div data-testid="organization-content-block-text">
            <h2>Presentation</h2>
            <p>WeWard rewards walking.</p>
          </div>
          <div data-testid="organization-content-block-text">
            <h2>Good to know</h2>
            <p>Hybrid working possible.</p>
          </div>
          <div data-testid="organization-content-block-map">83 Boulevard de Sébastopol 75002 Paris</div>
          <a data-testid="social-network-linkedin" href="https://www.linkedin.com/company/weward-app"></a>
        </main>
      </body>
    </html>
    """

    company = parse_company_html(html)

    assert company["name"] == "WeWard"
    assert company["url"] == "https://www.welcometothejungle.com/en/companies/weward"
    assert company["website"] == "https://www.weward.fr/"
    assert company["domain"] == "weward.fr"
    assert company["sectors"] == "Application mobile, Santé"
    assert company["offices"] == "Paris, New York"
    assert company["presentation"] == "WeWard rewards walking."
    assert company["good_to_know"] == "Hybrid working possible."
    assert company["addresses"] == ["83 Boulevard de Sébastopol 75002 Paris"]
    assert company["stats"]["employees"] == "50"
    assert company["social_links"]["linkedin"] == "https://www.linkedin.com/company/weward-app"


def test_scrape_matches_requests_uses_cookie_only_for_matches_api(mocker) -> None:  # noqa: ANN001
    matches_payload = {
        "data": [
            {
                "name": "ML Engineer",
                "slug": "ml-engineer_paris",
                "organization": {
                    "slug": "acme",
                    "name": "Acme",
                    "sectors": [{"name": "Artificial Intelligence / Machine Learning"}],
                },
            }
        ],
        "metadata": {"total": 1, "page": 1, "per_page": 10, "page_count": 1},
    }
    detail_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "JobPosting",
          "datePosted": "2026-05-27T22:01:01Z",
          "description": "<p>Build ML systems.</p>",
          "employmentType": "FULL_TIME",
          "hiringOrganization": {"@type": "Organization", "name": "Acme"},
          "jobLocation": [],
          "title": "ML Engineer"
        }
        </script>
      </head>
      <body>
        <a href="/fr/companies/acme">Explorer l’entreprise</a>
      </body>
    </html>
    """
    company_html = """
    <html>
      <head>
        <title>Acme: pictures, videos and careers</title>
        <link rel="canonical" href="https://www.welcometothejungle.com/fr/companies/acme" />
      </head>
      <body>
        <main data-testid="page-organization-profile">
          <header data-testid="showcase-header">
            Acme Follow
            <a data-testid="showcase-header-website-link" href="https://www.acme.com/">View website</a>
          </header>
          <div data-testid="organization-content-block-text">
            <h2>Presentation</h2>
            <p>Acme builds ML tools.</p>
          </div>
        </main>
      </body>
    </html>
    """

    detail_response = mocker.MagicMock()
    detail_response.text = detail_html
    detail_response.raise_for_status = mocker.MagicMock()
    company_response = mocker.MagicMock()
    company_response.text = company_html
    company_response.raise_for_status = mocker.MagicMock()

    fetch_api = mocker.patch(
        "smartapply.scrapers.welcometothejungle.fetch_matches_api_page",
        return_value=matches_payload,
    )
    public_get = mocker.patch(
        "smartapply.scrapers.welcometothejungle.requests.get",
        side_effect=[detail_response, company_response],
    )

    jobs = list(
        scrape_matches_requests(
            pages=[1],
            cookie_header="wttj_session=abc",
            max_jobs=1,
            per_page=10,
        )
    )

    fetch_api.assert_called_once_with(
        page=1,
        cookie_header="wttj_session=abc",
        per_page=10,
        timeout=30,
        extra_headers=None,
    )
    assert public_get.call_count == 2
    assert public_get.call_args_list[0].args[0] == (
        "https://www.welcometothejungle.com/fr/companies/acme/jobs/ml-engineer_paris"
    )
    assert public_get.call_args_list[1].args[0] == (
        "https://www.welcometothejungle.com/fr/companies/acme"
    )
    assert all("Cookie" not in call.kwargs["headers"] for call in public_get.call_args_list)
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].company == "Acme"
    assert jobs[0].source_data is not None
    assert jobs[0].source_data["matches_api"]["slug"] == "ml-engineer_paris"
    assert jobs[0].source_data["company_website"] == "https://www.acme.com/"
    assert jobs[0].source_data["company_domain"] == "acme.com"
    assert jobs[0].source_data["company_profile"]["sectors"] == (
        "Artificial Intelligence / Machine Learning"
    )
    assert jobs[0].source_data["company_profile"]["presentation"] == "Acme builds ML tools."


def test_scrape_matches_requests_stops_after_api_page_count(mocker) -> None:  # noqa: ANN001
    fetch_api = mocker.patch(
        "smartapply.scrapers.welcometothejungle.fetch_matches_api_page",
        return_value={"data": [], "metadata": {"page_count": 1}},
    )

    jobs = list(
        scrape_matches_requests(
            pages=[1, 2, 3],
            cookie_header="wttj_session=abc",
            include_company_profile=False,
            delay_seconds=0,
        )
    )

    assert jobs == []
    fetch_api.assert_called_once()


def test_scrape_matches_requests_stops_after_empty_api_page_without_page_count(mocker) -> None:  # noqa: ANN001
    fetch_api = mocker.patch(
        "smartapply.scrapers.welcometothejungle.fetch_matches_api_page",
        return_value={"data": [], "metadata": {}},
    )

    jobs = list(
        scrape_matches_requests(
            pages=[1, 2, 3],
            cookie_header="wttj_session=abc",
            include_company_profile=False,
            delay_seconds=0,
        )
    )

    assert jobs == []
    fetch_api.assert_called_once()


def test_scrape_matches_requests_skips_missing_page_by_default(mocker) -> None:  # noqa: ANN001
    fetch_api = mocker.patch(
        "smartapply.scrapers.welcometothejungle.fetch_matches_api_page",
        side_effect=[WTTJScraperError("page missing"), {"data": []}],
    )

    jobs = list(
        scrape_matches_requests(
            pages=[1, 2],
            cookie_header="wttj_session=abc",
            include_company_profile=False,
            delay_seconds=0,
        )
    )

    assert jobs == []
    assert fetch_api.call_count == 2


def test_scrape_matches_requests_skips_broken_public_job_by_default(mocker) -> None:  # noqa: ANN001
    matches_payload = {
        "data": [
            {
                "name": "Broken job",
                "slug": "broken-job_paris",
                "organization": {"slug": "acme", "name": "Acme"},
            },
            {
                "name": "Good job",
                "slug": "good-job_paris",
                "organization": {"slug": "acme", "name": "Acme"},
            },
        ]
    }
    broken_html = "<html><body>Expired job</body></html>"
    good_html = """
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "JobPosting",
          "description": "<p>Build ML systems.</p>",
          "employmentType": "FULL_TIME",
          "hiringOrganization": {"@type": "Organization", "name": "Acme"},
          "jobLocation": [],
          "title": "Good job"
        }
        </script>
      </head>
      <body></body>
    </html>
    """
    broken_response = mocker.MagicMock(text=broken_html)
    broken_response.raise_for_status = mocker.MagicMock()
    good_response = mocker.MagicMock(text=good_html)
    good_response.raise_for_status = mocker.MagicMock()
    mocker.patch(
        "smartapply.scrapers.welcometothejungle.fetch_matches_api_page",
        return_value=matches_payload,
    )
    mocker.patch(
        "smartapply.scrapers.welcometothejungle.fetch_detail_api_job",
        side_effect=WTTJScraperError("API detail missing"),
    )
    mocker.patch(
        "smartapply.scrapers.welcometothejungle.requests.get",
        side_effect=[broken_response, good_response],
    )

    jobs = list(
        scrape_matches_requests(
            pages=[1],
            cookie_header="wttj_session=abc",
            include_company_profile=False,
            delay_seconds=0,
        )
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Good job"
