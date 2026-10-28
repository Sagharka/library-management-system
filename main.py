"""Command-line interface for the Library Management System.

Run with::

    python main.py

The menu loops until the user chooses Exit. Every action opens its own
database session, calls a function from ``crud``, and prints the result.
Invalid input is re-prompted, and rule violations (for example, checking out a
book with no copies left) are shown as friendly messages instead of crashing.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

import crud
from crud import LibraryError
from models import LOAN_PERIOD_DAYS, Book, Borrowing, SessionLocal, init_db
from seed import reset_and_seed, seed_database

MENU = """
📚 Library Management System
1. Add a book
2. Add a member
3. Search books
4. Check out a book
5. Return a book
6. View member's borrowings
7. View overdue books
8. Exit
--- More options ---
9.  Add an author
10. Update a member's email
11. Remove a book
12. Remove a member
13. List all members
14. List all authors
15. Reset database with sample data
"""

LINE = "-" * 72


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------
def prompt_text(label: str, required: bool = True) -> Optional[str]:
    """Ask for text; keep asking until something is entered if ``required``."""
    while True:
        value = input(f"{label}: ").strip()
        if value or not required:
            return value or None
        print("  ⚠️  This field is required.")


def prompt_int(label: str, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    """Ask for a whole number within optional bounds; re-prompt on bad input."""
    while True:
        raw = input(f"{label}: ").strip()
        try:
            value = int(raw)
        except ValueError:
            print("  ⚠️  Please enter a whole number.")
            continue
        if minimum is not None and value < minimum:
            print(f"  ⚠️  Please enter a number of at least {minimum}.")
        elif maximum is not None and value > maximum:
            print(f"  ⚠️  Please enter a number no greater than {maximum}.")
        else:
            return value


def prompt_date(label: str) -> date:
    """Ask for a date as YYYY-MM-DD; pressing Enter means today."""
    while True:
        raw = input(f"{label} (YYYY-MM-DD, Enter for today): ").strip()
        if not raw:
            return date.today()
        try:
            return datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  ⚠️  Please use the format YYYY-MM-DD, e.g. 2026-01-31.")


def confirm(question: str) -> bool:
    """Ask a yes/no question; re-prompt until the answer is y or n."""
    while True:
        answer = input(f"{question} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  ⚠️  Please answer y or n.")


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
def format_authors(book: Book) -> str:
    """Comma-separated author names for a book."""
    return ", ".join(a.name for a in book.authors) or "Unknown author"


def print_books(books: list[Book]) -> None:
    """Print books as a table."""
    if not books:
        print("No books found.")
        return
    print(f"{'ID':>3}  {'Title':<28} {'Author(s)':<28} {'Year':>4} {'Avail':>5}")
    print(LINE)
    for b in books:
        print(f"{b.id:>3}  {b.title[:28]:<28} {format_authors(b)[:28]:<28} "
              f"{b.year_published:>4} {b.available_copies:>5}")
    print(f"({len(books)} book(s))")


def print_borrowings(borrowings: list[Borrowing], show_member: bool = False) -> None:
    """Print borrowings as a table, with due date and status."""
    if not borrowings:
        print("No borrowings found.")
        return
    who = f" {'Member':<16}" if show_member else ""
    print(f"{'Loan':>4}  {'Book':<28}{who} {'Out':<10} {'Due':<10} Status")
    print(LINE)
    for br in borrowings:
        member = f" {br.member.name[:16]:<16}" if show_member else ""
        if br.return_date:
            status = f"Returned {br.return_date}"
        elif br.days_overdue():
            status = f"OVERDUE {br.days_overdue()} day(s)"
        else:
            status = "Checked out"
        print(f"{br.id:>4}  {br.book.title[:28]:<28}{member} "
              f"{br.checkout_date!s:<10} {br.due_date!s:<10} {status}")
    print(f"({len(borrowings)} borrowing(s))")


def show_members(session) -> None:
    """Print a compact member list so the user can pick an id."""
    members = crud.list_members(session)
    if not members:
        print("No members yet.")
        return
    for m in members:
        active = sum(1 for b in m.borrowings if b.is_active)
        print(f"  [{m.id}] {m.name} <{m.email}>  joined {m.membership_date}, {active} active loan(s)")


def show_books_brief(session) -> None:
    """Print a compact book list so the user can pick an id."""
    for b in crud.list_books(session):
        print(f"  [{b.id}] {b.title} — {format_authors(b)} ({b.available_copies} available)")


# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def action_add_book(session) -> None:
    """1. Add a book."""
    title = prompt_text("Title")
    isbn = prompt_text("ISBN (10 or 13 digits)")
    year = prompt_int("Year published", 1, date.today().year)
    copies = prompt_int("Number of copies", 0)
    authors_raw = prompt_text("Author name(s), comma-separated", required=False) or ""
    author_names = [n.strip() for n in authors_raw.split(",") if n.strip()]
    book = crud.add_book(session, title, isbn, year, copies, author_names)
    print(f"✅ Added book [{book.id}] '{book.title}' by {format_authors(book)}.")


def action_add_member(session) -> None:
    """2. Add a member."""
    name = prompt_text("Name")
    email = prompt_text("Email")
    joined = prompt_date("Membership date")
    member = crud.add_member(session, name, email, joined)
    print(f"✅ Added member [{member.id}] {member.name} <{member.email}>.")


def action_search_books(session) -> None:
    """3. Search books: list all, by title, or by author."""
    print("  a) List all books\n  b) Search by title\n  c) Find by author")
    while True:
        choice = input("Choose a, b or c: ").strip().lower()
        if choice in ("a", "b", "c"):
            break
        print("  ⚠️  Please choose a, b or c.")
    if choice == "a":
        books = crud.list_books(session)
    elif choice == "b":
        books = crud.search_books_by_title(session, prompt_text("Title contains"))
    else:
        books = crud.find_books_by_author(session, prompt_text("Author name contains"))
    print_books(books)


def action_checkout(session) -> None:
    """4. Check out a book."""
    show_members(session)
    member_id = prompt_int("Member id", 1)
    show_books_brief(session)
    book_id = prompt_int("Book id", 1)
    checkout_date = prompt_date("Checkout date")
    loan = crud.checkout_book(session, member_id, book_id, checkout_date)
    print(f"✅ '{loan.book.title}' checked out to {loan.member.name} (loan #{loan.id}). "
          f"Due back {loan.due_date}. Copies left: {loan.book.available_copies}.")


def action_return(session) -> None:
    """5. Return a book."""
    show_members(session)
    member_id = prompt_int("Member id", 1)
    active = crud.list_member_borrowings(session, member_id, active_only=True)
    if not active:
        print("This member has no books checked out.")
        return
    print_borrowings(active)
    loan_ids = {br.id for br in active}
    while True:
        loan_id = prompt_int("Loan number to return", 1)
        if loan_id in loan_ids:
            break
        print("  ⚠️  Pick one of the loan numbers listed above.")
    return_date = prompt_date("Return date")
    loan = crud.return_book(session, loan_id, return_date)
    late = (loan.return_date - loan.due_date).days
    note = f" It was {late} day(s) late." if late > 0 else ""
    print(f"✅ '{loan.book.title}' returned by {loan.member.name} on {loan.return_date}.{note} "
          f"Copies available: {loan.book.available_copies}.")


def action_member_borrowings(session) -> None:
    """6. View a member's borrowings."""
    show_members(session)
    member_id = prompt_int("Member id", 1)
    member = crud.get_member(session, member_id)
    print(f"\nCurrent borrowings for {member.name}:")
    print_borrowings(crud.list_member_borrowings(session, member_id, active_only=True))
    if confirm("Show full borrowing history too?"):
        print(f"\nFull history for {member.name}:")
        print_borrowings(crud.list_member_borrowings(session, member_id, active_only=False))


