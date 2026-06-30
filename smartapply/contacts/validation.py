"""Contact candidate validation and ranking helpers."""

from __future__ import annotations

from smartapply.contacts.models import ContactCandidate

# Higher score = more likely to be a real recruitment contact.
PREFIX_SCORES: list[tuple[str, float]] = [
    ("recrutement", 0.99),
    ("recruit", 0.99),
    ("jobs", 0.98),
    ("careers", 0.98),
    ("carrieres", 0.98),
    ("talent", 0.97),
    ("hiring", 0.97),
    ("hr", 0.97),
    ("rh", 0.97),
    ("contact", 0.6),
    ("hello", 0.5),
    ("info", 0.4),
    ("support", 0.2),
    ("press", 0.1),
]

BLOCKED_PREFIXES = {
    "noreply",
    "no-reply",
    "donotreply",
    "postmaster",
    "abuse",
    "mailer-daemon",
    "webmaster",
}

def score_email(email: str) -> float:
    prefix = email.split("@", 1)[0].lower()
    if prefix in BLOCKED_PREFIXES:
        return 0.0
    for keyword, score in PREFIX_SCORES:
        if prefix.startswith(keyword) or keyword in prefix:
            return score
    # Generic person-like prefix (firstname.lastname@) — neutral.
    return 0.5


def is_recruitment_generic_email(email: str) -> bool:
    """True for role-based recruitment/RH addresses we prefer as primary To."""
    return score_email(email) >= 0.97

def _dedupe_rank(candidates: list[ContactCandidate]) -> list[ContactCandidate]:
    best: dict[str, ContactCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.email)
        if current is None or candidate.confidence > current.confidence:
            best[candidate.email] = candidate
    return sorted(best.values(), key=lambda c: c.confidence, reverse=True)
