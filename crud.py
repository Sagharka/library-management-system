"""CRUD operations for the Library Management System.

Every function takes an open SQLAlchemy ``Session`` as its first argument and
uses the ORM (no raw SQL strings). Functions that change data validate their
input first, then commit; if anything goes wrong the session is rolled back
and a ``LibraryError`` with a user-friendly message is raised, so the database
is never left half-updated.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Iterable, Iterator, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from models import LOAN_PERIOD_DAYS, Author, Book, Borrowing, Member

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LibraryError(Exception):
    """Raised when an operation is not allowed or its input is invalid."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
@contextmanager
def _transaction(session: Session) -> Iterator[None]:
    """Commit on success; roll back and raise ``LibraryError`` on failure."""
    try:
        yield
        session.commit()
    except LibraryError:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise LibraryError(_explain_integrity_error(exc)) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise LibraryError(f"Database error: {exc}") from exc


def _explain_integrity_error(exc: IntegrityError) -> str:
    """Turn a database constraint violation into a readable message."""
    message = str(exc.orig).lower()
    if "books.isbn" in message:
        return "A book with that ISBN already exists."
    if "members.email" in message:
        return "A member with that email already exists."
    if "foreign key" in message:
        return "That record is linked to other records and cannot be changed."
    if "check constraint" in message:
        return "That value breaks a data rule (for example, a negative number of copies)."
    return f"Data integrity error: {exc.orig}"


def _clean_text(value: Optional[str], field: str) -> str:
    """Strip whitespace and make sure a required text field is not empty."""
    cleaned = (value or "").strip()
    if not cleaned:
        raise LibraryError(f"{field} cannot be empty.")
    return cleaned


def normalize_isbn(isbn: str) -> str:
    """Return the ISBN without spaces/hyphens; raise if it is not ISBN-10 or ISBN-13."""
    cleaned = re.sub(r"[\s-]", "", isbn or "").upper()
    if re.fullmatch(r"\d{13}", cleaned) or re.fullmatch(r"\d{9}[\dX]", cleaned):
        return cleaned
    raise LibraryError("ISBN must have 10 or 13 digits (hyphens are allowed; ISBN-10 may end in X).")


def normalize_email(email: str) -> str:
    """Return the email lower-cased; raise if it does not look like an email."""
    cleaned = (email or "").strip().lower()
    if not EMAIL_PATTERN.match(cleaned):
        raise LibraryError(f"'{email}' is not a valid email address.")
    return cleaned


def _validate_year(year_published: int) -> int:
    """Make sure the publication year is a sensible whole number."""
    if isinstance(year_published, bool) or not isinstance(year_published, int):
        raise LibraryError("Year published must be a whole number.")
    if not 1 <= year_published <= date.today().year:
        raise LibraryError(f"Year published must be between 1 and {date.today().year}.")
    return year_published


def _validate_copies(copies: int) -> int:
    """Make sure the number of copies is a whole number that is not negative."""
    if isinstance(copies, bool) or not isinstance(copies, int) or copies < 0:
        raise LibraryError("Available copies must be a whole number of 0 or more.")
    return copies


# ---------------------------------------------------------------------------
# Lookups used by several operations
# ---------------------------------------------------------------------------
def get_book(session: Session, book_id: int) -> Book:
    """Return the book with this id, or raise ``LibraryError`` if there is none."""
    book = session.get(Book, book_id)
    if book is None:
        raise LibraryError(f"No book found with id {book_id}.")
    return book


def get_member(session: Session, member_id: int) -> Member:
    """Return the member with this id, or raise ``LibraryError`` if there is none."""
    member = session.get(Member, member_id)
    if member is None:
        raise LibraryError(f"No member found with id {member_id}.")
    return member


def get_borrowing(session: Session, borrowing_id: int) -> Borrowing:
    """Return the borrowing with this id, or raise ``LibraryError`` if there is none."""
    borrowing = session.get(Borrowing, borrowing_id)
    if borrowing is None:
        raise LibraryError(f"No borrowing found with id {borrowing_id}.")
    return borrowing


def find_author_by_name(session: Session, name: str) -> Optional[Author]:
    """Return the author whose name matches exactly (ignoring case), if any."""
    stmt = select(Author).where(func.lower(Author.name) == name.strip().lower())
    return session.scalars(stmt).first()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------
