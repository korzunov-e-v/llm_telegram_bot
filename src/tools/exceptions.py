from telegram import Update

from src.models import PTBContext
from src.tools.log import get_logger

logger = get_logger(__name__)


async def error_handler(update: object, context: PTBContext) -> None:
    """Хэндлер ошибок. Отправляет сообщение об ошибке пользователю и разработчику."""

    update: Update

    await update.message.reply_text(
        "Извините, что-то пошло не так. "
        "Если ошибка повторяется, попробуйте сбросить контекст и выбрать модель заново."
    )
    raise context.error

    # todo: move features to tracekit
    # logger.error("Exception while handling an update:", exc_info=context.error)
    # tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    # tb_string = "".join(tb_list)
    # update_str = update.to_dict() if isinstance(update, Update) else str(update)
    # message = (
    #     "An exception was raised while handling an update\n"
    #     "```json\n"
    #     f"{json.dumps(update_str, indent=2, ensure_ascii=False)}\n"
    #     "```\n\n"
    #     "```text\n"
    #     f"context.chat_data = {str(context.chat_data)}\n"
    #     "```\n\n"
    #     "```text\n"
    #     f"context.user_data = {str(context.user_data)}\n"
    #     "```\n\n"
    #     "```text\n"
    #     f"{tb_string}\n"
    #     "```"
    # )
    # await send_msg_as_md(
    #     bot=context.bot, chat_id=settings.admin_chat_id, msg_text=message, parse_mode=ParseMode.MARKDOWN_V2
    # )
