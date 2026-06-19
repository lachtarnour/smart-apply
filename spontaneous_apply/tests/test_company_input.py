from __future__ import annotations

from spontaneous_apply.src.company_input import load_companies


def test_load_companies_reads_wttj_url(tmp_path) -> None:
    seed_csv = tmp_path / "companies_seed.csv"
    seed_csv.write_text(
        "\n".join(
            [
                "company_name,wttj_url,sector_hint,spontaneous_score",
                "Sonio,https://www.welcometothejungle.com/fr/companies/sonio,medtech,A",
            ]
        ),
        encoding="utf-8",
    )

    companies = load_companies(seed_csv)

    assert companies[0].company_name == "Sonio"
    assert companies[0].wttj_url == "https://www.welcometothejungle.com/fr/companies/sonio"
