"""Order conversation: product -> params -> qty -> summary -> confirm.

Money rules (regression-tested):
- order_uuid makes provider calls idempotent; reuse it on retries
- user balance debited exactly once, at creation, inside the same session
- refunds (auto_failed / timeout / admin cancel) happen exactly once,
  guarded by `refunded`; never double-credit
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.catalog.normalize import dumps, is_qty_allowed, loads, pretty_qty
from app.core.database import SessionLocal
from app.core.models import ExchangeRate, Order, Product, User
from app.handlers.navigation import exit_to_categories
from app.i18n import t
from app.keyboards.inline import buy_confirm_buttons
from app.providers.base import (
    InsufficientBalanceError,
    ProviderError,
    StoreProvider,
    TryAgainLaterError,
    get_provider,
)

logger = logging.getLogger(__name__)

ASK_PARAM, ASK_QTY, CONFIRM = range(3)


def _rate(db: Session) -> float:
    rate = db.query(ExchangeRate).order_by(ExchangeRate.id.desc()).first()
    return rate.rate if rate else 13000.0


def _display_name(product: Product) -> str:
    return product.display_name or product.name


def _product_from_user_data(context: ContextTypes.DEFAULT_TYPE) -> Product | None:
    product_id = context.user_data.get("buy_product_id")
    if not product_id:
        return None
    db = SessionLocal()
    try:
        return db.query(Product).filter_by(id=product_id, status="active").first()
    finally:
        db.close()


async def start_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    product_id = int(query.data.split(":", 1)[1])

    db = SessionLocal()
    try:
        product = db.query(Product).filter_by(id=product_id, status="active").first()
        if not product:
            await query.answer(t("no_products"), show_alert=True)
            return ConversationHandler.END
        params = loads(product.params, [])
        context.user_data["buy_product_id"] = product.id
        context.user_data["buy_params"] = params or []
        context.user_data["buy_answers"] = {}
        context.user_data["buy_param_idx"] = 0
    finally:
        db.close()

    await query.answer()
    if params:
        await query.edit_message_text(_param_prompt(context, _param_key(params[0])))
        return ASK_PARAM
    return await _after_params(update, context)


def _param_prompt(context: ContextTypes.DEFAULT_TYPE, param: str | None) -> str:
    if param:
        return t("product_params_hint", param=param)
    return t("product_qty_hint")


async def ask_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    params = context.user_data.get("buy_params") or []
    answers = context.user_data.setdefault("buy_answers", {})
    idx = context.user_data.get("buy_param_idx", 0)

    param = _param_key(params[idx]) if idx < len(params) else None
    if param is None:
        return await _after_params(update, context)

    answers[param] = update.message.text
    context.user_data["buy_param_idx"] = idx + 1

    if idx + 1 < len(params):
        await update.message.reply_text(_param_prompt(context, _param_key(params[idx + 1])))
        return ASK_PARAM
    return await _after_params(update, context)


async def _after_params(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Params collected (or none) — decide qty vs direct summary."""
    product = _product_from_user_data(context)
    qty_rules = loads(product.qty_values, {"type": "unit"}) if product else {"type": "unit"}
    if qty_rules.get("type") == "unit":
        context.user_data["buy_qty"] = 1
        await _show_summary(update, context)
        return CONFIRM
    await update.effective_message.reply_text(
        t("product_qty_hint") + "\n" + t("qty_rule", rule=pretty_qty(qty_rules))
    )
    return ASK_QTY


def _param_key(param) -> str:
    if isinstance(param, str):
        return param
    if isinstance(param, dict):
        return param.get("label") or param.get("key") or "value"
    return str(param)


async def ask_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    try:
        qty = int(raw.replace(",", ""))
    except ValueError:
        await update.message.reply_text(t("qty_invalid"))
        return ASK_QTY

    product = _product_from_user_data(context)
    qty_rules = loads(product.qty_values, {"type": "unit"}) if product else {"type": "unit"}
    if not is_qty_allowed(qty_rules, qty):
        await update.message.reply_text(
            t("qty_not_allowed", rule=pretty_qty(qty_rules))
        )
        return ASK_QTY

    context.user_data["buy_qty"] = qty
    await _show_summary(update, context)
    return CONFIRM


async def _show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product = _product_from_user_data(context)
    if product is None:
        await update.effective_message.reply_text(t("error_generic"))
        return
    qty = context.user_data.get("buy_qty", 1)
    answers = context.user_data.get("buy_answers", {})
    db = SessionLocal()
    try:
        total_syp = int(round(product.price * qty * _rate(db)))
    finally:
        db.close()

    details = "\n".join(f"▫️ {k}: {v}" for k, v in answers.items())
    if details:
        details += "\n"
    text = t(
        "order_summary",
        name=_display_name(product),
        details=details,
        qty=qty,
        price=f"{total_syp:,.0f}",
    )
    await update.effective_message.reply_text(text, reply_markup=buy_confirm_buttons())


