from pymongo import MongoClient

from src.models import MessageRecord, UserInfo
from src.tools.custom_logging import get_logger


class MongoManager:
    def __init__(self, url: str):
        self.logger = get_logger(__name__)
        self._client = MongoClient(url, connect=True, connectTimeoutMS=5000)
        self.users_db = self._client.get_database("users")
        self.messages_db = self._client.get_database("messages")
        self.users_collection = self.users_db.get_collection("user_infos")
        self.chats_collection = self.users_db.get_collection("chat_infos")
        self.logger.info(f"users in db: {self.users_collection.count_documents({})}")

    def get_chat_message_records(self, chat_id: int, offset: int, sort=None) -> list[MessageRecord]:
        if sort is None:
            sort = {"timestamp": 1}
        col_mes = self.messages_db.get_collection(str(chat_id))
        messages_res: list[MessageRecord] = col_mes.find().sort(sort).skip(offset).to_list()
        return messages_res

    def add_chat_message_record(self, chat_id: int, message_record: MessageRecord) -> None:
        col = self.messages_db.get_collection(str(chat_id))
        col.insert_one(document=message_record)

    def count_chat_messages(self, chat_id: int, offset: int = 0) -> int:
        col_mes = self.messages_db.get_collection(str(chat_id))
        count = col_mes.count_documents({})
        return count - offset

    def get_user(self, user_id: int) -> UserInfo | None:
        user_info_list = self.users_collection.find({"user_id": str(user_id)}).to_list()
        if user_info_list:
            return user_info_list[0]
        return None

    def get_chat_info(self, user_id: int) -> UserInfo | None:
        user_info_list = self.users_collection.find({"user_id": str(user_id)}).to_list()
        if user_info_list:
            return user_info_list[0]
        return None

    def add_user(self, user_info: UserInfo) -> None:
        self.users_collection.insert_one(user_info)

    def update_user(self, user_info: UserInfo) -> None:
        self.users_collection.replace_one({"_id": user_info["_id"]}, user_info)
