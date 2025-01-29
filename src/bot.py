import os

from anthropic.types import ModelParam
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler

from src.tools.check_ip import check_ip
from src.service import Service

load_dotenv()

bot_token = os.getenv("BOT_TOKEN")


async def hello_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def models_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    models = ModelParam.__dict__["__args__"][1].__dict__["__args__"]
    keyboard_models = [[InlineKeyboardButton(a, callback_data=f"change_model+{a}")] for a in models]
    keyboard = keyboard_models + [[InlineKeyboardButton("Отмена", callback_data="cancel+0")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите модель:", reply_markup=reply_markup)


async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    user_query = update.message.text
    llm_resp_text = service.handle_text_message(user_id, user_query)
    await update.message.reply_text(llm_resp_text, parse_mode="Markdown")


async def user_info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message = service.get_user_info_message(user_id)
    await update.message.reply_text(message)


if __name__ == '__main__':
    check_ip()
    service = Service()
    app = ApplicationBuilder().token(bot_token).build()

    app.add_handler(MessageHandler(filters=filters.ALL, callback=ensure_user), group=100)
    app.add_handler(CommandHandler("hello", hello_handler))
    app.add_handler(CommandHandler("clear", clear_handler))
    app.add_handler(CommandHandler("models", models_handler))
    app.add_handler(CommandHandler("info", user_info_handler))
    app.add_handler(CallbackQueryHandler(button_change_model, pattern="change_model"))
    app.add_handler(CallbackQueryHandler(button_cancel, pattern="cancel"))
    app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=text_message_handler))

    app.run_polling()
