"""End-to-end tests that drive the CLI menu with scripted keyboard input."""

import pytest

import main
from models import engine, reset_db


def run_cli(monkeypatch, capsys, inputs):
    """Run ``main.main()`` feeding ``inputs`` one line at a time; return the output."""
    answers = iter(inputs)

    def fake_input(prompt=""):
        print(prompt, end="")
        try:
            return next(answers)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr("builtins.input", fake_input)
    main.main()
    return capsys.readouterr().out


@pytest.fixture
def seeded_db(seeded):
    """Sample data committed; the CLI opens its own sessions."""
    seeded.close()


def test_demo_flow_add_checkout_view_return(monkeypatch, capsys, seeded_db):
    out = run_cli(monkeypatch, capsys, [
        "1", "Dune", "978-0-441-17271-9", "1965", "1", "Frank Herbert", "",  # add a book (id 8)
        "4", "5", "8", "", "",          # Emma (id 5) checks out Dune today
        "4", "1", "8", "", "",          # Alice tries -> no copies left
        "6", "5", "n", "",              # view Emma's borrowings
        "5", "5", "9", "", "",          # return loan #9
        "8",
    ])
    assert "Added book [8] 'Dune' by Frank Herbert" in out
    assert "'Dune' checked out to Emma Wilson (loan #9)" in out
    assert "'Dune' has no available copies right now." in out
    assert "Current borrowings for Emma Wilson" in out
    assert "'Dune' returned by Emma Wilson" in out and "Copies available: 1" in out
    assert out.rstrip().endswith("Goodbye! 👋")


def test_search_submenu_and_overdue(monkeypatch, capsys, seeded_db):
    out = run_cli(monkeypatch, capsys, [
        "3", "x", "a", "",              # invalid sub-choice, then list all
        "3", "b", "magic", "",
        "3", "c", "gaiman", "",
        "7", "",
        "8",
    ])
    assert "Please choose a, b or c." in out
    assert "(7 book(s))" in out
    assert "The Colour of Magic" in out
    assert "(3 book(s))" in out          # Gaiman wrote 3 seeded books
    assert "OVERDUE 16 day(s)" in out and "OVERDUE 6 day(s)" in out


def test_input_validation_reprompts(monkeypatch, capsys, seeded_db):
    out = run_cli(monkeypatch, capsys, [
        "99",                           # invalid menu choice
        "2", "", "Zoe", "zoe-at-example", "", "",   # empty name, then invalid email -> error
        "1", "Book", "978-1-23-456789-7", "abc", "3000", "2000", "-1", "1", "", "",
        "8",
    ])
    assert "Invalid choice" in out
    assert "This field is required." in out
    assert "is not a valid email address" in out
    assert "Please enter a whole number." in out
    assert "no greater than" in out and "at least 0" in out
    assert "Added book [8] 'Book' by Unknown author" in out


def test_admin_options(monkeypatch, capsys, seeded_db):
    out = run_cli(monkeypatch, capsys, [
        "9", "Frank Herbert", "", "",                     # add author
        "10", "5", "emma.new@example.com", "",            # update email
        "11", "7", "y", "",                               # remove Kindred -> borrowed
        "11", "3", "y", "",                               # remove Coraline -> ok
        "12", "1", "y", "",                               # remove Alice -> active loans
        "12", "5", "n", "",                               # cancel
        "12", "5", "y", "",                               # remove Emma -> ok
        "13", "",
        "14", "",
        "8",
    ])
    assert "Added author" in out and "Frank Herbert" in out
    assert "Emma Wilson's email is now emma.new@example.com" in out
    assert "Cannot remove 'Kindred'" in out
    assert "Removed 'Coraline'." in out
    assert "Cannot remove Alice Johnson" in out
    assert "Cancelled." in out
    assert "Removed Emma Wilson." in out


def test_reseed_and_empty_db_offer(monkeypatch, capsys):
    reset_db(engine)
    out = run_cli(monkeypatch, capsys, [
        "y",                            # empty library -> load sample data
        "15", "y", "",                  # reset & reseed
        "8",
    ])
    assert "The library is empty. Load sample data?" in out
    assert "Loaded 4 authors, 7 books, 5 members, 8 borrowings." in out
    assert "Database reset: 4 authors, 7 books, 5 members, 8 borrowings." in out


def test_ctrl_d_exits_cleanly(monkeypatch, capsys, seeded_db):
    out = run_cli(monkeypatch, capsys, [])
    assert "Goodbye" in out
