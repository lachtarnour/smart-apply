from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from spontaneous_apply.src.models import RawCompanyInfo, StructuredCompanyProfile
from spontaneous_apply.src.settings import ROOT_DIR

PROMPT_PATH = ROOT_DIR / "config" / "prompts" / "company_structuring_prompt.txt"


def load_structuring_prompt(path: str | Path = PROMPT_PATH) -> str:
    return Path(path).read_text(encoding="utf-8")


def structure_company_with_llm(raw_info: RawCompanyInfo) -> StructuredCompanyProfile:
    raise NotImplementedError("LLM structuring is planned for V3.")


def parse_structured_profile(raw_json: str) -> StructuredCompanyProfile:
    try:
        payload = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON returned by LLM: {e}") from e

    try:
        return StructuredCompanyProfile.model_validate(payload)
    except ValidationError as e:
        raise ValueError(f"Invalid structured company profile: {e}") from e

