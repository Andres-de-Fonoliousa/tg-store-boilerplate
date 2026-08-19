from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def category_buttons(categories: list, depth: int = 0) -> InlineKeyboardMarkup:
    rows = []
    for cat in categories:
        rows.append([InlineKeyboardButton(cat.name, callback_data=f"cat:{cat.id}:{depth}")])
    if depth > 0:
        rows.append([InlineKeyboardButton("🔙", callback_data=f"cat:up:{depth}")])
    return InlineKeyboardMarkup(rows)


def product_buttons(products: list) -> InlineKeyboardMarkup:
    rows = []
    for prod in products:
        rows.append([InlineKeyboardButton(f"🛒 {prod.name}", callback_data=f"buy:{prod.id}")])
    rows.append([InlineKeyboardButton("🔙", callback_data="cat:up:0")])
    return InlineKeyboardMarkup(rows)


def buy_confirm_buttons() -> InlineKeyboardMarkup:
    from app.i18n import t

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("order_confirm"), callback_data="order:confirm"),
                InlineKeyboardButton(t("cancel"), callback_data="order:cancel"),
            ]
        ]
    )


def deposit_method_buttons(methods: list[dict]) -> InlineKeyboardMarkup:
    from app.i18n import t

    rows = []
    for idx, method in enumerate(methods):
        rows.append([InlineKeyboardButton(method.get("name"), callback_data=f"dep:{idx}")])
    rows.append([InlineKeyboardButton(t("cancel"), callback_data="dep:cancel")])
    return InlineKeyboardMarkup(rows)


def admin_menu_buttons() -> InlineKeyboardMarkup:
    from app.i18n import t

    rows = [
        [
            InlineKeyboardButton("📦 طلبات", callback_data="adm:orders"),
            InlineKeyboardButton("💳 شحنات", callback_data="adm:deposits"),
        ],
        [
            InlineKeyboardButton("📊 إحصائيات", callback_data="adm:stats"),
            InlineKeyboardButton("🔄 مزامنة الكتالوج", callback_data="adm:sync"),
        ],
        [
            InlineKeyboardButton("⚙️ كتالوج", callback_data="adm:catalog"),
            InlineKeyboardButton("📣 بث", callback_data="adm:broadcast"),
        ],
        [InlineKeyboardButton("⏯️ تشغيل/إيقاف", callback_data="adm:toggle_bot")],
    ]
    return InlineKeyboardMarkup(rows)