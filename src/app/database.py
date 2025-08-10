import datetime

from pymongo import MongoClient

from src.models import MessageRecord, UserInfo, ChatInfo, TopicInfo
from src.tools.log import get_logger


class MongoManager:
    def __init__(self, url: str):
        self.logger = get_logger(__name__)
        self._client = MongoClient(url, connect=True, connectTimeoutMS=5000)
        self.users_db = self._client.get_database("users")
        self.topics_db = self._client.get_database("topics")
        self.messages_db = self._client.get_database("messages")
        self.user_info_collection = self.users_db.get_collection("user_infos")
        self.chat_info_collection = self.users_db.get_collection("chat_infos")
        self.logger.info(f"users in db: {self.user_info_collection.count_documents({})}")

    # MESSAGES
    async def get_chat_message_records(
        self,
        chat_id: int,
        topic_id: int,
        offset: int = 0,
        sort=None,
    ) -> list[MessageRecord]:
        assert isinstance(chat_id, int)
        assert isinstance(topic_id, int)
        assert isinstance(offset, int)
        assert isinstance(sort, dict | None)
        collection_name = self.__get_mes_col_name(chat_id, topic_id)
        if sort is None:
            sort = {"timestamp": 1}
        col_mes = self.messages_db.get_collection(collection_name)
        messages_res = col_mes.find().sort(sort).skip(offset).to_list()
        messages = [MessageRecord.model_validate(doc) for doc in messages_res]
        return messages

    async def add_chat_message_record(self, message_record: MessageRecord, chat_id: int, topic_id: int) -> None:
        assert isinstance(message_record, MessageRecord)
        assert isinstance(chat_id, int)
        assert isinstance(topic_id, int)
        collection_name = self.__get_mes_col_name(chat_id, topic_id)
        col_mes = self.messages_db.get_collection(collection_name)
        col_mes.insert_one(document=message_record.model_dump())

    async def count_topic_messages(self, chat_id: int, topic_id: int, offset: int = 0) -> int:
        assert isinstance(chat_id, int)
        assert isinstance(topic_id, int)
        assert isinstance(offset, int)
        collection_name = self.__get_mes_col_name(chat_id, topic_id)
        col_mes = self.messages_db.get_collection(collection_name)
        count = col_mes.count_documents({})
        return count - offset

    async def count_tokens_used(self, user_id: int) -> int:
        chat_infos = await self.get_user_chat_infos(user_id)
        col_names = set()
        for chat_info in chat_infos:
            topics_ids = list(chat_info.allowed_topics.keys())
            col_names.update(set(map(lambda x: f"{chat_info.chat_id}+{x}", topics_ids)))
        col_names.add(f"{user_id}+1")
        count = 0
        for col in col_names:
            collection = self.messages_db.get_collection(col)
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

    # USERS
    async def add_user(self, user_info: UserInfo) -> None:
        assert isinstance(user_info, UserInfo)
        user_info.dt_created = datetime.datetime.now(datetime.UTC)
        user_info.is_admin = False
        self.logger.info(f"user created: {user_info}")
        self.user_info_collection.insert_one(user_info.model_dump())

    async def get_user_info(self, user_id: int) -> UserInfo | None:
        assert isinstance(user_id, int)
        user_info_list = self.user_info_collection.find({"user_id": user_id}).to_list()
        if user_info_list:
            return UserInfo.model_validate(user_info_list[0])
        return None

    async def get_users(self) -> list[UserInfo] | None:
        user_info_list = self.user_info_collection.find().to_list()
        if user_info_list:
            return [UserInfo.model_validate(user) for user in user_info_list]
        return None

    async def update_user(self, user_info: UserInfo) -> None:
        assert isinstance(user_info, UserInfo)
        self.user_info_collection.replace_one({"_id": user_info.id}, user_info.model_dump())

    # CHATS
    def sync_add_chat(self, chat_info: ChatInfo) -> None:
        assert isinstance(chat_info, ChatInfo)
        self.logger.info(f"chat created: {chat_info}")
        self.chat_info_collection.insert_one(chat_info.model_dump())

    async def add_chat(self, chat_info: ChatInfo) -> None:
        assert isinstance(chat_info, ChatInfo)
        self.logger.info(f"chat created: {chat_info}")
        self.chat_info_collection.insert_one(chat_info.model_dump())

    def sync_get_chat_info(self, chat_id: int) -> ChatInfo | None:
        assert isinstance(chat_id, int)
        chat_info_list = self.chat_info_collection.find({"chat_id": chat_id}).to_list()
        if chat_info_list:
            return ChatInfo.model_validate(chat_info_list[0])
        return None

    async def get_chat_info(self, chat_id: int) -> ChatInfo | None:
        assert isinstance(chat_id, int)
        chat_info_list = self.chat_info_collection.find({"chat_id": chat_id}).to_list()
        if chat_info_list:
            return ChatInfo.model_validate(chat_info_list[0])
        return None

    async def get_user_chat_infos(self, user_id: int) -> list[ChatInfo] | None:
        assert isinstance(user_id, int)
        chat_info_list = self.chat_info_collection.find({"owner_user_id": user_id}).to_list()
        if chat_info_list:
            return [ChatInfo.model_validate(info) for info in chat_info_list]
        return None

    async def update_chat_info(self, chat_info: ChatInfo) -> None:
        assert isinstance(chat_info, ChatInfo)
        self.chat_info_collection.replace_one({"_id": chat_info.id}, chat_info.model_dump())

    # TOPICS
    async def add_topic(self, topic_info: TopicInfo, chat_id: int) -> None:
        assert isinstance(topic_info, TopicInfo)
        assert isinstance(chat_id, int)
        self.logger.info(f"topic created: {topic_info}")
        col = self.topics_db.get_collection(str(chat_id))
        col.insert_one(topic_info.model_dump())

    async def get_topic_info(self, chat_id: int, topic_id: int) -> TopicInfo | None:
        assert isinstance(chat_id, int)
        assert isinstance(topic_id, int)
        col = self.topics_db.get_collection(str(chat_id))
        topic_info_list = col.find({"topic_id": topic_id}).to_list()
        if topic_info_list:
            return TopicInfo.model_validate(topic_info_list[0])
        return None

    async def update_topic_info(self, topic_info: TopicInfo, chat_id: int) -> None:
        assert isinstance(topic_info, TopicInfo)
        assert isinstance(chat_id, int)
        col = self.topics_db.get_collection(str(chat_id))
        col.replace_one({"_id": topic_info.id}, topic_info.model_dump())

    @staticmethod
    def __get_mes_col_name(chat_id: int, topic_id: int) -> str:
        if topic_id is None:
            topic_id = 1
        return f"{chat_id}+{topic_id}"
