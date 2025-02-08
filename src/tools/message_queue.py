import asyncio
from collections import defaultdict

from langchain_text_splitters import MarkdownTextSplitter
from telegram import Message
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.app.service import message_processing_facade as service
from src.tools.log import get_logger, log_decorator

logger = get_logger(__name__)


def get_queue_key(user_id: int, topic_id: int) -> str:
    """
    Составной ключ для словаря очереди сообщений.

    :param user_id: id пользователя в tg
    :param topic_id: id топика/темы в чате в tg
    :return: строка `f"{user_id}+{topic_id}"`
    """
    return f"{user_id}+{topic_id}"


messages_queue: dict[str, list[str]] = defaultdict(list)  # {f"{user_id}+{topic_id}": ["message_text", "continue_message_text"]}
"""Очередь сообщений по пользователю и топику."""


async def delay_send(_context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Отложенная отправка сообщений. После первого сообщения в чате/топике ожидает 2 секунды новых сообщений в этот же чат.
    Собирает сообщения в одно и отправляет в ллм.

    Клиент телеграм разделяет большие сообщения при отправке на меньшие, из-за этого
    в ллм отправляется обрезанная версия, а вслед вторая часть.


    Examples:

        .. code-block:: python

            _context.job_queue.run_once(
                callback=_delay_send,
                when=0,
                user_id=user_id,
                chat_id=chat_id,
                data={"update": update, "msg": msg, "topic_id": topic_id}
            )

        Ожидаемые данные:

        .. code-block::

            _context.job.user_id: int - id пользователя
            _context.job.chat_id: int - id чата
            _context.job.data["topic_id"]: int - id топика/темы чата
            _context.job.data["msg"]: str - сообщение пользователя
            _context.job.data["update"]: telegram.Update - объект обновления от tg с сообщением пользователя
    """
    user_id = _context.job.user_id
    topic_id = _context.job.data["topic_id"]
    key = get_queue_key(user_id, topic_id)
    await asyncio.sleep(2)
    if not messages_queue[key]:
        return
    message = "\n".join(messages_queue[key])
    del messages_queue[key]
    await send_msg_to_llm(_context, message)


@log_decorator
async def send_msg_to_llm(_context: ContextTypes.DEFAULT_TYPE, message: str):
    msg: Message = _context.job.data["msg"]
    update = _context.job.data["update"]
    chat_id = _context.job.chat_id
    user_id = _context.job.user_id
    topic_id = _context.job.data["topic_id"]
    try:
        llm_resp_text = service.process_message(message, user_id, chat_id, topic_id)
        sections = MarkdownTextSplitter(chunk_overlap=0, keep_separator="end").split_text(llm_resp_text)
        for i, section in enumerate(sections):
            try:
                await update.message.reply_text(section, parse_mode="Markdown")
            except BadRequest:
                logger.warning(f"can't send {i}/{len(sections)} message as md: {sections=}")
                await update.message.reply_text(section)
    except:
        await update.message.reply_text("Произошла ошибка, попробуйте снова.", parse_mode="Markdown")
    finally:
        await msg.delete()
