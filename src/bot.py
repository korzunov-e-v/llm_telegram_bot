import asyncio
import os
from contextlib import suppress
from collections import defaultdict

from anthropic.types import ModelParam
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from src.tools.check_ip import check_ip
from src.service import Service
from langchain_text_splitters import MarkdownTextSplitter

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")
state = {}
messages_queue: dict[int, list[str]] = defaultdict(list)


async def delay_send(context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(2)
    user_id = context.job.user_id
    if not messages_queue[user_id]:
        return None
    update = context.job.data
    message = "\n".join(messages_queue[user_id])
    del messages_queue[user_id]
    llm_resp_text = service.handle_text_message(user_id, message)
    sections = MarkdownTextSplitter(chunk_overlap=0, keep_separator="end").split_text(llm_resp_text)
    for section in sections:
        await update.message.reply_text(section, parse_mode="Markdown")


async def hello_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


async def button_change_model(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    model = query.data.split("+")[1]
    service.change_model(user_id, model)
    await query.edit_message_text(text=f"Выбрана модель: {query.data.split("+")[1]}")


async def button_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    await query.edit_message_reply_markup(None)
    await query.edit_message_text(text=f"Отменено.")


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    models = ModelParam.__dict__["__args__"][1].__dict__["__args__"]
    keyboard_models = [[InlineKeyboardButton(a, callback_data=f"change_model+{a}")] for a in models]
    keyboard = keyboard_models + [[InlineKeyboardButton("Отмена", callback_data="cancel+0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = service.get_user_info_message(user_id)
    message += "\nКонтекст очищен."
    service.clear_context(user_id)
    await update.message.reply_text(message)


async def ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    username = update.effective_user.username
    service.get_or_create_user(user_id, username)


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_msg_text = update.message.text

    if state.get(user_id) == "prompt":
        service.set_system_prompt(user_id, user_msg_text)
        del state[user_id]
        return await update.message.reply_text("Промпт установлен.")
    else:
        messages_queue[user_id].append(user_msg_text)
        context.job_queue.run_once(delay_send, 1, user_id=user_id, data=update)


async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = service.get_user_info_message(user_id)
    await update.message.reply_text(message)


async def prompt_change_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    state[user_id] = "prompt"
    await update.message.reply_text('Отправьте новый промпт, /cancel для отмены или /empty для сброса промпта.\n'
                                    f'Текущий промпт: "{service.get_system_prompt(user_id)}"')


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    with suppress(KeyError):
        del state[user_id]
        return await update.message.reply_text("Отмена, промпт не изменился.")
    await update.message.reply_text("Команды не ожидалось.")


async def empty_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if state.get(user_id) == "prompt":
        del state[user_id]
        service.clear_system_prompt(user_id)
        return await update.message.reply_text("Промпт сброшен.")
    await update.message.reply_text("Команды не ожидалось.")


if __name__ == '__main__':
    check_ip()
    service = Service()
    app = ApplicationBuilder().token(bot_token).build()

    app.add_handler(MessageHandler(filters=filters.ALL, callback=ensure_user), group=100)
    app.add_handler(CommandHandler("hello", hello_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CommandHandler("models", models_command))
    app.add_handler(CommandHandler("info", user_info_command))
    app.add_handler(CommandHandler("prompt", prompt_change_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("empty", empty_command))
    app.add_handler(CallbackQueryHandler(button_change_model, pattern="change_model"))
    app.add_handler(CallbackQueryHandler(button_cancel, pattern="cancel"))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=text_message_handler))

    job_queue = app.job_queue
    app.run_polling()
