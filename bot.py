import os

from anthropic import Anthropic
from anthropic.types import MessageParam
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from user_context_manager import user_contexts

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
bot_token = os.getenv("BOT_TOKEN")
client = Anthropic(api_key=api_key)


async def hello_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


async def clear_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_contexts.clear(user_id)
    await update.message.reply_text(f'Контекст очищен.')


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_query = update.message.text
    messages = user_contexts.get(user_id)
    user_message = MessageParam(role="user", content=user_query)
    response = client.messages.create(
            model="claude-3-haiku-20240307",  # claude-3-5-sonnet-20241022
            max_tokens=1000,
            messages=messages + [user_message]
    )
    llm_resp_text = response.content[0].text
    llm_message = MessageParam(content=response.content, role=response.role)

    user_contexts.add(update.effective_user.id, user_message)
    user_contexts.add(update.effective_user.id, llm_message)



    await update.message.reply_text(llm_resp_text)


app = ApplicationBuilder().token(bot_token).build()

app.add_handler(CommandHandler("hello", hello_handler))
app.add_handler(CommandHandler("clear", clear_handler))
app.add_handler(MessageHandler(filters=filters.TEXT & ~filters.COMMAND, callback=message_handler))

app.run_polling()
