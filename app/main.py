"""Entry point: bot + job queue (+ optional dashboard addon).

    python main.py
"""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    TypeHandler,
    filters,
)

from app.config import settings
from app.core.database import run_migrations

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

run_migrations()

# Global bot state (admin toggles it from the admin panel)
bot_active = True


def set_bot_active(state: bool) -> None:
    global bot_active
    bot_active = state


try:
    from telegram.ext import ApplicationHandlerStop
except ImportError:  # pragma: no cover
    class ApplicationHandlerStop(Exception):
        pass


async def global_bot_check(update: Update, _: ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id in settings.ADMIN_IDS:
        return
    global bot_active
    if not bot_active:
        if update.message:
            await update.message.reply_text("⚠️ البوت متوقف حالياً للصيانة.")
        elif update.callback_query:
            await update.callback_query.answer("⚠️ متوقف للصيانة.", show_alert=True)
        raise ApplicationHandlerStop()


def build_application() -> Application:
    application = (
        ApplicationBuilder()
        .token(settings.BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(TypeHandler(Update, global_bot_check), group=-1)

    from app.handlers.user import (
        balance_msg_handler,
        catalog_cb_handler,
        catalog_msg_handler,
        profile_handler,
        start_handler,
    )
    from app.conversations.order import order_conversation_handler, poll_pending_orders
    from app.conversations.deposit import deposit_conversation_handler
    from app.conversations.admin import admin_conversation_handler

    application.add_handler(start_handler)
    application.add_handler(profile_handler)
    application.add_handler(order_conversation_handler())
    application.add_handler(deposit_conversation_handler())
    application.add_handler(admin_conversation_handler())
    application.add_handler(catalog_cb_handler)
    application.add_handler(catalog_msg_handler)
    application.add_handler(balance_msg_handler)

    # ── Background jobs ──
    job_queue = application.job_queue
    if job_queue:
        if settings.CATALOG_SYNC_MINUTES > 0 and settings.STORE_PROVIDER != "dummy":
            job_queue.run_repeating(
                _job_sync_catalog,
                interval=settings.CATALOG_SYNC_MINUTES * 60,
                first=_catalog_first_run_secs(),
            )
        job_queue.run_repeating(poll_pending_orders, interval=120, first=30)

    return application


def _catalog_first_run_secs() -> int:
    """Sync shortly after boot (allow network warm-up)."""
    return 15


async def _job_sync_catalog(context: ContextTypes.DEFAULT_TYPE):
    from app.catalog.sync_catalog import sync_catalog
    from app.providers.base import get_provider

    try:
        cats, prods = await asyncio.to_thread(sync_catalog, get_provider())
        logger.info("scheduled catalog sync: %s cats, %s prods", cats, prods)
    except Exception as exc:  # noqa: BLE001
        logger.error("scheduled catalog sync failed: %s", exc)


async def post_init(application: Application) -> None:
    admin_filter = filters.User(user_id=settings.ADMIN_IDS)
    application.add_handler(
        CommandHandler("start_bot", _cmd_start_bot, filters=admin_filter), group=100
    )
    application.add_handler(
        CommandHandler("stop_bot", _cmd_stop_bot, filters=admin_filter), group=100
    )


async def _cmd_start_bot(update: Update, _: ContextTypes.DEFAULT_TYPE):
    set_bot_active(True)
    await update.message.reply_text("✅ تم تشغيل البوت.")


async def _cmd_stop_bot(update: Update, _: ContextTypes.DEFAULT_TYPE):
    set_bot_active(False)
    await update.message.reply_text("⏸️ تم إيقاف البوت مؤقتاً.")


def main() -> None:
    if not settings.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is not set — copy .env.example to .env and fill it.")

    application = build_application()
    application.run_polling()


if __name__ == "__main__":
    main()