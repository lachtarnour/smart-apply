"""High-level repository helpers grouped by aggregate."""

from smartapply.database.repository.analyses import set_analysis
from smartapply.database.repository.applications import (
    create_or_get_application,
    list_applications,
    update_application_tracking,
)
from smartapply.database.repository.contacts import (
    add_contact,
    find_contacts_for,
    get_contact_lookup_cache,
    upsert_contact_lookup_cache,
)
from smartapply.database.repository.documents import add_document, upsert_document
from smartapply.database.repository.jobs import (
    get_job_by_external_id,
    get_known_external_ids,
    list_jobs,
    list_known_jobs,
    list_pending_processing,
    mark_analyzed,
    mark_archived,
    mark_filtered,
    mark_ranked,
    rescue_archived_job,
    update_status,
    upsert_job,
)
from smartapply.database.repository.llm_cache import (
    cache_get,
    cache_set,
    record_usage,
    total_cost,
)
from smartapply.database.repository.scores import set_score, top_jobs_by_score

__all__ = [
    "add_contact",
    "add_document",
    "cache_get",
    "cache_set",
    "create_or_get_application",
    "find_contacts_for",
    "get_contact_lookup_cache",
    "get_job_by_external_id",
    "get_known_external_ids",
    "list_applications",
    "list_jobs",
    "list_known_jobs",
    "list_pending_processing",
    "mark_analyzed",
    "mark_archived",
    "mark_filtered",
    "mark_ranked",
    "record_usage",
    "rescue_archived_job",
    "set_analysis",
    "set_score",
    "top_jobs_by_score",
    "total_cost",
    "update_application_tracking",
    "update_status",
    "upsert_contact_lookup_cache",
    "upsert_document",
    "upsert_job",
]
