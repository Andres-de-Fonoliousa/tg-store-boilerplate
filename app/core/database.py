from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Idempotent, additive migrations for existing databases."""
    from sqlalchemy import inspect

    from app.core import models  # noqa: F401  (register tables on Base.metadata)

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    conn = engine.connect()

    def has_column(table: str, column: str) -> bool:
        return any(c["name"] == column for c in inspector.get_columns(table))

    def has_table(table: str) -> bool:
        return inspector.has_table(table)

    try:
        if has_table("products") and not has_column("products", "display_name"):
            conn.execute(text("ALTER TABLE products ADD COLUMN display_name VARCHAR"))
        if has_table("products") and not has_column("products", "price_override"):
            conn.execute(text("ALTER TABLE products ADD COLUMN price_override BOOLEAN DEFAULT 0"))
        if has_table("orders") and not has_column("orders", "refunded"):
            conn.execute(text("ALTER TABLE orders ADD COLUMN refunded BOOLEAN DEFAULT 0"))
        if has_table("deposit_orders") and not has_column("deposit_orders", "balance_credited"):
            conn.execute(text("ALTER TABLE deposit_orders ADD COLUMN balance_credited BOOLEAN DEFAULT 0"))
        conn.commit()
    finally:
        conn.close()
