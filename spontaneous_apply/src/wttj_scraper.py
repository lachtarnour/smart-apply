from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawPage:
    url: str
    html: str
    html_path: Path | None = None


def scrape_wttj_page(wttj_url: str) -> RawPage:
    raise NotImplementedError("WTTJ scraping is planned for V2.")

