import asyncio
from collections import defaultdict
from contextlib import suppress
from typing import Optional

from anthropic.types import ModelParam
from langchain_text_splitters import MarkdownTextSplitter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message, Chat, ChatMember, ChatMemberUpdated
from telegram.error import BadRequest
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler, ChatMemberHandler

from src.app.service import message_processing_facade as service, chat_manager
from src.config import settings
from src.tools.custom_logging import get_logger
from src.tools.filters import TopicFilter, InviteLinkFilter

state = {}
messages_queue: dict[str, list[str]] = defaultdict(list)
logger = get_logger(__name__)
topic_filter = TopicFilter()
invite_link_filter = InviteLinkFilter()


def __get_queue_key(user_id: int, topic_id: int) -> str:
    return f"{user_id}+{topic_id}"


def __get_state_key(chat_id: int, topic_id: int) -> str:
    return f"{chat_id}+{topic_id}"


async def invite_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await service.process_invite(update, context)


async def delay_send(_context: ContextTypes.DEFAULT_TYPE):
    msg: Message = _context.job.data["msg"]
    update = _context.job.data["update"]
    chat_id = _context.job.chat_id
    user_id = _context.job.user_id
    topic_id = _context.job.data["topic_id"]
    key = __get_queue_key(user_id, topic_id)
    try:
        await asyncio.sleep(2)
        if not messages_queue[key]:
            return None
        message = "\n".join(messages_queue[key])
        del messages_queue[key]
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


async def hello_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'Hello {update.effective_chat.first_name}')


