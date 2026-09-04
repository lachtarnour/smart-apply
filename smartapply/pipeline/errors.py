"""Pipeline exceptions with user-facing, actionable messages."""

from __future__ import annotations


class ApplicationAlreadyExistsError(RuntimeError):
    """Raised before generation when a job already owns an application."""

    def __init__(self, job_id: int, application_id: int | None = None):
        self.job_id = job_id
        self.application_id = application_id
        suffix = f" (dossier {application_id})" if application_id is not None else ""
        super().__init__(
            f"Un dossier existe déjà pour l’offre {job_id}{suffix}. "
            "Aucun nouvel appel IA n’a été lancé."
        )
