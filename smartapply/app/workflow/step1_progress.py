"""Progress formatting helpers for Welcome to the Jungle scraping."""

from __future__ import annotations

from typing import Any


def _event_int(event: dict[str, Any], key: str) -> int | None:
    value = event.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _wttj_progress_fraction(event: dict[str, Any]) -> float:
    event_name = str(event.get("event") or "")
    yielded = _event_int(event, "yielded") or 0
    target = _event_int(event, "progress_target") or _event_int(event, "max_jobs")
    if event_name == "done":
        return 1.0
    if target and target > 0:
        partial = {
            "page_fetch_start": 0.05,
            "page_links": 0.15,
            "job_detail_start": 0.35,
            "company_profile_start": 0.7,
        }.get(event_name, 0.0)
        return max(0.0, min(0.99, (yielded + partial) / target))

    page = _event_int(event, "page")
    pages_total = _event_int(event, "page_count") or _event_int(event, "pages_total")
    if not page or not pages_total:
        return 0.0
    partial = {
        "page_fetch_start": 0.05,
        "page_links": 0.25,
        "job_detail_start": 0.55,
        "company_profile_start": 0.75,
        "job_yielded": 0.9,
    }.get(event_name, 0.15)
    return max(0.0, min(0.99, ((page - 1) + partial) / pages_total))


def _wttj_progress_text(event: dict[str, Any]) -> str:
    event_name = str(event.get("event") or "")
    yielded = _event_int(event, "yielded") or 0
    target = _event_int(event, "progress_target") or _event_int(event, "max_jobs")
    page = _event_int(event, "page")
    pages_total = _event_int(event, "page_count") or _event_int(event, "pages_total")
    page_text = f"page {page}/{pages_total}" if page and pages_total else "préparation"
    count_text = f"{yielded}/{target} récupérée(s)" if target else f"{yielded} récupérée(s)"

    if event_name == "start":
        return f"WTTJ: préparation · objectif {target} offre(s)" if target else "WTTJ: préparation"
    if event_name == "page_fetch_start":
        return f"WTTJ: {page_text} · chargement des matches · {count_text}"
    if event_name == "page_links":
        links = _event_int(event, "links") or 0
        return f"WTTJ: {page_text} · {links} lien(s) trouvé(s) · {count_text}"
    if event_name == "page_empty":
        return f"WTTJ: {page_text} vide · arrêt de la recherche"
    if event_name == "page_duplicate":
        return f"WTTJ: {page_text} déjà lue · arrêt de la recherche"
    if event_name == "job_detail_start":
        page_job_index = _event_int(event, "page_job_index") or 0
        page_jobs = _event_int(event, "page_jobs") or 0
        return f"WTTJ: {page_text} · lecture offre {page_job_index}/{page_jobs} · {count_text}"
    if event_name == "company_profile_start":
        company = str(event.get("company") or "entreprise")
        return f"WTTJ: enrichissement {company[:40]} · {count_text}"
    if event_name == "job_yielded":
        title = str(event.get("title") or "offre")
        return f"WTTJ: {count_text} · {title[:50]}"
    if event_name == "done":
        return f"WTTJ: terminé · {count_text}"
    return f"WTTJ: {page_text} · {count_text}"


def _wttj_progress_callback(progress_widget: Any):
    def _callback(event: dict[str, Any]) -> None:
        progress_widget.progress(
            _wttj_progress_fraction(event),
            text=_wttj_progress_text(event),
        )

    return _callback
