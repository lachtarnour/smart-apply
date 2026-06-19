from __future__ import annotations

import argparse

from spontaneous_apply.src.settings import get_settings
from spontaneous_apply.src.wttj_company_search import (
    parse_company_search_html_file,
    scrape_wttj_company_search,
    write_companies_seed_csv,
)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=settings.wttj_company_search_max_pages)
    parser.add_argument("--output", default=str(settings.companies_seed_csv))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-algolia-fallback", action="store_true")
    parser.add_argument(
        "--from-html",
        default=None,
        help="Parse a saved WTTJ companies HTML file instead of fetching pages from the internet.",
    )
    args = parser.parse_args()

    if args.from_html:
        rows = parse_company_search_html_file(args.from_html)
    else:
        rows = scrape_wttj_company_search(
            max_pages=args.max_pages,
            use_browser=not args.no_browser,
            use_algolia_fallback=not args.no_algolia_fallback,
        )

    output_path = write_companies_seed_csv(rows, args.output)
    print(f"Wrote {len(rows)} companies to {output_path}")


if __name__ == "__main__":
    main()