def action_overdue(session) -> None:
    """7. View overdue books."""
    print(f"Books not returned within {LOAN_PERIOD_DAYS} days:")
    print_borrowings(crud.list_overdue_books(session), show_member=True)


def action_add_author(session) -> None:
    """9. Add an author."""
    name = prompt_text("Author name")
    bio = prompt_text("Short bio (optional)", required=False)
    author = crud.add_author(session, name, bio)
    print(f"✅ Added author [{author.id}] {author.name}.")


def action_update_email(session) -> None:
    """10. Update a member's email."""
    show_members(session)
    member_id = prompt_int("Member id", 1)
    member = crud.get_member(session, member_id)
    new_email = prompt_text(f"New email for {member.name} (currently {member.email})")
    member = crud.update_member_email(session, member_id, new_email)
    print(f"✅ {member.name}'s email is now {member.email}.")


def action_remove_book(session) -> None:
    """11. Remove a book (only if not currently borrowed)."""
    show_books_brief(session)
    book = crud.get_book(session, prompt_int("Book id to remove", 1))
    if not confirm(f"Really remove '{book.title}'?"):
        print("Cancelled.")
        return
    title = crud.delete_book(session, book.id)
    print(f"✅ Removed '{title}'.")


def action_remove_member(session) -> None:
    """12. Remove a member (only if they have no active borrowings)."""
    show_members(session)
    member = crud.get_member(session, prompt_int("Member id to remove", 1))
    if not confirm(f"Really remove {member.name}?"):
        print("Cancelled.")
        return
    name = crud.delete_member(session, member.id)
    print(f"✅ Removed {name}.")


