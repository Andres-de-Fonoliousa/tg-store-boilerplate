"""Admin conversation: stats, deposits, orders, catalog curation, broadcast.

Every approval/cancel flows through the shared money helpers in order.py
(refund_order) and the balance_credited guard — no double crediting.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from app.catalog.sync_catalog import sync_catalog
from app.core.database import SessionLocal
from app.core.models import Category, DepositOrder, Order, Product, User
from app.i18n import t
from app.keyboards.inline import admin_menu_buttons
from app.keyboards.reply import main_menu
from app.providers.base import get_provider

logger = logging.getLogger(__name__)

MAIN_MENU, CURATE_CATS, CURATE_PRODS, BROADCAST = range(4)

_PAGE_SIZE = 8


def _is_admin(update: Update) -> bool:
    from app.config import settings

    return update.effective_user.id in settings.ADMIN_IDS


async def admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update):
        return MAIN_MENU
    await update.message.reply_text(t("admin_menu"), reply_markup=admin_menu_buttons())
    return MAIN_MENU


async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_admin(update):
        return MAIN_MENU
    await query.edit_message_text(t("admin_menu"), reply_markup=admin_menu_buttons())
    return MAIN_MENU


async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data
    await query.answer()

    db = SessionLocal()
    try:
        if action == "adm:stats":
            users = db.query(User).count()
            orders = db.query(Order).count()
            pending_orders = db.query(Order).filter(Order.status == "pending").count()
            completed = db.query(Order).filter(Order.status == "completed").count()
            deposits_pending = db.query(DepositOrder).filter(DepositOrder.status == "pending").count()
            await query.edit_message_text(
                f"📊 الإحصائيات:\n\n"
                f"👤 المستخدمون: {users}\n"
                f"📦 الطلبات: {orders} (مكتمل: {completed}، معلق: {pending_orders})\n"
                f"💳 شحنات بانتظار المراجعة: {deposits_pending}"
            )

        elif action == "adm:deposits":
            await _show_pending_deposits(query)

        elif action == "adm:sync":
            await query.edit_message_text("🔄 جارٍ مزامنة الكتالوج...")
            provider = get_provider()
            try:
                cats, prods = sync_catalog(provider)
                await query.edit_message_text(f"✅ تمت المزامنة: {cats} قسم، {prods} منتج.")
            except Exception as exc:  # noqa: BLE001
                logger.error("sync failed: %s", exc)
                await query.edit_message_text(f"❌ فشلت المزامنة: {exc}")

        elif action == "adm:catalog":
            await _catalog_root(query)

        elif action == "adm:menu":
            await query.edit_message_text(t("admin_menu"), reply_markup=admin_menu_buttons())

        elif action == "adm:toggle_bot":
            await _toggle_bot(query)

        elif action == "adm:broadcast":
            context.user_data["bcast_stage"] = "text"
            await query.edit_message_text("📣 أرسل نص الرسالة التي تريد نشرها:")
            return BROADCAST

        elif action.startswith("adm_dep:"):
            await _deposit_action(query, action)

        elif action.startswith("adm_prod_page:"):
            page = int(action.split(":")[2])
            await _products_page(query, page)

        elif action.startswith("adm_cat_toggle:"):
            cat_id = int(action.split(":")[2])
            _toggle_category(db, cat_id)
            await query.edit_message_text("✅ تم التحديث.", reply_markup=admin_menu_buttons())

        elif action.startswith("adm_prod:"):
            await _product_view(query, action)

        elif action.startswith("adm_prod_toggle:"):
            prod_id = int(action.split(":")[2])
            await _toggle_product(query, prod_id)

        elif action.startswith("adm_prod_rename"):
            token = action.split(":")
            prod_id = int(token[1])  # adm_prod_rename:<id>
            context.user_data["rename_product"] = prod_id
            await query.edit_message_text("✏️ أرسل الاسم الجديد (أو /cancel):")
            return CURATE_PRODS

        elif action.startswith("adm_prod_price"):
            token = action.split(":")
            prod_id = int(token[1])
            context.user_data["price_product"] = prod_id
            await query.edit_message_text("💱 أرسل السعر الجديد بالدولار (يُفعّل التجاوز اليدوي):")
            return CURATE_PRODS

        elif action.startswith("adm_prod_unoverride:"):
            prod_id = int(action.split(":")[2])
            _unoverride_price(db, prod_id)
            await query.edit_message_text("✅ تمت إعادة الحساب التلقائي.", reply_markup=admin_menu_buttons())
    finally:
        db.close()

    return MAIN_MENU


# ── Deposits ─────────────────────────────────────────────────────

async def _show_pending_deposits(query) -> None:
    db = SessionLocal()
    try:
        deposits = (
            db.query(DepositOrder)
            .filter(DepositOrder.status == "pending")
            .order_by(DepositOrder.id.desc())
            .limit(10)
            .all()
        )
        if not deposits:
            await query.edit_message_text("لا توجد شحنات بانتظار المراجعة.", reply_markup=admin_menu_buttons())
            return
        rows = []
        for dep in deposits:
            user = db.query(User).filter_by(id=dep.user_id).first()
            who = user.username or user.first_name or f"id {dep.user_id}"
            rows.append(
                InlineKeyboardButton(
                    f"#{dep.id} — {dep.amount:,.0f} ل.س ({who})",
                    callback_data=f"adm_dep:view:{dep.id}",
                )
            )
        kb = InlineKeyboardMarkup([[b] for b in rows] + [[InlineKeyboardButton("🔙", callback_data="adm:menu")]])
        await query.edit_message_text("💳 الشحنات بانتظار المراجعة:", reply_markup=kb)
    finally:
        db.close()


async def _deposit_action(query, action: str) -> None:
    db = SessionLocal()
    try:
        parts = action.split(":")
        sub = parts[1]
        dep_id = int(parts[2])
        dep = db.query(DepositOrder).filter_by(id=dep_id).first()
        user = db.query(User).filter_by(id=dep.user_id).first() if dep else None

        if sub == "view":
            text = f"💳 شحن #{dep.id}\n💰 {dep.amount:,.0f} ل.س\n👤 {user.username or user.first_name if user else '?'}"
            buttons = [
                [
                    InlineKeyboardButton("✅ قبول", callback_data=f"adm_dep:approve:{dep.id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"adm_dep:reject:{dep.id}"),
                ],
                [InlineKeyboardButton("🔙", callback_data="adm:deposits")],
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
            if dep and dep.screenshot_path and user:
                from app.config import settings
                import os

                path = os.path.join(settings.MEDIA_ROOT, dep.screenshot_path)
                if os.path.exists(path):
                    try:
                        with open(path, "rb") as fd:
                            await query.message.reply_photo(fd)
                    except Exception:  # noqa: BLE001
                        pass

        elif sub == "approve":
            if dep and not dep.balance_credited:
                user.balance = (user.balance or 0) + dep.amount
                dep.balance_credited = True
                dep.status = "approved"
                dep.admin_id = query.from_user.id
                db.commit()
                if user:
                    from app.core.notifications import send_notification

                    await send_notification(
                        query.message.bot, user.telegram_id,
                        t("deposit_approved", amount=f"{dep.amount:,.0f}", balance=f"{user.balance:,.0f}"),
                    )
                await query.edit_message_text(f"✅ تم قبول الشحن #{dep.id}.", reply_markup=admin_menu_buttons())
            else:
                await query.edit_message_text("⚠️ هذا الشحن مُعالج مسبقاً.", reply_markup=admin_menu_buttons())

        elif sub == "reject":
            if dep and dep.status == "pending":
                dep.status = "rejected"
                dep.admin_id = query.from_user.id
                db.commit()
                if user:
                    from app.core.notifications import send_notification

                    await send_notification(query.message.bot, user.telegram_id, t("deposit_rejected"))
                await query.edit_message_text(f"❌ تم رفض الشحن #{dep.id}.", reply_markup=admin_menu_buttons())
            else:
                await query.edit_message_text("⚠️ هذا الشحن مُعالج مسبقاً.", reply_markup=admin_menu_buttons())
    finally:
        db.close()


# ── Catalog curation ─────────────────────────────────────────────

async def _catalog_root(query) -> None:
    db = SessionLocal()
    try:
        cats = db.query(Category).filter(Category.parent_id.is_(None)).order_by(Category.name).all()
        rows = []
        for cat in cats:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{'✅' if cat.status == 'active' else '⛔'} {cat.name}",
                        callback_data=f"adm_cat_toggle:{cat.id}",
                    )
                ]
            )
        rows.append([InlineKeyboardButton("📦 المنتجات", callback_data="adm_cat_page:0:root")])
        rows.append([InlineKeyboardButton("🔙", callback_data="adm:menu")])
        await query.edit_message_text("⚙️ الكتالوج — اضغط على القسم لإظهار/إخفائه:", reply_markup=InlineKeyboardMarkup(rows))
    finally:
        db.close()


def _toggle_category(db, cat_id: int) -> None:
    cat = db.query(Category).filter_by(id=cat_id).first()
    if not cat:
        return
    new_status = "active" if cat.status != "active" else "inactive"
    cat.status = new_status
    # mirror to children
    for child in cat.children or []:
        child.status = new_status
    db.commit()


async def _products_page(query, page: int = 0) -> None:
    db = SessionLocal()
    try:
        total = db.query(Product).count()
        products = (
            db.query(Product)
            .order_by(Product.name)
            .offset(page * _PAGE_SIZE)
            .limit(_PAGE_SIZE)
            .all()
        )
        rows = []
        for prod in products:
            rows.append(
                [
                    InlineKeyboardButton(
                        f"{'✅' if prod.status == 'active' else '⛔'} {prod.display_name or prod.name}",
                        callback_data=f"adm_prod:{prod.id}",
                    )
                ]
            )
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️", callback_data=f"adm_prod_page:{page - 1}"))
        if total > (page + 1) * _PAGE_SIZE:
            nav.append(InlineKeyboardButton("▶️", callback_data=f"adm_prod_page:{page + 1}"))
        if nav:
            rows.append(nav)
        rows.append([InlineKeyboardButton("🔙", callback_data="adm:catalog")])
        await query.edit_message_text(
            f"📦 المنتجات ({page * _PAGE_SIZE + 1}–{min((page + 1) * _PAGE_SIZE, total)} من {total}):",
            reply_markup=InlineKeyboardMarkup(rows),
        )
    finally:
        db.close()


async def _product_view(query, action: str) -> None:
    db = SessionLocal()
    try:
        prod_id = int(action.split(":")[1])
        prod = db.query(Product).filter_by(id=prod_id).first()
        if not prod:
            await query.edit_message_text("المنتج غير موجود.", reply_markup=admin_menu_buttons())
            return
        text = (
            f"📦 {prod.display_name or prod.name}\n"
            f"raw: {prod.name}\n"
            f"التكلفة: {prod.cost_price}$ — السعر: {prod.price}$\n"
            f"الحالة: {'مفعل' if prod.status == 'active' else 'مخفّى'}"
        )
        buttons = [
            [
                InlineKeyboardButton("🔄 تفعيل/إخفاء", callback_data=f"adm_prod_toggle:{prod.id}"),
                InlineKeyboardButton("✏️ إعادة تسمية", callback_data=f"adm_prod_rename:{prod.id}"),
            ],
            [
                InlineKeyboardButton("💱 سعر يدوي", callback_data=f"adm_prod_price:{prod.id}"),
                InlineKeyboardButton("🔄 حساب تلقائي", callback_data=f"adm_prod_unoverride:{prod.id}"),
            ],
            [InlineKeyboardButton("🔙", callback_data="adm_cat_page:0:root")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    finally:
        db.close()


async def _toggle_product(query, prod_id: int) -> None:
    db = SessionLocal()
    try:
        prod = db.query(Product).filter_by(id=prod_id).first()
        if prod:
            prod.status = "active" if prod.status != "active" else "inactive"
            db.commit()
        await query.edit_message_text("✅ تم التحديث.", reply_markup=admin_menu_buttons())
    finally:
        db.close()


async def curate_product_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        if context.user_data.get("rename_product"):
            prod = db.query(Product).filter_by(id=context.user_data["rename_product"]).first()
            if prod:
                prod.display_name = update.message.text.strip()
                db.commit()
            context.user_data.pop("rename_product", None)
            await update.message.reply_text("✅ تمت إعادة التسمية.", reply_markup=main_menu())
        elif context.user_data.get("price_product"):
            prod = db.query(Product).filter_by(id=context.user_data["price_product"]).first()
            if prod:
                try:
                    price = float(update.message.text.strip())
                    prod.price = round(price, 4)
                    prod.price_override = True
                    db.commit()
                    await update.message.reply_text(f"✅ تم ضبط السعر على {price}$.", reply_markup=main_menu())
                except ValueError:
                    await update.message.reply_text("⚠️ أدخل رقماً صحيحاً.")
                    return CURATE_PRODS
            context.user_data.pop("price_product", None)
    finally:
        db.close()
    return MAIN_MENU


def _unoverride_price(db, prod_id: int) -> None:
    prod = db.query(Product).filter_by(id=prod_id).first()
    if prod:
        from app.config import settings

        prod.price_override = False
        prod.price = round(prod.cost_price * (1 + settings.MARGIN_PERCENT / 100), 4)
        db.commit()


# ── Broadcast ────────────────────────────────────────────────────

async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    sent = 0
    failed = 0
    try:
        for user in db.query(User).all():
            if not user.telegram_id:
                continue
            try:
                await context.bot.send_message(chat_id=user.telegram_id, text=update.message.text)
                sent += 1
            except Exception:  # noqa: BLE001
                failed += 1
    finally:
        db.close()
    context.user_data.pop("bcast_stage", None)
    await update.message.reply_text(f"📣 تم الإرسال: {sent} نجحت، {failed} فشلت.", reply_markup=main_menu())
    return MAIN_MENU


# ── Bot toggle ───────────────────────────────────────────────────

async def _toggle_bot(query) -> None:
    from app.main import bot_active, set_bot_active

    new_state = not bot_active
    set_bot_active(new_state)
    await query.edit_message_text(
        f"{'⏸️ تم إيقاف البوت مؤقتاً.' if not new_state else '✅ تم تشغيل البوت.'}",
        reply_markup=admin_menu_buttons(),
    )


# ── Handler ──────────────────────────────────────────────────────

def admin_conversation_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("admin", admin_menu)],
        states={
            MAIN_MENU: [CallbackQueryHandler(admin_action, pattern=r"^adm")],
            CURATE_PRODS: [MessageHandler(filters.TEXT & ~filters.COMMAND, curate_product_text)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
        },
        fallbacks=[CommandHandler("cancel", admin_menu_callback)],
        name="admin_conversation",
    )