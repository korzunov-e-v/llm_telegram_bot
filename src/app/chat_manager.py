from contextlib import suppress

from anthropic.types import ModelParam
from telegram import Bot

from src.app.database import MongoManager
from src.config import settings
from src.models import MessageRecord, UserInfo, ChatInfo, TopicInfo, Settings, MessageModel


class ChatManager:
    def __init__(self, db_provider: MongoManager):  # todo: abstract
        self._db_provider = db_provider

    # ALLOWED_TOPICS
    def sync_get_allowed_topics(self, chat_id: int, user_id: int) -> list[int]:
        chat_info = self.sync_get_or_create_chat_info(chat_id, user_id)
        topics_dict = chat_info.allowed_topics
        return [int(k) for k, v in topics_dict.items() if v]

    async def get_allowed_topics(self, chat_id: int, user_id: int) -> list[int]:
        chat_info = await self.get_or_create_chat_info(chat_id, user_id)
        topics_dict = chat_info.allowed_topics
        return [int(k) for k, v in topics_dict.items() if v]

    async def add_allowed_topic(self, chat_id: int, topic_id: int, user_id: int) -> None:
        chat_info = await self.get_or_create_chat_info(chat_id, user_id)
        chat_info.allowed_topics[str(topic_id)] = True
        await self.update_chat_info(chat_info)

    async def remove_allowed_topics(self, chat_id: int, topic_id: int, user_id: int) -> bool:
        chat_info = await self.get_or_create_chat_info(chat_id, user_id)
        with suppress(KeyError):
            del chat_info.allowed_topics[str(topic_id)]
            await self.update_chat_info(chat_info)
            return True
        return False

    # CONTEXT
    async def get_context(self, chat_id: int, topic_id: int, offset: int = 0) -> list[MessageModel]:
        message_records: list[MessageRecord] = await self._db_provider.get_chat_message_records(
            chat_id=chat_id,
            topic_id=topic_id,
            offset=offset,
        )
        messages = [mes.message_param for mes in message_records]
        return messages

    async def clear_context(self, chat_id: int, topic_id: int) -> None:
        count = await self._db_provider.count_topic_messages(chat_id, topic_id)
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info.settings.offset = count
        await self.update_topic_info(topic_info)

    async def get_tokens_used(self, user_id: int) -> int:
        count = await self._db_provider.count_tokens_used(user_id)
        return count

    # TOPICS
    async def _create_new_topic(self, chat_id: int, topic_id: int) -> TopicInfo:
        topic_info = self.__get_default_chat_topic(chat_id, topic_id)
        await self._db_provider.add_topic(topic_info, chat_id)
        return topic_info

    async def get_or_create_topic_info(self, chat_id: int, topic_id: int) -> TopicInfo:
        topic_info = await self._db_provider.get_topic_info(chat_id, topic_id)
        if topic_info:
            return topic_info
        else:
            topic_info = await self._create_new_topic(chat_id, topic_id)
            return topic_info

    async def get_topic_settings(self, chat_id: int, topic_id: int) -> Settings:
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        return topic_info.settings

    async def update_topic_info(self, topic_info: TopicInfo) -> None:
        await self._db_provider.update_topic_info(topic_info, topic_info.chat_id)

    # USERS
    async def create_new_user(self, user_id: int, username: str, full_name: str) -> UserInfo:
        doc_user = self.__get_default_user_info(user_id, username, full_name)
        _doc_chat = await self.get_or_create_chat_info(user_id, user_id)
        _doc_topic = await self.get_or_create_topic_info(chat_id=user_id, topic_id=1)
        await self._db_provider.add_user(doc_user)
        return doc_user

    async def get_or_create_user(self, user_id: int, username: str, full_name: str) -> UserInfo:
        user_info = await self._db_provider.get_user_info(user_id)
        if user_info:
            return user_info
        else:
            return await self.create_new_user(user_id, username, full_name)

    async def get_user_info(self, user_id: int) -> UserInfo:
        user_info = await self._db_provider.get_user_info(user_id)
        if user_info:
            return user_info
        else:
            raise Exception(f"no user_info found: {user_id}")

    async def get_users(self) -> list[UserInfo]:
        users = await self._db_provider.get_users()
        return users

    async def update_user(self, user_info: UserInfo) -> None:
        await self._db_provider.update_user(user_info)

    # CHATS
    async def get_user_chat_infos(self, user_id: int) -> list[ChatInfo]:
        chat_infos = await self._db_provider.get_user_chat_infos(user_id)
        if chat_infos:
            return chat_infos
        else:
            raise Exception(f"no chat_info found: {user_id}")

    async def get_user_chat_titles(self, user_id: int, bot: Bot) -> list[str]:
        chat_infos = await self._db_provider.get_user_chat_infos(user_id)
        chats_names = []
        for chat_info in chat_infos:
            try:
                chat = await bot.get_chat(chat_info.chat_id)
                chat_name = chat.title if chat.title else chat.username
                chats_names.append(chat_name)
            except Exception:
                chats_names.append(chat_info.chat_id)
        return chats_names

    async def update_chat_info(self, chat_info: ChatInfo) -> None:
        await self._db_provider.update_chat_info(chat_info)

    def sync_get_or_create_chat_info(self, chat_id, user_id) -> ChatInfo:
        chat_info = self._db_provider.sync_get_chat_info(chat_id)
        if chat_info:
            return chat_info
        else:
            chat_info = self.sync_create_new_chat(chat_id, user_id)
            return chat_info

    async def get_or_create_chat_info(self, chat_id, user_id) -> ChatInfo:
        chat_info = await self._db_provider.get_chat_info(chat_id)
        if chat_info:
            return chat_info
        else:
            chat_info = await self.create_new_chat(chat_id, user_id)
            return chat_info

    def sync_create_new_chat(self, chat_id, user_id) -> ChatInfo:
        doc_chat = self.__get_default_user_chat_info(chat_id, user_id)
        self._db_provider.sync_add_chat(doc_chat)
        return doc_chat

    async def create_new_chat(self, chat_id, user_id) -> ChatInfo:
        doc_chat = self.__get_default_user_chat_info(chat_id, user_id)
        await self._db_provider.add_chat(doc_chat)
        return doc_chat

    # PROMPT
    async def set_system_prompt(self, prompt: str | None, chat_id: int, topic_id: int) -> None:
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info.settings.system_prompt = prompt
        await self.update_topic_info(topic_info)

    @staticmethod
    def format_system_prompt(prompt, short: bool = False) -> str:
        if prompt is None or prompt == "None" or prompt == "":
            return '<не задан>'
        if short:
            prompt = f"{prompt[:25]}...{prompt[-25:]}"
        return f'\n```\n{prompt}\n```'

    async def clear_system_prompt(self, chat_id: int, topic_id: int):
        await self.set_system_prompt(None, chat_id, topic_id)

    # TEMPERATURE
    async def set_temperature(self, temperature: float, chat_id: int, topic_id: int) -> None:
        temperature = float(temperature)
        if temperature and temperature > 1:
            temperature = 1
        elif temperature and temperature < 0:
            temperature = 0
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info.settings.temperature = temperature
        await self.update_topic_info(topic_info)

    async def reset_temperature(self, chat_id: int, topic_id: int) -> None:
        await self.set_temperature(settings.default_temperature, chat_id, topic_id)

    # MODEL
    async def change_model(self, chat_id: int, topic_id: int, model: ModelParam) -> None:
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info.settings.model = model
        await self.update_topic_info(topic_info)

    # _DEFAULTS
    @staticmethod
    def __get_default_user_info(user_id: int, username: str, full_name: str) -> UserInfo:
        doc: UserInfo = UserInfo.model_construct(
            user_id=user_id,
            username=username,
            full_name=full_name,
        )
        return doc

    @staticmethod
    def __get_default_user_chat_info(chat_id: int, owner_id: int) -> ChatInfo:
        doc = ChatInfo.model_construct(
            chat_id=chat_id,
            owner_user_id=owner_id,
        )
        return doc

    @staticmethod
    def __get_default_chat_topic(chat_id: int, topic_id: int) -> TopicInfo:
        doc = TopicInfo.model_construct(
            chat_id=chat_id,
            topic_id=topic_id,
            settings=Settings.model_construct(),
        )
        return doc