async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "order:cancel":
        context.user_data.clear()
        await query.edit_message_text(t("cancel"))
        return ConversationHandler.END

    product = _product_from_user_data(context)
    if product is None:
        await query.edit_message_text(t("error_generic"))
        return ConversationHandler.END
    qty = context.user_data.get("buy_qty", 1)
    answers = context.user_data.get("buy_answers", {})
    order_uuid = str(uuid.uuid4())

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if user is None:
            await query.edit_message_text(t("error_generic"))
            return ConversationHandler.END

        rate = _rate(db)
        total_syp = int(round(product.price * qty * rate))
        if (user.balance or 0) < total_syp:
            await query.edit_message_text(t("order_insufficient"))
            context.user_data.clear()
            return ConversationHandler.END

        user.balance -= total_syp
        order = Order(
            user_id=user.id,
            product_id=product.id,
            qty=qty,
            field_answers=None,
            total_price_syp=total_syp,
            order_uuid=order_uuid,
            status="pending",
        )
        db.add(order)
        db.flush()

        # keep params in field_answers for records/refunds
        import json

        order.field_answers = json.dumps(answers, ensure_ascii=False)

        provider: StoreProvider = context.bot_data.get("provider")
        if provider is None:
            from app.providers.base import get_provider

            provider = get_provider()
            context.bot_data["provider"] = provider

        await query.edit_message_text(t("order_processing"))
        try:
            result = provider.create_order(
                product.external_id, qty, answers, order_uuid
            )
        except (InsufficientBalanceError,) as exc:
            user.balance += total_syp
            order.status = "cancelled"
            order.refunded = True
            db.commit()
            await _replace_message(update, query, t("order_failed", reason=t("provider_insufficient")))
            logger.warning("provider order rejected (insufficient): %s", exc)
            return ConversationHandler.END
        except (TryAgainLaterError,) as exc:
            # transient — keep the order pending; polling will retry with the same uuid
            db.commit()
            await _replace_message(update, query, t("order_waiting"))
            logger.info("provider transient error, order %s kept pending: %s", order.id, exc)
            return ConversationHandler.END
        except ProviderError as exc:
            user.balance += total_syp
            order.status = "cancelled"
            order.refunded = True
            db.commit()
            await _replace_message(update, query, t("order_failed", reason=str(exc) or t("error_generic")))
            return ConversationHandler.END
        except Exception as exc:  # noqa: BLE001 - safety net
            logger.exception("unexpected provider error on order %s", order.id)
            user.balance += total_syp
            order.status = "cancelled"
            order.refunded = True
            db.commit()
            await _replace_message(update, query, t("order_failed", reason=t("error_generic")))
            return ConversationHandler.END

        # success path
        status = str(result.get("status", "")).lower()
        provider_order_id = result.get("order_id")
        order.provider_order_id = provider_order_id
        if status == "accept":
            from app.catalog.normalize import dumps as _dumps

            order.status = "completed"
            order.replay_api = _dumps(result.get("replay_api")) if result.get("replay_api") else "[]"
            db.commit()
            await _deliver_success(update, query, result)
        else:
            # wait / reject handled by polling
            order.status = "pending" if status == "wait" else "cancelled"
            if order.status == "cancelled":
                user.balance += total_syp
                order.refunded = True
            db.commit()
            if order.status == "cancelled":
                await _replace_message(update, query, t("order_failed", reason=t("provider_rejected")))
            else:
                await _replace_message(update, query, t("order_waiting"))
        return ConversationHandler.END

    finally:
        db.close()


async def _deliver_success(update: Update, query, result: dict):
    replay = result.get("replay_api") or []
    excerpt = ""
    if replay:
        try:
            if isinstance(replay, list) and isinstance(replay[0], dict):
                codes = replay[0].get("replay") or []
                excerpt = "\n".join(f"🔑 {c}" for c in codes)
        except Exception:  # noqa: BLE001
            excerpt = ""
    lines = [t("order_success")]
    if excerpt:
        lines.append("━━━━━━━━━━\n" + excerpt)
    await query.edit_message_text("\n".join(lines))


async def _replace_message(update: Update, query, text: str):
    try:
        await query.edit_message_text(text)
    except Exception:  # noqa: BLE001 - message may have been edited already
        pass


