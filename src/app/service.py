import asyncio
import base64
import os
import re
from datetime import datetime, UTC
from pathlib import Path

from anthropic.types import MessageParam, TextBlockParam, Base64PDFSourceParam, DocumentBlockParam, CacheControlEphemeralParam, \
    PlainTextSourceParam, CitationsConfigParam, Message
from telegram import Bot, Update
from telegram.ext import ContextTypes

from src.app.chat_manager import ChatManager
from src.app.database import MongoManager
from src.app.llm_provider import LLMProvider
from src.app.message_repo import MessageRepository
from src.config import settings
from src.tools.log import get_logger
from src.tools.pdf_tool import load_from_large_pdf

logger = get_logger(__name__)


class MessageProcessingFacade:
    def __init__(
        self,
        llm_provider: LLMProvider,
        chat_manager: ChatManager,
        message_repo: MessageRepository,
    ):
        self.llm_provider: LLMProvider = llm_provider
        self.chat_manager: ChatManager = chat_manager
        self.message_repo: MessageRepository = message_repo

    async def process_invite(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ссылки-приглашения"""
        topic_invite_pattern = re.compile(r'https?://t.me/\w+/(\d+)/(\d+)')
        match = re.search(topic_invite_pattern, update.message.text)
        try:
            chat_id = int(match.group(1))
            chat_id_minus = -1000000000000 - chat_id
            chat_id = min(chat_id, chat_id_minus)
            topic_id = int(match.group(2))
            user_id = update.effective_user.id
            topics = self.chat_manager.get_allowed_topics(chat_id, user_id)
            if topic_id == 1:
                topic_id_send = 0
            else:
                topic_id_send = topic_id
            try:
                if topic_id in topics:
                    msg = await context.bot.send_message(chat_id, "Ping. Проверка что бот может писать в этот топик.",
                                                         message_thread_id=topic_id_send)
                    await update.message.reply_text(f"Бот и так добавлен в топик.")
                    await asyncio.sleep(30)
                    await msg.delete()
                    return
                self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
                self.chat_manager.add_allowed_topic(chat_id, topic_id, user_id)
                await context.bot.send_message(chat_id, "Бот добавлен в этот чат.", message_thread_id=topic_id_send)
                await update.message.reply_text(f"Бот добавлен в этот топик.")
                logger.info(f"Добавлен новый топик: {topic_id} ({update.effective_user.full_name})")
            except Exception as e:
                await update.message.reply_text(
                    f"Не удалось получить доступ к топику: {str(e)}, скорее всего боту не дали админку в группе.")
                logger.error(f"Ошибка при получении доступа к топику: {str(e)}")
        except Exception as e:
            await update.message.reply_text(f"Что-то пошло не так :(")
            logger.error(f"Ошибка при обработке ссылки: {str(e)}")

    async def send_pdf_message(self, update: Update, user_id: int, chat_id: int, topic_id: int) -> str:
        if topic_id is None:
            topic_id = 1
        topic_info = self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        topic_settings = topic_info["settings"]

        filename = update.message.document.file_name
        doc = await update.message.document.get_file(read_timeout=30, connect_timeout=30)
        bo = bytearray()
        await doc.download_as_bytearray(bo)
        download_path = Path(f"tmp")
        download_path.mkdir(exist_ok=True)
        doc_path = download_path.joinpath(filename)
        doc_path = await doc.download_to_drive(doc_path)
        pdf_data = base64.standard_b64encode(bo).decode("utf-8")

        context = self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])

        if topic_settings.get("parse_pdf", True):
            txt = load_from_large_pdf(doc_path)
            logger.info(f"parsed {doc_path}. txt_len={len(txt)}")
            if not txt:
                return "Ошибка парсинга файла."
            os.remove(doc_path)
            source = PlainTextSourceParam(data=txt, media_type="text/plain", type="text")
        else:
            source = Base64PDFSourceParam(data=pdf_data, media_type="application/pdf", type="base64")

        user_doc_message = MessageParam(
            content=[
                DocumentBlockParam(
                    source=source,
                    type="document",
                    cache_control=CacheControlEphemeralParam(type="ephemeral"),
                    citations=CitationsConfigParam(enabled=True),
                ),
            ],
            role="user"
        )
        user_message = MessageParam(content=[TextBlockParam(text=update.message.text or update.message.caption, type="text")], role="user")

        messages = context + [user_doc_message, user_message]
        llm_resp = self.send_messages(messages, user_id, chat_id, topic_id, extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"})
        llm_resp_text = self.join_llm_response(llm_resp)
        return llm_resp_text

    @staticmethod
    def join_llm_response(message: Message) -> str:
        content = message.content
        result = ""
        for part in content:
            result += part.text.strip() + "\n"
            if part.citations:
                for cit in part.citations:
                    lines = cit.cited_text.split("\n")
                    text = "\n> ".join(lines)
                    result += '> ' + text + "\n\n"
            result = result.strip("> \n")
            result = result.strip()
            result += "\n\n"
        result = result.strip()
        result = re.sub("\n{2,}", "\n\n", result)
        result = re.sub("(> ?\n)*", "", result)
        return result

    def send_messages(self, messages: list[MessageParam], user_id: int, chat_id: int, topic_id: int, extra_headers: dict = None) -> Message:
        if topic_id is None:
            topic_id = 1
        topic_info = self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        topic_settings = topic_info["settings"]
        context = self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])

        user_messages = []
        for i in messages[::-1]:
            if i["role"] == "user":
                user_messages.append(i)
            else:
                break
        user_messages = user_messages[::-1]
        input_sing_tokens_count = [self.llm_provider.count_tokens(topic_settings["model"], [mes]) for mes in user_messages]

        cache = False
        for mes in context:
            for m in mes["content"]:
                if m.get("cache_control"):
                    cache = True
                    break

        if cache:
            messages[-1]["content"][0]["cache_control"] = {"type": "ephemeral"}

        u_dt = datetime.now(UTC)
        response = self.llm_provider.send_messages(
            model=topic_settings["model"],
            messages=messages,
            user_id=user_id,
            system_prompt=topic_settings["system_prompt"],
            temp=topic_settings["temperature"],
            extra_headers=extra_headers,
        )

        a_dt = datetime.now(UTC)
        llm_message = MessageParam(
            content=[m.model_dump() for m in response.content],
            role=response.role,
        )

        self.message_repo.add_message_to_db(  # llm
            chat_id=chat_id,
            topic_id=topic_id,
            user_id=user_id,
            message=llm_message,
            context_n=0,
            model=response.model,
            tokens_message=0,
            tokens_from_prov=response.usage.output_tokens,
            timestamp=a_dt,
        )
        for i, mes in enumerate(user_messages):
            self.message_repo.add_message_to_db(  # user
                chat_id=chat_id,
                topic_id=topic_id,
                user_id=user_id,
                message=mes,
                context_n=len(context),
                model=response.model,
                tokens_message=input_sing_tokens_count[i],
                tokens_from_prov=response.usage.input_tokens,
                timestamp=u_dt,
            )

        if settings.debug:
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            input_tokens_cache_read = getattr(response.usage, 'cache_read_input_tokens', '---')
            input_tokens_cache_create = getattr(response.usage, 'cache_creation_input_tokens', '---')
            print(f"User input tokens: {input_tokens}")
            print(f"Output tokens: {output_tokens}")
            print(f"Input tokens (cache read): {input_tokens_cache_read}")
            print(f"Input tokens (cache write): {input_tokens_cache_create}")
            total_input_tokens = input_tokens + (int(input_tokens_cache_read) if input_tokens_cache_read != '---' else 0)
            percentage_cached = (int(input_tokens_cache_read) / total_input_tokens * 100 if input_tokens_cache_read != '---' and total_input_tokens > 0 else 0)
            print(f"{percentage_cached:.1f}% of input prompt cached ({total_input_tokens} tokens)")

        return response

    def process_txt_message(self, message_text: str, user_id: int, chat_id: int, topic_id: int) -> str:
        if topic_id is None:
            topic_id = 1
        topic_info = self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        topic_settings = topic_info["settings"]
        context = self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])

        user_message = MessageParam(
            content=[TextBlockParam(text=message_text, type="text")],
            role="user"
        )
        messages = context + [user_message]

        llm_resp = self.send_messages(messages, user_id, chat_id, topic_id)
        llm_resp_text = self.join_llm_response(llm_resp)
        return llm_resp_text

    async def get_topic_info_message(self, chat_id: int, topic_id: int, user_id: int, bot: Bot, with_prompt: bool = True) -> str:
        if topic_id is None:
            topic_id = 1
        topic_settings = self.chat_manager.get_topic_settings(chat_id, topic_id)
        chat = await bot.get_chat(chat_id)
        chat_name = chat.title if chat.title else chat.username
        messages_records = self.message_repo.get_messages_from_db(chat_id, topic_id, offset=topic_settings["offset"])
        messages = self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])
        model = topic_settings["model"]
        if with_prompt:
            prompt = self.chat_manager.format_system_prompt(topic_settings["system_prompt"])
        else:
            if topic_settings["system_prompt"]:
                prompt = "<задан>"
            else:
                prompt = "<не задан>"
        temperature = topic_settings["temperature"]
        context_len = len(messages)
        try:
            context_tokens = self.llm_provider.count_tokens(topic_settings["model"], messages)
        except Exception:
            context_tokens = "<error>"
            logger.error(f"context was broken. {user_id=} {chat_id=} {topic_id=} {topic_settings["offset"]=}")
        allowed_topics = self.chat_manager.get_allowed_topics(chat_id, user_id)
        tokens_total_input = sum([mes["tokens_message"] + mes["tokens_from_prov"] for mes in messages_records if mes["message_param"]["role"] == "user"])
        tokens_total_output = sum([mes["tokens_message"] + mes["tokens_from_prov"] for mes in messages_records if mes["message_param"]["role"] == "assistant"])
        if topic_id not in allowed_topics:
            can_reply = "Нет"
        else:
            can_reply = "Да"
        message = (
            f"Инфо: для чата `{chat_name}` ({topic_id})\n"
            f"\n"
            f"Модель: `{model}`\n"
            f'Промпт: {prompt}\n'
            f"Температура (от 0 до 1): {temperature}\n"
            f"Контекст:\n"
            f"    сообщений: {context_len}\n"
            f"    токенов: {context_tokens}\n"
            f"Токенов использовано:\n"
            f"    input:  {tokens_total_input}\n"
            f"    output: {tokens_total_output}\n"
            f"Бот может отвечать в этом чате: {can_reply}\n"
        )
        return message

    async def get_users(self, bot: Bot) -> str:
        users = self.chat_manager.get_users()
        message = ""
        message += (
            f"Инфо:\n\n"
        )
        templ = (
            "Username: {username}\n"
            "ID пользователя: {user_id}\n"
            "Дата рег: {reg_date}\n"
            "Токены: {tokens}\n"
            "Токенов всего: {tokens_used}\n"
            "Чаты: {chats}\n"
        )
        infos = [
            templ.format(
                username=user["username"],
                user_id=user["user_id"],
                reg_date=user["dt_created"],
                tokens=user["tokens_balance"],
                tokens_used=self.chat_manager.get_tokens_used(user["user_id"]),
                chats=await self.chat_manager.get_user_chat_titles(user["user_id"], bot)
            ) for user in users
        ]
        message += "\n".join(infos)
        return message

    async def get_user_info_message(self, user_id: int, bot: Bot) -> str:
        user_info = self.chat_manager.get_user_info(user_id)
        chats_names = await self.chat_manager.get_user_chat_titles(user_id, bot)
        chats = ", ".join(map(str, chats_names))
        tokens = user_info["tokens_balance"]
        username = user_info["username"]
        reg_date = user_info["dt_created"]
        message = (
            f"Инфо:\n"
            f"\n"
            f"Username: {username}\n"
            f"ID пользователя: {user_id}\n"
            f"Дата рег: {reg_date}\n"
            f"Токены: {tokens}\n"
            f"Чаты: {chats}\n"
        )
        return message

    def new_private_chat(self, user_id: int, username: str, full_name: str):
        self.chat_manager.get_or_create_user(user_id, username, full_name)

    def new_group(self, user_id: int, username: str, full_name: str, chat_id: int, topic_id: int):
        self.chat_manager.get_or_create_user(user_id, username, full_name)
        self.chat_manager.get_or_create_chat_info(chat_id, user_id)


db_provider = MongoManager(settings.mongo_url)
chat_manager = ChatManager(db_provider)
message_repo = MessageRepository(db_provider)
llm_provider = LLMProvider(settings.anthropic_api_key)
message_processing_facade = MessageProcessingFacade(
    llm_provider=llm_provider,
    message_repo=message_repo,
    chat_manager=chat_manager,
)
