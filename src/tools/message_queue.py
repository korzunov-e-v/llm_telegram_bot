import asyncio
import traceback
from collections import defaultdict

import telegramify_markdown
from langchain_text_splitters import MarkdownTextSplitter
from telegram import Message
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src.app.service import message_processing_facade as service
from src.tools.log import get_logger, log_decorator

logger = get_logger(__name__)


def get_queue_key(user_id: int, topic_id: int) -> str:
    if topic_id is None:
        topic_id = 1
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
    if topic_id is None:
        topic_id = 1
    md_v2_mode = _context.job.data["md_v2_mode"]
    key = get_queue_key(user_id, topic_id)
    await asyncio.sleep(2)
    if not messages_queue[key]:
        return
    message = "\n".join(messages_queue[key])
    del messages_queue[key]
    chat_id = _context.job.chat_id
    user_id = _context.job.user_id
    topic_id = _context.job.data["topic_id"]
    llm_resp_text = await service.process_txt_message(message, user_id, chat_id, topic_id)
    update = _context.job.data["update"]
    msg: Message = _context.job.data["msg"]
    await send_msg_as_md(update, msg, llm_resp_text, md_v2_mode)


@log_decorator
async def send_msg_as_md(update, msg, llm_resp_text: str, md_v2_mode: bool = False):
    try:
        sections = MarkdownTextSplitter(chunk_overlap=0, keep_separator="end").split_text(llm_resp_text)
        for i, section in enumerate(sections):
            try:
                if md_v2_mode:
                    parse_mode = ParseMode.MARKDOWN_V2
                    section = telegramify_markdown.markdownify(section)
                else:
                    parse_mode = ParseMode.MARKDOWN
                await update.message.reply_text(section, parse_mode=parse_mode)
            except BadRequest:
                logger.warning(f"can't send {i}/{len(sections)} message as md: {sections=}")
                await update.message.reply_text(section)
    except Exception:
        await update.message.reply_text("Произошла ошибка, попробуйте снова.", parse_mode=ParseMode.MARKDOWN)
        logger.error(traceback.format_exc())
    finally:
        await msg.delete()
