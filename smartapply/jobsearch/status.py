"""Status metadata shared by the macOS application and business services."""

from __future__ import annotations

from typing import Any

from smartapply.database.models import JobStatus

STATUS_FLOW: tuple[dict[str, Any], ...] = (
    {
        "status": JobStatus.SCRAPED,
        "label": "Nouvelle",
        "description": "Offre importée.",
        "group": "offers",
    },
    {
        "status": JobStatus.FILTERED,
        "label": "Retenue",
        "description": "Offre retenue par le filtrage local.",
        "group": "offers",
    },
    {
        "status": JobStatus.SHORTLISTED,
        "label": "Top sélection",
        "description": "Offre ajoutée à votre Top sélection.",
        "group": "offers",
    },
    {
        "status": JobStatus.ANALYZED,
        "label": "Analysée",
        "description": "Analyse détaillée terminée.",
        "group": "offers",
    },
    {
        "status": JobStatus.READY_FOR_FORM_SUBMISSION,
        "label": "À relire",
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


def status_label(status: str) -> str:
    """Return the concise product label for a persisted status."""
    return STATUS_LABELS.get(status, status.replace("_", " ").title())
