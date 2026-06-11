from __future__ import annotations

from spontaneous_apply.src.models import RawCompanyInfo

VALID_COMPANY_STATUSES = {
    "pending",
    "wttj_searching",
    "wttj_found",
    "wttj_not_found",
    "wttj_scraped",
    "raw_extracted",
    "structured",
    "email_generated",
    "needs_manual_review",
    "failed",
}


def has_enough_raw_info(raw_info: RawCompanyInfo, min_length: int = 800) -> bool:
    text_parts = [
        raw_info.description_raw,
        raw_info.looking_for_raw,
        raw_info.good_to_know_raw,
        raw_info.raw_text,
    ]
    total_length = sum(len(x or "") for x in text_parts)
    return total_length >= min_length


def validate_company_status(status: str) -> str:
    if status not in VALID_COMPANY_STATUSES:
        raise ValueError(f"Unknown company status: {status}")
    return status

