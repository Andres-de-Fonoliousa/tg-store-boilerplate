"""Optional Flask dashboard addon.

Importable:  from app.dashboard import create_app
Standalone:  python -m app.dashboard

Hardening: env-routed secret key (fail-closed random), access code stored as
SHA-256 hash, 5-attempt rate limit, CSRF on every form, localhost by default.
"""

from __future__ import annotations

import functools
import hashlib
import hmac
import os
import secrets
from contextlib import contextmanager

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func

from app.catalog.normalize import loads
from app.config import settings
from app.core.database import SessionLocal
from app.core.models import Category, DepositOrder, ExchangeRate, Order, Product, Setting, User

_MAX_CODE_ATTEMPTS = 5


def create_app() -> Flask:
    media_root = os.path.abspath(settings.MEDIA_ROOT)
    app = Flask(
        __name__,
        static_folder=media_root,
        static_url_path="/media",
    )
    app.secret_key = settings.FLASK_SECRET_KEY or secrets.token_hex(32)

    code_hash = hashlib.sha256((settings.ADMIN_ACCESS_CODE or "").encode()).hexdigest()
    app.config["_code_hash"] = code_hash

    # ── CSRF ──
    @app.context_processor
    def inject_csrf_token():
        return {"csrf_token": _csrf_token()}

    @app.before_request
    def csrf_protect():
        if request.method == "POST" and request.endpoint and request.endpoint != "login":
            token = request.form.get("csrf_token", "")
            if not _csrf_ok(token):
                abort(403)

    # ── Auth helpers ──
    def login_required(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("admin_logged_in"):
                return redirect(url_for("login"))
            return view(*args, **kwargs)

        return wrapped

    def _admin(code: str) -> bool:
        return hmac.compare_digest(
            hashlib.sha256(code.encode()).hexdigest(),
            app.config["_code_hash"],
        )

    # ── Routes ──
    @app.route("/admin/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if not _csrf_ok(request.form.get("csrf_token", "")):
                abort(403)
            attempts = session.get("login_attempts", 0)
            if attempts >= _MAX_CODE_ATTEMPTS:
                flash("محاولات كثيرة — انتظر دقيقة ثم أعد المحاولة.", "error")
                return render_template("login.html")
            if _admin(request.form.get("code", "")):
                session["admin_logged_in"] = True
                session.pop("login_attempts", None)
                return redirect(url_for("admin_dashboard"))
            session["login_attempts"] = attempts + 1
            flash("رمز الدخول غير صحيح.", "error")
        return render_template("login.html")

    @app.route("/admin/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.route("/admin")
    @login_required
    def admin_dashboard():
        with get_db() as db:
            users = db.query(User).count()
            orders = db.query(Order).count()
            revenue = db.query(func.sum(Order.total_price_syp)).filter(Order.status == "completed").scalar() or 0
            pending_deposits = db.query(DepositOrder).filter(DepositOrder.status == "pending").count()
            balance = db.query(func.sum(User.balance)).scalar() or 0
            deposits_total = db.query(func.sum(DepositOrder.amount)).filter(DepositOrder.balance_credited == True).scalar() or 0  # noqa: E712
        return render_template(
            "dashboard.html",
            stats={"users": users, "orders": orders, "revenue": revenue,
                   "pending_deposits": pending_deposits, "balance": balance,
                   "deposits_total": deposits_total},
        )

    @app.route("/admin/orders")
    @login_required
    def manage_orders():
        with get_db() as db:
            order_list = []
            for order in db.query(Order).order_by(Order.id.desc()).limit(200).all():
                product = db.query(Product).filter_by(id=order.product_id).first()
                user = db.query(User).filter_by(id=order.user_id).first()
                order_list.append({
                    "id": order.id,
                    "user": (user.username or user.first_name) if user else "?",
                    "product": (product.display_name or product.name) if product else "?",
                    "qty": order.qty,
                    "total": order.total_price_syp,
                    "status": order.status,
                    "created_at": order.created_at,
                })
        return render_template("orders.html", orders=order_list)

    @app.route("/admin/orders/update/<int:order_id>", methods=["POST"])
    @login_required
    def update_order_status(order_id):
        new_status = request.form.get("status")
        with get_db() as db:
            order = db.query(Order).filter_by(id=order_id).first()
            if order:
                if new_status == "cancelled" and not order.refunded:
                    from app.conversations.order import refund_order

                    refund_order(db, order)
                    flash("تم الإلغاء وإرجاع المبلغ.", "success")
                else:
                    order.status = new_status
                    db.commit()
                    flash("تم تحديث الحالة.", "success")
            else:
                flash("الطلب غير موجود.", "error")
        return redirect(url_for("manage_orders"))

    @app.route("/admin/deposits")
    @login_required
    def manage_deposits():
        with get_db() as db:
            deposits = []
            for dep in db.query(DepositOrder).order_by(DepositOrder.id.desc()).limit(200).all():
                user = db.query(User).filter_by(id=dep.user_id).first()
                deposits.append({
                    "id": dep.id,
                    "user": (user.username or user.first_name) if user else "?",
                    "amount": dep.amount,
                    "status": dep.status,
                    "screenshot_path": dep.screenshot_path,
                    "created_at": dep.created_at,
                })
        return render_template("deposits.html", deposits=deposits)

    @app.route("/admin/deposits/update/<int:deposit_id>", methods=["POST"])
    @login_required
    def update_deposit_status(deposit_id):
        new_status = request.form.get("status")
        with get_db() as db:
            deposit = db.query(DepositOrder).filter_by(id=deposit_id).first()
            if not deposit:
                flash("الشحن غير موجود.", "error")
                return redirect(url_for("manage_deposits"))
            user = db.query(User).filter_by(id=deposit.user_id).first()
            if new_status == "approved" and not deposit.balance_credited and user:
                user.balance = (user.balance or 0) + deposit.amount
                deposit.balance_credited = True
            deposit.status = new_status
            db.commit()
            flash("تم تحديث حالة الشحن.", "success")
        return redirect(url_for("manage_deposits"))

    @app.route("/admin/catalog")
    @login_required
    def manage_catalog():
        with get_db() as db:
            cats = db.query(Category).order_by(Category.name).all()
            products = db.query(Product).order_by(Product.name).limit(400).all()
        return render_template("catalog.html", categories=cats, products=products)

    @app.route("/admin/catalog/category/<int:cat_id>/toggle", methods=["POST"])
    @login_required
    def toggle_category(cat_id):
        with get_db() as db:
            cat = db.query(Category).filter_by(id=cat_id).first()
            if cat:
                cat.status = "active" if cat.status != "active" else "inactive"
                db.commit()
        return redirect(url_for("manage_catalog"))

    @app.route("/admin/catalog/product/<int:prod_id>", methods=["POST"])
    @login_required
    def update_product(prod_id):
        with get_db() as db:
            product = db.query(Product).filter_by(id=prod_id).first()
            if product:
                product.status = "active" if request.form.get("status") == "active" else "inactive"
                display = request.form.get("display_name", "").strip()
                if display:
                    product.display_name = display
                raw_price = request.form.get("price", "").strip()
                if raw_price:
                    try:
                        product.price = round(float(raw_price), 4)
                        product.price_override = True
                    except ValueError:
                        pass
                db.commit()
                flash("تم تحديث المنتج.", "success")
        return redirect(url_for("manage_catalog"))

    @app.route("/admin/settings", methods=["GET", "POST"])
    @login_required
    def manage_settings():
        with get_db() as db:
            if request.method == "POST":
                margin = request.form.get("margin_percent", "").strip()
                if margin:
                    _set_setting(db, "margin_percent", margin)
                methods = request.form.get("payment_methods", "").strip()
                if methods:
                    _set_setting(db, "payment_methods", methods)
                rate = request.form.get("exchange_rate", "").strip()
                if rate:
                    try:
                        rate_row = db.query(ExchangeRate).order_by(ExchangeRate.id.desc()).first()
                        if rate_row is None:
                            rate_row = ExchangeRate(rate=float(rate))
                            db.add(rate_row)
                        else:
                            rate_row.rate = float(rate)
                        db.commit()
                    except ValueError:
                        flash("سعر صرف غير صحيح.", "error")
                flash("تم حفظ الإعدادات.", "success")
            margin = db.query(Setting).filter_by(key="margin_percent").first()
            methods = db.query(Setting).filter_by(key="payment_methods").first()
            rate = db.query(ExchangeRate).order_by(ExchangeRate.id.desc()).first()
        return render_template(
            "settings.html",
            margin_percent=margin.value if margin else settings.MARGIN_PERCENT,
            payment_methods=methods.value if methods else "",
            exchange_rate=rate.rate if rate else 13000.0,
        )

    return app


# ── Helpers ──────────────────────────────────────────────────────

def _csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


def _csrf_ok(token: str) -> bool:
    return bool(token) and hmac.compare_digest(token, session.get("csrf_token", ""))


@contextmanager
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _set_setting(db, key: str, value: str) -> None:
    row = db.query(Setting).filter_by(key=key).first()
    if row is None:
        row = Setting(key=key)
        db.add(row)
    row.value = value
    db.commit()


app = create_app()


if __name__ == "__main__":
    app.run(host=settings.ADMIN_HOST, port=settings.ADMIN_PORT, debug=False)