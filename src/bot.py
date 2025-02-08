from contextlib import suppress

from anthropic.types import ModelParam
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Chat
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ChatMemberHandler,
    Application,
)

from src.app.service import message_processing_facade as service, chat_manager
from src.config import settings
from src.filters import TopicFilter, InviteLinkFilter
from src.tools.chat_state import get_state_key, state, ChatState
from src.tools.log import get_logger
from src.tools.message_queue import get_queue_key, messages_queue, delay_send
from src.tools.update_getters import get_ids, extract_status_change

logger = get_logger(__name__)


# COMMANDS
async def start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    service.chat_manager.get_or_create_user(user_id, username, full_name)
    allowed_topics = service.chat_manager.get_allowed_topics(chat_id, user_id)
    if topic_id in allowed_topics:
        await update.message.reply_text("Бот уже тут.")
    else:
        service.chat_manager.add_allowed_topic(chat_id, topic_id, user_id)
        await update.message.reply_text("Бот добавлен в чат.")


async def stop_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    res = service.chat_manager.remove_allowed_topics(chat_id, topic_id, user_id)
    if not res:
        return await update.message.reply_text("Не ожидалось этой команды.")

    await update.message.reply_text(
        "Покинул топик. Чтобы добавить снова, отправьте ссылку-приглашение боту в лc.\n"
        "Или отправьте /start в этот чат."
    )


async def hello_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f'Hello {update.effective_chat.first_name}')


