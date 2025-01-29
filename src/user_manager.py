import os

from anthropic.types import MessageParam, ModelParam
from pymongo import MongoClient

from src.tools.custom_logging import get_logger
from src.models import UserInfo, MessageRecord

mongo_url = os.getenv("MONGO_URL")


class UserManager:
    default_model = "claude-3-haiku-latest"
    default_temperature = 0.7

    def __init__(self):
        self.logger = get_logger(__name__)
        self.mongo_client = MongoClient(mongo_url, connect=True, connectTimeoutMS=5000)
        self.mongo_users_db = self.mongo_client.get_database("users")
        self.mongo_messages_db = self.mongo_client.get_database("messages")
        self.mongo_users_col = self.mongo_users_db.get_collection("info")
        self.logger.info(f"users in db: {self.mongo_users_col.count_documents({})}")

    def add_message_to_db(self, user_id: int, message: MessageRecord) -> None:
        col = self.mongo_messages_db.get_collection(str(user_id))
        col.insert_one(document=message)

    def get_messages_from_db(self, user_id: int) -> list[MessageParam]:
        user_info = self.mongo_users_col.find({"user_id": str(user_id)}).to_list()[0]
        col_mes = self.mongo_messages_db.get_collection(str(user_id))
        messages_res: list[MessageRecord] = col_mes.find().sort({"timestamp": 1}).skip(user_info["offset"]).to_list()
        messages = [mes["message_param"] for mes in messages_res]
        return messages

    def clear_context(self, user_id: int) -> None:
        user_info = self.get_or_create_user(user_id)
        col_mes = self.mongo_messages_db.get_collection(str(user_id))
        count = col_mes.count_documents({})
        user_info["offset"] = count
        self.__update_user(user_info)

    def get_or_create_user(self, user_id: int, username: str = "None") -> UserInfo:
        user_info_list = self.mongo_users_col.find({"user_id": str(user_id)}).to_list()
        if user_info_list:
            return user_info_list[0]
        else:
            user_info_doc = self._get_default_user_info(user_id, username)
            self.mongo_users_col.insert_one(user_info_doc)
            return user_info_doc

    def __update_user(self, user_info: UserInfo):
        self.mongo_users_col.replace_one({"_id": user_info["_id"]}, user_info)

    def _get_default_user_info(self, user_id: int, username: str) -> UserInfo:
        doc: UserInfo = {
            "user_id": str(user_id),
            "username": username,
            "tokens_balance": 0,
            "settings": {"model": self.default_model, "system_prompt": None, "temperature": self.default_temperature},
            "offset": 0
        }
        return doc

    def change_model(self, user_id: int, model: ModelParam) -> None:
        user_info = self.get_or_create_user(user_id)
        user_info["settings"]["model"] = model
        self.mongo_users_col.replace_one({"_id": user_info["_id"]}, user_info)

    def set_system_prompt(self, user_id: int, prompt: str | None):
        user_info = self.get_or_create_user(user_id)
        user_info["settings"]["system_prompt"] = prompt
        self.__update_user(user_info)

    def get_system_prompt(self, user_id: int):
        user_info = self.get_or_create_user(user_id)
        prompt = user_info["settings"]["system_prompt"]
        print(type(prompt), prompt)
        if prompt is None:
            return ""
        return prompt

    def set_temperature(self, user_id: int, temperature: float = None):
        if temperature and temperature > 1:
            temperature = 1
        elif temperature and temperature < 0:
            temperature = 0
        user_info = self.get_or_create_user(user_id)
        user_info["settings"]["temperature"] = temperature or self.default_temperature
        self.__update_user(user_info)
