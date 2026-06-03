"""Practical application-tracking helpers.

The project is first a job-search companion, so this module keeps the
human workflow visible: what state a candidature is in, and what should
happen next.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from smartapply.database.models import JobStatus


APPLICATION_STATUSES = [
    JobStatus.EMAIL_GENERATED,
    JobStatus.DRAFT_CREATED,
    JobStatus.READY_FOR_FORM_SUBMISSION,
    JobStatus.CONTACT_MISSING,
    JobStatus.QUALITY_REJECTED,
    JobStatus.SENT,
    JobStatus.INTERVIEW,
    JobStatus.REJECTED,
    JobStatus.ARCHIVED,
]

STATUS_LABELS = {
    JobStatus.EMAIL_GENERATED: "Email pret",
    JobStatus.DRAFT_CREATED: "Brouillon Gmail",
    JobStatus.READY_FOR_FORM_SUBMISSION: "Dossier pret",
    JobStatus.CONTACT_MISSING: "Contact manquant",
    JobStatus.QUALITY_REJECTED: "Rejete qualite",
    JobStatus.SENT: "Envoyee",
    JobStatus.INTERVIEW: "Entretien",
    JobStatus.REJECTED: "Refusee",
    JobStatus.ARCHIVED: "Archivee",
}


def _date_label(value: datetime | None, *, days: int) -> str:
    if value is None:
        return f"J+{days}"
    due = value + timedelta(days=days)
    return due.strftime("%d/%m/%Y")


def next_action_for(
    status: str,
    updated_at: datetime | None = None,
    *,
    has_contact: bool = False,
    has_gmail_draft: bool = False,
) -> str:
    """Return a short next-action hint for the application tracker."""
    if status == JobStatus.EMAIL_GENERATED:
        if has_contact:
            return "Relire le CV/email, puis envoyer aujourd'hui"
        return "Trouver un contact ou envoyer via le formulaire"
    if status == JobStatus.DRAFT_CREATED:
        return "Verifier le brouillon Gmail, puis envoyer"
    if status == JobStatus.READY_FOR_FORM_SUBMISSION:
        return "Soumettre via le formulaire de l'offre"
    if status == JobStatus.CONTACT_MISSING:
        return "Chercher un contact RH ou utiliser le formulaire"
    if status == JobStatus.QUALITY_REJECTED:
        return "Ne pas candidater sans reprise manuelle"
    if status == JobStatus.SENT:
        return f"Relancer si pas de reponse le {_date_label(updated_at, days=7)}"
    if status == JobStatus.INTERVIEW:
        return "Preparer l'entretien et noter les questions"
    if status == JobStatus.REJECTED:
        return "Noter le retour utile puis archiver"
    if status == JobStatus.ARCHIVED:
        return "Aucune action"
    if has_gmail_draft:
        return "Verifier le brouillon Gmail"
    return "Choisir la prochaine action"
