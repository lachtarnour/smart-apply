from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompanySeed(BaseModel):
    company_name: str
    website: str | None = None
    sector_hint: str | None = None
    spontaneous_score: Literal["A", "B", "C"] | None = None


class CompanyRecord(CompanySeed):
    id: int
    status: str = "pending"


class WTTJProfile(BaseModel):
    company_name: str
    has_wttj_profile: bool
    wttj_url: str | None = None
    wttj_status: Literal[
        "active_profile",
        "probable_active_profile",
        "not_found",
        "inactive_removed",
        "partial",
        "error",
    ]
    discovery_method: str
    error_message: str | None = None


class RawCompanyInfo(BaseModel):
    company_name_raw: str
    source_type: Literal["wttj", "official_website", "manual"]
    source_url: str | None = None

    domain_raw: str | None = None
    address_raw: str | None = None
    description_raw: str | None = None
    looking_for_raw: str | None = None
    good_to_know_raw: str | None = None

    team_size_raw: str | None = None
    creation_year_raw: str | None = None
    jobs_raw: str | None = None

    raw_text: str | None = None
    raw_html_path: str | None = None
    extraction_method: str = "manual_or_stub"
    quality_score: float | None = Field(default=None, ge=0, le=1)
    error_message: str | None = None


class StructuredCompanyProfile(BaseModel):
    model_config = ConfigDict(validate_default=True)

    company_name: str

    sector: str | None = None
    sub_sector: str | None = None

    short_description: str
    detailed_description: str | None = None

    products_or_services: list[str] = Field(default_factory=list)
    target_users: list[str] = Field(default_factory=list)

    business_model: str | None = None

    ai_data_relevance: list[str] = Field(default_factory=list)
    tech_keywords: list[str] = Field(default_factory=list)
    health_keywords: list[str] = Field(default_factory=list)

    what_they_look_for: str | None = None
    good_to_know: str | None = None

    candidate_fit_score: int = Field(ge=0, le=10)
    candidate_fit_reason: str

    personalization_anchor: str
    email_angle: str

    confidence: Literal["high", "medium", "low"]
    risk_notes: str | None = None


class EmailDraft(BaseModel):
    subject: str
    email_body: str
    recipient_type: str | None = None
    tone: str | None = None
    language: str = "fr"
    validation_status: str | None = None
    validation_notes: str | None = None

