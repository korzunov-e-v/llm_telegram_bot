import html
import json
import traceback

from telegram import Update
from telegram.constants import ParseMode

from src.config import settings
from src.models import PTBContext
from src.tools.log import get_logger

logger = get_logger(__name__)


async def error_handler(update: object, context: PTBContext) -> None:
    """Хэндлер ошибок. Отправляет сообщение об ошибке пользователю и разработчику."""

    update: Update

    await update.message.reply_text(
        "Извините, что-то пошло не так. "
        "Если повторяется, попробуйте сбросить контекст и выбрать модель заново."
    )

    logger.error("Exception while handling an update:", exc_info=context.error)
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    await context.bot.send_message(
        chat_id=settings.admin_chat_id, text=message, parse_mode=ParseMode.HTML
    )
