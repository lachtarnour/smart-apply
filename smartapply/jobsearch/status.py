"""Status metadata shared by the macOS application and business services."""

from __future__ import annotations

from typing import Any

from smartapply.database.models import JobStatus

STATUS_FLOW: tuple[dict[str, Any], ...] = (
    {
        "status": JobStatus.DUPLICATE_REVIEW,
        "label": "Doublon à vérifier",
        "description": "Offre ressemblante : choisissez si elle est identique ou indépendante.",
        "group": "offers",
    },
    {
        "status": JobStatus.SCRAPED,
        "label": "Nouvelle",
        "description": "Offre passée le filtre local, en attente d’analyse.",
        "group": "offers",
    },
    {
        "status": JobStatus.ANALYZED,
        "label": "Analysée",
        "description": "Analyse détaillée terminée.",
        "group": "offers",
    },
    {
        "status": JobStatus.SHORTLISTED,
        "label": "Top sélection",
        "description": "Offre ajoutée à votre Top sélection.",
        "group": "offers",
    },
    {
        "status": JobStatus.READY_FOR_FORM_SUBMISSION,
        "label": "Prête",
        "description": "CV et lettre disponibles.",
        "group": "applications",
    },
    {
        "status": JobStatus.QUALITY_REJECTED,
        "label": "À corriger",
        "description": "Les documents nécessitent une correction.",
        "group": "applications",
    },
    {
        "status": JobStatus.SENT,
        "label": "Envoyée",
        "description": "Candidature envoyée.",
        "group": "applications",
    },
    {
        "status": JobStatus.INTERVIEW,
        "label": "Entretien",
        "description": "Entretien obtenu.",
        "group": "applications",
    },
    {
        "status": JobStatus.REJECTED,
        "label": "Refusée",
        "description": "Réponse négative enregistrée.",
        "group": "applications",
    },
    {
        "status": JobStatus.ARCHIVED,
        "label": "Archivée",
        "description": "Offre retirée de la liste active.",
        "group": "applications",
    },
)

STATUS_LABELS = {row["status"]: row["label"] for row in STATUS_FLOW}

# States exposed by the unified Offers page. ``FILTERED`` is deliberately
# absent: it is the internal result of local filtering and is presented as
# ``Nouvelle`` through the SCRAPED state. Detailed application-tracking states
# remain available in the offer detail and workflow, but are not filters.
OFFER_FILTER_STATUSES = (
    JobStatus.DUPLICATE_REVIEW,
    JobStatus.SCRAPED,
    JobStatus.ANALYZED,
    JobStatus.SHORTLISTED,
    JobStatus.READY_FOR_FORM_SUBMISSION,
    JobStatus.SENT,
    JobStatus.ARCHIVED,
)


def status_label(status: str) -> str:
    """Return the concise product label for a persisted status."""
    if status == JobStatus.FILTERED:
        # FILTERED is an internal marker, never a user-facing label.
        status = JobStatus.SCRAPED
    return STATUS_LABELS.get(status, status.replace("_", " ").title())
