from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler


async def exit_to_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """End any conversation state and return to the catalog."""
    from app.i18n import t
    from app.keyboards.reply import main_menu

    await update.message.reply_text(t("catalog_title"), reply_markup=main_menu())
    return ConversationHandler.END


async def exit_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from app.i18n import t
    from app.keyboards.reply import main_menu

    await update.message.reply_text(t("welcome"), reply_markup=main_menu())
    return ConversationHandler.END