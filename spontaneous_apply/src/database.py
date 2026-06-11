from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from spontaneous_apply.src.models import (
    CompanyRecord,
    CompanySeed,
    EmailDraft,
    RawCompanyInfo,
    StructuredCompanyProfile,
    WTTJProfile,
)
from spontaneous_apply.src.settings import get_settings

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL UNIQUE,
    website TEXT,
    sector_hint TEXT,
    spontaneous_score TEXT,
    status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS wttj_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    has_wttj_profile INTEGER NOT NULL,
    wttj_url TEXT,
    wttj_status TEXT,
    discovery_method TEXT,
    checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,

    FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS raw_company_infos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,

    source_type TEXT NOT NULL,
    source_url TEXT,

    company_name_raw TEXT,
    domain_raw TEXT,
    address_raw TEXT,
    description_raw TEXT,
    looking_for_raw TEXT,
    good_to_know_raw TEXT,

    team_size_raw TEXT,
    creation_year_raw TEXT,
    jobs_raw TEXT,

    raw_text TEXT,
    raw_html_path TEXT,

    extraction_method TEXT,
    scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
    quality_score REAL,
    error_message TEXT,

    FOREIGN KEY(company_id) REFERENCES companies(id)
);

CREATE TABLE IF NOT EXISTS structured_company_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    raw_info_id INTEGER NOT NULL,

    company_name TEXT NOT NULL,
    sector TEXT,
    sub_sector TEXT,

    short_description TEXT,
    detailed_description TEXT,

    products_or_services_json TEXT,
    target_users_json TEXT,
    business_model TEXT,

    ai_data_relevance_json TEXT,
    tech_keywords_json TEXT,
    health_keywords_json TEXT,

    what_they_look_for TEXT,
    good_to_know TEXT,

    candidate_fit_score INTEGER,
    candidate_fit_reason TEXT,
    personalization_anchor TEXT,

    email_angle TEXT,
    risk_notes TEXT,

    confidence TEXT,
    structured_json TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(company_id) REFERENCES companies(id),
    FOREIGN KEY(raw_info_id) REFERENCES raw_company_infos(id)
);

CREATE TABLE IF NOT EXISTS email_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL,
    structured_profile_id INTEGER NOT NULL,

    subject TEXT,
    email_body TEXT,

    recipient_type TEXT,
    tone TEXT,
    language TEXT DEFAULT 'fr',

    validation_status TEXT,
    validation_notes TEXT,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(company_id) REFERENCES companies(id),
    FOREIGN KEY(structured_profile_id) REFERENCES structured_company_profiles(id)
);
"""


def get_db_path() -> Path:
    return get_settings().database_path


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> Path:
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as conn:
        conn.executescript(SCHEMA_SQL)
    return path


def get_or_create_company(conn: sqlite3.Connection, seed: CompanySeed | str) -> CompanyRecord:
    if isinstance(seed, str):
        seed = CompanySeed(company_name=seed)

    existing = conn.execute(
        "SELECT * FROM companies WHERE lower(company_name) = lower(?)",
        (seed.company_name,),
    ).fetchone()
    if existing:
        updates = {
            "website": seed.website,
            "sector_hint": seed.sector_hint,
            "spontaneous_score": seed.spontaneous_score,
        }
        non_empty = {k: v for k, v in updates.items() if v}
        if non_empty:
            assignments = ", ".join(f"{key} = ?" for key in non_empty)
            conn.execute(
                f"UPDATE companies SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (*non_empty.values(), existing["id"]),
            )
            existing = conn.execute("SELECT * FROM companies WHERE id = ?", (existing["id"],)).fetchone()
        return _company_from_row(existing)

    cursor = conn.execute(
        """
        INSERT INTO companies (company_name, website, sector_hint, spontaneous_score)
        VALUES (?, ?, ?, ?)
        """,
        (seed.company_name, seed.website, seed.sector_hint, seed.spontaneous_score),
    )
    row = conn.execute("SELECT * FROM companies WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _company_from_row(row)


def mark_company_status(conn: sqlite3.Connection, company_id: int, status: str) -> None:
    conn.execute(
        "UPDATE companies SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (status, company_id),
    )


def save_wttj_profile(conn: sqlite3.Connection, company_id: int, profile: WTTJProfile) -> int:
    cursor = conn.execute(
        """
        INSERT INTO wttj_profiles (
            company_id,
            has_wttj_profile,
            wttj_url,
            wttj_status,
            discovery_method,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            int(profile.has_wttj_profile),
            profile.wttj_url,
            profile.wttj_status,
            profile.discovery_method,
            profile.error_message,
        ),
    )
    return int(cursor.lastrowid)


