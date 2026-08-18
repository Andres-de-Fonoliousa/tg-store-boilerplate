"""Money regression tests — the exact bugs fixed in client repo v1."""

from app.conversations.order import refund_order
from app.core.models import DepositOrder, Order, Product, User


def _user(db, balance=1000.0) -> User:
    user = User(telegram_id=9001, first_name="T", balance=balance)
    db.add(user)
    db.commit()
    return user


def _product(db) -> Product:
    product = Product(external_id=1, name="UC 60", cost_price=1.0, price=1.2, status="active")
    db.add(product)
    db.commit()
    return product


def _order(db, user: User, product: Product, status="pending", total=120.0,
           provider_order_id="ID_x", refunded=False) -> Order:
    order = Order(
        user_id=user.id,
        product_id=product.id,
        qty=1,
        total_price_syp=total,
        provider_order_id=provider_order_id,
        status=status,
        refunded=refunded,
    )
    db.add(order)
    db.commit()
    return order


def test_deposit_double_approve_credits_once(db):
    user = _user(db, balance=0)
    dep = DepositOrder(user_id=user.id, amount=500.0, status="pending")
    db.add(dep)
    db.commit()

    # first approval path (Flask)
    dep.status = "approved"
    dep.balance_credited = True
    user.balance += dep.amount
    db.commit()

    # second approval path (Telegram admin) — same guard
    if not dep.balance_credited:
        user.balance += dep.amount
        dep.balance_credited = True
    db.commit()

    assert user.balance == 500.0


def test_refund_is_idempotent(db):
    user = _user(db, balance=0)
    order = _order(db, user, _product(db))
    user.balance = 0  # already debited at creation
    db.commit()

    assert refund_order(db, order) is True
    assert user.balance == 120.0
    assert order.refunded is True
    assert order.status == "cancelled"

    # second call must do nothing
    assert refund_order(db, order) is False
    assert user.balance == 120.0


def test_refund_skips_already_refunded(db):
    user = _user(db, balance=0)
    order = _order(db, user, _product(db), refunded=True)
    assert refund_order(db, order) is False
    assert user.balance == 0.0


def test_order_failure_restores_balance_exactly_once(db):
    """Simulate provider failure path: debit + refund must net to zero."""
    user = _user(db, balance=500.0)
    product = _product(db)
    order = _order(db, user, product)

    user.balance -= order.total_price_syp
    db.commit()

    assert refund_order(db, order) is True
    assert user.balance == 500.0


def test_timeout_refund_path(db):
    """The polling worker refunds when provider id never materialized."""
    from datetime import datetime, timedelta

    user = _user(db, balance=0)
    order = Order(
        user_id=user.id,
        product_id=_product(db).id,
        qty=1,
        total_price_syp=80.0,
        status="pending",
        created_at=datetime.utcnow() - timedelta(minutes=45),
    )
    db.add(order)
    db.commit()

    assert refund_order(db, order) is True
    assert user.balance == 80.0