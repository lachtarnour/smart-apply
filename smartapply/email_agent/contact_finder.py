"""Public recruitment contact finder.

Strategy:
1. Resolve the company homepage from the application URL (or directly).
2. Crawl a small list of candidate pages: /careers, /jobs, /contact, etc.
3. Extract email addresses via regex.
4. Score each by recipient type (recrutement@ > jobs@ > hr@ > contact@).
5. Drop obviously bad addresses (noreply@, postmaster@).

We deliberately avoid LinkedIn or any address that requires authentication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from smartapply.logging_setup import get_logger

logger = get_logger(__name__)


CANDIDATE_PATHS = [
    "",
    "/contact",
    "/contact-us",
    "/contactez-nous",
    "/careers",
    "/career",
    "/jobs",
    "/recrutement",
    "/nous-rejoindre",
    "/team",
    "/about",
    "/about-us",
    "/qui-sommes-nous",
]

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)

# Higher score = more likely to be a real recruitment contact.
PREFIX_SCORES: list[tuple[str, float]] = [
    ("recrutement", 0.95),
    ("recruit", 0.95),
    ("jobs", 0.9),
    ("careers", 0.9),
    ("carrieres", 0.9),
    ("talent", 0.85),
    ("hiring", 0.85),
    ("hr", 0.75),
    ("rh", 0.75),
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

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 SmartApplyAI/0.1"
    )
}


@dataclass(frozen=True)
class FoundContact:
    email: str
    source_url: str
    confidence: float


def score_email(email: str) -> float:
    prefix = email.split("@", 1)[0].lower()
    if prefix in BLOCKED_PREFIXES:
        return 0.0
    for keyword, score in PREFIX_SCORES:
        if prefix.startswith(keyword) or keyword in prefix:
            return score
    # Generic person-like prefix (firstname.lastname@) — neutral
    return 0.5


def _normalize_base_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


class ContactFinder:
    def __init__(
        self,
        timeout: int = 15,
        max_pages: int = 6,
        min_confidence: float = 0.4,
    ):
        self.timeout = timeout
        self.max_pages = max_pages
        self.min_confidence = min_confidence

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=False,
    )
    def _fetch(self, url: str) -> str | None:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=self.timeout)
            if response.status_code >= 400:
                return None
            return response.text
        except requests.RequestException as e:
            logger.debug("Skipping %s: %s", url, e)
            return None

    def find(self, base_url: str) -> list[FoundContact]:
        base = _normalize_base_url(base_url)
        if base is None:
            return []
        seen_emails: dict[str, FoundContact] = {}
        for path in CANDIDATE_PATHS[: self.max_pages + 1]:
            url = urljoin(base, path) if path else base
            html = self._fetch(url)
            if not html:
                continue
            text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
            for raw in EMAIL_RE.findall(text):
                email = raw.lower().strip(".,;:")
                if email in seen_emails:
                    continue
                conf = score_email(email)
                if conf < self.min_confidence:
                    continue
                seen_emails[email] = FoundContact(email=email, source_url=url, confidence=conf)
        return sorted(seen_emails.values(), key=lambda c: c.confidence, reverse=True)

    def best(self, base_url: str) -> FoundContact | None:
        contacts = self.find(base_url)
        return contacts[0] if contacts else None