def action_list_members(session) -> None:
    """13. List all members."""
    show_members(session)


def action_list_authors(session) -> None:
    """14. List all authors and their books."""
    authors = crud.list_authors(session)
    if not authors:
        print("No authors yet.")
    for a in authors:
        titles = ", ".join(b.title for b in a.books) or "no books yet"
        print(f"  [{a.id}] {a.name}: {titles}")


def action_reseed(session) -> None:
    """15. Wipe the database and load the sample data."""
    if confirm("This deletes ALL data and loads the sample data. Continue?"):
        session.close()
        counts = reset_and_seed()
        print("✅ Database reset: " + ", ".join(f"{n} {k}" for k, n in counts.items()) + ".")
    else:
        print("Cancelled.")


ACTIONS: dict[str, Callable] = {
    "1": action_add_book,
    "2": action_add_member,
    "3": action_search_books,
    "4": action_checkout,
    "5": action_return,
    "6": action_member_borrowings,
    "7": action_overdue,
    "9": action_add_author,
    "10": action_update_email,
    "11": action_remove_book,
    "12": action_remove_member,
    "13": action_list_members,
    "14": action_list_authors,
    "15": action_reseed,
}


def run_action(action: Callable) -> None:
    """Run one menu action in its own session and report any error politely."""
    with SessionLocal() as session:
        try:
            action(session)
        except LibraryError as exc:
            session.rollback()
            print(f"❌ {exc}")
        except SQLAlchemyError as exc:
            session.rollback()
            print(f"❌ Unexpected database error: {exc}")


def offer_seed_if_empty() -> None:
    """On first run, offer to load the sample data into an empty database."""
    with SessionLocal() as session:
        if session.scalar(select(func.count(Book.id))) == 0:
            if confirm("The library is empty. Load sample data?"):
                counts = seed_database(session)
                print("✅ Loaded " + ", ".join(f"{n} {k}" for k, n in counts.items()) + ".")


def main() -> None:
    """Create the tables if needed, then loop over the menu until Exit."""
    init_db()
    try:
        offer_seed_if_empty()
        while True:
            print(MENU)
            choice = input("Choose an option: ").strip()
            if choice == "8":
                print("Goodbye! 👋")
                break
            action = ACTIONS.get(choice)
            if action is None:
                print("⚠️  Invalid choice. Please enter a number from the menu (1-15).")
                continue
            print()
            run_action(action)
            input("\nPress Enter to continue...")
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye! 👋")


if __name__ == "__main__":
    main()
