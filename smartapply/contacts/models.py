"""Shared contact domain models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContactCandidate:
    email: str
    source_url: str
    confidence: float
    provider: str
    verified: bool = False
    kind: str = "contact"
    form_url: str | None = None
    full_name: str | None = None
    job_title: str | None = None
    location_hint: str | None = None
    decision_reason: str | None = None


@dataclass(frozen=True)
class ContactLookupDecision:
    lookup_company: str | None
    lookup_application_url: str | None
    lookup_domain: str | None
    lookup_location: str | None
    strategy: str
    confidence: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candidate_domains: list[str] = field(default_factory=list)
    rejected_domains: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceDomainCandidate:
    domain: str
    url: str | None
    source_field: str
