"""Shared types for the local filtering pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class FilterDisposition(str, Enum):
    """Final local-filter outcome persisted for product-level traceability."""

    RELEVANT = "relevant"
    UNCERTAIN = "uncertain"
    REJECTED = "rejected"


@dataclass
class FilterResult:
    kept: bool
    score: float
    reasons: list[str]
    disposition: FilterDisposition | None = None

    def __post_init__(self) -> None:
        if self.disposition is None:
            self.disposition = (
                FilterDisposition.RELEVANT if self.kept else FilterDisposition.REJECTED
            )


class HasJobFields(Protocol):
    title: str
    company: str
    description: str
    location: str | None
    contract_type: str | None
    remote_policy: str | None
