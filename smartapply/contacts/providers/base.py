"""Contact provider protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod

from smartapply.contacts.models import ContactCandidate


class ContactProvider(ABC):
    name: str = ""

    def is_available(self) -> bool:
        return True

    @abstractmethod
    def find(
        self,
        *,
        company: str,
        application_url: str | None,
        job_location: str | None = None,
    ) -> list[ContactCandidate]:
        """Return ranked contact candidates."""
