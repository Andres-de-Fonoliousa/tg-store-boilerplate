from telegram import KeyboardButton, ReplyKeyboardMarkup


def main_menu() -> ReplyKeyboardMarkup:
    from app.i18n import t

    buttons = [
        [KeyboardButton(t("main_menu_catalog"))],
        [KeyboardButton(t("main_menu_balance")), KeyboardButton(t("main_menu_deposit"))],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)


def back_button() -> ReplyKeyboardMarkup:
    from app.i18n import t

    return ReplyKeyboardMarkup([[KeyboardButton(t("back"))]], resize_keyboard=True)