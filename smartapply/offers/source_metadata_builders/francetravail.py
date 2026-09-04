"""France Travail metadata blocks for analyzer prompts."""

from __future__ import annotations

from typing import Any

from smartapply.offers.source_metadata_builders.common import (
    _MAX_URLS,
    _add_url,
    _add_urls_from_text,
    _append_context_summary,
    _append_list_summary,
    _append_scalar,
    _compact_mapping,
    _dict,
)


def build_francetravail_source_metadata(source_data: dict[str, Any] | None) -> str:
    """Build a compact France Travail metadata block without raw JSON."""
    if not isinstance(source_data, dict):
        return ""

    url_lines = _application_url_lines(source_data)
    fact_lines = _structured_job_fact_lines(source_data)
    if not url_lines and not fact_lines:
        return ""

    sections: list[str] = []
    if url_lines:
        sections.append("APPLICATION_URL_METADATA:\n" + "\n".join(url_lines))
    if fact_lines:
        sections.append("STRUCTURED_JOB_FACTS:\n" + "\n".join(fact_lines))
    return "\n\n".join(sections)


def _application_url_lines(source_data: dict[str, Any]) -> list[str]:
    entreprise = _dict(source_data.get("entreprise"))
    contact = _dict(source_data.get("contact"))
    origine = _dict(source_data.get("origineOffre"))
    lines = ["source: francetravail"]
    _append_scalar(lines, "raw_id", source_data.get("id"))
    _append_scalar(lines, "entreprise.nom", entreprise.get("nom"))
    _append_scalar(lines, "origineOffre.origine", origine.get("origine"))
    _append_scalar(lines, "contact.nom", contact.get("nom"))
    _append_scalar(lines, "contact.courriel", contact.get("courriel"))

    urls: list[dict[str, str]] = []
    _add_url(urls, origine.get("urlOrigine"), "origineOffre.urlOrigine")
    for index, partner in enumerate(origine.get("partenaires") or []):
        if not isinstance(partner, dict):
            continue
        _append_scalar(lines, f"origineOffre.partenaires[{index}].nom", partner.get("nom"))
        _add_url(
            urls,
            partner.get("url"),
            f"origineOffre.partenaires[{index}].url",
        )
    _add_url(urls, contact.get("urlPostulation"), "contact.urlPostulation")
    _add_urls_from_text(urls, contact.get("coordonnees1"), "contact.coordonnees1")
    _add_url(urls, entreprise.get("url"), "entreprise.url")
    _add_urls_from_text(urls, source_data.get("description"), "description")
    _add_urls_from_text(urls, entreprise.get("description"), "entreprise.description")

    for item in urls[:_MAX_URLS]:
        line = (
            f"url: source_field={item['source_field']} | url={item['url']} | "
            f"domain={item['domain']} | url_kind={item['url_kind']}"
        )
        if item.get("company_domain_candidate"):
            line += f" | company_domain_candidate={item['company_domain_candidate']}"
        lines.append(line)
    return lines


def _structured_job_fact_lines(source_data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key in (
        "experienceExige",
        "experienceLibelle",
        "typeContratLibelle",
        "natureContrat",
        "dureeTravailLibelle",
        "salaire",
        "secteurActiviteLibelle",
        "trancheEffectifEtab",
        "nombrePostes",
        "deplacementLibelle",
    ):
        _append_scalar(lines, key, source_data.get(key))

    if source_data.get("_smartapply_experience"):
        _append_scalar(
            lines, "_smartapply_experience", _compact_mapping(source_data["_smartapply_experience"])
        )
    _append_list_summary(
        lines,
        "formations",
        source_data.get("formations"),
        ("niveauLibelle", "domaineLibelle", "commentaire"),
    )
    _append_list_summary(lines, "langues", source_data.get("langues"), ("libelle", "exigence"))
    _append_list_summary(
        lines, "competences", source_data.get("competences"), ("libelle", "exigence")
    )
    _append_list_summary(
        lines,
        "qualitesProfessionnelles",
        source_data.get("qualitesProfessionnelles"),
        ("libelle", "description"),
    )
    _append_context_summary(lines, source_data.get("contexteTravail"))
    return lines
