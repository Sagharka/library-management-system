"""Shared pytest fixtures.

Points the app at a throw-away SQLite file *before* any project module is
imported, so tests never touch the real ``library.db``.
"""

import os
import sys
import tempfile

TEST_DB = os.path.join(tempfile.mkdtemp(prefix="library-tests-"), "test_library.db")
os.environ["LIBRARY_DB_URL"] = f"sqlite:///{TEST_DB}"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from models import SessionLocal, engine, reset_db  # noqa: E402
from seed import seed_database  # noqa: E402


@pytest.fixture
def session():
    """An empty database and an open session for one test."""
    reset_db(engine)
    with SessionLocal() as s:
        yield s


@pytest.fixture
def seeded(session):
    """A session on a database loaded with the sample data."""
    seed_database(session)
    return session
