"""Shared types for the local filtering pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class FilterResult:
    kept: bool
    score: float
    reasons: list[str]


class HasJobFields(Protocol):
    title: str
    company: str
    description: str
    location: str | None
    contract_type: str | None
    remote_policy: str | None
