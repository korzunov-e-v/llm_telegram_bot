import asyncio
from collections import defaultdict
from contextlib import suppress

from anthropic.types import ModelParam
from langchain_text_splitters import MarkdownTextSplitter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from src.app.service import message_processing_facade as service, chat_manager
from src.tools.custom_logging import get_logger
from src.tools.filters import TopicFilter, InviteLinkFilter

state = {}
messages_queue: dict[int, list[str]] = defaultdict(list)
logger = get_logger(__name__)


async def invite_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await service.process_invite(update, context)


async def delay_send(_context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(2)
    chat_id = _context.job.chat_id
    if not messages_queue[chat_id]:
        return None
    update = _context.job.data["update"]
    msg: Message = _context.job.data["msg"]
    message = "\n".join(messages_queue[chat_id])
    del messages_queue[chat_id]
    llm_resp_text = service.process_message(chat_id, message)
    sections = MarkdownTextSplitter(chunk_overlap=0, keep_separator="end").split_text(llm_resp_text)
    await msg.delete()
    for i, section in enumerate(sections):
        try:
            await update.message.reply_text(section, parse_mode="Markdown")
        except BadRequest as e:
            logger.warning(f"can't send {i}/{len(sections)} message as md: {sections=}")
            await update.message.reply_text(section)


async def hello_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'Hello {update.effective_chat.first_name}')


async def button_change_model(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id
    await query.answer()
    model = query.data.split("+")[1]
    chat_manager.change_model(chat_id, model)
    await query.edit_message_text(text=f"Выбрана модель: {model}")


async def button_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.edit_message_text(text=f"Отменено.")


async def models_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    models = ModelParam.__dict__["__args__"][1].__dict__["__args__"]
    keyboard_models = [[InlineKeyboardButton(a, callback_data=f"change_model+{a}")] for a in models]
    keyboard = keyboard_models + [[InlineKeyboardButton("Отмена", callback_data="cancel+0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


async def clear_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id
    message = service.get_user_info_message(chat_id, topic_id)
    message += "\nКонтекст очищен."
    chat_manager.clear_context(chat_id)
    await update.message.reply_text(message)


async def leave_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    thread_id = update.message.message_thread_id
    with suppress(KeyError):
        service.user_manager.remove_allowed_topics(chat_id, thread_id)
        await update.message.reply_text("Покинул топик. Чтобы добавить снова, отправьте ссылку-приглашение боту.")
    await update.message.reply_text("Не ожидалось этой команды.")


async def ensure_user(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_chat.username
    chat_manager.get_user(chat_id, username)


async def text_message_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_msg_text = update.message.text

    msg = await update.message.reply_text("Пишет...")

    if state.get(chat_id) == "prompt":
        chat_manager.set_system_prompt(chat_id, user_msg_text)
        del state[chat_id]
        return await msg.edit_text("Промпт установлен.")
    else:
        messages_queue[chat_id].append(user_msg_text)
        _context.job_queue.run_once(delay_send, 0, chat_id=chat_id, data={"update": update, "msg": msg})


# todo: chat info and user info
async def info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id
    message = service.get_user_info_message(chat_id, topic_id)
    await update.message.reply_text(message)


async def prompt_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    state[chat_id] = "prompt"
    await update.message.reply_text('Отправьте новый промпт, /cancel для отмены или /empty для сброса промпта.\n'
                                    f'Текущий промпт: "{chat_manager.get_system_prompt(chat_id)}"')


async def cancel_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with suppress(KeyError):
        del state[chat_id]
        return await update.message.reply_text("Отменено.")
    await update.message.reply_text("Команды не ожидалось.")


async def empty_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if state.get(chat_id) == "prompt":
        del state[chat_id]
        service.clear_system_prompt(chat_id)
        return await update.message.reply_text("Промпт сброшен.")
    await update.message.reply_text("Команды не ожидалось.")


def build_app(bot_token: str):
    topic_filter = TopicFilter()
    invite_link_filter = InviteLinkFilter()

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(MessageHandler(filters=filters.ALL, callback=ensure_user), group=100)
    app.add_handler(CommandHandler("hello", hello_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("info", info_command))
    app.add_handler(CommandHandler("prompt", prompt_change_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("empty", empty_command))
    app.add_handler(CommandHandler("leave", leave_command))
    app.add_handler(CallbackQueryHandler(button_change_model, pattern="change_model"))
    app.add_handler(CallbackQueryHandler(button_cancel, pattern="cancel"))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & invite_link_filter, callback=invite_link_handler))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & topic_filter, callback=text_message_handler))
    return app