async def button_change_model(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = query.message.message_thread_id
    else:
        topic_id = None
    await query.answer()
    model = query.data.split("+")[1]
    service.chat_manager.change_model(chat_id, topic_id, model)
    await query.edit_message_text(text=f"Выбрана модель: {model}")


async def button_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.edit_message_text(text=f"Отменено.")


async def models_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    models = ModelParam.__dict__["__args__"][1].__dict__["__args__"]
    keyboard_models = [[InlineKeyboardButton(model, callback_data=f"change_model+{model}")] for model in models]
    keyboard = keyboard_models + [[InlineKeyboardButton("Отмена", callback_data="cancel+0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


async def clear_context_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    user_id = update.effective_user.id
    message = await service.get_topic_info_message(chat_id, topic_id, user_id, _context.bot, with_prompt=False)
    message += "\nКонтекст очищен."
    service.chat_manager.clear_context(chat_id, topic_id)
    await update.message.reply_text(message)


async def stop_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_id = update.effective_user.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    res = service.chat_manager.remove_allowed_topics(chat_id, topic_id, user_id)
    if res:
        return await update.message.reply_text("Покинул топик. Чтобы добавить снова, отправьте ссылку-приглашение боту в лc.\n"
                                               "Или отправьте /start в этот чат.")
    await update.message.reply_text("Не ожидалось этой команды.")


async def start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    chat_id = update.message.chat_id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = 1
    service.chat_manager.get_or_create_user(user_id, username, full_name)
    allowed_topics = service.chat_manager.get_allowed_topics(chat_id, user_id)
    if topic_id in allowed_topics:
        await update.message.reply_text("Бот уже тут.")
    else:
        service.chat_manager.add_allowed_topic(chat_id, topic_id, user_id)
        await update.message.reply_text("Бот добавлен в чат.")


async def ensure_user(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    # chat_id = update.effective_chat.id
    # topic_id = update.message.message_thread_id
    user_id = update.effective_user.id
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    service.chat_manager.get_or_create_user(user_id, username, full_name)


async def text_message_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    user_id = update.effective_user.id
    msg_text = update.message.text

    msg = await update.message.reply_text("Пишет...")
    state_key = __get_state_key(chat_id, topic_id)
    queue_key = __get_queue_key(user_id, topic_id)

    if state.get(state_key) == "prompt":
        service.chat_manager.set_system_prompt(msg_text, chat_id, topic_id)
        del state[state_key]
        return await msg.edit_text("Промпт установлен.")
    if state.get(state_key) == "temperature":
        service.chat_manager.set_temperature(msg_text, chat_id, topic_id)
        del state[state_key]
        return await msg.edit_text("Температура установлена.")
    else:
        messages_queue[queue_key].append(msg_text)
        _context.job_queue.run_once(delay_send, 0, user_id=user_id, chat_id=chat_id, data={"update": update, "msg": msg, "topic_id": topic_id})


async def topic_info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    user_id = update.effective_user.id
    message = await service.get_topic_info_message(chat_id, topic_id, user_id, _context.bot)
    await update.message.reply_text(message, parse_mode="Markdown")


async def user_info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = await service.get_user_info_message(user_id, _context.bot)
    await update.message.reply_text(message)


async def user_infos_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = service.chat_manager.get_user_info(user_id)
    if user["is_admin"]:
        message = await service.get_users(_context.bot)
        await update.message.reply_text(message)


async def i_am_admin_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        token = _context.args[0]
        if token == settings.admin_token:
            user = service.chat_manager.get_user_info(user_id)
            user["is_admin"] = True
            service.chat_manager.update_user(user)
            await update.effective_message.reply_text("Token accepted.")
        else:
            await update.effective_message.reply_text("No.")
    except:
        await update.effective_message.reply_text("No.")


async def prompt_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    state[__get_state_key(chat_id, topic_id)] = "prompt"
    topic_settings = service.chat_manager.get_topic_settings(chat_id, topic_id)
    current_prompt = topic_settings["system_prompt"]
    await update.message.reply_text(
        'Отправьте новый промпт, /cancel для отмены или /empty для сброса промпта.\n'
        f'Текущий промпт: {chat_manager.format_system_prompt(current_prompt)}',
        parse_mode="Markdown",
    )


async def temperature_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    state[__get_state_key(chat_id, topic_id)] = "temperature"
    topic_settings = service.chat_manager.get_topic_settings(chat_id, topic_id)
    await update.message.reply_text(
        'Отправьте значение температуры (креативность/непредсказуемость модели), /cancel для отмены или /empty для сброса.\n'
        f'Текущая температура: {topic_settings["temperature"]}\n'
        f'Температура по-умолчанию: {settings.default_temperature}'
    )


async def cancel_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    with suppress(KeyError):
        del state[__get_state_key(chat_id, topic_id)]
        return await update.message.reply_text("Отменено.")
    await update.message.reply_text("Команды не ожидалось.")


async def empty_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.message.message_thread_id
    else:
        topic_id = None
    if state.get(__get_state_key(chat_id, topic_id)) == "prompt":
        del state[__get_state_key(chat_id, topic_id)]
        service.chat_manager.clear_system_prompt(chat_id, topic_id)
        return await update.message.reply_text("Промпт сброшен.")
    if state.get(__get_state_key(chat_id, topic_id)) == "temperature":
        del state[__get_state_key(chat_id, topic_id)]
        service.chat_manager.reset_temperature(chat_id, topic_id)
        return await update.message.reply_text("Настройка температуры сброшена.")
    await update.message.reply_text("Команды не ожидалось.")


def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[tuple[bool, bool]]:
    """Takes a ChatMemberUpdated instance and extracts whether the 'old_chat_member' was a member
    of the chat and whether the 'new_chat_member' is a member of the chat. Returns None, if
    the status didn't change.
    """
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = old_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    is_member = new_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

    return was_member, is_member


async def track_chats(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tracks the chats the bot is in."""
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result

    # Let's check who is responsible for the change
    full_name = update.effective_user.full_name
    username = update.effective_user.username

    chat_id = update.effective_chat.id
    message = update.message
    if message:
        topic_id = message.message_thread_id
    else:
        topic_id = None
    user_id = update.effective_user.id

    # Handle chat types differently:
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        if not was_member and is_member:
            # This may not be really needed in practice because most clients will automatically
            # send a /start command after the user unblocks the bot, and start_private_chat()
            # will add the user to "user_ids".
            # We're including this here for the sake of the example.
            logger.info("%s unblocked the bot", full_name)
            # _context.bot_data.setdefault("user_ids", set()).add(chat.id)
            service.new_private_chat(user_id, username, full_name)
        elif was_member and not is_member:
            logger.info("%s blocked the bot", full_name)
            _context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", full_name, chat.title)
            # _context.bot_data.setdefault("group_ids", set()).add(chat.id)
            service.new_group(user_id, full_name, chat_id, topic_id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", full_name, chat.title)
            _context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    elif not was_member and is_member:
        logger.info("%s added the bot to the channel %s", full_name, chat.title)
        _context.bot_data.setdefault("channel_ids", set()).add(chat.id)
    elif was_member and not is_member:
        logger.info("%s removed the bot from the channel %s", full_name, chat.title)
        _context.bot_data.setdefault("channel_ids", set()).discard(chat.id)


async def messages_not_allowed(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Бот не добавлен в чат.\n'
                                    'Чтобы добавить, отправьте ссылку приглашение боту в лс.\n'
                                    'Или отправьте /start. Чтобы остановить бота в чате, отправьте /stop')


def build_app(bot_token: str):
    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters=filters.ALL, callback=ensure_user), group=100)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters=~topic_filter & filters.COMMAND, callback=messages_not_allowed))
    app.add_handler(CommandHandler("hello", hello_command))
    app.add_handler(CommandHandler("clear", clear_context_command))
    app.add_handler(CommandHandler("user", user_info_command))
    app.add_handler(CommandHandler("info", topic_info_command))
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("prompt", prompt_change_command))
    app.add_handler(CommandHandler("temperature", temperature_change_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("empty", empty_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin_users", user_infos_command))
    app.add_handler(CommandHandler("i_am_admin", i_am_admin_command))
    app.add_handler(CallbackQueryHandler(button_change_model, pattern="change_model"))
    app.add_handler(CallbackQueryHandler(button_cancel, pattern="cancel"))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & invite_link_filter & filters.ChatType.PRIVATE, callback=invite_link_handler))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & topic_filter, callback=text_message_handler))
    return app
