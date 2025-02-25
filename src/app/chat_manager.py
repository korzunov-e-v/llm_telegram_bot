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
        topics_dict = chat_info["allowed_topics"]
        return [int(k) for k, v in topics_dict.items() if v]

    async def get_allowed_topics(self, chat_id: int, user_id: int) -> list[int]:
        chat_info = await self.get_or_create_chat_info(chat_id, user_id)
        topics_dict = chat_info["allowed_topics"]
        return [int(k) for k, v in topics_dict.items() if v]

    #     def set_allowed_topics(self, chat_id: int, topics: list[int]):
    #         user = self.get_user(chat_id)
    #         user["allowed_topics"] = {str(k): True for k, v in topics}
    #         self.update_user(user)

    async def add_allowed_topic(self, chat_id: int, topic_id: int, user_id: int) -> None:
        if topic_id is None:
            topic_id = 1
        chat_info = await self.get_or_create_chat_info(chat_id, user_id)
        chat_info["allowed_topics"][str(topic_id)] = True
        await self.update_chat_info(chat_info)

    async def remove_allowed_topics(self, chat_id: int, topic_id: int, user_id: int) -> bool:
        chat_info = await self.get_or_create_chat_info(chat_id, user_id)
        if topic_id is None:
            topic_id = 1
        with suppress(KeyError):
            del chat_info["allowed_topics"][str(topic_id)]
            await self.update_chat_info(chat_info)
            return True
        return False

    # CONTEXT
    async def get_context(self, chat_id: int, topic_id: int, offset: int = 0) -> list[MessageModel]:
        if topic_id is None:
            topic_id = 1
        message_records: list[MessageRecord] = await self._db_provider.get_chat_message_records(chat_id, topic_id, offset)
        messages = [mes["message_param"] for mes in message_records]
        return messages

    async def clear_context(self, chat_id: int, topic_id: int) -> None:
        if topic_id is None:
            topic_id = 1
        count = await self._db_provider.count_topic_messages(chat_id, topic_id)
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["offset"] = count
        await self.update_topic_info(topic_info)

    async def get_tokens_used(self, user_id: int):
        chat_infos = await self._db_provider.get_user_chat_infos(user_id)
        col_names = set()
        for chat_info in chat_infos:
            topics_ids = list(chat_info["allowed_topics"].keys())
            col_names.update(set(map(lambda x: f"{chat_info["chat_id"]}+{x}", topics_ids)))
        col_names.add(f"{user_id}+1")
        count = 0
        for col in col_names:
            collection = self._db_provider.messages_db.get_collection(col)
            col_results = collection.aggregate([
                {
                    '$group': {
                        '_id': None,
                        'total_from_prov': {'$sum': '$tokens_from_prov'},
                        'total_message': {'$sum': '$tokens_message'},
                    }
                }
            ]).to_list()
            for col_result in col_results:
                count += col_result["total_from_prov"] + col_result["total_message"]
        return count

    # TOPICS
    async def _create_new_topic(self, chat_id: int, topic_id: int):
        if topic_id is None:
            topic_id = 1
        topic_info = self.__get_default_chat_topic(chat_id, topic_id)
        await self._db_provider.add_topic(topic_info, chat_id)
        return topic_info

    async def get_or_create_topic_info(self, chat_id: int, topic_id: int):
        if topic_id is None:
            topic_id = 1
        topic_info = await self._db_provider.get_topic_info(chat_id, topic_id)
        if topic_info:
            return topic_info
        else:
            topic_info = await self._create_new_topic(chat_id, topic_id)
            return topic_info

    async def get_topic_settings(self, chat_id: int, topic_id: int) -> Settings:
        if topic_id is None:
            topic_id = 1
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        return topic_info["settings"]

    async def update_topic_info(self, topic_info: TopicInfo):
        await self._db_provider.update_topic_info(topic_info, topic_info["chat_id"])

    # USERS
    async def create_new_user(self, user_id: int, username: str, full_name: str):
        doc_user = self.__get_default_user_info(user_id, username, full_name)
        _doc_chat = await self.get_or_create_chat_info(user_id, user_id)
        _doc_topic = await self.get_or_create_topic_info(chat_id=user_id, topic_id=1)
        await self._db_provider.add_user(doc_user)
        return doc_user

    async def get_or_create_user(self, user_id: int, username: str, full_name: str):
        user_info = await self._db_provider.get_user_info(user_id)
        if user_info:
            return user_info
        else:
            await self.create_new_user(user_id, username, full_name)

    async def get_user_info(self, user_id: int) -> UserInfo:
        user_info = await self._db_provider.get_user_info(user_id)
        if user_info:
            return user_info
        else:
            raise Exception(f"no user_info found: {user_id}")

    async def get_users(self) -> list[UserInfo]:
        users = await self._db_provider.get_users()
        return users

    async def update_user(self, user_info: UserInfo):
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
                chat = await bot.get_chat(chat_info["chat_id"])
                chat_name = chat.title if chat.title else chat.username
                chats_names.append(chat_name)
            except Exception:
                chats_names.append(chat_info["chat_id"])
        return chats_names

    async def update_chat_info(self, chat_info: ChatInfo) -> None:
        await self._db_provider.update_chat_info(chat_info)

    def sync_get_or_create_chat_info(self, chat_id, user_id):
        chat_info = self._db_provider.sync_get_chat_info(chat_id)
        if chat_info:
            return chat_info
        else:
            chat_info = self.sync_create_new_chat(chat_id, user_id)
            return chat_info

    async def get_or_create_chat_info(self, chat_id, user_id):
        chat_info = await self._db_provider.get_chat_info(chat_id)
        if chat_info:
            return chat_info
        else:
            chat_info = await self.create_new_chat(chat_id, user_id)
            return chat_info

    def sync_create_new_chat(self, chat_id, user_id):
        doc_chat = self.__get_default_user_chat_info(chat_id, user_id)
        self._db_provider.sync_add_chat(doc_chat)
        return doc_chat

    async def create_new_chat(self, chat_id, user_id):
        doc_chat = self.__get_default_user_chat_info(chat_id, user_id)
        await self._db_provider.add_chat(doc_chat)
        return doc_chat

    # PROMPT
    async def set_system_prompt(self, prompt: str | None, chat_id: int, topic_id: int):
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["system_prompt"] = prompt
        await self.update_topic_info(topic_info)

    @staticmethod
    def format_system_prompt(prompt):
        if prompt is None or prompt == "None":
            return '<не задан>'
        return f'\n```\n{prompt}\n```'

    async def clear_system_prompt(self, chat_id: int, topic_id: int):
        if topic_id is None:
            topic_id = 1
        await self.set_system_prompt(None, chat_id, topic_id)

    # TEMPERATURE
    async def set_temperature(self, temperature: float, chat_id: int, topic_id: int) -> None:
        if topic_id is None:
            topic_id = 1
        temperature = float(temperature)
        if temperature and temperature > 1:
            temperature = 1
        elif temperature and temperature < 0:
            temperature = 0
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["temperature"] = temperature
        await self.update_topic_info(topic_info)

    async def reset_temperature(self, chat_id: int, topic_id: int):
        if topic_id is None:
            topic_id = 1
        await self.set_temperature(settings.default_temperature, chat_id, topic_id)

    # MODEL
    async def change_model(self, chat_id: int, topic_id: int, model: ModelParam) -> None:
        if topic_id is None:
            topic_id = 1
        topic_info = await self.get_or_create_topic_info(chat_id, topic_id)
        topic_info["settings"]["model"] = model
        await self.update_topic_info(topic_info)

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
        if topic_id is None:
            topic_id = 1
        doc = TopicInfo(
            chat_id=chat_id,
            topic_id=topic_id,
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
            md_v2_mode=True,
            parse_pdf=False,
        )
        return doc
