"""Configuration centralisee chargee depuis .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # LLM
    llm_provider: str = Field(default="openai")
    openai_api_key: str = Field(default="")
    openai_model_cheap: str = Field(default="gpt-4o-mini")
    openai_model_smart: str = Field(default="gpt-4o")
    openai_model_embed: str = Field(default="text-embedding-3-small")
    anthropic_api_key: str = Field(default="")
    anthropic_model_cheap: str = Field(default="claude-haiku-4-5")
    anthropic_model_smart: str = Field(default="claude-sonnet-4-6")

    # Embeddings
    embeddings_provider: str = Field(default="openai")
    local_embeddings_model: str = Field(default="paraphrase-multilingual-MiniLM-L12-v2")

    # Database
    database_url: str = Field(default=f"sqlite:///{ROOT_DIR / 'data' / 'smartapply.db'}")

    # Paths
    profile_dir: Path = Field(default=ROOT_DIR / "smartapply" / "profile" / "data")
    output_dir: Path = Field(default=ROOT_DIR / "data" / "output")
    cache_dir: Path = Field(default=ROOT_DIR / "data" / "cache")
    samples_dir: Path = Field(default=ROOT_DIR / "data" / "samples")

    # Job sources (comma-separated names)
    job_sources: str = Field(default="serpapi,francetravail,manual")

    # SerpApi Google Jobs
    serpapi_api_key: str = Field(default="")
    serpapi_google_domain: str = Field(default="google.com")
    # Comma-separated Google Jobs UI languages. "en,fr" searches both English
    # and French result contexts while keeping the country/location in France.
    serpapi_hl: str = Field(default="en,fr")
    serpapi_gl: str = Field(default="fr")
    serpapi_default_location: str = Field(default="Paris, France")
    serpapi_max_pages: int = Field(default=3, ge=1, le=300)
    # Google Jobs freshness filter. Allowed values: any, today, 3days, week, month.
    # "week" maps to the Google Jobs "Last week" / last 7 days filter.
    serpapi_date_posted: str = Field(default="week")
    # Optional raw Google Jobs filter string from SerpApi's `filters[].parameters.uds`.
    serpapi_uds: str = Field(default="")

    # France Travail
    francetravail_client_id: str = Field(default="")
    francetravail_client_secret: str = Field(default="")
    francetravail_scope: str = Field(default="api_offresdemploiv2 o2dsoffre")

    # Contact enrichment (Snov.io)
    snov_client_id: str = Field(default="")
    snov_client_secret: str = Field(default="")
    snov_preflight_email_count: bool = Field(default=True)
    # Resolve the company-owned domain from its name via Snov when the
    # application URL points to an ATS / job board (Greenhouse, Lever,
    # LinkedIn, France Travail, ...). Without this, postings on job boards
    # would always end with "no contact" even though the company name is
    # in the offer.
    snov_resolve_company_domain: bool = Field(default=True)
    snov_max_contacts: int = Field(default=5, ge=1, le=50)
    contact_cache_enabled: bool = Field(default=True)
    contact_cache_ttl_days: int = Field(default=45, ge=1)
    contact_cache_negative_ttl_days: int = Field(default=14, ge=1)

    @property
    def enabled_sources(self) -> list[str]:
        return [s.strip().lower() for s in self.job_sources.split(",") if s.strip()]

    # Gmail
    gmail_credentials_path: Path = Field(default=ROOT_DIR / "secrets" / "credentials.json")
    gmail_token_path: Path = Field(default=ROOT_DIR / "secrets" / "token.json")
    gmail_user: str = Field(default="me")

    # Pipeline tuning
    top_k_ranked: int = Field(default=25, ge=1)
    top_k_cv_blocks: int = Field(default=8, ge=1)
    dedup_title_threshold: int = Field(default=85, ge=0, le=100)
    dedup_desc_threshold: int = Field(default=70, ge=0, le=100)
    autopilot_target_drafts: int = Field(default=25, ge=1)
    autopilot_min_score: float = Field(default=0.62, ge=0.0, le=1.0)
    autopilot_contact_min_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    autopilot_require_quality_gate: bool = Field(default=True)
    autopilot_analyze_multiplier: float = Field(default=2.0, ge=1.0, le=5.0)
    autopilot_candidate_multiplier: float = Field(default=3.0, ge=1.0, le=6.0)
    # Concurrency for parallel LLM analysis calls in Processor. Capped to
    # respect provider rate limits while still giving a large wall-clock win
    # on top-K analysis (15 jobs go from ~30s serial to ~4s with 5 workers).
    llm_max_concurrent: int = Field(default=5, ge=1, le=20)

    # Logging
    log_level: str = Field(default="INFO")

    def ensure_dirs(self) -> None:
        for p in (self.output_dir, self.cache_dir, self.samples_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
