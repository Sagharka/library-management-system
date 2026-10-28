"""Tests for models, relationships, CRUD operations and edge cases."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

import crud
from crud import LibraryError
from models import Author, Book, Borrowing, Member

TODAY = date.today()


def book_by_title(session, title):
    return session.scalars(select(Book).where(Book.title == title)).one()


def member_by_email(session, email):
    return session.scalars(select(Member).where(Member.email == email)).one()


# --- Seeding ---------------------------------------------------------------
def test_seed_meets_minimum_counts(seeded):
    assert len(crud.list_books(seeded)) >= 5
    assert len(crud.list_authors(seeded)) >= 3
    assert len(crud.list_members(seeded)) >= 4
    loans = list(seeded.scalars(select(Borrowing)))
    assert len(loans) >= 6
    assert any(l.return_date is None for l in loans)
    assert any(l.return_date is not None for l in loans)


def test_seed_copies_reflect_active_loans(seeded):
    # Kindred has 1 copy and Brian has it out -> 0 left.
    assert book_by_title(seeded, "Kindred").available_copies == 0
    # Good Omens has 3 copies; one active loan (David) -> 2 left.
    assert book_by_title(seeded, "Good Omens").available_copies == 2


# --- Relationships (bidirectional) -----------------------------------------
def test_many_to_many_books_authors_both_directions(seeded):
    good_omens = book_by_title(seeded, "Good Omens")
    assert {a.name for a in good_omens.authors} == {"Terry Pratchett", "Neil Gaiman"}
    gaiman = crud.find_author_by_name(seeded, "neil gaiman")
    assert {"Good Omens", "American Gods", "Coraline"} <= {b.title for b in gaiman.books}


def test_one_to_many_borrowings_both_directions(seeded):
    alice = member_by_email(seeded, "alice@example.com")
    assert len(alice.borrowings) == 2
    for loan in alice.borrowings:
        assert loan.member is alice
        assert loan in loan.book.borrowings


# --- Create ----------------------------------------------------------------
def test_add_book_creates_new_and_reuses_existing_authors(session):
    crud.add_author(session, "Jane Austen")
    book = crud.add_book(session, "Sense and Sensibility & More", "978-0-14-143966-2", 1811, 2,
                         ["jane austen", "New Person", "New Person"])
    assert [a.name for a in book.authors] == ["Jane Austen", "New Person"]
    assert book.isbn == "9780141439662"
    assert len(crud.list_authors(session)) == 2


@pytest.mark.parametrize("kwargs, message", [
    ({"title": "  "}, "Title"),
    ({"isbn": "123"}, "ISBN"),
    ({"year_published": TODAY.year + 1}, "Year"),
    ({"available_copies": -1}, "copies"),
])
def test_add_book_validation(session, kwargs, message):
    args = {"title": "T", "isbn": "9780000000002", "year_published": 2000, "available_copies": 1}
    args.update(kwargs)
    with pytest.raises(LibraryError, match=message):
        crud.add_book(session, **args)
    assert crud.list_books(session) == []


def test_duplicate_isbn_rejected(seeded):
    with pytest.raises(LibraryError, match="ISBN"):
        crud.add_book(seeded, "Copy", "9780060853983", 2000, 1)


def test_add_member_validation_and_unique_email(seeded):
    with pytest.raises(LibraryError, match="valid email"):
        crud.add_member(seeded, "X", "not-an-email")
    with pytest.raises(LibraryError, match="already exists"):
        crud.add_member(seeded, "Alice Again", "ALICE@example.com")
    m = crud.add_member(seeded, "Frank", "Frank@Example.com")
    assert m.email == "frank@example.com" and m.membership_date == TODAY


def test_duplicate_author_rejected(seeded):
    with pytest.raises(LibraryError, match="already exists"):
        crud.add_author(seeded, "terry pratchett")


def test_checkout_decrements_copies(seeded):
    emma = member_by_email(seeded, "emma@example.com")
    coraline = book_by_title(seeded, "Coraline")
    before = coraline.available_copies
    loan = crud.checkout_book(seeded, emma.id, coraline.id)
    assert loan.return_date is None and loan.checkout_date == TODAY
    assert coraline.available_copies == before - 1
    assert loan.due_date == TODAY + timedelta(days=14)


def test_cannot_checkout_unavailable_book(seeded):
    emma = member_by_email(seeded, "emma@example.com")
    kindred = book_by_title(seeded, "Kindred")
    with pytest.raises(LibraryError, match="no available copies"):
        crud.checkout_book(seeded, emma.id, kindred.id)
    assert kindred.available_copies == 0


def test_cannot_checkout_same_book_twice(seeded):
    david = member_by_email(seeded, "david@example.com")
    good_omens = book_by_title(seeded, "Good Omens")
    with pytest.raises(LibraryError, match="already has"):
        crud.checkout_book(seeded, david.id, good_omens.id)


def test_checkout_unknown_ids_and_future_date(seeded):
    with pytest.raises(LibraryError, match="No member"):
        crud.checkout_book(seeded, 999, 1)
    with pytest.raises(LibraryError, match="No book"):
        crud.checkout_book(seeded, 1, 999)
    with pytest.raises(LibraryError, match="future"):
        crud.checkout_book(seeded, 1, 3, TODAY + timedelta(days=1))


# --- Read ------------------------------------------------------------------
def test_search_by_title_is_case_insensitive(seeded):
    assert [b.title for b in crud.search_books_by_title(seeded, "the")] == [
        "The Colour of Magic", "The Left Hand of Darkness"]
    assert crud.search_books_by_title(seeded, "zzz") == []


def test_find_books_by_author_partial_name(seeded):
    titles = [b.title for b in crud.find_books_by_author(seeded, "pratch")]
    assert titles == ["Good Omens", "The Colour of Magic"]


def test_member_borrowings_active_vs_history(seeded):
    alice = member_by_email(seeded, "alice@example.com")
    assert [l.book.title for l in crud.list_member_borrowings(seeded, alice.id)] == [
        "A Wizard of Earthsea"]
    assert len(crud.list_member_borrowings(seeded, alice.id, active_only=False)) == 2
    with pytest.raises(LibraryError):
        crud.list_member_borrowings(seeded, 999)


def test_overdue_books(seeded):
    overdue = crud.list_overdue_books(seeded)
    assert [l.book.title for l in overdue] == ["A Wizard of Earthsea", "The Left Hand of Darkness"]
    assert overdue[0].days_overdue() == 16
    # Nothing is overdue if we look from 30 days in the past.
    assert crud.list_overdue_books(seeded, today=TODAY - timedelta(days=60)) == []


# --- Update ----------------------------------------------------------------
def test_return_book_sets_date_and_increments_copies(seeded):
    brian = member_by_email(seeded, "brian@example.com")
    loan = crud.list_member_borrowings(seeded, brian.id)[0]
    assert loan.book.available_copies == 0
    crud.return_book(seeded, loan.id)
    assert loan.return_date == TODAY and loan.book.available_copies == 1
    with pytest.raises(LibraryError, match="already returned"):
        crud.return_book(seeded, loan.id)
    assert loan.book.available_copies == 1


def test_return_date_rules(seeded):
    carmen = member_by_email(seeded, "carmen@example.com")
    loan = crud.list_member_borrowings(seeded, carmen.id)[0]
    with pytest.raises(LibraryError, match="before the checkout"):
        crud.return_book(seeded, loan.id, loan.checkout_date - timedelta(days=1))
    with pytest.raises(LibraryError, match="future"):
        crud.return_book(seeded, loan.id, TODAY + timedelta(days=1))
    assert loan.return_date is None


def test_update_member_email(seeded):
    emma = member_by_email(seeded, "emma@example.com")
    crud.update_member_email(seeded, emma.id, "Emma.W@Example.com")
    assert emma.email == "emma.w@example.com"
    with pytest.raises(LibraryError, match="already used"):
        crud.update_member_email(seeded, emma.id, "alice@example.com")
    with pytest.raises(LibraryError, match="valid email"):
        crud.update_member_email(seeded, emma.id, "bad")
    assert emma.email == "emma.w@example.com"


# --- Delete ----------------------------------------------------------------
def test_cannot_delete_borrowed_book(seeded):
    kindred = book_by_title(seeded, "Kindred")
    with pytest.raises(LibraryError, match="still checked out"):
        crud.delete_book(seeded, kindred.id)
    assert seeded.get(Book, kindred.id) is not None


def test_delete_book_with_only_returned_history(seeded):
    coraline = book_by_title(seeded, "Coraline")
    gaiman = crud.find_author_by_name(seeded, "Neil Gaiman")
    assert crud.delete_book(seeded, coraline.id) == "Coraline"
    assert seeded.get(Book, coraline.id) is None
    assert "Coraline" not in {b.title for b in gaiman.books}
    assert seeded.get(Author, gaiman.id) is not None  # author survives


def test_cannot_delete_member_with_active_loans(seeded):
    alice = member_by_email(seeded, "alice@example.com")
    with pytest.raises(LibraryError, match="still have"):
        crud.delete_member(seeded, alice.id)
    assert seeded.get(Member, alice.id) is not None


def test_delete_member_without_active_loans(seeded):
    emma = member_by_email(seeded, "emma@example.com")
    assert crud.delete_member(seeded, emma.id) == "Emma Wilson"
    assert seeded.get(Member, emma.id) is None
    with pytest.raises(LibraryError, match="No member"):
        crud.delete_member(seeded, emma.id)


# --- Database-level constraints --------------------------------------------
def test_database_rejects_negative_copies(seeded):
    book = book_by_title(seeded, "Coraline")
    book.available_copies = -5
    with pytest.raises(IntegrityError):
        seeded.commit()
    seeded.rollback()


def test_database_enforces_foreign_keys(seeded):
    seeded.add(Borrowing(book_id=999, member_id=999, checkout_date=TODAY))
    with pytest.raises(IntegrityError):
        seeded.commit()
    seeded.rollback()


def test_session_usable_after_failed_operation(seeded):
    with pytest.raises(LibraryError):
        crud.add_book(seeded, "Dup", "9780060853983", 2000, 1)
    # The rollback leaves the session healthy for the next operation.
    crud.add_member(seeded, "Grace", "grace@example.com")
    assert member_by_email(seeded, "grace@example.com").name == "Grace"
