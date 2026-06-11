from __future__ import annotations

from spontaneous_apply.src.raw_extractor import extract_raw_company_info
from spontaneous_apply.src.wttj_scraper import RawPage


def test_extract_raw_company_info_extracts_visible_text() -> None:
    raw = extract_raw_company_info(
        RawPage(
            url="https://www.welcometothejungle.com/fr/companies/example",
            html="<html><script>hidden()</script><body><h1>Example</h1><p>Visible text</p></body></html>",
        ),
        company_name="Example",
    )

    assert raw.company_name_raw == "Example"
    assert "Visible text" in (raw.raw_text or "")
    assert "hidden" not in (raw.raw_text or "")

