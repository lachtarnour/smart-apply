"""Cheap local heuristic to guess the offer language for output text.

The CV is always rendered in English. The email/motivation letter, however,
follows the offer language so recruiters get a culturally-aligned message.
"""

from __future__ import annotations


_FRENCH_MARKERS = (
    "vos missions",
    "profil recherché",
    "profil recherche",
    "candidature",
    "poste",
    "maîtrise",
    "maitrise",
    "expérience",
    "développement",
    "developpement",
    "requis",
    "anglais courant",
    "cdi",
    "île-de-france",
)
_ENGLISH_MARKERS = (
    "responsibilities",
    "requirements",
    "apply",
    "role",
    "candidate",
    "experience required",
    "english",
    "remote",
)


def detect_offer_language(text: str) -> str:
    """Return 'fr' or 'en' based on bilingual keyword hits.

    Ties resolve to French — the candidate is Paris-based and most offers
    in scope are FR; this avoids accidentally English replies to French postings.
    """
    normalized = (text or "").lower()
    french_score = sum(1 for marker in _FRENCH_MARKERS if marker in normalized)
    english_score = sum(1 for marker in _ENGLISH_MARKERS if marker in normalized)
    return "fr" if french_score >= english_score else "en"
