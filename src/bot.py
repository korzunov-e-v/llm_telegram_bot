from contextlib import suppress
import random

from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ChatMemberHandler,
    Application,
)

from src.app.service import message_processing_facade as service
from src.config import settings
from src.filters import TopicFilter
from src.models import PTBContext
from src.tools.chat_state import get_state_key, state, ChatState
from src.tools.exceptions import error_handler
from src.tools.log import get_logger, log_decorator
from src.tools.message_queue import send_reply_as_md
from src.tools.tracekit import install_tracekit, TraceKitConfig
from src.tools.update_getters import get_update_info, extract_status_change

logger = get_logger(__name__)


# COMMANDS
@log_decorator
async def start_command(update: Update, _context: PTBContext) -> None:
    """
    Команда запуска бота для чата/топика.

    Разрешает отправлять сообщения в этот чат/топик.
    По-умолчанию боту не разрешено отправлять сообщения в групповые чаты, даже если бот уже участник и админ.
    """
    update_info = await get_update_info(update)
    reply_text = await service.start(update_info)
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def stop_command(update: Update, _context: PTBContext) -> None:
    """
    Команда остановки бота для чата/топика.

    Запрещает боту отправлять сообщения в этот чат/топик.
    """
    update_info = await get_update_info(update)
    reply_text = await service.stop(update_info)
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def hello_command(update: Update, _context: PTBContext) -> None:
    """
    Команда проверки связи для бота.

    Проверяет, что tg бот и ллм могут принимать и отправлять сообщения.
    """
    update_info = await get_update_info(update)
    msg = await update.message.reply_text(f'tg: Hello {update_info.username or update_info.full_name}\nllm: ...', parse_mode=ParseMode.MARKDOWN)
    reply_text = await service.hello(update_info)
    await msg.edit_text(reply_text, parse_mode=ParseMode.MARKDOWN)