def save_raw_company_info(conn: sqlite3.Connection, company_id: int, raw_info: RawCompanyInfo) -> int:
    cursor = conn.execute(
        """
        INSERT INTO raw_company_infos (
            company_id,
            source_type,
            source_url,
            company_name_raw,
            domain_raw,
            address_raw,
            description_raw,
            looking_for_raw,
            good_to_know_raw,
            team_size_raw,
            creation_year_raw,
            jobs_raw,
            raw_text,
            raw_html_path,
            extraction_method,
            quality_score,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            raw_info.source_type,
            raw_info.source_url,
            raw_info.company_name_raw,
            raw_info.domain_raw,
            raw_info.address_raw,
            raw_info.description_raw,
            raw_info.looking_for_raw,
            raw_info.good_to_know_raw,
            raw_info.team_size_raw,
            raw_info.creation_year_raw,
            raw_info.jobs_raw,
            raw_info.raw_text,
            raw_info.raw_html_path,
            raw_info.extraction_method,
            raw_info.quality_score,
            raw_info.error_message,
        ),
    )
    return int(cursor.lastrowid)


def save_structured_profile(
    conn: sqlite3.Connection,
    company_id: int,
    raw_info_id: int,
    profile: StructuredCompanyProfile,
) -> int:
    structured_json = profile.model_dump_json()
    cursor = conn.execute(
        """
        INSERT INTO structured_company_profiles (
            company_id,
            raw_info_id,
            company_name,
            sector,
            sub_sector,
            short_description,
            detailed_description,
            products_or_services_json,
            target_users_json,
            business_model,
            ai_data_relevance_json,
            tech_keywords_json,
            health_keywords_json,
            what_they_look_for,
            good_to_know,
            candidate_fit_score,
            candidate_fit_reason,
            personalization_anchor,
            email_angle,
            risk_notes,
            confidence,
            structured_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            raw_info_id,
            profile.company_name,
            profile.sector,
            profile.sub_sector,
            profile.short_description,
            profile.detailed_description,
            json.dumps(profile.products_or_services, ensure_ascii=False),
            json.dumps(profile.target_users, ensure_ascii=False),
            profile.business_model,
            json.dumps(profile.ai_data_relevance, ensure_ascii=False),
            json.dumps(profile.tech_keywords, ensure_ascii=False),
            json.dumps(profile.health_keywords, ensure_ascii=False),
            profile.what_they_look_for,
            profile.good_to_know,
            profile.candidate_fit_score,
            profile.candidate_fit_reason,
            profile.personalization_anchor,
            profile.email_angle,
            profile.risk_notes,
            profile.confidence,
            structured_json,
        ),
    )
    return int(cursor.lastrowid)


def save_email_draft(
    conn: sqlite3.Connection,
    company_id: int,
    structured_profile_id: int,
    draft: EmailDraft,
) -> int:
    cursor = conn.execute(
        """
        INSERT INTO email_drafts (
            company_id,
            structured_profile_id,
            subject,
            email_body,
            recipient_type,
            tone,
            language,
            validation_status,
            validation_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            company_id,
            structured_profile_id,
            draft.subject,
            draft.email_body,
            draft.recipient_type,
            draft.tone,
            draft.language,
            draft.validation_status,
            draft.validation_notes,
        ),
    )
    return int(cursor.lastrowid)


def _company_from_row(row: sqlite3.Row) -> CompanyRecord:
    return CompanyRecord(
        id=row["id"],
        company_name=row["company_name"],
        website=row["website"],
        sector_hint=row["sector_hint"],
        spontaneous_score=row["spontaneous_score"],
        status=row["status"],
    )

