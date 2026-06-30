"""Contact repository helpers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from smartapply.database.models import Contact, ContactLookupCache


def add_contact(
    session: Session,
    *,
    company: str,
    email: str,
    **fields: Any,
) -> Contact:
    company = company.strip()
    email = email.strip().lower()
    existing = session.execute(
        select(Contact).where(Contact.company == company, Contact.email == email)
    ).scalar_one_or_none()
    if existing is not None:
        for key, value in fields.items():
            if value is not None:
                setattr(existing, key, value)
        return existing
    if session.get_bind().dialect.name == "sqlite":
        insert_fields = {"company": company, "email": email, **fields}
        update_fields = {key: value for key, value in fields.items() if value is not None}
        stmt = sqlite_insert(Contact).values(**insert_fields)
        if update_fields:
            stmt = stmt.on_conflict_do_update(
                index_elements=["company", "email"],
                set_=update_fields,
            )
        else:
            stmt = stmt.on_conflict_do_nothing(index_elements=["company", "email"])
        session.execute(stmt)
        session.flush()
        return session.execute(
            select(Contact).where(Contact.company == company, Contact.email == email)
        ).scalar_one()
    contact = Contact(company=company, email=email, **fields)
    session.add(contact)
    session.flush()
    return contact


def find_contacts_for(session: Session, company: str) -> Sequence[Contact]:
    stmt = select(Contact).where(Contact.company == company).order_by(Contact.confidence.desc())
    return session.execute(stmt).scalars().all()


def get_contact_lookup_cache(
    session: Session,
    *,
    provider_key: str,
    lookup_key: str,
) -> ContactLookupCache | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(ContactLookupCache)
        .where(ContactLookupCache.provider_key == provider_key)
        .where(ContactLookupCache.lookup_key == lookup_key)
        .where(
            or_(
                ContactLookupCache.expires_at.is_(None),
                ContactLookupCache.expires_at >= now,
            )
        )
    )
    return session.execute(stmt).scalar_one_or_none()


def upsert_contact_lookup_cache(
    session: Session,
    *,
    provider_key: str,
    lookup_key: str,
    company: str,
    domain: str | None,
    application_url: str | None,
    status: str,
    contacts: Any | None,
    expires_at: datetime | None,
) -> ContactLookupCache:
    existing = session.execute(
        select(ContactLookupCache)
        .where(ContactLookupCache.provider_key == provider_key)
        .where(ContactLookupCache.lookup_key == lookup_key)
    ).scalar_one_or_none()
    fields = {
        "company": company,
        "domain": domain,
        "application_url": application_url,
        "status": status,
        "contacts": contacts,
        "checked_at": datetime.now(timezone.utc),
        "expires_at": expires_at,
    }
    if session.get_bind().dialect.name == "sqlite":
        stmt = (
            sqlite_insert(ContactLookupCache)
            .values(provider_key=provider_key, lookup_key=lookup_key, **fields)
            .on_conflict_do_update(
                index_elements=["provider_key", "lookup_key"],
                set_=fields,
            )
        )
        session.execute(stmt)
        session.flush()
        if existing is not None:
            session.refresh(existing)
            return existing
        return session.execute(
            select(ContactLookupCache)
            .where(ContactLookupCache.provider_key == provider_key)
            .where(ContactLookupCache.lookup_key == lookup_key)
        ).scalar_one()
    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return existing
    entry = ContactLookupCache(
        provider_key=provider_key,
        lookup_key=lookup_key,
        **fields,
    )
    session.add(entry)
    session.flush()
    return entry
