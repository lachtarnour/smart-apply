"""CLI probe for the Welcome to the Jungle personalized matches scraper."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from smartapply.scrapers.welcometothejungle import (
    WTTJScraperError,
    parse_saved_detail,
    parse_saved_listing,
    scrape_matches_live,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listing-html", action="append", default=[], help="Saved jobs-matches HTML file.")
    parser.add_argument("--detail-html", action="append", default=[], help="Saved job detail HTML file.")
    parser.add_argument("--live", action="store_true", help="Open WTTJ in Chrome via Playwright.")
    parser.add_argument("--start-page", type=int, default=1, help="First jobs-matches page.")
    parser.add_argument("--pages", type=int, default=1, help="Number of jobs-matches pages to visit.")
    parser.add_argument("--max-jobs", type=int, default=None, help="Stop after N detail pages.")
    parser.add_argument("--cdp-url", default=None, help="Chrome DevTools URL, e.g. http://127.0.0.1:9222.")
    parser.add_argument(
        "--user-data-dir",
        default="~/.smartapply/wttj-chrome-profile",
        help="Dedicated Chrome profile for WTTJ login persistence.",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    parser.add_argument("--save-html-dir", default=None, help="Optional directory to save live HTML.")
    parser.add_argument("--output", default=None, help="Write parsed RawJob rows as JSONL.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON to stdout.")
    args = parser.parse_args()

    rows: list[dict] = []

    for path in args.listing_html:
        links = parse_saved_listing(path)
        print(f"{path}: {len(links)} unique job links")
        for link in links[:10]:
            print(f"  - {link.title_hint or '?'} | {link.url}")

    for path in args.detail_html:
        job = parse_saved_detail(path)
        rows.append(job.model_dump(mode="json"))
        print(f"{path}: parsed detail -> {job.title} | {job.company} | {job.location}")

    if args.live:
        page_numbers = list(range(args.start_page, args.start_page + args.pages))
        try:
            for job in scrape_matches_live(
                pages=page_numbers,
                max_jobs=args.max_jobs,
                cdp_url=args.cdp_url,
                user_data_dir=args.user_data_dir,
                headless=args.headless,
                save_html_dir=args.save_html_dir,
            ):
                row = job.model_dump(mode="json")
                rows.append(row)
                print(f"parsed live -> {job.title} | {job.company} | {job.location}")
        except WTTJScraperError as exc:
            print(f"ERROR: {exc}")
            return 2

    if args.output and rows:
        output = Path(args.output).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"Wrote {len(rows)} jobs to {output}")
    elif rows:
        if args.pretty:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
        else:
            for row in rows:
                print(json.dumps(row, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