def add_author(session: Session, name: str, bio: Optional[str] = None) -> Author:
    """Add a new author.

    Args:
        session: open database session.
        name: the author's full name (required).
        bio: optional short biography.

    Returns:
        The new ``Author``.

    Raises:
        LibraryError: if the name is empty or an author with that name already exists.
    """
    with _transaction(session):
        name = _clean_text(name, "Author name")
        if find_author_by_name(session, name):
            raise LibraryError(f"An author named '{name}' already exists.")
        author = Author(name=name, bio=(bio or "").strip() or None)
        session.add(author)
    return author


def add_book(
    session: Session,
    title: str,
    isbn: str,
    year_published: int,
    available_copies: int = 1,
    author_names: Iterable[str] = (),
) -> Book:
    """Add a new book and link it to its authors.

    Authors are matched by name (ignoring case); an author that does not exist yet
    is created in the same transaction, so either everything is saved or nothing is.

    Args:
        session: open database session.
        title: book title (required).
        isbn: ISBN-10 or ISBN-13; hyphens/spaces are removed before saving. Must be unique.
        year_published: publication year (1 .. current year).
        available_copies: number of copies on the shelf (0 or more).
        author_names: names of the book's authors.

    Returns:
        The new ``Book``.

    Raises:
        LibraryError: on invalid input or if the ISBN is already used.
    """
    with _transaction(session):
        title = _clean_text(title, "Title")
        isbn = normalize_isbn(isbn)
        _validate_year(year_published)
        _validate_copies(available_copies)
        if session.scalars(select(Book).where(Book.isbn == isbn)).first():
            raise LibraryError(f"A book with ISBN {isbn} already exists.")

        authors: list[Author] = []
        seen: set[str] = set()
        for raw_name in author_names:
            name = (raw_name or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            authors.append(find_author_by_name(session, name) or Author(name=name))

        book = Book(
            title=title,
            isbn=isbn,
            year_published=year_published,
            available_copies=available_copies,
            authors=authors,
        )
        session.add(book)
    return book


def add_member(
    session: Session,
    name: str,
    email: str,
    membership_date: Optional[date] = None,
) -> Member:
    """Add a new library member.

    Args:
        session: open database session.
        name: member's full name (required).
        email: member's email; stored lower-case and must be unique.
        membership_date: date they joined (defaults to today; cannot be in the future).

    Returns:
        The new ``Member``.

    Raises:
        LibraryError: on invalid input or if the email is already used.
    """
    with _transaction(session):
        name = _clean_text(name, "Member name")
        email = normalize_email(email)
        membership_date = membership_date or date.today()
        if membership_date > date.today():
            raise LibraryError("Membership date cannot be in the future.")
        if session.scalars(select(Member).where(Member.email == email)).first():
            raise LibraryError(f"A member with email {email} already exists.")
        member = Member(name=name, email=email, membership_date=membership_date)
        session.add(member)
    return member


def checkout_book(
    session: Session,
    member_id: int,
    book_id: int,
    checkout_date: Optional[date] = None,
) -> Borrowing:
    """Check a book out to a member.

    Creates a ``Borrowing`` (with ``return_date`` = NULL) and lowers the book's
    ``available_copies`` by one, in one transaction.

    Raises:
        LibraryError: if the member or book does not exist, no copies are available,
            the member already has this book, or the date is in the future.
    """
    with _transaction(session):
        member = get_member(session, member_id)
        book = get_book(session, book_id)
        checkout_date = checkout_date or date.today()

        if checkout_date > date.today():
            raise LibraryError("Checkout date cannot be in the future.")
        if checkout_date < member.membership_date:
            raise LibraryError("Checkout date cannot be before the member joined.")
        if book.available_copies <= 0:
            raise LibraryError(f"'{book.title}' has no available copies right now.")
        already_has_it = any(b.book_id == book.id and b.is_active for b in member.borrowings)
        if already_has_it:
            raise LibraryError(f"{member.name} already has '{book.title}' checked out.")

        book.available_copies -= 1
        borrowing = Borrowing(book=book, member=member, checkout_date=checkout_date)
        session.add(borrowing)
    return borrowing


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------
def list_books(session: Session) -> list[Book]:
    """Return every book, sorted by title, with authors pre-loaded."""
    stmt = select(Book).options(selectinload(Book.authors)).order_by(Book.title)
    return list(session.scalars(stmt))


def search_books_by_title(session: Session, term: str) -> list[Book]:
    """Return books whose title contains ``term`` (case-insensitive)."""
    term = _clean_text(term, "Search term")
    stmt = (
        select(Book)
        .options(selectinload(Book.authors))
        .where(Book.title.ilike(f"%{term}%"))
        .order_by(Book.title)
    )
    return list(session.scalars(stmt))


def find_books_by_author(session: Session, author_name: str) -> list[Book]:
    """Return books written by any author whose name contains ``author_name``.

    Navigates the books <-> authors many-to-many relationship with a join.
    """
    author_name = _clean_text(author_name, "Author name")
    stmt = (
        select(Book)
        .join(Book.authors)
        .options(selectinload(Book.authors))
        .where(Author.name.ilike(f"%{author_name}%"))
        .distinct()
        .order_by(Book.title)
    )
    return list(session.scalars(stmt))


def list_members(session: Session) -> list[Member]:
    """Return every member, sorted by name."""
    return list(session.scalars(select(Member).order_by(Member.name)))


def list_authors(session: Session) -> list[Author]:
    """Return every author, sorted by name, with their books pre-loaded."""
    stmt = select(Author).options(selectinload(Author.books)).order_by(Author.name)
    return list(session.scalars(stmt))


def list_member_borrowings(
    session: Session, member_id: int, active_only: bool = True
) -> list[Borrowing]:
    """Return a member's borrowings (only the ones not yet returned by default).

    Raises:
        LibraryError: if the member does not exist.
    """
    get_member(session, member_id)
    stmt = (
        select(Borrowing)
        .options(selectinload(Borrowing.book))
        .where(Borrowing.member_id == member_id)
        .order_by(Borrowing.checkout_date)
    )
    if active_only:
        stmt = stmt.where(Borrowing.return_date.is_(None))
    return list(session.scalars(stmt))


def list_overdue_books(session: Session, today: Optional[date] = None) -> list[Borrowing]:
    """Return unreturned borrowings checked out more than ``LOAN_PERIOD_DAYS`` days ago.

    Sorted with the most overdue first.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=LOAN_PERIOD_DAYS)
    stmt = (
        select(Borrowing)
        .options(selectinload(Borrowing.book), selectinload(Borrowing.member))
        .where(Borrowing.return_date.is_(None), Borrowing.checkout_date < cutoff)
        .order_by(Borrowing.checkout_date)
    )
    return list(session.scalars(stmt))


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------
def return_book(
    session: Session, borrowing_id: int, return_date: Optional[date] = None
) -> Borrowing:
    """Mark a borrowing as returned and put the copy back on the shelf.

    Sets ``return_date`` and raises the book's ``available_copies`` by one.

    Raises:
        LibraryError: if the borrowing does not exist, was already returned, or the
            return date is before the checkout date or in the future.
    """
    with _transaction(session):
        borrowing = get_borrowing(session, borrowing_id)
        return_date = return_date or date.today()
        if not borrowing.is_active:
            raise LibraryError(
                f"'{borrowing.book.title}' was already returned on {borrowing.return_date}."
            )
        if return_date > date.today():
            raise LibraryError("Return date cannot be in the future.")
        if return_date < borrowing.checkout_date:
            raise LibraryError("Return date cannot be before the checkout date.")

        borrowing.return_date = return_date
        borrowing.book.available_copies += 1
    return borrowing


def update_member_email(session: Session, member_id: int, new_email: str) -> Member:
    """Change a member's email address.

    Raises:
        LibraryError: if the member does not exist, the email is invalid, or another
            member already uses it.
    """
    with _transaction(session):
        member = get_member(session, member_id)
        new_email = normalize_email(new_email)
        taken = session.scalars(
            select(Member).where(Member.email == new_email, Member.id != member_id)
        ).first()
        if taken:
            raise LibraryError(f"{new_email} is already used by {taken.name}.")
        member.email = new_email
    return member


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------
def delete_book(session: Session, book_id: int) -> str:
    """Remove a book, but only if no copy of it is currently borrowed.

    Its returned-borrowing history and author links are removed with it.

    Returns:
        The title of the deleted book.

    Raises:
        LibraryError: if the book does not exist or is currently borrowed.
    """
    with _transaction(session):
        book = get_book(session, book_id)
        active = [b for b in book.borrowings if b.is_active]
        if active:
            raise LibraryError(
                f"Cannot remove '{book.title}': {len(active)} copy/copies still checked out."
            )
        title = book.title
        session.delete(book)
    return title


def delete_member(session: Session, member_id: int) -> str:
    """Remove a member, but only if they have no active borrowings.

    Their returned-borrowing history is removed with them.

    Returns:
        The name of the deleted member.

    Raises:
        LibraryError: if the member does not exist or still has books checked out.
    """
    with _transaction(session):
        member = get_member(session, member_id)
        active = [b for b in member.borrowings if b.is_active]
        if active:
            raise LibraryError(
                f"Cannot remove {member.name}: they still have {len(active)} book(s) checked out."
            )
        name = member.name
        session.delete(member)
    return name
