from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    first_name = Column(String(120))
    last_name = Column(String(120))
    username = Column(String(120))
    balance = Column(Float, default=0.0)  # display currency (SYP)
    discount_percent = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())

    orders = relationship("Order", backref="user")


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("provider_category_id", name="uq_cat_provider_id"),)

    id = Column(Integer, primary_key=True)
    provider_category_id = Column(Integer, nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    name = Column(String(255))
    image = Column(String(500))
    status = Column(String(20), default="active")  # active | inactive (curated off)

    children = relationship("Category", backref="parent", remote_side=[id])
    products = relationship("Product", backref="category")


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("external_id", name="uq_product_external_id"),)

    id = Column(Integer, primary_key=True)
    external_id = Column(Integer, nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    name = Column(String(255))           # raw provider name
    display_name = Column(String(255))   # curated override (fixes malnamed)
    cost_price = Column(Float, default=0.0)   # provider base price (USD)
    price = Column(Float, default=0.0)        # sell price (USD) = cost * margin
    price_override = Column(Boolean, default=False)  # manual price, sync won't touch
    params = Column(Text)                # JSON list of required params
    qty_values = Column(Text)            # JSON: {type: unit|list|range, ...}
    image = Column(String(500))
    status = Column(String(20), default="active")  # active | inactive (curated off)
    is_auto = Column(Boolean, default=True)        # fulfillable via provider
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    qty = Column(Integer, default=1)
    field_answers = Column(Text)          # JSON of params -> values
    total_price_syp = Column(Float)       # display currency at order time
    provider_order_id = Column(String(100))  # ID_xxx from provider
    order_uuid = Column(String(64))       # idempotency key for the attempt
    status = Column(String(20), default="pending")  # pending | completed | cancelled
    refunded = Column(Boolean, default=False)
    replay_api = Column(Text)             # JSON payload delivered on success
    created_at = Column(DateTime, server_default=func.now())

    product = relationship("Product")


class DepositOrder(Base):
    __tablename__ = "deposit_orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, default=0.0)   # display currency (SYP)
    status = Column(String(20), default="pending")  # pending | approved | rejected
    screenshot_path = Column(String(500))
    balance_credited = Column(Boolean, default=False)
    admin_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class ExchangeRate(Base):
    """Current conversion from provider currency (USD) to display currency (SYP)."""

    __tablename__ = "exchange_rates"

    id = Column(Integer, primary_key=True)
    rate = Column(Float, default=13000.0)  # SYP per 1 USD
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text)


class AdminLog(Base):
    __tablename__ = "admin_logs"

    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer)
    action = Column(String(255))
    details = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
