import asyncio
import re
from datetime import datetime, UTC

from anthropic.types import MessageParam, TextBlockParam
from telegram import Update
from telegram.ext import ContextTypes

from src.app.database import MongoManager
from src.app.llm_provider import LLMProvider
from src.app.message_repo import MessageRepository
from src.config import settings
from src.app.chat_manager import ChatManager
from src.tools.custom_logging import get_logger

logger = get_logger(__name__)


class MessageProcessingFacade:
    def __init__(
        self,
        llm_provider: LLMProvider,
        chat_manager: ChatManager,
        message_repo: MessageRepository,
    ):
        self.llm_provider: LLMProvider = llm_provider
        self.user_manager: ChatManager = chat_manager
        self.message_repo: MessageRepository = message_repo

    async def process_invite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ссылки-приглашения"""
        # service.process_invite_link(update.message.text)
        topic_invite_pattern = re.compile(r'https?://t.me/\w+/(\d+)/(\d+)')
        match = re.search(topic_invite_pattern, update.message.text)
        try:
            chat_id = int(match.group(1))
            chat_id_minus = -1000000000000 - chat_id
            chat_id = min(chat_id, chat_id_minus)
            topic_id = int(match.group(2))
            topics = self.user_manager.get_allowed_topics(chat_id)
            try:
                if topic_id in topics:
                    msg = await context.bot.send_message(chat_id, "Ping. Проверка что бот может писать в этот топик.", message_thread_id=topic_id)
                    await update.message.reply_text(f"Бот и так имеет доступ к топику")
                    await asyncio.sleep(30)
                    await msg.delete()
                    return
                self.user_manager.add_allowed_topics(chat_id, topic_id)
                await context.bot.send_message(chat_id, "Бот теперь имеет доступ к этому топику", message_thread_id=topic_id)
                await update.message.reply_text(f"Бот теперь имеет доступ к топику")
                logger.info(f"Добавлен новый топик: {topic_id} ({update.effective_user.full_name})")
            except Exception as e:
                await update.message.reply_text(f"Не удалось получить доступ к топику: {str(e)}")
                logger.error(f"Ошибка при получении доступа к топику: {str(e)}")
        except Exception as e:
            logger.error(f"Ошибка при обработке ссылки: {str(e)}")

    def process_message(self, user_id: int, message_text: str, username: str = ""):
        user_info = self.user_manager.get_user(user_id, username)
        user_settings = user_info["settings"]
        context = self.user_manager.get_context(user_id, user_info["offset"])

        user_message = MessageParam(
            content=[TextBlockParam(text=message_text, type="text")],
            role="user"
        )
        messages = context + [user_message]
        input_sing_tokens_count = self.llm_provider.count_tokens(user_settings["model"], [user_message])

        u_dt = datetime.now(UTC)
        response = self.llm_provider.send_messages(
            model=user_settings["model"],
            messages=messages,
            user_id=user_id,
            system_prompt=user_settings["system_prompt"],
            temp=user_settings["temperature"],
        )

        a_dt = datetime.now(UTC)
        llm_resp_text = response.content[0].text
        llm_message = MessageParam(
            content=[m.model_dump() for m in response.content],
            role=response.role,
        )

        self.message_repo.add_message_to_db(  # llm
            user_id=user_id,
            message=llm_message,
            context=messages,
            model=response.model,
            tokens=response.usage.output_tokens,
            tokens_plus=0,
            timestamp=a_dt,
        )
        self.message_repo.add_message_to_db(  # user
            user_id=user_id,
            message=user_message,
            context=context,
            model=response.model,
            tokens=input_sing_tokens_count,
            tokens_plus=response.usage.input_tokens,
            timestamp=u_dt,
        )
        return llm_resp_text

    def get_user_info_message(self, chat_id: int, topic_id: int = None) -> str:
        user_info = self.user_manager.get_user(chat_id)
        message_templ = (
            "Инфо:\n"
            "\n"
            "Модель: {model}\n"
            'Промпт: {prompt}\n'
            "Температура (от 0 до 1): {temp}\n"
            "Токены: {tokens}\n"
            "Контекст:\n"
            "    сообщений: {context_len}\n"
            "    токенов: {context_tokens}\n"
            "Бот может отвечать в этом чате: {can_reply}"
        )
        messages = self.user_manager.get_context(chat_id, offset=user_info["offset"])
        context_len = len(messages)
        context_tokens = self.llm_provider.count_tokens(user_info["settings"]["model"], messages)
        system_prompt = user_info["settings"]["system_prompt"]
        if system_prompt is None or system_prompt == "None":
            system_prompt = '<не задан>'
        if topic_id:
            if topic_id not in self.user_manager.get_allowed_topics(chat_id):
                can_reply = "Нет"
            else:
                can_reply = "Да"
        else:
            can_reply = "Да"
        message = message_templ.format(
            model=user_info["settings"]["model"],
            prompt=system_prompt,
            temp=user_info["settings"].get("temperature") or settings.default_temperature,
            tokens=user_info["tokens_balance"],
            context_len=context_len,
            context_tokens=context_tokens,
            can_reply=can_reply
        )
        return message


db_provider = MongoManager(settings.mongo_url)
chat_manager = ChatManager(db_provider)
message_repo = MessageRepository(db_provider)
llm_provider = LLMProvider(settings.anthropic_api_key)
message_processing_facade = MessageProcessingFacade(
    llm_provider=llm_provider,
    message_repo=message_repo,
    chat_manager=chat_manager,
)
