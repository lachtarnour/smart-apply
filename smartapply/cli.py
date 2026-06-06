"""Command-line interface for SmartApply AI."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import click

from smartapply.config import get_settings
from smartapply.database import init_db as _init_db
from smartapply.database import session_scope
from smartapply.database.repository import (
    list_applications,
    list_jobs,
    total_cost,
    update_application_tracking,
)
from smartapply.jobsearch import (
    APPLICATION_STATUSES,
    STATUS_LABELS,
    AutopilotRunner,
    next_action_for,
)
from smartapply.logging_setup import setup_logging
from smartapply.scrapers import SERPAPI_DATE_POSTED_OPTIONS

DATE_POSTED_CHOICE = click.Choice(list(SERPAPI_DATE_POSTED_OPTIONS))
SCRAPER_SOURCE_CHOICE = click.Choice(["serpapi", "francetravail", "welcometothejungle"])
AUTOPILOT_SOURCE_CHOICE = click.Choice(
    ["serpapi", "francetravail", "welcometothejungle", "manual"]
)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli() -> None:
    """SmartApply AI — pipeline d'optimisation de candidatures."""
    setup_logging()


@cli.command("init-db")
def init_db_command() -> None:
    """Create the SQLite tables."""
    _init_db()
    click.echo(f"Database initialized at {get_settings().database_url}")


@cli.command("ingest")
@click.option("--source", required=True, type=SCRAPER_SOURCE_CHOICE)
@click.option("--query", "-q", required=True)
@click.option("--location", "-l", default=None)
@click.option("--max-results", type=int, default=20)
@click.option("--date-posted", type=DATE_POSTED_CHOICE, default=None)
@click.option("--serpapi-hl", default=None, help="Google Jobs language(s), e.g. en, fr or en,fr.")
def ingest_command(
    source: str,
    query: str,
    location: str | None,
    max_results: int,
    date_posted: str | None,
    serpapi_hl: str | None,
) -> None:
    """Scrape one source and persist new jobs."""
    from smartapply.pipeline import Pipeline
    from smartapply.pipeline.pipeline import freshness_kwargs

    p = Pipeline()
    kwargs = freshness_kwargs(source, date_posted=date_posted, serpapi_hl=serpapi_hl)
    report = p.ingest(source, query, location, max_results=max_results, **kwargs)
    click.echo(json.dumps(report.__dict__, indent=2, default=str))


@cli.command("ingest-url")
@click.option("--url", "-u", required=True)
def ingest_url_command(url: str) -> None:
    from smartapply.pipeline import Pipeline

    report = Pipeline().ingest_url(url)
    click.echo(json.dumps(report.__dict__, indent=2, default=str))


@cli.command("ingest-text")
@click.option("--title", required=True)
@click.option("--company", required=True)
@click.option("--location", default=None)
@click.option("--application-url", default=None)
@click.option("--file", "text_file", type=click.Path(exists=True))
def ingest_text_command(
    title: str,
    company: str,
    location: str | None,
    application_url: str | None,
    text_file: str | None,
) -> None:
    """Ingest a job from raw text (paste via stdin or --file)."""
    from smartapply.pipeline import Pipeline

    text = Path(text_file).read_text() if text_file else sys.stdin.read()
    report = Pipeline().ingest_text(
        text,
        title=title,
        company=company,
        location=location,
        application_url=application_url,
    )
    click.echo(json.dumps(report.__dict__, indent=2, default=str))


@cli.command("process")
@click.option("--top-k", type=int, default=None)
def process_command(top_k: int | None) -> None:
    """Filter, rank and analyze pending jobs."""
    from smartapply.pipeline import Pipeline

    report = Pipeline().process_pending(top_k_analyze=top_k)
    click.echo(json.dumps(report.__dict__, indent=2))


