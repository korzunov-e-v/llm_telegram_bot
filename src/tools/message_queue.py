import datetime
import traceback
from collections import defaultdict

import telegramify_markdown
from langchain_text_splitters import MarkdownTextSplitter
from telegram import Bot
from telegram.constants import ParseMode
from telegram.error import BadRequest

from src.tools.log import get_logger, log_decorator

logger = get_logger(__name__)


def get_queue_key(user_id: int, topic_id: int) -> str:
    if topic_id is None:
        topic_id = 1
    """
    Составной ключ для словаря очереди сообщений.

    :param user_id: id пользователя в tg
    :param topic_id: id топика/темы в чате в tg
    :return: строка `f"user_{user_id}+topic_{topic_id}"`
    """
    return f"user_{user_id}+topic_{topic_id}"


messages_queue: dict[str, list[tuple[str, datetime.datetime]]] = defaultdict(list)
"""Очередь сообщений по пользователю и топику."""


# {f"user_{user_id}+topic_{topic_id}": [("message_text", datetime.now), ("continue_message_text", datetime.now)]}

@log_decorator
async def send_reply_as_md(update, llm_resp_text: str, parse_mode: ParseMode = ParseMode.MARKDOWN, msg_for_delete=None):
    try:
        sections = MarkdownTextSplitter(chunk_overlap=0, keep_separator="end").split_text(llm_resp_text)
        for i, section in enumerate(sections):
            try:
                if parse_mode == ParseMode.MARKDOWN_V2:
                    section = telegramify_markdown.markdownify(section)
                await update.message.reply_text(section, parse_mode=parse_mode)
            except BadRequest:
                logger.warning(f"can't send {i}/{len(sections)} message as md: {sections=}")
                await update.message.reply_text(section)
    except Exception:
        await update.message.reply_text("Произошла ошибка, попробуйте снова.", parse_mode=ParseMode.MARKDOWN)
        logger.error(traceback.format_exc())
    finally:
        if msg_for_delete:
            await msg_for_delete.delete()


async def send_msg_as_md(bot: Bot, chat_id: int, msg_text: str, parse_mode: ParseMode = ParseMode.MARKDOWN):
    try:
        sections = MarkdownTextSplitter(chunk_overlap=0, keep_separator="end").split_text(msg_text)
        for i, section in enumerate(sections):
            try:
                if parse_mode == ParseMode.MARKDOWN_V2:
                    section = telegramify_markdown.markdownify(section)
                await bot.send_message(chat_id, section, parse_mode=parse_mode)
            except BadRequest:
                logger.warning(f"can't send {i}/{len(sections)} message as md: {sections=}")
                await bot.send_message(chat_id, section)
    except Exception:
        await bot.send_message(chat_id, "Произошла ошибка, попробуйте снова.", parse_mode=ParseMode.MARKDOWN)
        logger.error(traceback.format_exc())