# TOPIC SETTINGS
async def show_models_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    models = ModelParam.__dict__["__args__"][1].__dict__["__args__"]
    keyboard_models = [[InlineKeyboardButton(model, callback_data=f"change_model+{model}")] for model in models]
    keyboard = keyboard_models + [[InlineKeyboardButton("Отмена", callback_data="cancel+0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


async def button_change_model(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    query = update.callback_query
    await query.answer()
    model = query.data.split("+")[1]
    service.chat_manager.change_model(chat_id, topic_id, model)
    await query.edit_message_text(text=f"Выбрана модель: {model}")


async def system_prompt_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    state[get_state_key(chat_id, topic_id)] = ChatState.PROMPT
    topic_settings = service.chat_manager.get_topic_settings(chat_id, topic_id)
    current_prompt = topic_settings["system_prompt"]
    await update.message.reply_text(
        'Отправьте новый промпт, /cancel для отмены или /empty для сброса промпта.\n'
        f'Текущий промпт: {chat_manager.format_system_prompt(current_prompt)}',
        parse_mode="Markdown",
    )


async def temperature_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    state[get_state_key(chat_id, topic_id)] = ChatState.TEMPERATURE
    topic_settings = service.chat_manager.get_topic_settings(chat_id, topic_id)
    await update.message.reply_text(
        'Отправьте значение температуры (креативность/непредсказуемость модели), /cancel для отмены или /empty для сброса.\n'
        f'Текущая температура: {topic_settings["temperature"]}\n'
        f'Температура по-умолчанию: {settings.default_temperature}'
    )


async def clear_context_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    message = await service.get_topic_info_message(chat_id, topic_id, user_id, _context.bot, with_prompt=False)
    message += "\nКонтекст очищен."
    service.chat_manager.clear_context(chat_id, topic_id)
    await update.message.reply_text(message)


# COMMON
async def cancel_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    with suppress(KeyError):
        del state[get_state_key(chat_id, topic_id)]
        return await update.message.reply_text("Отменено.")
    await update.message.reply_text("Команды не ожидалось.")


async def empty_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    if state.get(get_state_key(chat_id, topic_id)) == ChatState.PROMPT:
        del state[get_state_key(chat_id, topic_id)]
        service.chat_manager.clear_system_prompt(chat_id, topic_id)
        return await update.message.reply_text("Промпт сброшен.")
    if state.get(get_state_key(chat_id, topic_id)) == ChatState.TEMPERATURE:
        del state[get_state_key(chat_id, topic_id)]
        service.chat_manager.reset_temperature(chat_id, topic_id)
        return await update.message.reply_text("Настройка температуры сброшена.")
    await update.message.reply_text("Команды не ожидалось.")


async def button_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.edit_message_text(text=f"Отменено.")


# INFO
async def user_info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    message = await service.get_user_info_message(user_id, _context.bot)
    await update.message.reply_text(message)


async def topic_info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    message = await service.get_topic_info_message(chat_id, topic_id, user_id, _context.bot)
    await update.message.reply_text(message, parse_mode="Markdown")


# ADMIN
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


async def admin_users_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = service.chat_manager.get_user_info(user_id)
    if user["is_admin"]:
        message = await service.get_users(_context.bot)
        await update.message.reply_text(message)


# TEXT
async def text_message_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)
    state_key = get_state_key(chat_id, topic_id)
    queue_key = get_queue_key(user_id, topic_id)

    msg = await update.message.reply_text("Пишет...")

    if state.get(state_key) == ChatState.PROMPT:
        service.chat_manager.set_system_prompt(msg_text, chat_id, topic_id)
        del state[state_key]
        return await msg.edit_text("Промпт установлен.")
    if state.get(state_key) == ChatState.TEMPERATURE:
        service.chat_manager.set_temperature(msg_text, chat_id, topic_id)
        del state[state_key]
        return await msg.edit_text("Температура установлена.")
    else:
        messages_queue[queue_key].append(msg_text)
        _context.job_queue.run_once(
            callback=delay_send,
            when=0,
            user_id=user_id,
            chat_id=chat_id,
            data={"update": update, "msg": msg, "topic_id": topic_id}
        )


# CHAT MEMBER HANDLER
async def track_chats_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для обновлений участников чата. Создаёт пользователей/чаты/топики в базе.
    """
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result

    # check who is responsible for the change
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
            # _context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", full_name, chat.title)
            # _context.bot_data.setdefault("group_ids", set()).add(chat.id)
            service.new_group(user_id, full_name, chat_id, topic_id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", full_name, chat.title)
            # _context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    # elif not was_member and is_member:
    #     logger.info("%s added the bot to the channel %s", full_name, chat.title)
    #     _context.bot_data.setdefault("channel_ids", set()).add(chat.id)
    # elif was_member and not is_member:
    #     logger.info("%s removed the bot from the channel %s", full_name, chat.title)
    #     _context.bot_data.setdefault("channel_ids", set()).discard(chat.id)


async def ensure_user(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    При любом сообщении проверяет, есть ли пользователь в базе. Создаёт пользователя, чат и топик для ЛС.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = get_ids(update)

    service.chat_manager.get_or_create_user(user_id, username, full_name)


async def invite_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для сообщений с ссылками-приглашениями в чат.
    Добавляет чат в список разрешённых для бота. То же самое что и `/start`.
    """
    await service.process_invite(update, context)


async def messages_not_allowed_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Бот не добавлен в чат.\n'
        'Чтобы добавить, отправьте ссылку приглашение боту в лс.\n'
        'Или отправьте /start. Чтобы остановить бота в чате, отправьте /stop'
    )


def build_app(bot_token: str) -> Application:
    """
    Регистрирует хэндлеры и возвращает инстанс бота.

    :param bot_token: tg токен бота, см BotFather
    :return: Инстанс приложения бота
    """
    topic_filter = TopicFilter()
    invite_link_filter = InviteLinkFilter()

    app = ApplicationBuilder().token(bot_token).build()
    app.add_handler(ChatMemberHandler(track_chats_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters=filters.ALL, callback=ensure_user), group=100)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters=~topic_filter & filters.COMMAND, callback=messages_not_allowed_handler))
    app.add_handler(CommandHandler("hello", hello_command))
    app.add_handler(CommandHandler("clear", clear_context_command))
    app.add_handler(CommandHandler("user", user_info_command))
    app.add_handler(CommandHandler("info", topic_info_command))
    app.add_handler(CommandHandler("models", show_models_command))
    app.add_handler(CommandHandler("prompt", system_prompt_change_command))
    app.add_handler(CommandHandler("temperature", temperature_change_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("empty", empty_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin_users", admin_users_command))
    app.add_handler(CommandHandler("i_am_admin", i_am_admin_command))
    app.add_handler(CallbackQueryHandler(button_change_model, pattern="change_model"))
    app.add_handler(CallbackQueryHandler(button_cancel, pattern="cancel"))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & invite_link_filter & filters.ChatType.PRIVATE,
                                   callback=invite_link_handler))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & topic_filter, callback=text_message_handler))
    return app
