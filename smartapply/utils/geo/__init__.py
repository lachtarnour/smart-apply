"""French geo validation and INSEE resolution helpers."""

from smartapply.utils.geo.resolver import (
    ResolvedLocation,
    reset_cache_for_tests,
    resolve_french_location,
)
from smartapply.utils.geo.validation import (
    canonical_french_city,
    french_city_mismatch,
    is_foreign_location,
    is_french_location,
)

__all__ = [
    "ResolvedLocation",
    "canonical_french_city",
    "french_city_mismatch",
    "is_foreign_location",
    "is_french_location",
    "reset_cache_for_tests",
    "resolve_french_location",
]