@cli.command("apply")
@click.option("--job-id", type=int, required=True)
@click.option("--gmail-draft", is_flag=True)
@click.option("--contact-email", default=None, help="Manual recruiter/contact email.")
@click.option("--contact-form-url", default=None, help="Manual ATS/form URL if known.")
def apply_command(
    job_id: int,
    gmail_draft: bool,
    contact_email: str | None,
    contact_form_url: str | None,
) -> None:
    """Generate CV + letter + sending email for a single analyzed job."""
    from smartapply.pipeline import Pipeline

    report = Pipeline().apply_to(
        job_id,
        contact_email=contact_email,
        contact_form_url=contact_form_url,
        create_gmail_draft=gmail_draft,
    )
    click.echo(json.dumps(report.__dict__, indent=2, default=str))


@cli.command("gmail-check")
def gmail_check_command() -> None:
    """Check local Gmail OAuth setup without creating a draft."""
    from smartapply.email_agent import check_gmail_setup

    status = check_gmail_setup()
    click.echo(json.dumps(asdict(status), indent=2, default=str))
    if not status.ready_for_auth:
        raise click.ClickException(
            "Gmail is not ready yet. Install the gmail extras and configure "
            "GMAIL_CREDENTIALS_PATH."
        )


@cli.command("pipeline")
@click.option("--source", "sources", multiple=True, required=True,
              type=SCRAPER_SOURCE_CHOICE)
@click.option("--query", "-q", required=True)
@click.option("--location", "-l", default=None)
@click.option("--max-per-source", type=int, default=20)
@click.option("--top-apply", type=int, default=5)
@click.option("--gmail-draft", is_flag=True)
@click.option("--date-posted", type=DATE_POSTED_CHOICE, default=None)
@click.option("--serpapi-hl", default=None, help="Google Jobs language(s), e.g. en, fr or en,fr.")
def pipeline_command(
    sources: tuple[str, ...],
    query: str,
    location: str | None,
    max_per_source: int,
    top_apply: int,
    gmail_draft: bool,
    date_posted: str | None,
    serpapi_hl: str | None,
) -> None:
    """End-to-end: ingest from sources → process → apply to top K."""
    from smartapply.pipeline import Pipeline

    p = Pipeline()
    source_tuples = [(name, query, location) for name in sources]
    report = p.run_end_to_end(
        sources=source_tuples,
        max_per_source=max_per_source,
        top_k_apply=top_apply,
        create_gmail_drafts=gmail_draft,
        date_posted=date_posted,
        serpapi_hl=serpapi_hl,
    )
    click.echo(json.dumps(report, indent=2, default=str))


@cli.command("autopilot")
@click.option(
    "--query",
    "-q",
    default="Data Scientist OR Machine Learning Engineer",
    show_default=True,
)
@click.option("--location", "-l", default=None)
@click.option(
    "--source",
    "sources",
    multiple=True,
    type=AUTOPILOT_SOURCE_CHOICE,
    default=("serpapi", "francetravail", "welcometothejungle", "manual"),
    show_default=True,
)
@click.option("--max-per-source", type=int, default=None)
@click.option("--target-drafts", type=int, default=None)
@click.option("--gmail-draft", is_flag=True)
@click.option("--no-quality-gate", is_flag=True)
@click.option("--date-posted", type=DATE_POSTED_CHOICE, default=None)
@click.option("--serpapi-hl", default=None, help="Google Jobs language(s), e.g. en, fr or en,fr.")
def autopilot_command(
    query: str,
    location: str | None,
    sources: tuple[str, ...],
    max_per_source: int | None,
    target_drafts: int | None,
    gmail_draft: bool,
    no_quality_gate: bool,
    date_posted: str | None,
    serpapi_hl: str | None,
) -> None:
    """Run the autonomous daily application drafting loop."""
    _init_db()
    report = AutopilotRunner().run(
        query=query,
        location=location,
        sources=list(sources),
        max_per_source=max_per_source,
        target_drafts=target_drafts,
        create_gmail_drafts=gmail_draft,
        require_quality_gate=not no_quality_gate,
        date_posted=date_posted,
        serpapi_hl=serpapi_hl,
    )
    click.echo(json.dumps(report.to_dict(), indent=2, default=str))


