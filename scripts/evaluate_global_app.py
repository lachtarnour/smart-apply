"""End-to-end evaluation runner for SmartApply.

This script intentionally exercises the production pipeline on a fresh DB:
- fake offers that must be rejected by deterministic filters;
- real scraping across sources and locations;
- local filter, ranking, LLM analysis;
- CV / motivation letter / email generation;
- contact provider integration without creating Gmail drafts.

It writes a JSON report under ``data/evaluation/global_eval_report.json``.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from sqlalchemy import select

from smartapply.config import get_settings
from smartapply.database import init_db, session_scope
from smartapply.database.models import (
    Application,
    Contact,
    ContactLookupCache,
    GeneratedDocument,
    Job,
    JobScore,
    LLMUsage,
)
from smartapply.pipeline import Pipeline
from smartapply.pipeline.pipeline import freshness_kwargs


QUERY = "Data Scientist OR Machine Learning Engineer OR AI Engineer OR Data Analyst"
LOCATIONS = ["Paris, France", "Lyon, France"]
SOURCES = ["serpapi", "francetravail"]


FAKE_OFFERS = [
    {
        "key": "alternance_data_science",
        "title": "Alternance Data Science",
        "company": "Fake Reject School",
        "location": "Paris, France",
        "application_url": "https://example.invalid/jobs/alternance-data-science",
        "text": """
        Contrat: alternance.
        Nous recherchons un alternant Data Science pour construire des dashboards
        et explorer Python, SQL et machine learning avec l'equipe data.
        """,
        "expected_reason_prefix": "blocked_contract",
    },
    {
        "key": "pure_mlops_title",
        "title": "MLOps Engineer",
        "company": "Fake Infra Ops",
        "location": "Paris, France",
        "application_url": "https://example.invalid/jobs/mlops",
        "text": """
        Poste centre sur Kubernetes, Terraform, CI/CD, monitoring et astreintes.
        Le titre du poste est MLOps Engineer, pas data scientist.
        """,
        "expected_reason_prefix": "title_hard_reject",
    },
    {
        "key": "pure_devops_title",
        "title": "DevOps Engineer",
        "company": "Fake DevOps",
        "location": "Lyon, France",
        "application_url": "https://example.invalid/jobs/devops",
        "text": """
        Mission: infrastructure cloud, Terraform, Kubernetes, CI/CD, SRE,
        observabilite et support production.
        """,
        "expected_reason_prefix": "title_hard_reject",
    },
    {
        "key": "too_many_years",
        "title": "Data Scientist Generative AI",
        "company": "Fake Senior Gate",
        "location": "Paris, France",
        "application_url": "https://example.invalid/jobs/senior-years",
        "text": """
        CDI. Nous demandons 5 ans minimum d'experience professionnelle en data
        science, machine learning et mise en production de modeles.
        """,
        "expected_reason_prefix": "experience_required_too_high",
    },
    {
        "key": "foreign_location",
        "title": "Data Scientist NLP",
        "company": "Fake Foreign",
        "location": "Berlin, Germany",
        "application_url": "https://example.invalid/jobs/berlin-data",
        "text": """
        CDI base a Berlin. Build NLP and LLM products with Python and SQL.
        """,
        "expected_reason_prefix": "foreign_location",
    },
]


def _job_row(job: Job) -> dict[str, Any]:
    score = job.score
    analysis = job.analysis
    raw = analysis.raw_response if analysis and isinstance(analysis.raw_response, dict) else {}
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "source": job.source,
        "status": job.status,
        "score": round(score.final_score, 4) if score and score.final_score is not None else None,
        "rule_score": (
            round(score.rule_based_score, 4)
            if score and score.rule_based_score is not None
            else None
        ),
        "reasons": (score.components or {}).get("reasons", []) if score else [],
        "analysis": {
            "role_type": analysis.role_type if analysis else None,
            "seniority": analysis.seniority if analysis else None,
            "domain": analysis.domain if analysis else None,
            "company_size": raw.get("company_size"),
            "company_size_reason": raw.get("company_size_reason"),
            "offer_language": raw.get("offer_language"),
            "extracted_location": raw.get("extracted_location"),
            "company_context": raw.get("company_context"),
            "offer_interest_points": raw.get("offer_interest_points", []),
        },
    }


def _status_counts() -> dict[str, int]:
    with session_scope() as s:
        return dict(Counter(job.status for job in s.execute(select(Job)).scalars().all()))


def _table_count(model) -> int:  # noqa: ANN001
    with session_scope() as s:
        return len(s.execute(select(model)).scalars().all())


def inject_fake_offers(pipeline: Pipeline) -> tuple[list[int], list[dict[str, Any]]]:
    ids: list[int] = []
    inserted: list[dict[str, Any]] = []
    for fake in FAKE_OFFERS:
        report = pipeline.ingest_text(
            fake["text"],
            title=fake["title"],
            company=fake["company"],
            location=fake["location"],
            application_url=fake["application_url"],
        )
        job_id = int(report.job_ids[0])
        ids.append(job_id)
        inserted.append({"key": fake["key"], "job_id": job_id, "title": fake["title"]})
    return ids, inserted


def evaluate_fake_rejections(fake_ids: list[int]) -> list[dict[str, Any]]:
    expected_by_title = {fake["title"]: fake for fake in FAKE_OFFERS}
    out: list[dict[str, Any]] = []
    with session_scope() as s:
        jobs = s.execute(select(Job).where(Job.id.in_(fake_ids))).scalars().all()
        for job in jobs:
            fake = expected_by_title[job.title]
            reasons = (job.score.components or {}).get("reasons", []) if job.score else []
            expected = fake["expected_reason_prefix"]
            out.append(
                {
                    "key": fake["key"],
                    "job_id": job.id,
                    "title": job.title,
                    "status": job.status,
                    "reasons": reasons,
                    "passed": job.status == "archived"
                    and any(str(reason).startswith(expected) for reason in reasons),
                }
            )
    return sorted(out, key=lambda row: row["job_id"])


def scrape_real_offers(
    pipeline: Pipeline,
    *,
    max_per_source: int,
    date_posted: str,
    serpapi_hl: str,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for location in LOCATIONS:
        for source in SOURCES:
            kwargs = freshness_kwargs(
                source,
                date_posted=date_posted,
                serpapi_hl=serpapi_hl,
            )
            try:
                report = pipeline.ingest(
                    source,
                    QUERY,
                    location,
                    max_results=max_per_source,
                    **kwargs,
                )
                reports.append(
                    {
                        "source": source,
                        "location": location,
                        "ok": True,
                        "report": report.__dict__,
                    }
                )
            except Exception as exc:  # noqa: BLE001
                reports.append(
                    {
                        "source": source,
                        "location": location,
                        "ok": False,
                        "error": str(exc),
                    }
                )
    return reports


def top_analyzed_jobs(limit: int) -> list[int]:
    with session_scope() as s:
        stmt = (
            select(Job)
            .join(JobScore)
            .where(Job.source != "manual")
            .where(Job.status == "analyzed")
            .where(JobScore.final_score.is_not(None))
            .order_by(JobScore.final_score.desc())
            .limit(limit)
        )
        return [int(job.id) for job in s.execute(stmt).scalars().all()]


def generate_applications(
    pipeline: Pipeline,
    job_ids: list[int],
) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    for job_id in job_ids:
        try:
            report = pipeline.apply_to_autopilot(
                job_id,
                create_gmail_draft=False,
                require_quality_gate=False,
            )
            outputs.append(
                {
                    "job_id": report.job_id,
                    "application_id": report.application_id,
                    "status": report.status,
                    "strategy": report.application_strategy,
                    "company_size": report.company_size,
                    "contact_email_present": bool(report.contact_email),
                    "contact_domain": (
                        report.contact_email.split("@", 1)[1]
                        if report.contact_email and "@" in report.contact_email
                        else None
                    ),
                    "contact_source": report.contact_source,
                    "contact_cc_present": bool(report.contact_cc_email),
                    "gmail_draft_created": bool(report.gmail_draft_id),
                    "paths": {
                        "docx": report.docx_path,
                        "cv_pdf": report.cv_pdf_path,
                        "letter_pdf": report.letter_pdf_path,
                        "eml": report.eml_path,
                    },
                    "warnings": report.validation_warnings,
                    "errors": report.validation_errors,
                    "audit_contact": (report.audit or {}).get("contact"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            outputs.append({"job_id": job_id, "error": str(exc)})
    return outputs


def _eml_summary(path: str | None) -> dict[str, Any]:
    if not path:
        return {"exists": False}
    eml_path = Path(path)
    if not eml_path.exists():
        return {"exists": False, "path": path}
    message = BytesParser(policy=policy.default).parsebytes(eml_path.read_bytes())
    attachments = [
        part.get_filename()
        for part in message.iter_attachments()
        if part.get_filename()
    ]
    return {
        "exists": True,
        "path": path,
        "subject_present": bool(message.get("Subject")),
        "to_present": bool(message.get("To")),
        "cc_present": bool(message.get("Cc")),
        "attachments": attachments,
        "attachment_count": len(attachments),
    }


def inspect_applications() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with session_scope() as s:
        apps = s.execute(select(Application).order_by(Application.id.asc())).scalars().all()
        for app in apps:
            docs = {doc.doc_type: doc for doc in app.documents}
            letter = docs.get("motivation_letter")
            letter_body = letter.content if letter else ""
            raw = (
                app.job.analysis.raw_response
                if app.job and app.job.analysis and isinstance(app.job.analysis.raw_response, dict)
                else {}
            )
            paths = {
                "docx": app.cv_docx_path,
                "cv_pdf": app.cv_pdf_path,
                "letter_pdf": docs.get("motivation_letter_pdf").path
                if docs.get("motivation_letter_pdf")
                else None,
                "eml": app.eml_path,
            }
            out.append(
                {
                    "application_id": app.id,
                    "job_id": app.job_id,
                    "title": app.job.title if app.job else None,
                    "company": app.job.company if app.job else None,
                    "status": app.status,
                    "strategy": app.application_strategy,
                    "offer_language": raw.get("offer_language"),
                    "company_context_present": bool(raw.get("company_context")),
                    "interest_points_count": len(raw.get("offer_interest_points") or []),
                    "letter_chars": len(letter_body),
                    "letter_mentions_company": bool(app.job and app.job.company in letter_body),
                    "contact": {
                        "email_present": bool(app.contact.email if app.contact else None),
                        "domain": (
                            app.contact.email.split("@", 1)[1]
                            if app.contact and app.contact.email and "@" in app.contact.email
                            else None
                        ),
                        "source_url": app.contact.source_url if app.contact else None,
                        "confidence": app.contact.confidence if app.contact else None,
                        "reason": app.contact.decision_reason if app.contact else None,
                        "job_title": app.contact.job_title if app.contact else None,
                    },
                    "email": {
                        "subject_present": bool(app.email_subject),
                        "body_chars": len(app.email_body or ""),
                        "cc_present": bool(app.email_cc),
                        "eml": _eml_summary(app.eml_path),
                    },
                    "artifacts": {
                        key: {
                            "path": value,
                            "exists": bool(value and Path(value).exists()),
                            "size_bytes": Path(value).stat().st_size
                            if value and Path(value).exists()
                            else 0,
                        }
                        for key, value in paths.items()
                    },
                    "validation_warnings": app.validation_warnings or [],
                }
            )
    return out


def collect_jobs_snapshot(limit: int = 40) -> list[dict[str, Any]]:
    with session_scope() as s:
        jobs = (
            s.execute(select(Job).order_by(Job.scraped_at.asc()).limit(limit))
            .scalars()
            .all()
        )
        return [_job_row(job) for job in jobs]


def collect_top_ranked(limit: int = 20) -> list[dict[str, Any]]:
    with session_scope() as s:
        stmt = (
            select(Job)
            .join(JobScore)
            .where(JobScore.final_score.is_not(None))
            .order_by(JobScore.final_score.desc())
            .limit(limit)
        )
        return [_job_row(job) for job in s.execute(stmt).scalars().all()]


def collect_usage() -> dict[str, Any]:
    with session_scope() as s:
        rows = s.execute(select(LLMUsage)).scalars().all()
        by_purpose: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "cost_usd": 0.0, "cached": 0}
        )
        for row in rows:
            bucket = by_purpose[row.purpose]
            bucket["calls"] += 1
            bucket["cost_usd"] += float(row.cost_usd or 0.0)
            bucket["cached"] += 1 if row.cached else 0
        return {
            "total_calls": len(rows),
            "total_cost_usd": round(sum(float(row.cost_usd or 0.0) for row in rows), 6),
            "by_purpose": {
                key: {
                    "calls": value["calls"],
                    "cached": value["cached"],
                    "cost_usd": round(value["cost_usd"], 6),
                }
                for key, value in sorted(by_purpose.items())
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-source", type=int, default=14)
    parser.add_argument("--top-k-analyze", type=int, default=20)
    parser.add_argument("--target-applications", type=int, default=8)
    parser.add_argument("--date-posted", default="week")
    parser.add_argument("--serpapi-hl", default="en,fr")
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Only collect the current DB/output state into the JSON report.",
    )
    args = parser.parse_args()

    init_db()
    settings = get_settings()
    report_path = Path("data/evaluation/global_eval_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    pipeline = Pipeline()
    report: dict[str, Any] = {
        "settings": {
            "database_url": settings.database_url,
            "output_dir": str(settings.output_dir),
            "serpapi_hl": args.serpapi_hl,
            "date_posted": args.date_posted,
            "gmail_drafts_created": False,
        }
    }

    if args.collect_only:
        fake_ids = []
        with session_scope() as s:
            fake_ids = [
                int(job.id)
                for job in s.execute(
                    select(Job).where(Job.company.like("Fake%"))
                ).scalars().all()
            ]
        report["fake_offers"] = {"results": evaluate_fake_rejections(fake_ids)}
        report["status_counts_final"] = _status_counts()
        report["top_ranked"] = collect_top_ranked(limit=20)
        report["applications"] = inspect_applications()
        report["db_counts"] = {
            "jobs": _table_count(Job),
            "applications": _table_count(Application),
            "contacts": _table_count(Contact),
            "contact_lookup_cache": _table_count(ContactLookupCache),
            "generated_documents": _table_count(GeneratedDocument),
        }
        report["jobs_snapshot"] = collect_jobs_snapshot(limit=80)
        report["llm_usage"] = collect_usage()
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(json.dumps({"report_path": str(report_path), **report["db_counts"]}, indent=2))
        return

    fake_ids, fake_inserted = inject_fake_offers(pipeline)
    filter_report = pipeline.filter_pending(job_ids=fake_ids)
    report["fake_offers"] = {
        "inserted": fake_inserted,
        "filter_report": filter_report.__dict__,
        "results": evaluate_fake_rejections(fake_ids),
    }

    report["scraping"] = scrape_real_offers(
        pipeline,
        max_per_source=args.max_per_source,
        date_posted=args.date_posted,
        serpapi_hl=args.serpapi_hl,
    )

    process_report = pipeline.process_pending(top_k_analyze=args.top_k_analyze)
    report["process"] = process_report.__dict__
    report["status_counts_after_process"] = _status_counts()
    report["top_ranked"] = collect_top_ranked(limit=20)

    job_ids = top_analyzed_jobs(limit=args.target_applications)
    report["generation_target_job_ids"] = job_ids
    report["generation"] = generate_applications(pipeline, job_ids)
    report["applications"] = inspect_applications()
    report["status_counts_final"] = _status_counts()
    report["db_counts"] = {
        "jobs": _table_count(Job),
        "applications": _table_count(Application),
        "contacts": _table_count(Contact),
        "contact_lookup_cache": _table_count(ContactLookupCache),
        "generated_documents": _table_count(GeneratedDocument),
    }
    report["jobs_snapshot"] = collect_jobs_snapshot(limit=60)
    report["llm_usage"] = collect_usage()

    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report_path": str(report_path), **report["db_counts"]}, indent=2))


if __name__ == "__main__":
    main()
