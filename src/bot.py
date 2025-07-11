import traceback
from contextlib import suppress

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

from src.app.service import message_processing_facade as service
from src.config import settings
from src.filters import TopicFilter, InviteLinkFilter, WebLinkFilter
from src.models import MessageModel
from src.tools.chat_state import get_state_key, state, ChatState
from src.tools.log import get_logger, log_decorator
from src.tools.message_queue import get_queue_key, messages_queue, delay_send, send_msg_as_md
from src.tools.update_getters import get_ids, extract_status_change

logger = get_logger(__name__)


# COMMANDS
@log_decorator
async def start_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда запуска бота для чата/топика.

    Разрешает отправлять сообщения в этот чат/топик.
    По-умолчанию боту не разрешено отправлять сообщения в групповые чаты, даже если бот уже участник и админ.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    await service.chat_manager.get_or_create_user(user_id, username, full_name)
    allowed_topics = await service.chat_manager.get_allowed_topics(chat_id, user_id)
    if topic_id in allowed_topics:
        await update.message.reply_text("Бот уже тут.")
    else:
        await service.chat_manager.add_allowed_topic(chat_id, topic_id, user_id)
        await update.message.reply_text("Бот добавлен в чат.")


@log_decorator
async def stop_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда остановки бота для чата/топика.

    Запрещает боту отправлять сообщения в этот чат/топик.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    res = await service.chat_manager.remove_allowed_topics(chat_id, topic_id, user_id)
    if not res:
        await update.message.reply_text("Не ожидалось этой команды.")
        return

    await update.message.reply_text(
        "Покинул топик. Чтобы добавить снова, отправьте ссылку-приглашение боту в лc.\n"
        "Или отправьте /start в этот чат."
    )


@log_decorator
async def hello_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Команда проверки связи для бота.

    Проверяет что tg бот и ллм могут принимать и отправлять сообщения.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)
    msg = await update.message.reply_text(f'tg: Hello {username}\nllm: ...')
    try:
        response = await service.llm_provider.send_messages(
            model="claude-3-5-haiku-latest",
            messages=[MessageModel(content="На связи?", role="user")],
            user_id=user_id,
            temp=1,
            max_tokens=10,
        )
        llm_resp = response["model_response"].parts[0].content
        await msg.edit_text(f'tg: Hello {username}\nllm: {llm_resp}')
    except Exception as e:
        logger.error("hello command error: ", exc_info=e)
        logger.error(traceback.format_exc())
        await msg.edit_text(f'tg: Hello {username}\nllm: <error>')