@cli.command("list-jobs")
@click.option("--status", default=None)
@click.option("--limit", type=int, default=50)
def list_jobs_command(status: str | None, limit: int) -> None:
    with session_scope() as s:
        jobs = list_jobs(s, status=status, limit=limit)
        rows = [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "location": j.location,
                "source": j.source,
                "status": j.status,
                "score": j.score.final_score if j.score else None,
            }
            for j in jobs
        ]
    click.echo(json.dumps(rows, indent=2))


@cli.command("list-applications")
def list_applications_command() -> None:
    with session_scope() as s:
        apps = list_applications(s)
        rows = [
            {
                "id": a.id,
                "job_id": a.job_id,
                "status": a.status,
                "strategy": a.application_strategy,
                "form_url": a.form_submission_url,
                "email_sent_at": a.email_sent_at,
                "form_submitted_at": a.form_submitted_at,
                "next_action": next_action_for(
                    a.status,
                    a.updated_at,
                    has_contact=a.contact is not None,
                    has_gmail_draft=bool(a.gmail_draft_id),
                ),
                "cv_docx": a.cv_docx_path,
                "cv_pdf": a.cv_pdf_path,
                "motivation_letter_pdf": next(
                    (
                        doc.path
                        for doc in a.documents
                        if doc.doc_type == "motivation_letter_pdf"
                    ),
                    None,
                ),
                "eml": a.eml_path,
                "subject": a.email_subject,
                "notes": a.notes,
            }
            for a in apps
        ]
    click.echo(json.dumps(rows, indent=2, default=str))


@cli.command("update-application")
@click.option("--application-id", type=int, required=True)
@click.option(
    "--status",
    type=click.Choice(APPLICATION_STATUSES),
    default=None,
    help="Nouveau statut de suivi.",
)
@click.option("--notes", default=None, help="Notes de suivi ou prochaine action.")
@click.option(
    "--email-sent",
    is_flag=True,
    help="Marque l'email comme envoye (timestamp + auto-promotion vers sent).",
)
@click.option(
    "--form-submitted",
    is_flag=True,
    help="Marque le formulaire ATS comme soumis (timestamp + auto-promotion).",
)
def update_application_command(
    application_id: int,
    status: str | None,
    notes: str | None,
    email_sent: bool,
    form_submitted: bool,
) -> None:
    """Update application follow-up status, notes, and sent/submitted flags."""
    if status is None and notes is None and not email_sent and not form_submitted:
        raise click.UsageError(
            "Provide --status, --notes, --email-sent and/or --form-submitted."
        )
    with session_scope() as s:
        app = update_application_tracking(
            s,
            application_id,
            status=status,
            notes=notes,
            email_sent=email_sent,
            form_submitted=form_submitted,
        )
        row = {
            "id": app.id,
            "job_id": app.job_id,
            "status": app.status,
            "status_label": STATUS_LABELS.get(app.status, app.status),
            "application_strategy": app.application_strategy,
            "email_sent_at": app.email_sent_at,
            "form_submitted_at": app.form_submitted_at,
            "next_action": next_action_for(
                app.status,
                app.updated_at,
                has_contact=app.contact is not None,
                has_gmail_draft=bool(app.gmail_draft_id),
            ),
            "notes": app.notes,
        }
    click.echo(json.dumps(row, indent=2, default=str))


@cli.command("stats")
def stats_command() -> None:
    """Display pipeline statistics — counts per status and total cost."""
    with session_scope() as s:
        all_jobs = list_jobs(s)
        per_status: dict[str, int] = {}
        for j in all_jobs:
            per_status[j.status] = per_status.get(j.status, 0) + 1
        cost = total_cost(s)
    click.echo(
        json.dumps(
            {
                "total_jobs": len(all_jobs),
                "per_status": per_status,
                "total_llm_cost_usd": round(cost, 4),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    cli()
