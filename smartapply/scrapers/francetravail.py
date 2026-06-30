"""France Travail (ex Pôle emploi) — Offres d'emploi v2 API.

Documentation: https://francetravail.io/data/api/offres-emploi

Auth: OAuth 2.0 client_credentials. The token is cached in-memory for its
lifetime (1500s default).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from smartapply.config import get_settings
from smartapply.logging_setup import get_logger
from smartapply.offers import RawJob, make_external_id
from smartapply.scrapers.base import Scraper, ScraperConfigError
from smartapply.scrapers.francetravail_experience import (
    _extract_experience,
    _format_experience_section,
)
from smartapply.utils.contracts import normalize_source_contract_type
from smartapply.utils.french_geo import resolve_french_location

logger = get_logger(__name__)

TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=%2Fpartenaire"
)
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"

# Map the shared SerpApi-style freshness tokens (``today``/``3days``/``week``/``month``)
# to the equivalent rolling window in days. France Travail's API uses
# ``minCreationDate`` (ISO 8601 UTC), not chips, so we derive the threshold here.
_DATE_POSTED_TO_DAYS = {
    "today": 1,
    "3days": 3,
    "week": 7,
    "month": 30,
}

def _date_posted_to_creation_window(
    date_posted: str | None, *, now: datetime | None = None
) -> tuple[str, str] | None:
    """Convert a ``date_posted`` token to a ``(min, max)`` ISO creation window.

    ``any`` (or unknown) returns ``None`` so no filter is appended. The FT API
    requires ``minCreationDate`` and ``maxCreationDate`` to be sent together
    (error 1780533709701), so the helper always returns the pair when active.

    ``now`` is injectable so tests can lock the window instead of relying on
    wall-clock. Format is the only one accepted by FT: ``YYYY-MM-DDTHH:MM:SSZ``.
    """
    if not date_posted:
        return None
    # Reuse the SerpApi normaliser so both scrapers accept the same aliases
    # (``lastweek``, ``7days``, etc.) without redefining them.
    from smartapply.scrapers.serpapi import normalize_date_posted

    normalized = normalize_date_posted(date_posted)
    days = _DATE_POSTED_TO_DAYS.get(normalized)
    if days is None:
        return None
    reference = now or datetime.now(tz=timezone.utc)
    threshold = reference - timedelta(days=days)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return threshold.strftime(fmt), reference.strftime(fmt)


# ---- Location resolution -----------------------------------------------------
# Free-text locations ("Paris", "Île-de-France", "La Défense", …) are mapped
# to FT's structured filters via :mod:`smartapply.utils.french_geo`, which is
# backed by the open ``geo.api.gouv.fr`` referential. Without this layer the
# old code path silently appended the location to ``motsCles``, which made
# "Paris, France" return only offers whose text literally contained the word
# "Paris" — about a third of the real Paris job pool.


def _resolve_ft_location_params(
    location: str | None,
) -> tuple[dict[str, str], str | None]:
    """Translate a free-text location to FT API params.

    Returns ``(structured, keyword)``:

    - ``structured``: dict of FT params (``region`` / ``departement`` /
      ``commune``) to merge into the request. Empty when no structured
      match is available.
    - ``keyword``: the string to append to ``motsCles`` when the location
      could not be resolved. ``None`` means "no location filter at all"
      (national search).

    Resolution rules live in :func:`resolve_french_location`. This function
    is a thin adapter that maps the generic :class:`ResolvedLocation` to
    the parameter names the FT API understands.
    """
    resolved = resolve_french_location(location)
    if resolved.national:
        return ({}, None)
    if resolved.region:
        return ({"region": resolved.region}, None)
    if resolved.departement:
        return ({"departement": resolved.departement}, None)
    if resolved.commune:
        return ({"commune": resolved.commune}, None)
    # Unresolved: preserve the previous keyword-append behaviour so we
    # never silently lose recall on a typo or an unmapped place.
    return ({}, resolved.unresolved or location)


class FranceTravailScraper(Scraper):
    name = "francetravail"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
    ):
        settings = get_settings()
        self.client_id = client_id or settings.francetravail_client_id
        self.client_secret = client_secret or settings.francetravail_client_secret
        self.scope = scope or settings.francetravail_scope
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def is_available(self) -> bool:
        return bool(self.client_id and self.client_secret)

    # -------------------- auth --------------------

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token
        if not self.is_available():
            raise ScraperConfigError(
                "FRANCETRAVAIL_CLIENT_ID/SECRET must be set to use this scraper"
            )
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + payload.get("expires_in", 1500)
        return self._token

    # -------------------- search --------------------

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    def _fetch_range(
        self, *, params: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        response = requests.get(SEARCH_URL, params=params, headers=headers, timeout=30)
        if response.status_code == 204:
            return {}
        response.raise_for_status()
        return response.json()

    def search(
        self,
        query: str,
        location: str | None = None,
        *,
        max_results: int | None = None,
        commune: str | None = None,
        departement: str | None = None,
        type_contrat: str | None = None,
        date_posted: str | None = None,
        **kwargs: Any,
    ) -> Iterator[RawJob]:
        if max_results is not None and max_results <= 0:
            return

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        creation_window = _date_posted_to_creation_window(date_posted)

        # Resolve the free-text location once. Explicit ``commune`` /
        # ``departement`` kwargs always win — the resolver only runs when the
        # caller did not supply a structured filter itself.
        if commune or departement:
            structured_location: dict[str, str] = {}
            keyword_location: str | None = None
        else:
            structured_location, keyword_location = _resolve_ft_location_params(location)

        # France Travail paginates by `range=start-end`, max 150 per request.
        page_size = 50
        results_yielded = 0
        offset = 0

        while True:
            end = offset + page_size - 1
            params: dict[str, Any] = {
                "motsCles": query,
                "range": f"{offset}-{end}",
            }
            if commune:
                params["commune"] = commune
            if departement:
                params["departement"] = departement
            for structured_key, structured_value in structured_location.items():
                params.setdefault(structured_key, structured_value)
            if type_contrat:
                params["typeContrat"] = type_contrat
            if creation_window:
                params["minCreationDate"], params["maxCreationDate"] = creation_window
            if keyword_location:
                params["motsCles"] = f"{query} {keyword_location}".strip()

            try:
                payload = self._fetch_range(params=params, headers=headers)
            except requests.RequestException as e:
                logger.error("France Travail request failed: %s", e)
                break

            jobs = payload.get("resultats") or []
            if not jobs:
                break

            for raw in jobs:
                job = self._to_raw_job(raw)
                if job is None:
                    continue
                yield job
                results_yielded += 1
                if max_results is not None and results_yielded >= max_results:
                    return

            offset += page_size
            # 1149 is the maximum offset supported by FT API
            if len(jobs) < page_size or offset > 1149:
                break

    # -------------------- mapping --------------------

    def _to_raw_job(self, raw: dict[str, Any]) -> RawJob | None:
        title = raw.get("intitule")
        entreprise = raw.get("entreprise") or {}
        company = entreprise.get("nom") or "Entreprise non communiquée"
        if not title:
            return None

        ext_id = raw.get("id") or ""
        external_id = make_external_id(self.name, ext_id, title, company)

        lieu_travail = raw.get("lieuTravail") or {}
        location = lieu_travail.get("libelle")

        # Many FT offers leave ``entreprise.nom`` empty but ship the real hiring
        # entity name (or a "Name - tagline" header) in ``entreprise.description``.
        # Prepend that text so the LLM extractor — and human reviewers — see it.
        entreprise_desc = (entreprise.get("description") or "").strip()
        company_header = (
            f"À propos de l'entreprise :\n{entreprise_desc}" if entreprise_desc else ""
        )
        experience = _extract_experience(raw)
        experience_section = _format_experience_section(experience)

        description_parts = [
            company_header,
            experience_section,
            raw.get("description") or "",
            raw.get("competences") and "Compétences:\n- " + "\n- ".join(
                f"{c.get('libelle','')} ({c.get('exigence','')})"
                for c in (raw.get("competences") or [])
            ),
            raw.get("qualitesProfessionnelles") and "Qualités:\n- " + "\n- ".join(
                q.get("libelle", "") for q in (raw.get("qualitesProfessionnelles") or [])
            ),
        ]
        description = "\n\n".join(p.strip() for p in description_parts if p)

        contract_type = normalize_source_contract_type(
            raw.get("typeContratLibelle") or raw.get("natureContrat")
        )
        remote_policy: str | None = None
        if isinstance(raw.get("trancheSalaire"), str) and "télétravail" in raw.get(
            "trancheSalaire", ""
        ).lower():
            remote_policy = "remote"

        published: datetime | None = None
        if pub := raw.get("dateCreation"):
            try:
                published = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                published = None

        application_url = raw.get("origineOffre", {}).get("urlOrigine")

        source_data = dict(raw)
        if experience:
            source_data["_smartapply_experience"] = experience

        return RawJob(
            external_id=external_id,
            title=title.strip(),
            company=company.strip(),
            location=location,
            contract_type=contract_type,
            remote_policy=remote_policy,
            description=description,
            experience=experience,
            application_url=application_url,
            published_date=published,
            source=self.name,
            source_data=source_data,
        )