# TOPIC SETTINGS
@log_decorator
async def show_models(update: Update, _context: PTBContext) -> None:
    """
    Хэндлер команды смены модели для чата/топика.

    Отправляет inline клавиатуру с моделями.
    """
    query = update.callback_query
    if query:
        await query.answer()
        page = int(query.data.split("+")[1])
        reply_markup = await service.get_models_keyboard(page)
        await query.edit_message_text("Выберите модель:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return

    reply_markup = await service.get_models_keyboard()
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def show_providers(update: Update, _context: PTBContext) -> None:
    """
    Хэндлер команды смены модели для чата/топика.

    Отправляет inline клавиатуру с провайдерами моделей.
    """
    query = update.callback_query
    if query:
        await query.answer()
        page = int(query.data.split("+")[1])
        reply_markup = await service.get_providers_keyboard(page)
        await query.edit_message_text("Выберите разработчика модели:", reply_markup=reply_markup)
        return

    reply_markup = await service.get_providers_keyboard()
    await update.message.reply_text("Выберите разработчика модели:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def show_provider_models(update: Update, _context: PTBContext) -> None:
    """
    Хэндлер инлайн клавиатуры выбора модели для чата/топика от заданного провайдера.

    Отправляет inline клавиатуру с моделями определённого провайдера.
    """
    query = update.callback_query
    await query.answer()
    provider = query.data.split("+")[1]
    if "+" in provider:
        provider, page = provider.split("+", maxsplit=1)
    else:
        page = 0
    reply_markup = await service.get_provider_models_keyboard(provider, page)
    await query.edit_message_text(f"Выберите модель от {provider}:", reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def button_change_model(update: Update, _context: PTBContext) -> None:
    """
    Хэндлер нажатия inline кнопки выбора модели.

    Изменяет модель для чата/топика.
    """
    update_info = await get_update_info(update)
    query = update.callback_query
    await query.answer()
    model_hash = query.data.split("+")[1]
    model_name = await service.change_model(update_info, model_hash)
    await query.edit_message_text(text=f"Выбрана модель: `{model_name}`", parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def system_prompt_change_command(update: Update, _context: PTBContext) -> None:
    """
    Команда изменения системного промпта для чата/топика.

    Устанавливает ChatState для чата/топика равным ChatState.PROMPT.
    """
    update_info = await get_update_info(update)
    resp_text = await service.prompt_command(update_info)
    await send_reply_as_md(update, resp_text, ParseMode.MARKDOWN)


@log_decorator
async def temperature_change_command(update: Update, _context: PTBContext) -> None:
    """
    Команда изменения настройки температуры для чата/топика.

    Устанавливает ChatState для чата/топика равным ChatState.TEMPERATURE.
    """
    update_info = await get_update_info(update)
    reply_text = await service.temperature_command(update_info)
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def clear_context_command(update: Update, _context: PTBContext) -> None:
    """
    Команда сброса контекста. После неё ллм "забывает" историю чата.

    Устанавливает offset для чата/топика равным количеству сообщений.
    """
    update_info = await get_update_info(update)
    chat = await _context.bot.get_chat(update_info.chat_id)
    chat_name = chat.title if chat.title else chat.username
    reply_text = await service.get_topic_info_message(
        chat_id=update_info.chat_id,
        topic_id=update_info.topic_id,
        user_id=update_info.user_id,
        chat_name=chat_name,
    )
    reply_text += "\nКонтекст очищен."
    await service.chat_manager.clear_context(update_info.chat_id, update_info.topic_id)
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


# COMMON
@log_decorator
async def cancel_command(update: Update, _context: PTBContext) -> None:
    """
    Команда отмены. Сбрасывает ChatState для чата/топика.
    """
    update_info = await get_update_info(update)

    with suppress(KeyError):
        del state[get_state_key(update_info.chat_id, update_info.topic_id)]
        await update.message.reply_text("Отменено.", parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text("Команды не ожидалось.", parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def empty_command(update: Update, _context: PTBContext) -> None:
    """
    Команда для сброса настройки. Ожидается ChatState для чата/топика.
    """
    update_info = await get_update_info(update)

    if state.get(get_state_key(update_info.chat_id, update_info.topic_id)) == ChatState.PROMPT:
        del state[get_state_key(update_info.chat_id, update_info.topic_id)]
        await service.chat_manager.clear_system_prompt(update_info.chat_id, update_info.topic_id)
        await update.message.reply_text("Промпт сброшен.", parse_mode=ParseMode.MARKDOWN)
        return
    if state.get(get_state_key(update_info.chat_id, update_info.topic_id)) == ChatState.TEMPERATURE:
        del state[get_state_key(update_info.chat_id, update_info.topic_id)]
        await service.chat_manager.reset_temperature(update_info.chat_id, update_info.topic_id)
        await update.message.reply_text("Настройка температуры сброшена.", parse_mode=ParseMode.MARKDOWN)
        return
    await update.message.reply_text("Команды не ожидалось.", parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def button_cancel(update: Update, _context: PTBContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.edit_message_text(text="Отменено.", parse_mode=ParseMode.MARKDOWN)


# INFO
@log_decorator
async def user_info_command(update: Update, _context: PTBContext) -> None:
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
    reply_text = await service.get_user_info_message(user_id, _context.bot)
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


@log_decorator
async def topic_info_command(update: Update, _context: PTBContext) -> None:
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
    chat = await _context.bot.get_chat(update_info.chat_id)
    chat_name = chat.title if chat.title else chat.username
    reply_text = await service.get_topic_info_message(
        chat_id=update_info.chat_id,
        topic_id=update_info.topic_id,
        user_id=update_info.user_id,
        chat_name=chat_name,
    )
    await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


# ADMIN
@log_decorator
async def i_am_admin_command(update: Update, _context: PTBContext) -> None:
    """
    Если пользователь прислал токен, то становится админом.

    Токен задаётся в настройках `src.config.Settings.admin_token`.
    """
    user_id = update.effective_user.id
    try:
        token = _context.args[0]
        if token == settings.admin_token:
            user = await service.chat_manager.get_user_info(user_id)
            user.is_admin = True
            await service.chat_manager.update_user(user)
            await update.effective_message.reply_text("Token accepted.")
            return
        else:
            await update.effective_message.reply_text("No.")
    except Exception:
        await update.effective_message.reply_text("Error.")


@log_decorator
async def admin_users_command(update: Update, _context: PTBContext) -> None:
    """
    Инфо о всех пользователях. Для администраторов.
    """
    user_id = update.effective_user.id
    user_info = await service.chat_manager.get_user_info(user_id)
    if user_info.is_admin:
        reply_text = await service.get_users(_context.bot)
        await update.message.reply_text(reply_text, parse_mode=ParseMode.MARKDOWN)


# TEXT
@log_decorator
async def text_message_handler(update: Update, _context: PTBContext) -> None:
    """
    Хэндлер для всех текстовых сообщений.
    """
    update_info = await get_update_info(update)
    reply_text = await service.new_text_message(update_info, update)
    if reply_text is not None:
        await send_reply_as_md(update, reply_text, parse_mode=ParseMode.MARKDOWN_V2)


# CHAT MEMBER HANDLER
@log_decorator
async def track_chats_handler(update: Update, _context: PTBContext) -> None:
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
async def ensure_user(update: Update, _context: PTBContext) -> None:
    """
    При любом сообщении проверяет, есть ли пользователь в базе. Создаёт пользователя, чат и топик для ЛС.
    """
    update_info = await get_update_info(update)
    await service.chat_manager.get_or_create_user(update_info.user_id, update_info.username, update_info.full_name)


@log_decorator
async def messages_not_allowed_handler(update: Update, _context: PTBContext) -> None:
    await update.message.reply_text(
        'Бот не добавлен в чат.\n'
        'Чтобы добавить, отправьте ссылку приглашение боту в лс.\n'
        'Или отправьте /start. Чтобы остановить бота в чате, отправьте /stop',
        parse_mode=ParseMode.MARKDOWN,
    )


async def noop_handler(update: Update, _context: PTBContext) -> None:
    spin_vals = ["🐵", "🍄", "🏆", "💥", "⚡", "🎃", "👑", "💰", "💲", "💩"]
    texts = [
        "Это номер страницы",
        "Это номер страницы.",
        "Это номер страницы..",
        "Это номер страницы. Он не нажимается.",
        "фриспин!"
    ]

    user_info = await service.chat_manager.get_user_info(user_id=update.effective_user.id)
    spin_count = user_info.spin_counter

    if spin_count < len(texts):
        await update.callback_query.answer(texts[spin_count])
    else:
        result = [random.choice(spin_vals) for _ in range(3)]
        resp_text = "".join(result)
        if len(set(result)) == 1:
            resp_text += "\nWIN!"
        await update.callback_query.answer(resp_text)
    user_info.spin_counter += 1
    await service.chat_manager.update_user(user_info)


def build_app(bot_token: str) -> Application:
    """
    Регистрирует хэндлеры и возвращает инстанс бота.

    :param bot_token: токен бота, см BotFather
    :return: Инстанс приложения бота
    """
    topic_filter = TopicFilter()

    app = ApplicationBuilder().concurrent_updates(True).token(bot_token).build()

    install_tracekit(
        app,
        TraceKitConfig(
            admin_chat_id=settings.admin_chat_id,
            sample_rate=1,
            enable_telegram_notify=True,
            enable_json_logs=True,
            include_stack_text = True,
        )
    )

    app.add_handler(ChatMemberHandler(track_chats_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters=filters.ALL, callback=ensure_user), group=100)
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters=~topic_filter & filters.COMMAND, callback=messages_not_allowed_handler))
    app.add_handler(CommandHandler("hello", hello_command))
    app.add_handler(CommandHandler("clear", clear_context_command))
    app.add_handler(CommandHandler("user", user_info_command))
    app.add_handler(CommandHandler("info", topic_info_command))
    app.add_handler(CommandHandler("models", show_models))
    app.add_handler(CommandHandler("providers", show_providers))
    app.add_handler(CommandHandler("prompt", system_prompt_change_command))
    app.add_handler(CommandHandler("temperature", temperature_change_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("empty", empty_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(CommandHandler("admin_users", admin_users_command))
    app.add_handler(CommandHandler("i_am_admin", i_am_admin_command))
    app.add_handler(CallbackQueryHandler(button_change_model, pattern="change_model"))
    app.add_handler(CallbackQueryHandler(show_models, pattern="models"))
    app.add_handler(CallbackQueryHandler(show_providers, pattern="providers"))
    app.add_handler(CallbackQueryHandler(show_provider_models, pattern="provider"))
    app.add_handler(CallbackQueryHandler(button_cancel, pattern="cancel"))
    app.add_handler(CallbackQueryHandler(noop_handler, pattern="noop"))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND & topic_filter, callback=text_message_handler, block=False))

    app.add_error_handler(error_handler)
    return app
