from __future__ import annotations

from bs4 import BeautifulSoup

from spontaneous_apply.src.models import RawCompanyInfo
from spontaneous_apply.src.wttj_scraper import RawPage


def extract_raw_company_info(raw_page: RawPage, company_name: str | None = None) -> RawCompanyInfo:
    text = _html_to_text(raw_page.html)
    return RawCompanyInfo(
        company_name_raw=company_name or "",
        source_type="wttj",
        source_url=raw_page.url,
        raw_text=text,
        raw_html_path=str(raw_page.html_path) if raw_page.html_path else None,
        extraction_method="html_text_v1",
        quality_score=_quality_score(text),
    )


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "noscript"]):
        node.decompose()
    return "\n".join(part.strip() for part in soup.get_text("\n").splitlines() if part.strip())


def _quality_score(text: str) -> float:
    if len(text) >= 2000:
        return 1.0
    if len(text) >= 800:
        return 0.75
    if len(text) >= 300:
        return 0.4
    return 0.1

