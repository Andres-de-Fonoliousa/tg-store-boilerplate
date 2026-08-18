"""Deposit conversation: amount -> method -> receipt photo -> admin review.

Money rules (regression-tested):
- balance credited exactly once on approval (balance_credited guard)
- screenshots stored under media/ (gitignored)
- cancel always returns the user to the main menu
"""

from __future__ import annotations

import logging
import os

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.catalog.normalize import loads
from app.config import settings
from app.core.database import SessionLocal
from app.core.models import DepositOrder, User
from app.handlers.navigation import exit_to_main
from app.i18n import t
from app.keyboards.inline import deposit_method_buttons
from app.keyboards.reply import main_menu

logger = logging.getLogger(__name__)

ASK_AMOUNT, CHOOSE_METHOD, GET_RECEIPT = range(3)


def _payment_methods() -> list[dict]:
    db = SessionLocal()
    try:
        from app.core.models import Setting

        row = db.query(Setting).filter_by(key="payment_methods").first()
        if not row or not row.value:
            return []
        return loads(row.value, [])
    finally:
        db.close()


async def start_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    methods = _payment_methods()
    if not methods:
        await update.message.reply_text(t("deposit_no_methods"))
        return ConversationHandler.END
    context.user_data["deposit_methods"] = methods
    await update.message.reply_text(t("deposit_amount"))
    return ASK_AMOUNT


async def ask_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        await update.message.reply_text(t("deposit_amount_invalid"))
        return ASK_AMOUNT
    if amount <= 0:
        await update.message.reply_text(t("deposit_amount_invalid"))
        return ASK_AMOUNT

    context.user_data["deposit_amount"] = round(amount, 0)
    methods = context.user_data.get("deposit_methods") or _payment_methods()
    await update.message.reply_text(
        t("deposit_method") + "\n" + "\n".join(f"▫️ {m.get('name')}" for m in methods),
        reply_markup=deposit_method_buttons(methods),
    )
    return CHOOSE_METHOD


async def choose_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "dep:cancel":
        context.user_data.pop("deposit_amount", None)
        await query.edit_message_text(t("cancel"))
        return ConversationHandler.END

    method_idx = int(query.data.split(":")[1])
    methods = context.user_data.get("deposit_methods") or _payment_methods()
    if method_idx >= len(methods):
        return CHOOSE_METHOD
    method = methods[method_idx]
    context.user_data["deposit_method"] = method

    number = method.get("number") or ""
    text = t("deposit_send_to", name=method.get("name", ""))
    if number:
        text += f"\n\n💰 رقم الحساب: <code>{number}</code>"
    await query.edit_message_text(text, parse_mode="HTML")
    await query.message.reply_text(t("deposit_receipt"))
    return GET_RECEIPT


async def get_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text and update.message.text == t("back"):
        await exit_to_main(update, context)
        return ConversationHandler.END

    photo = update.message.photo
    if not photo:
        await update.message.reply_text(t("deposit_receipt_invalid"))
        return GET_RECEIPT

    amount = context.user_data.get("deposit_amount", 0)
    method = context.user_data.get("deposit_method") or {}

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(telegram_id=update.effective_user.id).first()
        if user is None:
            await update.message.reply_text(t("error_generic"))
            return ConversationHandler.END

        deposit = DepositOrder(user_id=user.id, amount=amount, status="pending")
        db.add(deposit)
        db.flush()

        path = await _save_photo(update, deposit.id)
        deposit.screenshot_path = path
        db.commit()

        # notify admins
        for admin_id in settings.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"💳 طلب شحن جديد #{deposit.id}: {amount:,.0f} ل.س — {method.get('name', '')}",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("admin notify failed for %s: %s", admin_id, exc)
    finally:
        db.close()

    context.user_data.pop("deposit_amount", None)
    context.user_data.pop("deposit_method", None)
    await update.message.reply_text(t("deposit_pending"), reply_markup=main_menu())
    return ConversationHandler.END


async def _save_photo(update: Update, deposit_id: int) -> str:
    os.makedirs(settings.MEDIA_SCREENSHOTS, exist_ok=True)
    photo = update.message.photo[-1]
    filename = f"deposit_{deposit_id}.jpg"
    full_path = os.path.join(settings.MEDIA_SCREENSHOTS, filename)
    try:
        await photo.get_file().download_to_drive(full_path)
        return f"screenshots/{filename}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("photo download failed: %s", exc)
        raise


def deposit_conversation_handler():
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.Text([t("main_menu_deposit")]), start_deposit)
        ],
        states={
            ASK_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_amount)],
            CHOOSE_METHOD: [
                CallbackQueryHandler(choose_method, pattern=r"^dep:")
            ],
            GET_RECEIPT: [
                MessageHandler(filters.PHOTO, get_receipt),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_receipt),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", exit_to_main),
            MessageHandler(filters.Text([t("back")]), exit_to_main),
        ],
        name="deposit_conversation",
    )