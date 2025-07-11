import asyncio
# import os
import re
from datetime import datetime, UTC
# from pathlib import Path

from telegram import Bot, Update
from telegram.ext import ContextTypes

from src.app.chat_manager import ChatManager
from src.app.database import MongoManager
from src.app.llm_provider import AnthropicLlmProvider, AbstractLlmProvider
from src.app.message_repo import MessageRepository
from src.config import settings
from src.models import MessageModel, LlmProviderSendResponse
from src.tools.log import get_logger
# from src.tools.pdf_tool import load_from_large_pdf

logger = get_logger(__name__)


class MessageProcessingFacade:
    def __init__(
        self,
        llm_provider: AbstractLlmProvider,
        chat_manager: ChatManager,
        message_repo: MessageRepository,
    ):
        self.llm_provider: AbstractLlmProvider = llm_provider
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
            topics = await self.chat_manager.get_allowed_topics(chat_id, user_id)
            if topic_id == 1:
                topic_id_send = 0
            else:
                topic_id_send = topic_id
            try:
                if topic_id in topics:
                    msg = await context.bot.send_message(
                        chat_id=chat_id,
                        text="Ping. Проверка что бот может писать в этот топик.",
                        message_thread_id=topic_id_send,
                    )
                    await update.message.reply_text(f"Бот и так добавлен в топик.")
                    await asyncio.sleep(30)
                    await msg.delete()
                    return
                await self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
                await self.chat_manager.add_allowed_topic(chat_id, topic_id, user_id)
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
        return "Not supported yet."
        # if topic_id is None:
        #     topic_id = 1
        # topic_info = await self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        # topic_settings = topic_info["settings"]
        #
        # filename = update.message.document.file_name
        # doc = await update.message.document.get_file(read_timeout=30, connect_timeout=30)
        # bo = bytearray()
        # await doc.download_as_bytearray(bo)
        # download_path = Path(f"tmp")
        # download_path.mkdir(exist_ok=True)
        # doc_path = download_path.joinpath(filename)
        # doc_path = await doc.download_to_drive(doc_path)
        # # pdf_data = base64.standard_b64encode(bo).decode("utf-8")
        #
        # context = await self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])
        #
        # txt = await load_from_large_pdf(doc_path)
        # os.remove(doc_path)
        # if not txt:
        #     return "Ошибка парсинга файла."
        # logger.info(f"parsed {doc_path}. txt_len={len(txt)}")

        ## todo: pdf anthropic
        ## if topic_settings.get("parse_pdf", True):
        ##     txt = await load_from_large_pdf(doc_path)
        ##     logger.info(f"parsed {doc_path}. txt_len={len(txt)}")
        ##     if not txt:
        ##         return "Ошибка парсинга файла."
        ##     os.remove(doc_path)
        ##     source = PlainTextSourceParam(data=txt, media_type="text/plain", type="text")
        ## else:
        ##     source = Base64PDFSourceParam(data=pdf_data, media_type="application/pdf", type="base64")
        ##
        ## user_doc_message = MessageParam(
        ##     content=[
        ##         DocumentBlockParam(
        ##             source=source,
        ##             type="document",
        ##             cache_control=CacheControlEphemeralParam(type="ephemeral"),
        ##             citations=CitationsConfigParam(enabled=True),
        ##         ),
        ##     ],
        ##     role="user"
        ## )
        ## user_message = MessageParam(content=[TextBlockParam(text=update.message.text or update.message.caption, type="text")], role="user")

        # txt = "Далее будет содержимое файла документа, по нему будут вопросы.\n\nPDF file content:\n\n\n" + txt
        # user_doc_message = MessageModel(content=txt, role="user")
        # user_message = MessageModel(content=update.message.text or update.message.caption, role="user")
        #
        # messages = context + [user_doc_message, user_message]
        # llm_resp = await self.send_messages(messages, user_id, chat_id, topic_id, cache=True)
        # # llm_resp_text = self.join_llm_response(llm_resp)  # todo: for anthropic citations
        # llm_resp_text = llm_resp["model_response"].parts[0].content
        # return llm_resp_text

    # todo: its for anthropic citations
    # @staticmethod
    # def join_llm_response(llm_resp: LlmProviderSendResponse) -> str:
    #     """With citations"""
    #     content = llm_resp["model_response"].parts[0].content
    #     result = ""
    #     for part in content:
    #         result += part.text.strip() + "\n"
    #         if part.citations:
    #             for cit in part.citations:
    #                 lines = cit.cited_text.split("\n")
    #                 text = "\n> ".join(lines)
    #                 result += '> ' + text + "\n\n"
    #         result = result.strip("> \n")
    #         result = result.strip()
    #         result += "\n\n"
    #     result = result.strip()
    #     result = re.sub("\n{2,}", "\n\n", result)
    #     result = re.sub("(> ?\n)*", "", result)
    #     return result

    async def send_messages(self, messages: list[MessageModel], user_id: int, chat_id: int, topic_id: int, cache: bool = None) -> LlmProviderSendResponse:
        if topic_id is None:
            topic_id = 1
        topic_info = await self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        topic_settings = topic_info["settings"]
        context = await self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])

        user_messages = []
        for i in messages[::-1]:
            if i["role"] == "user":
                user_messages.append(i)
            else:
                break
        user_messages = user_messages[::-1]
        input_sing_tokens_count = [await self.llm_provider.count_tokens(topic_settings["model"], [mes]) for mes in user_messages]

        # todo: cache
        # cache_used_in_context = False
        # for mes in context:
        #     for m in mes["content"]:
        #         if m.get("cache_control"):
        #             cache_used_in_context = True
        #             break
        #
        # if cache_used_in_context:
        #     messages[-1]["content"][0]["cache_control"] = {"type": "ephemeral"}

        u_dt = datetime.now(UTC)
        response = await self.llm_provider.send_messages(
            model=topic_settings["model"],
            messages=messages,
            user_id=user_id,
            system_prompt=topic_settings["system_prompt"],
            temp=topic_settings["temperature"],
            cache=cache,
        )

        a_dt = datetime.now(UTC)
        llm_message = MessageModel(
            content=response["model_response"].parts[0].content,
            role="assistant",
        )

        await self.message_repo.add_message_to_db(  # llm
            chat_id=chat_id,
            topic_id=topic_id,
            user_id=user_id,
            message=llm_message,
            context_n=0,
            model=response["model_response"].model_name,
            tokens_message=0,
            tokens_from_prov=response["usage"].response_tokens,
            timestamp=a_dt,
        )
        for i, mes in enumerate(user_messages):
            await self.message_repo.add_message_to_db(  # user
                chat_id=chat_id,
                topic_id=topic_id,
                user_id=user_id,
                message=mes,
                context_n=len(context),
                model=response["model_response"].model_name,
                tokens_message=input_sing_tokens_count[i],
                tokens_from_prov=response["usage"].request_tokens,
                timestamp=u_dt,
            )

        # todo: its for anthropic
        # if settings.debug:
        #     input_tokens = response.usage.input_tokens
        #     output_tokens = response.usage.output_tokens
        #     input_tokens_cache_read = getattr(response.usage, 'cache_read_input_tokens', '---')
        #     input_tokens_cache_create = getattr(response.usage, 'cache_creation_input_tokens', '---')
        #     print(f"User input tokens: {input_tokens}")
        #     print(f"Output tokens: {output_tokens}")
        #     print(f"Input tokens (cache read): {input_tokens_cache_read}")
        #     print(f"Input tokens (cache write): {input_tokens_cache_create}")
        #     total_input_tokens = input_tokens + (int(input_tokens_cache_read) if input_tokens_cache_read != '---' else 0)
        #     percentage_cached = (int(input_tokens_cache_read) / total_input_tokens * 100 if input_tokens_cache_read != '---' and total_input_tokens > 0 else 0)
        #     print(f"{percentage_cached:.1f}% of input prompt cached ({total_input_tokens} tokens)")

        return response

    async def process_txt_message(self, message_text: str, user_id: int, chat_id: int, topic_id: int) -> str:
        if topic_id is None:
            topic_id = 1
        topic_info = await self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        topic_settings = topic_info["settings"]
        context = await self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])

        user_message = MessageModel(
            content=message_text,
            role="user",
        )
        messages = context + [user_message]

        llm_resp = await self.send_messages(messages, user_id, chat_id, topic_id)
        # llm_resp_text = self.join_llm_response(llm_resp)  # todo: for anthropic citations
        llm_resp_text = llm_resp["model_response"].parts[0].content
        return llm_resp_text

    async def get_topic_info_message(self, chat_id: int, topic_id: int, user_id: int, bot: Bot, with_prompt: bool = True) -> str:
        if topic_id is None:
            topic_id = 1
        topic_settings = await self.chat_manager.get_topic_settings(chat_id, topic_id)
        chat = await bot.get_chat(chat_id)
        chat_name = chat.title if chat.title else chat.username
        messages_records = await self.message_repo.get_messages_from_db(chat_id, topic_id, offset=topic_settings["offset"])
        messages = await self.chat_manager.get_context(chat_id, topic_id, topic_settings["offset"])
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
            context_tokens = await self.llm_provider.count_tokens(topic_settings["model"], messages)
        except Exception:
            context_tokens = "<error>"
            logger.error(f"context was broken. {user_id=} {chat_id=} {topic_id=} {topic_settings["offset"]=}")
        allowed_topics = await self.chat_manager.get_allowed_topics(chat_id, user_id)
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
        users = await self.chat_manager.get_users()
        message = f"Инфо:\n\n"
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
                tokens_used=await self.chat_manager.get_tokens_used(user["user_id"]),
                chats=await self.chat_manager.get_user_chat_titles(user["user_id"], bot)
            ) for user in users
        ]
        message += "\n".join(infos)
        return message

    async def get_user_info_message(self, user_id: int, bot: Bot) -> str:
        user_info = await self.chat_manager.get_user_info(user_id)
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

    async def new_private_chat(self, user_id: int, username: str, full_name: str):
        await self.chat_manager.get_or_create_user(user_id, username, full_name)

    async def new_group(self, user_id: int, username: str, full_name: str, chat_id: int):
        await self.chat_manager.get_or_create_user(user_id, username, full_name)
        await self.chat_manager.get_or_create_chat_info(chat_id, user_id)


db_provider_instance = MongoManager(settings.mongo_url)
chat_manager_instance = ChatManager(db_provider_instance)
message_repo_instance = MessageRepository(db_provider_instance)
llm_provider_instance = AnthropicLlmProvider(api_key=settings.anthropic_api_key)
message_processing_facade = MessageProcessingFacade(
    llm_provider=llm_provider_instance,
    message_repo=message_repo_instance,
    chat_manager=chat_manager_instance,
)
