"""Populate the database with sample data from ``sample_data.json``.

Run directly to wipe the database and load fresh sample data::

    python seed.py

Dates in the sample file are stored as "days ago", so the data always looks
current: some borrowings are returned, some are still out, and some are overdue
no matter what day you run it.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import crud
from models import BASE_DIR, Book, Member, SessionLocal, engine, reset_db

SAMPLE_DATA_PATH = os.path.join(BASE_DIR, "sample_data.json")


def _days_ago(days: Optional[int], today: date) -> Optional[date]:
    """Convert a 'days ago' number from the JSON file into a date."""
    return None if days is None else today - timedelta(days=days)


def seed_database(session: Session, data_path: str = SAMPLE_DATA_PATH) -> dict[str, int]:
    """Load authors, books, members and borrowings into an empty database.

    Everything is created through the functions in ``crud`` so the same
    validation and business rules (copies going down on checkout and back up on
    return) apply to the sample data.

    Returns:
        How many rows of each kind were created.
    """
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    today = date.today()

    for author in data["authors"]:
        crud.add_author(session, author["name"], author.get("bio"))

    for book in data["books"]:
        crud.add_book(
            session,
            title=book["title"],
            isbn=book["isbn"],
            year_published=book["year_published"],
            available_copies=book["available_copies"],
            author_names=book["authors"],
        )

    for member in data["members"]:
        crud.add_member(
            session,
            name=member["name"],
            email=member["email"],
            membership_date=_days_ago(member["joined_days_ago"], today),
        )

    for loan in data["borrowings"]:
        member = session.scalars(select(Member).where(Member.email == loan["member_email"])).one()
        book = session.scalars(select(Book).where(Book.isbn == loan["book_isbn"])).one()
        borrowing = crud.checkout_book(
            session, member.id, book.id, _days_ago(loan["checkout_days_ago"], today)
        )
        if loan["returned_days_ago"] is not None:
            crud.return_book(session, borrowing.id, _days_ago(loan["returned_days_ago"], today))

    return {
        "authors": len(data["authors"]),
        "books": len(data["books"]),
        "members": len(data["members"]),
        "borrowings": len(data["borrowings"]),
    }


def reset_and_seed() -> dict[str, int]:
    """Drop all tables, recreate them, and load the sample data."""
    reset_db(engine)
    with SessionLocal() as session:
        return seed_database(session)


if __name__ == "__main__":
    counts = reset_and_seed()
    summary = ", ".join(f"{count} {name}" for name, count in counts.items())
    print(f"Database reset and seeded with {summary}.")
