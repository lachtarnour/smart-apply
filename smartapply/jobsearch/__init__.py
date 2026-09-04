"""Job-search workflow helpers."""

from smartapply.jobsearch.status import STATUS_FLOW, STATUS_LABELS, status_label
from smartapply.jobsearch.workflow import (
    APPLICATION_STATUSES,
    next_action_for,
)

__all__ = [
    "APPLICATION_STATUSES",
    "STATUS_FLOW",
    "STATUS_LABELS",
    "next_action_for",
    "status_label",
]
