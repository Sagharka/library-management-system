"""SQLAlchemy 2.0 models and database setup for the Library Management System.

Tables
------
- ``books``         : the books the library owns
- ``authors``       : people who write books
- ``book_authors``  : association table for the books <-> authors many-to-many
- ``members``       : people who can borrow books
- ``borrowings``    : one row per checkout (books <-> members, with extra columns)

All tables are created from these models with ``Base.metadata.create_all`` --
there is no raw ``CREATE TABLE`` SQL anywhere in the project.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

# A borrowing is overdue when it has not been returned this many days after checkout.
LOAN_PERIOD_DAYS = 14

# The database file lives next to this script unless LIBRARY_DB_URL overrides it.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get(
    "LIBRARY_DB_URL", f"sqlite:///{os.path.join(BASE_DIR, 'library.db')}"
)


class Base(DeclarativeBase):
    """Base class every model inherits from."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    """Turn on foreign-key enforcement, which SQLite leaves off by default."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ---------------------------------------------------------------------------
# Association table: books <-> authors (many-to-many)
# ---------------------------------------------------------------------------
book_authors = Table(
    "book_authors",
    Base.metadata,
    Column("book_id", ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("author_id", ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True),
)


class Book(Base):
    """A title in the library's catalogue."""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint("available_copies >= 0", name="ck_books_available_copies_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    isbn: Mapped[str] = mapped_column(String(13), unique=True, nullable=False)
    year_published: Mapped[int] = mapped_column(Integer, nullable=False)
    available_copies: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # many-to-many: book.authors <-> author.books
    authors: Mapped[list["Author"]] = relationship(
        secondary=book_authors, back_populates="books"
    )
    # one-to-many: book.borrowings <-> borrowing.book
    # Deleting a book also deletes its (returned) borrowing history; crud.delete_book
    # refuses to delete a book that still has an active borrowing.
    borrowings: Mapped[list["Borrowing"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Book id={self.id} title={self.title!r} isbn={self.isbn}>"


class Author(Base):
    """A person who wrote one or more books."""

    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    books: Mapped[list["Book"]] = relationship(
        secondary=book_authors, back_populates="authors"
    )

    def __repr__(self) -> str:
        return f"<Author id={self.id} name={self.name!r}>"


class Member(Base):
    """A library member who can borrow books."""

    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    membership_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    # one-to-many: member.borrowings <-> borrowing.member
    borrowings: Mapped[list["Borrowing"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Member id={self.id} name={self.name!r} email={self.email}>"


class Borrowing(Base):
    """One checkout of one book by one member.

    This is the books <-> members many-to-many relationship, implemented as its
    own model (an "association object") because it carries extra columns.
    ``return_date`` is NULL while the book is still out.
    """

    __tablename__ = "borrowings"
    __table_args__ = (
        CheckConstraint(
            "return_date IS NULL OR return_date >= checkout_date",
            name="ck_borrowings_return_after_checkout",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), nullable=False, index=True
    )
    checkout_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    return_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, default=None)

    book: Mapped["Book"] = relationship(back_populates="borrowings")
    member: Mapped["Member"] = relationship(back_populates="borrowings")

    @property
    def due_date(self) -> date:
        """The date the book should be back by."""
        return self.checkout_date + timedelta(days=LOAN_PERIOD_DAYS)

    @property
    def is_active(self) -> bool:
        """True while the book has not been returned."""
        return self.return_date is None

    def days_overdue(self, today: Optional[date] = None) -> int:
        """How many days past the due date an unreturned book is (0 if not overdue)."""
        if not self.is_active:
            return 0
        today = today or date.today()
        return max(0, (today - self.due_date).days)

    def __repr__(self) -> str:
        return (
            f"<Borrowing id={self.id} book_id={self.book_id} member_id={self.member_id} "
            f"checkout={self.checkout_date} return={self.return_date}>"
        )


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind: Engine = engine) -> None:
    """Create every table that does not exist yet."""
    Base.metadata.create_all(bind)


def reset_db(bind: Engine = engine) -> None:
    """Drop and recreate every table (all data is lost)."""
    Base.metadata.drop_all(bind)
    Base.metadata.create_all(bind)
