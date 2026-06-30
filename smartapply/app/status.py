"""Business status metadata used by the Streamlit UI."""

from __future__ import annotations

from typing import Any

from smartapply.database.models import JobStatus

STATUS_FLOW: list[dict[str, Any]] = [
    {
        "status": JobStatus.SCRAPED,
        "label": "Collectée",
        "description": "Offre importée depuis une source, pas encore filtrée.",
        "group": "Pipeline principal",
        "color": "#8D8D8D",
    },
    {
        "status": JobStatus.FILTERED,
        "label": "Filtrée",
        "description": "Offre gardée après filtre local, encore active même hors top-K.",
        "group": "Pipeline principal",
        "color": "#78A9FF",
    },
    {
        "status": JobStatus.SHORTLISTED,
        "label": "Shortlistée",
        "description": "Bon score local avant analyse détaillée.",
        "group": "Pipeline principal",
        "color": "#A6C8FF",
    },
    {
        "status": JobStatus.ANALYZED,
        "label": "Analysée LLM",
        "description": "Le LLM a identifié rôle, compétences, risques et matching.",
        "group": "Pipeline principal",
        "color": "#82CFFF",
    },
    {
        "status": JobStatus.CV_GENERATED,
        "label": "CV généré",
        "description": "CV adapté produit, avant finalisation email/lettre.",
        "group": "Pipeline principal",
        "color": "#C6C6C6",
    },
    {
        "status": JobStatus.EMAIL_GENERATED,
        "label": "Dossier prêt",
        "description": "CV, lettre, email et pièces jointes sont prêts à relire.",
        "group": "Pipeline principal",
        "color": "#D0E2FF",
    },
    {
        "status": JobStatus.DRAFT_CREATED,
        "label": "Brouillon Gmail",
        "description": "Brouillon créé dans Gmail, rien n'est envoyé automatiquement.",
        "group": "Pipeline principal",
        "color": "#A8A8A8",
    },
    {
        "status": JobStatus.READY_FOR_FORM_SUBMISSION,
        "label": "Formulaire prêt",
        "description": "Pas d'email fiable, dossier prêt pour soumission ATS/formulaire.",
        "group": "Pipeline principal",
        "color": "#BAE6FF",
    },
    {
        "status": JobStatus.SENT,
        "label": "Envoyée",
        "description": "Email envoyé ou formulaire soumis.",
        "group": "Pipeline principal",
        "color": "#78A9FF",
    },
    {
        "status": JobStatus.INTERVIEW,
        "label": "Entretien",
        "description": "Candidature convertie en échange recruteur.",
        "group": "Pipeline principal",
        "color": "#D2B36A",
    },
    {
        "status": JobStatus.CONTACT_MISSING,
        "label": "Contact manquant",
        "description": "Le dossier existe, mais aucun contact fiable n'a été trouvé.",
        "group": "Blocages et rejets",
        "color": "#D2B36A",
    },
    {
        "status": JobStatus.QUALITY_REJECTED,
        "label": "Rejet qualité",
        "description": "Le quality gate bloque la candidature.",
        "group": "Blocages et rejets",
        "color": "#FFB3B8",
    },
    {
        "status": JobStatus.REJECTED,
        "label": "Refusée",
        "description": "Retour négatif reçu ou candidature à abandonner.",
        "group": "Blocages et rejets",
        "color": "#FF8389",
    },
    {
        "status": JobStatus.ARCHIVED,
        "label": "Archivée",
        "description": "Offre retirée du pipeline actif.",
        "group": "Blocages et rejets",
        "color": "#A8A8A8",
    },
]

STATUS_LABEL_BY_KEY = {row["status"]: row["label"] for row in STATUS_FLOW}


def status_label(status: str) -> str:
    return STATUS_LABEL_BY_KEY.get(status, status.replace("_", " ").title())


def ordered_status_rows(
    counts: dict[str, int],
    *,
    include_zero: bool = True,
    group: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    known = {row["status"] for row in STATUS_FLOW}
    for order, meta in enumerate(STATUS_FLOW, start=1):
        if group and meta["group"] != group:
            continue
        count = int(counts.get(meta["status"], 0))
        if count == 0 and not include_zero:
            continue
        rows.append(
            {
                **meta,
                "order": order,
                "count": count,
                "axis_label": f"{order}. {meta['label']}",
            }
        )
    for status, count in sorted(counts.items()):
        if status in known or (count == 0 and not include_zero):
            continue
        rows.append(
            {
                "status": status,
                "label": status_label(status),
                "description": "Statut non documenté dans le pipeline.",
                "group": "Autres",
                "color": "#A8A8A8",
                "order": len(rows) + 1,
                "count": int(count),
                "axis_label": f"{len(rows) + 1}. {status_label(status)}",
            }
        )
    return rows