def order_conversation_handler():
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_order, pattern=r"^buy:")],
        states={
            ASK_PARAM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_param)],
            ASK_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_qty)],
            CONFIRM: [CallbackQueryHandler(confirm_order, pattern=r"^order:")],
        },
        fallbacks=[
            CommandHandler("cancel", exit_to_categories),
            MessageHandler(filters.Text([t("back")]), exit_to_categories),
        ],
        name="order_conversation",
    )


# ── Polling & refunds ───────────────────────────────────────────

def refund_order(db: Session, order: Order, amount_syp: float | None = None) -> bool:
    """Refund exactly once. Safe to call repeatedly (guarded by refunded)."""
    if order.refunded or order.status == "cancelled" and order.refunded:
        return False
    if order.refunded:
        return False

    user = db.query(User).filter_by(id=order.user_id).first()
    if user is None:
        return False

    amount = amount_syp if amount_syp is not None else (order.total_price_syp or 0)
    user.balance = (user.balance or 0) + amount
    order.refunded = True
    order.status = "cancelled"
    db.commit()
    return True


async def refund_and_notify(context: ContextTypes.DEFAULT_TYPE, order: Order, reason_key: str = "order_refunded"):
    from app.core.notifications import send_notification

    db = SessionLocal()
    try:
        if refund_order(db, order):
            user = db.query(User).filter_by(id=order.user_id).first()
            if user:
                await send_notification(
                    context.bot,
                    user.telegram_id,
                    t("order_refunded", amount=f"{order.total_price_syp:,.0f}"),
                )
    finally:
        db.close()


async def poll_pending_orders(context: ContextTypes.DEFAULT_TYPE):
    """Job: resolve pending orders against the provider.

    - accept   -> complete, deliver replay, notify
    - reject   -> refund once, notify
    - wait     -> keep pending (provider owns the money; no auto-refund)
    - no op    -> timeout refund (unacknowledged attempt)
    Capped per run; the job re-runs to drain the rest.
    """
    import datetime

    from app.core.notifications import send_notification

    db = SessionLocal()
    processed = 0
    try:
        pending = (
            db.query(Order)
            .filter(Order.status == "pending")
            .order_by(Order.id)
            .limit(20)
            .all()
        )
        provider: StoreProvider = context.bot_data.get("provider") or get_provider()
        context.bot_data["provider"] = provider
        timeout = _timeout_minutes()
        now = datetime.datetime.utcnow()

        for order in pending:
            created = order.created_at
            if created is None:
                db.delete(order)
                db.commit()
                continue

            age_min = (now - created).total_seconds() / 60

            # unacknowledged attempt (no provider id) — give up after timeout
            if not order.provider_order_id and age_min > timeout:
                if refund_order(db, order):
                    await _notify_refund(context, order)
                processed += 1
                continue

            try:
                result = provider.check_order(order.order_uuid, is_uuid=True)
            except TryAgainLaterError:
                continue
            except ProviderError as exc:
                logger.warning("check failed for order %s: %s", order.id, exc)
                continue

            if not result:
                if age_min > timeout * 2:
                    if refund_order(db, order):
                        await _notify_refund(context, order)
                continue

            status = str(result.get("status", "")).lower()
            if status == "accept":
                order.status = "completed"
                order.provider_order_id = result.get("order_id") or order.provider_order_id
                order.replay_api = dumps(result.get("replay_api"))
                db.commit()
                await _deliver_success_to_user(context, order)
                processed += 1
            elif status == "reject":
                if refund_order(db, order):
                    await _notify_refund(context, order)
                processed += 1
            # wait -> leave pending
    finally:
        db.close()


def _timeout_minutes() -> int:
    from app.config import settings

    return int(getattr(settings, "ORDER_TIMEOUT_MINUTES", 30))


async def _notify_refund(context: ContextTypes.DEFAULT_TYPE, order: Order):
    from app.core.notifications import send_notification

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=order.user_id).first()
        if user:
            await send_notification(
                context.bot,
                user.telegram_id,
                t("order_refunded", amount=f"{order.total_price_syp:,.0f}"),
            )
    finally:
        db.close()


async def _deliver_success_to_user(context: ContextTypes.DEFAULT_TYPE, order: Order):
    from app.core.notifications import send_notification

    replay = loads(order.replay_api, [])
    excerpt = ""
    if replay:
        try:
            if isinstance(replay, list) and replay and isinstance(replay[0], dict):
                codes = replay[0].get("replay") or []
                excerpt = "\n".join(f"🔑 {c}" for c in codes)
        except Exception:  # noqa: BLE001
            excerpt = ""
    lines = [t("order_success")]
    if excerpt:
        lines.append("━━━━━━━━━━\n" + excerpt)
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=order.user_id).first()
        if user:
            await send_notification(context.bot, user.telegram_id, "\n".join(lines))
    finally:
        db.close()