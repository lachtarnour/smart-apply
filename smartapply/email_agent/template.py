"""Deterministic application email templates."""

from __future__ import annotations

from smartapply.llm import EmailDraft


def build_application_email(
    *,
    candidate_name: str,
    job_title: str,
    job_company: str,
    language: str = "fr",
) -> EmailDraft:
    """Return a short sending email for CV + motivation letter attachments."""
    if language == "fr":
        return EmailDraft(
            subject=f"Candidature - {job_title} - {candidate_name}",
            body=(
                "Bonjour,\n\n"
                f"Je vous adresse ma candidature pour le poste de {job_title} "
                f"chez {job_company}.\n\n"
                "Vous trouverez ci-joint mon dossier de candidature. "
                "Je reste disponible pour échanger sur mon profil et ma motivation.\n\n"
                "Cordialement,\n"
                f"{candidate_name}"
            ),
        )

    return EmailDraft(
        subject=f"Application - {job_title} - {candidate_name}",
        body=(
            "Dear Hiring Team,\n\n"
            f"I am sending you my application for the {job_title} position "
            f"at {job_company}.\n\n"
            "Please find attached my application documents. "
            "I would be happy to discuss my profile and motivation further.\n\n"
            "Best regards,\n"
            f"{candidate_name}"
        ),
    )
