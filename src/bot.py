from contextlib import suppress

from telegram import Update, Chat
from telegram.constants import ParseMode
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

from src.app.service import message_processing_facade as service
from src.config import settings
from src.filters import TopicFilter
from src.tools.chat_state import get_state_key, state, ChatState
from src.tools.log import get_logger, log_decorator
from src.tools.message_queue import send_msg_as_md
from src.tools.update_getters import get_update_info, extract_status_change

logger = get_logger(__name__)


# COMMANDS
@log_decorator
async def start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда запуска бота для чата/топика.

    Разрешает отправлять сообщения в этот чат/топик.
    По-умолчанию боту не разрешено отправлять сообщения в групповые чаты, даже если бот уже участник и админ.
    """
    update_info = await get_update_info(update)
    reply_text = await service.start(update_info)
    await update.message.reply_text(reply_text)


@log_decorator
async def stop_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда остановки бота для чата/топика.

    Запрещает боту отправлять сообщения в этот чат/топик.
    """
    update_info = await get_update_info(update)
    reply_text = await service.start(update_info)
    await update.message.reply_text(reply_text)


@log_decorator
async def hello_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Команда проверки связи для бота.

    Проверяет, что tg бот и ллм могут принимать и отправлять сообщения.
    """
    update_info = await get_update_info(update)
    msg = await update.message.reply_text(f'tg: Hello {update_info.username}\nllm: ...')
    reply_text = await service.hello(update_info)
    await msg.edit_text(reply_text)


# TOPIC SETTINGS
@log_decorator
async def show_models_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Команда смены модели для чата/топика.

    Отправляет inline клавиатуру с моделями.
    """
    reply_markup = await service.get_models_keyboard()
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


