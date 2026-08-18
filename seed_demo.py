"""Seed a runnable demo store with the dummy provider.

Usage:
    python seed_demo.py            # sync demo catalog + defaults
    python seed_demo.py --store bot_token_value
"""

from __future__ import annotations

import sys

from app.catalog.sync_catalog import sync_catalog
from app.core.database import SessionLocal, run_migrations
from app.core.models import ExchangeRate, Setting, User
from app.providers.dummy import DummyProvider


def main() -> None:
    run_migrations()
    sync_catalog(DummyProvider())

    db = SessionLocal()
    try:
        if db.query(ExchangeRate).count() == 0:
            db.add(ExchangeRate(rate=13000.0))
        if db.query(Setting).filter_by(key="payment_methods").count() == 0:
            db.add(Setting(key="payment_methods", value="[{\"name\": \"SHAM Cash\", \"number\": \"0935956516\"}]"))
        if db.query(User).count() == 0:
            db.add(User(telegram_id=0, first_name="Demo", balance=100000.0))
        db.commit()
    finally:
        db.close()

    print("Demo store seeded: catalog (dummy provider), exchange rate, payment method, demo user.")


if __name__ == "__main__":
    main()