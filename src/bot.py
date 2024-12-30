import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from service import Service

load_dotenv()

service = Service()
bot_token = os.getenv("BOT_TOKEN")


async def hello_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    service.clear_context(user_id)
    await update.message.reply_text(f'Контекст очищен.')


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_query = update.message.text
    llm_resp_text = service.handle_text_message(user_id, user_query)
    await update.message.reply_text(llm_resp_text)


app = ApplicationBuilder().token(bot_token).build()

app.add_handler(CommandHandler("hello", hello_handler))
app.add_handler(CommandHandler("clear", clear_handler))
app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=text_message_handler))

app.run_polling()
