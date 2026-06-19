from __future__ import annotations

from spontaneous_apply.src.wttj_company_search import parse_company_search_html


def test_parse_company_search_html_extracts_company_seed_rows() -> None:
    html = """
    <main>
      <article>
        <a href="https://www.welcometothejungle.com/fr/companies/aico-technology"></a>
        <header><a href="/fr/companies/aico-technology">AICO TECHNOLOGY</a></header>
      </article>
      <footer>
        <a href="https://www.welcometothejungle.com/fr/companies/wttj">On recrute</a>
      </footer>
    </main>
    """

    rows = parse_company_search_html(html)

    assert len(rows) == 1
    assert rows[0].company_name == "AICO TECHNOLOGY"
    assert rows[0].wttj_url == "https://www.welcometothejungle.com/fr/companies/aico-technology"