# TOPIC SETTINGS
@log_decorator
async def show_models_command(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    """
    Команда смены модели для чата/топика.

    Отправляет inline клавиатуру с моделями.
    """
    models = await service.llm_provider.get_models()
    keyboard_models = [[InlineKeyboardButton(f"{model["display_name"]} | {model["name"]}", callback_data=f"change_model+{model["name"]}")]
                       for model in models]
    keyboard = keyboard_models + [[InlineKeyboardButton("Отмена", callback_data="cancel+0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


@log_decorator
async def button_change_model(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер нажатия inline кнопки смены модели.

    Изменяет модель для чата/топика.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    query = update.callback_query
    await query.answer()
    model = query.data.split("+")[1]
    await service.chat_manager.change_model(chat_id, topic_id, model)
    await query.edit_message_text(text=f"Выбрана модель: {model}")


@log_decorator
async def system_prompt_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда изменения системного промпта для чата/топика.

    Устанавливает ChatState для чата/топика равным ChatState.PROMPT.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    state[get_state_key(chat_id, topic_id)] = ChatState.PROMPT
    topic_settings = await service.chat_manager.get_topic_settings(chat_id, topic_id)
    current_prompt = topic_settings["system_prompt"]
    resp_text = ('Отправьте новый промпт, /cancel для отмены или /empty для сброса промпта.\n'
                 f'Текущий промпт: {service.chat_manager.format_system_prompt(current_prompt)}')
    await send_msg_as_md(update, resp_text, "Markdown")


@log_decorator
async def temperature_change_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда изменения настройки температуры для чата/топика.

    Устанавливает ChatState для чата/топика равным ChatState.TEMPERATURE.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    state[get_state_key(chat_id, topic_id)] = ChatState.TEMPERATURE
    topic_settings = await service.chat_manager.get_topic_settings(chat_id, topic_id)
    await update.message.reply_text(
        'Отправьте значение температуры (креативность/непредсказуемость модели), /cancel для отмены или /empty для сброса.\n'
        f'Текущая температура: {topic_settings["temperature"]}\n'
        f'Температура по-умолчанию: {settings.default_temperature}'
    )


@log_decorator
async def clear_context_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда сброса контекста. После неё ллм "забывает" историю чата.

    Устанавливает offset для чата/топика равным количеству сообщений.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    message = await service.get_topic_info_message(chat_id, topic_id, user_id, _context.bot, with_prompt=False)
    message += "\nКонтекст очищен."
    await service.chat_manager.clear_context(chat_id, topic_id)
    await send_msg_as_md(update, message, "Markdown")


# COMMON
@log_decorator
async def cancel_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда отмены. Сбрасывает ChatState для чата/топика.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    with suppress(KeyError):
        del state[get_state_key(chat_id, topic_id)]
        await update.message.reply_text("Отменено.")
        return
    await update.message.reply_text("Команды не ожидалось.")


@log_decorator
async def empty_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Команда для сброса настройки. Ожидается ChatState для чата/топика.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    if state.get(get_state_key(chat_id, topic_id)) == ChatState.PROMPT:
        del state[get_state_key(chat_id, topic_id)]
        await service.chat_manager.clear_system_prompt(chat_id, topic_id)
        await update.message.reply_text("Промпт сброшен.")
        return
    if state.get(get_state_key(chat_id, topic_id)) == ChatState.TEMPERATURE:
        del state[get_state_key(chat_id, topic_id)]
        await service.chat_manager.reset_temperature(chat_id, topic_id)
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
    await send_msg_as_md(update, message, "Markdown")


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
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    message = await service.get_topic_info_message(chat_id, topic_id, user_id, _context.bot)
    await send_msg_as_md(update, message, "Markdown")


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
        await send_msg_as_md(update, message, "Markdown")


# TEXT
@log_decorator
async def text_message_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для всех текстовых сообщений.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)
    state_key = get_state_key(chat_id, topic_id)
    queue_key = get_queue_key(user_id, topic_id)
    topic_settings = await service.chat_manager.get_topic_settings(chat_id, topic_id)

    msg = await update.message.reply_text("Пишет...")

    if state.get(state_key) == ChatState.PROMPT:
        await service.chat_manager.set_system_prompt(msg_text, chat_id, topic_id)
        del state[state_key]
        await msg.edit_text("Промпт установлен.")
        return
    if state.get(state_key) == ChatState.TEMPERATURE:
        await service.chat_manager.set_temperature(msg_text, chat_id, topic_id)
        del state[state_key]
        await msg.edit_text("Температура установлена.")
        return
    else:
        messages_queue[queue_key].append(msg_text)
        _context.job_queue.run_once(
            callback=delay_send,
            when=0,
            user_id=user_id,
            chat_id=chat_id,
            data={"update": update, "msg": msg, "topic_id": topic_id, "md_v2_mode": topic_settings.get("md_v2_mode", False)}
        )


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

    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

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
            await service.new_private_chat(user_id, username, full_name)
        elif was_member and not is_member:
            logger.info("%s blocked the bot", full_name)
            # _context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            logger.info("%s added the bot to the group %s", full_name, chat.title)
            # _context.bot_data.setdefault("group_ids", set()).add(chat.id)
            await service.new_group(user_id, username, full_name, chat_id)
        elif was_member and not is_member:
            logger.info("%s removed the bot from the group %s", full_name, chat.title)
            # _context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    # elif not was_member and is_member:
    #     logger.info("%s added the bot to the channel %s", full_name, chat.title)
    #     _context.bot_data.setdefault("channel_ids", set()).add(chat.id)
    # elif was_member and not is_member:
    #     logger.info("%s removed the bot from the channel %s", full_name, chat.title)
    #     _context.bot_data.setdefault("channel_ids", set()).discard(chat.id)


@log_decorator
async def ensure_user(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    При любом сообщении проверяет, есть ли пользователь в базе. Создаёт пользователя, чат и топик для ЛС.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)

    await service.chat_manager.get_or_create_user(user_id, username, full_name)


@log_decorator
async def invite_link_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для ссылок-приглашений.
    Добавляет чат в список разрешённых для бота. То же самое что и `/start`.
    """
    await service.process_invite(update, context)


@log_decorator
async def web_link_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для ссылок на сайты.
    Получает контент с сайта и отправляет в ллм.
    """
    logger.info("Not supported yet.")
    await update.message.reply_text("Not supported yet.")


@log_decorator
async def pdf_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Хэндлер для сообщений с pdf файлами.
    Получает контент и отправляет в ллм.
    """
    username, full_name, user_id, chat_id, topic_id, msg_text = await get_ids(update)
    msg = await update.message.reply_text("Пишет...")

    topic_settings = await service.chat_manager.get_topic_settings(chat_id, topic_id)
    llm_resp_text = await service.send_pdf_message(update, user_id, chat_id, topic_id)
    await send_msg_as_md(update, llm_resp_text, md_v2_mode=topic_settings.get("md_v2_mode", False), msg_for_delete=msg)  # todo


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

    :param bot_token: tg токен бота, см BotFather
    :return: Инстанс приложения бота
    """
    topic_filter = TopicFilter()
    invite_link_filter = InviteLinkFilter()
    web_link_filter = WebLinkFilter()

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
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & web_link_filter,
                                   callback=web_link_handler))
    app.add_handler(MessageHandler(filters=filters.Document.PDF, callback=pdf_handler))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & topic_filter, callback=text_message_handler))
    return app
