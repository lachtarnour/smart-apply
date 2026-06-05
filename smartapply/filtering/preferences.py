"""Build filter rules from user profile preferences."""

from __future__ import annotations

from smartapply.filtering.rules import RuleSet
from smartapply.profile import JobPreferences
from smartapply.utils.contracts import normalize_contract_preferences


def ruleset_from_preferences(prefs: JobPreferences) -> RuleSet:
    return RuleSet(
        target_roles=[r.lower() for r in prefs.target_roles],
        deal_breakers=[d.lower() for d in prefs.deal_breakers],
        preferred_locations=[loc.lower() for loc in prefs.preferred_locations],
        accepted_contract_types=normalize_contract_preferences(prefs.accepted_contract_types),
        accepted_remote_policies=[p.lower() for p in prefs.accepted_remote_policies],
    )
