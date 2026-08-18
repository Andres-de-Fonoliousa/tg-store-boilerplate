import os
import sys
import tempfile

TEST_DB = os.path.join(tempfile.gettempdir(), "opencode", "bp_tests.db")
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["STORE_PROVIDER"] = "dummy"
os.environ["FLASK_SECRET_KEY"] = "test_secret"
os.environ["ADMIN_ACCESS_CODE"] = "1234"
os.environ["MARGIN_PERCENT"] = "20"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.core.database import Base, engine, run_migrations


@pytest.fixture(scope="session", autouse=True)
def _bootstrap():
    run_migrations()
    yield


@pytest.fixture()
def db():
    from app.core.database import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_tables(db):
    yield
    from sqlalchemy import text

    for table in (
        "admin_logs",
        "settings",
        "exchange_rates",
        "deposit_orders",
        "orders",
        "products",
        "categories",
        "users",
    ):
        db.execute(text(f"DELETE FROM {table}"))
    db.commit()