from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import tomllib

ROOT_DIR = Path(__file__).resolve().parents[1]
SETTINGS_PATH = ROOT_DIR / "config" / "settings.toml"


class SpontaneousApplySettings:
    def __init__(self, raw: dict):
        self.raw = raw
        self.database_path = self._resolve(raw["database"]["path"])
        paths = raw.get("paths", {})
        self.companies_seed_csv = self._resolve(paths.get("companies_seed_csv", "data/input/companies_seed.csv"))
        self.company_profiles_jsonl = self._resolve(
            paths.get("company_profiles_jsonl", "data/processed/company_profiles.jsonl")
        )
        self.email_drafts_jsonl = self._resolve(
            paths.get("email_drafts_jsonl", "data/processed/email_drafts.jsonl")
        )
        self.wttj_raw_dir = self._resolve(paths.get("wttj_raw_dir", "data/raw/wttj_pages"))
        self.log_file = self._resolve(paths.get("log_file", "data/logs/pipeline.log"))
        self.llm_model = raw.get("llm", {}).get("model", "gpt-4o")
        self.llm_temperature = float(raw.get("llm", {}).get("temperature", 0.2))
        wttj_search = raw.get("wttj_company_search", {})
        self.wttj_company_search_max_pages = int(wttj_search.get("max_pages", 12))
        self.wttj_company_search_timeout_seconds = int(
            wttj_search.get("request_timeout_seconds", 30)
        )
        self.wttj_company_search_delay_seconds = float(wttj_search.get("delay_seconds", 0.5))
        self.wttj_company_search_hits_per_page = int(wttj_search.get("hits_per_page", 30))
        self.wttj_company_search_render_with_browser = bool(
            wttj_search.get("render_with_browser", True)
        )
        self.wttj_company_search_url_template = wttj_search.get("url_template", "")

    def _resolve(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return ROOT_DIR / path

    def ensure_dirs(self) -> None:
        paths = [
            self.database_path.parent,
            self.companies_seed_csv.parent,
            self.company_profiles_jsonl.parent,
            self.email_drafts_jsonl.parent,
            self.wttj_raw_dir,
            self.log_file.parent,
        ]
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> SpontaneousApplySettings:
    with SETTINGS_PATH.open("rb") as f:
        settings = SpontaneousApplySettings(tomllib.load(f))
    settings.ensure_dirs()
    return settings
