"""Persistence layer — SQLAlchemy models, session and repository."""

from smartapply.database.models import (
    Application,
    Base,
    Contact,
    ContactLookupCache,
    GeneratedDocument,
    Job,
    JobAnalysis,
    JobEmbedding,
    JobScore,
    JobStatus,
    LLMCache,
    LLMUsage,
)
from smartapply.database.session import (
    auto_migrate,
    drop_db,
    get_engine,
    get_session_factory,
    init_db,
    reset_engine_cache,
    session_scope,
)

__all__ = [
    "Application",
    "Base",
    "Contact",
    "ContactLookupCache",
    "GeneratedDocument",
    "Job",
    "JobAnalysis",
    "JobEmbedding",
    "JobScore",
    "JobStatus",
    "LLMCache",
    "LLMUsage",
    "auto_migrate",
    "drop_db",
    "get_engine",
    "get_session_factory",
    "init_db",
    "reset_engine_cache",
    "session_scope",
]
