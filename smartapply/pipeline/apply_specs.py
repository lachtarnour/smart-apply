"""Apply-mode presets used by the application phase."""

from dataclasses import dataclass
from typing import Literal

ApplyMode = Literal["manual", "autopilot"]
ContactProviderKind = Literal["chain", "none"]


@dataclass(frozen=True)
class ApplySpec:
    """The knobs that distinguish manual from autopilot apply."""

    quality_gate: bool
    contact_provider: ContactProviderKind
    build_audit: bool
    default_gmail_draft: bool


_PRESETS: dict[ApplyMode, ApplySpec] = {
    "manual": ApplySpec(
        quality_gate=False,
        contact_provider="none",
        build_audit=False,
        default_gmail_draft=False,
    ),
    "autopilot": ApplySpec(
        quality_gate=True,
        contact_provider="chain",
        build_audit=True,
        default_gmail_draft=True,
    ),
}


def apply_spec_for(mode: ApplyMode) -> ApplySpec:
    return _PRESETS[mode]
