from contextlib import suppress

from anthropic.types import MessageParam, ModelParam
from telegram import Bot

from src.config import settings
from src.models import MessageRecord, UserInfo, ChatInfo, TopicInfo, Settings
from src.app.database import MongoManager


class ChatManager:
    def __init__(self, db_provider: MongoManager):  # todo: abstract
        self._db_provider = db_provider

    # ALLOWED_TOPICS
    def get_allowed_topics(self, chat_id: int, user_id: int) -> list[int]:
        chat_info = self.get_or_create_chat_info(chat_id, user_id)
        topics_dict = chat_info["allowed_topics"]
        return [int(k) for k, v in topics_dict.items() if v]

#     def set_allowed_topics(self, chat_id: int, topics: list[int]):
#         user = self.get_user(chat_id)
#         user["allowed_topics"] = {str(k): True for k, v in topics}
#         self.update_user(user)

    def add_allowed_topic(self, chat_id: int, topic_id: int, user_id: int) -> None:
        chat_info = self.get_or_create_chat_info(chat_id, user_id)
        chat_info["allowed_topics"][str(topic_id)] = True
        self.update_chat_info(chat_info)

    def remove_allowed_topics(self, chat_id: int, topic_id: int, user_id: int) -> bool:
        chat_info = self.get_or_create_chat_info(chat_id, user_id)
        with suppress(KeyError):
            del chat_info["allowed_topics"][str(topic_id)]
            self.update_chat_info(chat_info)
            return True
        return False

    # CONTEXT
    def get_context(self, chat_id: int, topic_id: int, offset: int = 0) -> list[MessageParam]:
        message_records: list[MessageRecord] = self._db_provider.get_chat_message_records(chat_id, topic_id, offset)
        messages = [mes["message_param"] for mes in message_records]
        return messages

    def clear_context(self, chat_id: int, topic_id: int) -> None:
        count = self._db_provider.count_topic_messages(chat_id, topic_id)
        topic_info = self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["offset"] = count
        self.update_topic_info(topic_info)

    def get_tokens_used(self, user_id: int):
        collections = self._db_provider.messages_db.list_collections(filter={'name': {'$regex': f'^{user_id}'}}).to_list()
        count = 0
        for col in collections:
            collection = self._db_provider.messages_db.get_collection(col["name"])
            total_tokens = collection.aggregate([
                {'$group': {'_id': None, 'total': {'$sum': '$tokens_from_prov'}}}
            ]).next()['total']
            count += total_tokens
        return count

    # TOPICS
    def _create_new_topic(self, chat_id: int, topic_id: int):
        topic_info = self.__get_default_chat_topic(chat_id, topic_id)
        self._db_provider.add_topic(topic_info, chat_id)
        return topic_info

    def get_or_create_topic_info(self, chat_id: int, topic_id: int):
        topic_info = self._db_provider.get_topic_info(chat_id, topic_id)
        if topic_info:
            return topic_info
        else:
            topic_info = self._create_new_topic(chat_id, topic_id)
            return topic_info

    def get_topic_settings(self, chat_id: int, topic_id: int) -> Settings:
        topic_info = self.get_or_create_topic_info(chat_id, topic_id)
        return topic_info["settings"]

    def update_topic_info(self, topic_info: TopicInfo):
        self._db_provider.update_topic_info(topic_info, topic_info["chat_id"])

    # USERS
    def create_new_user(self, user_id: int, username: str, full_name: str):
        doc_user = self.__get_default_user_info(user_id, username, full_name)
        _doc_chat = self.get_or_create_chat_info(user_id, user_id)
        _doc_topic = self.get_or_create_topic_info(chat_id=user_id, topic_id=1)
        self._db_provider.add_user(doc_user)
        return doc_user

    def get_or_create_user(self, user_id: int, username: str, full_name: str):
        user_info = self._db_provider.get_user_info(user_id)
        if user_info:
            return user_info
        else:
            self.create_new_user(user_id, username, full_name)

    def get_user_info(self, user_id: int) -> UserInfo:
        user_info = self._db_provider.get_user_info(user_id)
        if user_info:
            return user_info
        else:
            raise Exception(f"no user_info found: {user_id}")

    def get_users(self) -> list[UserInfo]:
        users = self._db_provider.get_users()
        return users

    def update_user(self, user_info: UserInfo):
        self._db_provider.update_user(user_info)

    # CHATS
    def get_user_chat_infos(self, user_id: int) -> list[ChatInfo]:
        chat_infos = self._db_provider.get_user_chat_infos(user_id)
        if chat_infos:
            return chat_infos
        else:
            raise Exception(f"no chat_info found: {user_id}")

    async def get_user_chat_titles(self, user_id: int, bot: Bot) -> list[str]:
        chat_infos = self._db_provider.get_user_chat_infos(user_id)
        chats_names = []
        for chat_info in chat_infos:
            try:
                chat = await bot.get_chat(chat_info["chat_id"])
                chat_name = chat.title if chat.title else chat.username
                chats_names.append(chat_name)
            except:
                chats_names.append(chat_info["chat_id"])
        return chats_names

    def update_chat_info(self, chat_info: ChatInfo) -> None:
        self._db_provider.update_chat(chat_info)

    def get_or_create_chat_info(self, chat_id, user_id):
        chat_info = self._db_provider.get_chat_info(chat_id)
        if chat_info:
            return chat_info
        else:
            chat_info = self.create_new_chat(chat_id, user_id)
            return chat_info

    def create_new_chat(self, chat_id, user_id):
        doc_chat = self.__get_default_user_chat_info(chat_id, user_id)
        self._db_provider.add_chat(doc_chat)
        return doc_chat

    # PROMPT
    def set_system_prompt(self, prompt: str | None, chat_id: int, topic_id: int):
        topic_info = self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["system_prompt"] = prompt
        self.update_topic_info(topic_info)

    @staticmethod
    def format_system_prompt(prompt):
        if prompt is None or prompt == "None":
            return '<не задан>'
        return f'\n```\n{prompt}\n```'

    def clear_system_prompt(self, chat_id: int, topic_id: int):
        self.set_system_prompt(None, chat_id, topic_id)

    # TEMPERATURE
    def set_temperature(self, temperature: float, chat_id: int, topic_id: int) -> None:
        temperature = float(temperature)
        if temperature and temperature > 1:
            temperature = 1
        elif temperature and temperature < 0:
            temperature = 0
        topic_info = self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["temperature"] = temperature
        self.update_topic_info(topic_info)

    def reset_temperature(self, chat_id: int, topic_id: int):
        self.set_temperature(settings.default_temperature, chat_id, topic_id)

    # MODEL
    def change_model(self, chat_id: int, topic_id: int, model: ModelParam) -> None:
        topic_info = self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["model"] = model
        self.update_topic_info(topic_info)

    # _DEFAULTS
    @staticmethod
    def __get_default_user_info(user_id: int, username: str, full_name: str) -> UserInfo:
        doc: UserInfo = UserInfo(
            user_id=user_id,
            username=username,
            full_name=full_name,
            tokens_balance=0,
        )
        return doc

    @staticmethod
    def __get_default_user_chat_info(chat_id: int, owner_id: int) -> ChatInfo:
        doc = ChatInfo(
            chat_id=chat_id,
            owner_user_id=owner_id,
            allowed_topics=dict(),
        )
        return doc

    def __get_default_chat_topic(self, chat_id: int, topic_id: int) -> TopicInfo:
        doc = TopicInfo(
            chat_id=chat_id,
            topic_id=topic_id or 1,
            settings=self.__get_default_topic_settings(),
        )
        return doc

    @staticmethod
    def __get_default_topic_settings() -> Settings:
        doc = Settings(
            offset=0,
            model=settings.default_model,
            system_prompt=None,
            temperature=settings.default_temperature,
        )
        return doc
