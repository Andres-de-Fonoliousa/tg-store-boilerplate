import logging

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


async def send_notification(bot: Bot, chat_id: int, text: str) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        return True
    except TelegramError as exc:
        logger.warning("send_message to %s failed: %s", chat_id, exc)
        return False