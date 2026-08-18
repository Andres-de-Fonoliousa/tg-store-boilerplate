from telegram import Update
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from app.catalog.normalize import loads, pretty_qty
from app.core.database import SessionLocal
from app.core.models import Category, ExchangeRate, Order, Product, User
from app.i18n import t
from app.keyboards.inline import category_buttons, product_buttons
from app.keyboards.reply import main_menu


def _get_or_create_user(db, telegram_id: int, from_user) -> User:
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    if user is None:
        user = User(
            telegram_id=telegram_id,
            first_name=from_user.first_name,
            last_name=from_user.last_name,
            username=from_user.username,
        )
        db.add(user)
        db.commit()
    return user


def _rate(db) -> float:
    rate = db.query(ExchangeRate).order_by(ExchangeRate.id.desc()).first()
    return rate.rate if rate else 13000.0


def _syp(usd_price: float, db) -> int:
    return int(round(usd_price * _rate(db)))


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        _get_or_create_user(db, update.effective_user.id, update.effective_user)
    finally:
        db.close()
    await update.message.reply_text(t("welcome"), reply_markup=main_menu())


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        user = _get_or_create_user(db, update.effective_user.id, update.effective_user)
        await update.message.reply_text(t("balance_label", balance=f"{user.balance:,.0f}"))
    finally:
        db.close()


async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        user = _get_or_create_user(db, update.effective_user.id, update.effective_user)
        orders = db.query(Order).filter_by(user_id=user.id).count()
        lines = [
            t("balance_label", balance=f"{user.balance:,.0f}"),
            f"📦 الطلبات: {orders}",
        ]
        await update.message.reply_text("\n".join(lines))
    finally:
        db.close()


async def open_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db = SessionLocal()
    try:
        cats = (
            db.query(Category)
            .filter(Category.parent_id.is_(None), Category.status == "active")
            .order_by(Category.name)
            .all()
        )
        if cats:
            await update.message.reply_text(t("catalog_title"), reply_markup=category_buttons(cats))
        else:
            await update.message.reply_text(t("no_products"))
    finally:
        db.close()


async def catalog_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    data = query.data
    db = SessionLocal()
    try:
        if data.startswith("cat:up"):
            await query.answer()
            await query.edit_message_text(
                t("catalog_title"),
                reply_markup=category_buttons(
                    db.query(Category)
                    .filter(Category.parent_id.is_(None), Category.status == "active")
                    .order_by(Category.name)
                    .all()
                ),
            )
            return

        # cat:<id>:<depth>
        cat_id = int(data.split(":")[1])
        cat = db.query(Category).filter_by(id=cat_id, status="active").first()
        if not cat:
            await query.answer(t("no_products"), show_alert=True)
            return

        child_cats = (
            db.query(Category)
            .filter(Category.parent_id == cat.id, Category.status == "active")
            .order_by(Category.name)
            .all()
        )
        products = (
            db.query(Product)
            .filter(Product.category_id == cat.id, Product.status == "active")
            .order_by(Product.name)
            .all()
        )
        await query.answer()
        if child_cats:
            await query.edit_message_text(
                f"📁 {cat.name}",
                reply_markup=category_buttons(child_cats, depth=1),
            )
        elif products:
            await query.edit_message_text(
                f"📦 {cat.name}",
                reply_markup=product_buttons(products),
            )
        else:
            await query.edit_message_text(t("no_products"))
    finally:
        db.close()


async def handle_main_menu_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    if text == t("main_menu_catalog"):
        await open_catalog(update, context)
    elif text == t("main_menu_balance"):
        await show_balance(update, context)
    elif text == t("main_menu_deposit"):
        from app.conversations.deposit import start_deposit

        await start_deposit(update, context)
    else:
        await update.message.reply_text(t("unknown"))


start_handler = CommandHandler("start", start_handler)
profile_handler = CommandHandler("profile", show_profile)
catalog_msg_handler = MessageHandler(filters.Text([t("main_menu_catalog")]), open_catalog)
balance_msg_handler = MessageHandler(filters.Text([t("main_menu_balance")]), show_balance)
catalog_cb_handler = CallbackQueryHandler(catalog_callback, pattern=r"^cat:")