@log_decorator
async def button_change_model(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер нажатия inline кнопки смены модели.

    Изменяет модель для чата/топика.
    """
    update_info = await get_update_info(update)
    query = update.callback_query
    await query.answer()
    model_name = query.data.split("+")[1]
    await service.change_model(update_info, model_name)
    await query.edit_message_text(text=f"Выбрана модель: {model_name}")


@log_decorator
async def system_prompt_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда изменения системного промпта для чата/топика.

    Устанавливает ChatState для чата/топика равным ChatState.PROMPT.
    """
    update_info = await get_update_info(update)
    resp_text = await service.prompt_command(update_info)
    await send_msg_as_md(update, resp_text, ParseMode.MARKDOWN)


@log_decorator
async def temperature_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда изменения настройки температуры для чата/топика.

    Устанавливает ChatState для чата/топика равным ChatState.TEMPERATURE.
    """
    update_info = await get_update_info(update)
    reply_text = await service.temperature_command(update_info)
    await send_msg_as_md(update, reply_text, ParseMode.MARKDOWN)


@log_decorator
async def clear_context_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда сброса контекста. После неё ллм "забывает" историю чата.

    Устанавливает offset для чата/топика равным количеству сообщений.
    """
    update_info = await get_update_info(update)

    message = await service.get_topic_info_message(update_info.chat_id, update_info.topic_id, update_info.user_id, _context.bot, with_prompt=False)
    message += "\nКонтекст очищен."
    await service.chat_manager.clear_context(update_info.chat_id, update_info.topic_id)
    await send_msg_as_md(update, message, ParseMode.MARKDOWN)


# COMMON
@log_decorator
async def cancel_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда отмены. Сбрасывает ChatState для чата/топика.
    """
    update_info = await get_update_info(update)

    with suppress(KeyError):
        del state[get_state_key(update_info.chat_id, update_info.topic_id)]
        await update.message.reply_text("Отменено.")
        return
    await update.message.reply_text("Команды не ожидалось.")


@log_decorator
async def empty_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда для сброса настройки. Ожидается ChatState для чата/топика.
    """
    update_info = await get_update_info(update)

    if state.get(get_state_key(update_info.chat_id, update_info.topic_id)) == ChatState.PROMPT:
        del state[get_state_key(update_info.chat_id, update_info.topic_id)]
        await service.chat_manager.clear_system_prompt(update_info.chat_id, update_info.topic_id)
        await update.message.reply_text("Промпт сброшен.")
        return
    if state.get(get_state_key(update_info.chat_id, update_info.topic_id)) == ChatState.TEMPERATURE:
        del state[get_state_key(update_info.chat_id, update_info.topic_id)]
        await service.chat_manager.reset_temperature(update_info.chat_id, update_info.topic_id)
        await update.message.reply_text("Настройка температуры сброшена.")
        return
    await update.message.reply_text("Команды не ожидалось.")


@log_decorator
async def button_cancel(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.edit_message_text(text=f"Отменено.")


# INFO
@log_decorator
async def user_info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Инфо о пользователе.

    Examples:

        .. code-block::

            Инфо:

            Username: jkich1337
            ID пользователя: 392350805
            Дата рег: 2025-02-07 16:13:59.602000
            Токены: 0
            Чаты: jkich1337, Llm bots

    """
    user_id = update.effective_user.id
    message = await service.get_user_info_message(user_id, _context.bot)
    await send_msg_as_md(update, message, ParseMode.MARKDOWN)


@log_decorator
async def topic_info_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Инфо о топике/чате для пользователя.

    Examples:

        .. code-block:: python
            Инфо: для чата `Llm bots` (436)

            Модель: `claude-3-5-sonnet-latest`
            Промпт: <не задан>
            Температура (от 0 до 1): 0.7
            Контекст:
                сообщений: 4
                токенов: 593
            Бот может отвечать в этом чате: Да
    """
    update_info = await get_update_info(update)

    message = await service.get_topic_info_message(update_info.chat_id, update_info.topic_id, update_info.user_id, _context.bot)
    await send_msg_as_md(update, message, ParseMode.MARKDOWN)


# ADMIN
@log_decorator
async def i_am_admin_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Если пользователь прислал токен, то становится админом.

    Токен задаётся в настройках `src.config.Settings.admin_token`.
    """
    user_id = update.effective_user.id
    try:
        token = _context.args[0]
        if token == settings.admin_token:
            user = await service.chat_manager.get_user_info(user_id)
            user["is_admin"] = True
            await service.chat_manager.update_user(user)
            await update.effective_message.reply_text("Token accepted.")
            return
        else:
            await update.effective_message.reply_text("No.")
    except Exception:
        await update.effective_message.reply_text("Error.")


@log_decorator
async def admin_users_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Инфо о всех пользователях. Для администраторов.
    """
    user_id = update.effective_user.id
    user_info = await service.chat_manager.get_user_info(user_id)
    if user_info["is_admin"]:
        message = await service.get_users(_context.bot)
        await send_msg_as_md(update, message, ParseMode.MARKDOWN)


# TEXT
@log_decorator
async def text_message_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для всех текстовых сообщений.
    """
    update_info = await get_update_info(update)
    reply_text = await service.new_text_message(update_info, update, _context)
    if reply_text is not None:
        await update.message.reply_text(reply_text)


# CHAT MEMBER HANDLER
@log_decorator
async def track_chats_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для обновлений участников чата. Создаёт пользователей/чаты/топики в базе.
    """
    result = extract_status_change(update.my_chat_member)
    if result is None:
        return
    was_member, is_member = result

    update_info = await get_update_info(update)

    # Handle chat types differently:
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        if not was_member and is_member:
            logger.info("%s unblocked the bot", update_info.full_name)
            await service.new_private_chat(update_info.user_id, update_info.username, update_info.full_name)
        elif was_member and not is_member:
            logger.info("%s blocked the bot", update_info.full_name)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", update_info.full_name, chat.title)
            await service.new_group(update_info.user_id, update_info.username, update_info.full_name, update_info.chat_id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", update_info.full_name, chat.title)


@log_decorator
async def ensure_user(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    При любом сообщении проверяет, есть ли пользователь в базе. Создаёт пользователя, чат и топик для ЛС.
    """
    update_info = await get_update_info(update)
    await service.chat_manager.get_or_create_user(update_info.user_id, update_info.username, update_info.full_name)


@log_decorator
async def messages_not_allowed_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Бот не добавлен в чат.\n'
        'Чтобы добавить, отправьте ссылку приглашение боту в лс.\n'
        'Или отправьте /start. Чтобы остановить бота в чате, отправьте /stop'
    )


def build_app(bot_token: str) -> Application:
    """
    Регистрирует хэндлеры и возвращает инстанс бота.

    :param bot_token: токен бота, см BotFather
    :return: Инстанс приложения бота
    """
    topic_filter = TopicFilter()

    app = ApplicationBuilder().concurrent_updates(True).token(bot_token).build()
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
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & topic_filter, callback=text_message_handler, block=False))
    return app
