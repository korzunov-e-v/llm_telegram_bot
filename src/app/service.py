import asyncio
import traceback
from datetime import datetime, UTC, timedelta

from telegram import Bot, InlineKeyboardMarkup, Update

from src.app.chat_manager import ChatManager
from src.app.database import MongoManager
from src.app.llm_provider import get_llm_provider, BaseLlmProvider
from src.app.message_repo import MessageRepository
from src.config import settings
from src.models import MessageModel, LlmProviderSendResponse
from src.tools.chat_state import get_state_key, state, ChatState
from src.tools.log import get_logger
from src.tools.message_queue import messages_queue, get_queue_key
from src.tools.pagination import build_list_keyboard, PageItem
from src.tools.update_getters import UpdateInfo

logger = get_logger(__name__)


class MessageProcessingFacade:
    def __init__(
        self,
        llm_provider: BaseLlmProvider,
        chat_manager: ChatManager,
        message_repo: MessageRepository,
    ):
        self.llm_provider: BaseLlmProvider = llm_provider
        self.chat_manager: ChatManager = chat_manager
        self.message_repo: MessageRepository = message_repo

    async def new_text_message(self, update_info: UpdateInfo, update: Update) -> str | None:
        state_key = get_state_key(update_info.chat_id, update_info.topic_id)
        queue_key = get_queue_key(update_info.user_id, update_info.topic_id)

        if state.get(state_key) == ChatState.TEMPERATURE:
            reply_text = await self.temperature_command(update_info)
            return reply_text

        messages_queue[queue_key].append((update_info.msg_text, datetime.now(UTC)))
        if len(messages_queue[queue_key]) == 1:
            if state.get(state_key) == ChatState.PROMPT:
                reply_text = await self.delay_prompt(update_info)
                return reply_text
            else:
                msg = await update.message.reply_text("Пишет...")
                reply_text = await self.delay_send(update_info)
                await msg.delete()
                return reply_text
        return None

    async def send_message(
        self,
        message_text: str,
        user_id: int,
        chat_id: int,
        topic_id: int,
        cache: bool = None,
    ) -> str:
        llm_resp = await self._send_message(message_text, user_id, chat_id, topic_id, cache)
        llm_resp_text = self._get_llm_resp_str(llm_resp)
        return llm_resp_text

    async def _send_message(
        self,
        message_text: str,
        user_id: int,
        chat_id: int,
        topic_id: int,
        cache: bool = None,
    ) -> LlmProviderSendResponse:
        if topic_id is None:
            topic_id = 1
        topic_info = await self.chat_manager.get_or_create_topic_info(chat_id, topic_id)
        topic_settings = topic_info.settings
        context = await self.chat_manager.get_context(chat_id, topic_id, topic_settings.offset)
        user_message = MessageModel(
            content=message_text,
            role="user",
        )
        messages = context + [user_message]

        u_dt = datetime.now(UTC)
        response = await self.llm_provider.send_messages(
            model=topic_settings.model,
            messages=messages,
            user_id=user_id,
            system_prompt=topic_settings.system_prompt,
            temp=topic_settings.temperature,
            cache=cache,
        )

        a_dt = datetime.now(UTC)
        input_sing_tokens_count = await self.llm_provider.count_tokens(topic_settings.model, messages)
        llm_message = MessageModel(
            content=response.model_response.parts[0].content,
            role="assistant",
        )

        await self.message_repo.add_message_to_db(  # llm
            chat_id=chat_id,
            topic_id=topic_id,
            user_id=user_id,
            message=llm_message,
            context_n=0,
            model=response.model_response.model_name,
            tokens_message=0,
            tokens_from_prov=response.usage.response_tokens,
            timestamp=a_dt,
        )
        await self.message_repo.add_message_to_db(  # user
            chat_id=chat_id,
            topic_id=topic_id,
            user_id=user_id,
            message=user_message,
            context_n=len(context),
            model=response.model_response.model_name,
            tokens_message=input_sing_tokens_count,
            tokens_from_prov=response.usage.request_tokens,
            timestamp=u_dt,
        )
        return response

    @staticmethod
    def _get_llm_resp_str(llm_resp: LlmProviderSendResponse) -> str:
        return llm_resp.model_response.parts[0].content

    async def get_topic_info_message(
        self,
        chat_id: int,
        topic_id: int,
        user_id: int,
        chat_name: str,
    ) -> str:
        topic_settings = await self.chat_manager.get_topic_settings(chat_id, topic_id)

        messages_records = await self.message_repo.get_messages_from_db(chat_id, topic_id, offset=topic_settings.offset)
        messages = await self.chat_manager.get_context(chat_id, topic_id, topic_settings.offset)
        model = topic_settings.model
        prompt = self.chat_manager.format_system_prompt(topic_settings.system_prompt, short=True)
        temperature = topic_settings.temperature
        context_len = len(messages)
        try:
            context_tokens = await self.llm_provider.count_tokens(topic_settings.model, messages)
        except Exception:
            context_tokens = "<error>"
            logger.error(f"context was broken. {user_id=} {chat_id=} {topic_id=} {topic_settings.offset=}")
        allowed_topics = await self.chat_manager.get_allowed_topics(chat_id, user_id)
        tokens_total_input = sum(
            [
                mes.tokens_message + mes.tokens_from_prov
                for mes in messages_records
                if mes.message_param.role == "user"
            ]
        )
        tokens_total_output = sum(
            [
                mes.tokens_message + mes.tokens_from_prov
                for mes in messages_records
                if mes.message_param.role == "assistant"
            ]
        )
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
                username=user.username,
                user_id=user.user_id,
                reg_date=user.dt_created,
                tokens=user.tokens_balance,
                tokens_used=await self.chat_manager.get_tokens_used(user.user_id),
                chats=await self.chat_manager.get_user_chat_titles(user.user_id, bot),
            ) for user in users
        ]
        message += "\n".join(infos)
        return message

    async def get_user_info_message(self, user_id: int, bot: Bot) -> str:
        user_info = await self.chat_manager.get_user_info(user_id)
        chats_names = await self.chat_manager.get_user_chat_titles(user_id, bot)
        chats = ", ".join(map(str, chats_names))
        tokens = user_info.tokens_balance
        username = user_info.username
        reg_date = user_info.dt_created
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

    async def new_private_chat(self, user_id: int, username: str, full_name: str) -> None:
        await self.chat_manager.get_or_create_user(user_id, username, full_name)

    async def new_group(self, user_id: int, username: str, full_name: str, chat_id: int) -> None:
        await self.chat_manager.get_or_create_user(user_id, username, full_name)
        await self.chat_manager.get_or_create_chat_info(chat_id, user_id)

    async def start(self, update_info: UpdateInfo) -> str:
        await self.chat_manager.get_or_create_user(update_info.user_id, update_info.username, update_info.full_name)
        allowed_topics = await self.chat_manager.get_allowed_topics(update_info.chat_id, update_info.user_id)
        if update_info.topic_id in allowed_topics:
            return "Бот уже тут."
        else:
            await self.chat_manager.add_allowed_topic(update_info.chat_id, update_info.topic_id, update_info.user_id)
            return "Бот добавлен в чат."

    async def stop(self, update_info: UpdateInfo) -> str:
        res = await self.chat_manager.remove_allowed_topics(update_info.chat_id, update_info.topic_id, update_info.user_id)
        if not res:
            return "Не ожидалось этой команды."
        return "Покинул топик. Чтобы добавить снова, отправьте ссылку-приглашение боту в лc.\nИли отправьте /start в этот чат."

    async def hello(self, update_info: UpdateInfo) -> str:
        try:
            response = await self.llm_provider.ping()
            llm_resp = response.model_response.parts[0].content
            return f'tg: Hello {update_info.username}\nllm: {llm_resp}'
        except Exception as e:
            logger.error("hello command error: ", exc_info=e)
            logger.error(traceback.format_exc())
            return f'tg: Hello {update_info.username}\nllm: <error>'

    async def get_providers_keyboard(self, page: int = 0) -> InlineKeyboardMarkup:
        """
        Создаёт клавиатуру с пагинацией со списком провайдеров моделей.

        :param page: страница пагинации.
        :return: клавиатура InlineKeyboardMarkup.
        """
        providers = await self.llm_provider.get_providers_models()
        providers_page_items = [PageItem(cb_data=p, display_name=f"{p}"[:63]) for p in providers.keys()]
        reply_markup = build_list_keyboard(
            items=providers_page_items,
            page=page,
            # per_page=98,
            per_page=8,
            item_cb_prefix="provider",
            page_cb_prefix="providers",
        )
        return reply_markup

    async def get_provider_models_keyboard(self, provider: str, page: int = 0) -> InlineKeyboardMarkup:
        """
        Создаёт клавиатуру с пагинацией со списком моделей от провайдера.

        :param provider: id провайдера (anthropic, openai, z-ai, mistralai).
        :param page: страница пагинации.
        :return: клавиатура InlineKeyboardMarkup.
        """
        providers = await self.llm_provider.get_providers_models()
        providers_page_items = [
            PageItem(cb_data=p.id_hash, display_name=f"{p.name} | {p.id}"[:63])
            for p in providers[provider]
        ]
        reply_markup = build_list_keyboard(
            items=providers_page_items,
            page=page,
            # per_page=98,
            per_page=8,
            item_cb_prefix="change_model",
            page_cb_prefix=f"provider+{provider}",
            back_button_cb="providers+0"
        )
        return reply_markup

    async def get_models_keyboard(self, page: int = 0) -> InlineKeyboardMarkup:
        """
        Создаёт клавиатуру с пагинацией со списком всех доступных моделей.

        :param page: страница пагинации.
        :return: клавиатура InlineKeyboardMarkup.
        """
        models = await self.llm_provider.get_models()
        models_page_items = [PageItem(cb_data=m.id_hash, display_name=f"{m.name} | {m.id}"[:62]) for m in models]
        models.sort(key=lambda x: x.created, reverse=True)

        reply_markup = build_list_keyboard(
            items=models_page_items,
            page=page,
            # per_page=98,
            per_page=8,
            item_cb_prefix="change_model",
            page_cb_prefix="models",
        )
        return reply_markup

    async def change_model(self, update_info: UpdateInfo, model_hash: str) -> str:
        model_name = await self.llm_provider.get_model_id_by_hash(model_hash)
        await self.chat_manager.change_model(update_info.chat_id, update_info.topic_id, model_name)
        return model_name

    async def prompt_command(self, update_info: UpdateInfo) -> str:
        state[get_state_key(update_info.chat_id, update_info.topic_id)] = ChatState.PROMPT
        topic_settings = await self.chat_manager.get_topic_settings(update_info.chat_id, update_info.topic_id)
        current_prompt = topic_settings.system_prompt
        resp_text = ('Отправьте новый промпт, /cancel для отмены или /empty для сброса промпта.\n'
                     f'Текущий промпт: {self.chat_manager.format_system_prompt(current_prompt)}')
        return resp_text

    async def temperature_command(self, update_info: UpdateInfo) -> str:
        state_key = get_state_key(update_info.chat_id, update_info.topic_id)
        current_state = state.get(state_key, None)

        if current_state == ChatState.TEMPERATURE:
            new_temp = update_info.msg_text
            try:
                new_temp = float(new_temp.replace(",", "."))
                await self.chat_manager.set_temperature(new_temp, update_info.chat_id, update_info.topic_id)
                del state[state_key]
                return "Температура установлена."
            except (ValueError, AttributeError):
                return "Ошибка. Отправьте температуру числом. Например `0.6`."
        else:
            state[get_state_key(update_info.chat_id, update_info.topic_id)] = ChatState.TEMPERATURE
            topic_settings = await self.chat_manager.get_topic_settings(update_info.chat_id, update_info.topic_id)
            return ('Отправьте значение температуры (креативность/непредсказуемость модели), /cancel для отмены или /empty для сброса.\n'
                    'Более низкие температуры приводят к более предсказуемым и целенаправленным реакциям, в то время как более высокие '
                    'температуры привносят больше случайности и креативности.\n\n'
                    f'Текущая температура: {topic_settings.temperature}\n'
                    f'Температура по-умолчанию: {settings.default_temperature}')

    async def delay_send(self, update_info: UpdateInfo) -> str:
        """
        Отложенная отправка сообщений. После первого сообщения в чате/топике ожидает новые сообщения в этот же чат.
        После n секунд с последнего сообщения собирает все в одно и отправляет в ллм.

        Клиент телеграм разделяет большие сообщения при отправке на меньшие, из-за этого
        в ллм отправлялась обрезанная версия, а вслед вторая часть.

        :param update_info: username, full_name, user_id, chat_id, topic_id, msg_text, etc...
        :return: Текст ответа ллм.
        """
        queue_key = get_queue_key(update_info.user_id, update_info.topic_id)
        messages = await self.wait_messages(queue_key)
        message = "\n".join(messages)

        llm_resp_text = await self.send_message(message, update_info.user_id, update_info.chat_id, update_info.topic_id)
        return llm_resp_text

    async def delay_prompt(self, update_info: UpdateInfo) -> str:
        """
        Отложенное задание промпта. После первого сообщения в чате/топике ожидает новые сообщения в этот же чат.
        После n секунд с последнего сообщения собирает все в одно и записывает в настройку промпта.

        Клиент телеграм разделяет большие сообщения при отправке на меньшие, из-за этого
        в настройки попадала обрезанная версия, а вторая часть отправлялась в ллм как сообщение.

        :param update_info: username, full_name, user_id, chat_id, topic_id, msg_text, etc...
        :return: Сообщение что промпт установлен.
        """
        queue_key = get_queue_key(update_info.user_id, update_info.topic_id)
        state_key = get_state_key(update_info.chat_id, update_info.topic_id)

        messages = await self.wait_messages(queue_key)
        message = "\n".join(messages)

        await self.chat_manager.set_system_prompt(message, update_info.chat_id, update_info.topic_id)
        del state[state_key]
        return "Промпт установлен."

    @staticmethod
    async def wait_messages(queue_key: str, delay_seconds: int = settings.wait_new_message_sec) -> list[str]:
        """
        Ожидание новых сообщений в очереди `delay_seconds` секунд.

        :param queue_key: Ключ для очереди сообщений топика, src.tools.message_queue.get_queue_key(user_id, topic_id)
        :param delay_seconds: Сколько секунд ждать после последнего сообщения
        :return: Список текстов сообщений
        """
        while datetime.now(UTC) - messages_queue[queue_key][-1][1] < timedelta(seconds=delay_seconds):
            await asyncio.sleep(0.3)
        messages = messages_queue[queue_key]
        del messages_queue[queue_key]
        return [mes[0] for mes in messages]


db_provider_instance = MongoManager(settings.mongo_url)
chat_manager_instance = ChatManager(db_provider_instance)
message_repo_instance = MessageRepository(db_provider_instance)
llm_provider_instance = get_llm_provider(settings.llm_provider_type, settings.llm_api_key)

message_processing_facade = MessageProcessingFacade(
    llm_provider=llm_provider_instance,
    message_repo=message_repo_instance,
    chat_manager=chat_manager_instance,
)
