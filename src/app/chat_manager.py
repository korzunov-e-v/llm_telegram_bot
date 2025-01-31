from anthropic.types import MessageParam, ModelParam

from src.config import settings
from src.models import MessageRecord, UserSettings, UserInfo
from src.app.database import MongoManager


class ChatManager:
    def __init__(self, db_provider: MongoManager):  # todo: abstract
        self.__db_provider = db_provider

    def get_allowed_topics(self, chat_id: int) -> list[int]:
        topics_dict = self.get_user(chat_id).get("allowed_topics")
        if topics_dict:
            return [int(k) for k, v in topics_dict.items() if v]
        else:
            return []

    def set_allowed_topics(self, chat_id: int, topics: list[int]):
        user = self.get_user(chat_id)
        user["allowed_topics"] = {str(k): True for k, v in topics}
        self.update_user(user)

    def add_allowed_topics(self, chat_id: int, topic: int):
        user = self.get_user(chat_id)
        user["allowed_topics"][str(topic)] = True
        self.update_user(user)

    def remove_allowed_topics(self, chat_id: int, topic: int):
        user = self.get_user(chat_id)
        user["allowed_topics"][str(topic)] = False
        self.update_user(user)

    def get_context(self, user_id: int, offset: int = 0) -> list[MessageParam]:
        message_records: list[MessageRecord] = self.__db_provider.get_chat_message_records(user_id, offset)
        messages = [mes["message_param"] for mes in message_records]
        return messages

    def clear_context(self, user_id: int) -> None:
        count = self.__db_provider.count_chat_messages(user_id)
        user_info = self.get_user(user_id)
        user_info["offset"] = count
        self.update_user(user_info)

    def get_user_settings(self, user_id: int, username: str = "None") -> UserSettings:
        user = self.get_user(user_id, username)
        return user["settings"]

    def get_user(self, user_id: int, username: str = "None") -> UserInfo:
        user_info = self.__db_provider.get_user(user_id)
        if user_info:
            return user_info
        else:
            user_info_doc = self.__get_default_user_info(user_id, username)
            self.__db_provider.add_user(user_info_doc)
            return user_info_doc

    @staticmethod
    def __get_default_user_info(user_id: int, username: str) -> UserInfo:
        doc: UserInfo = {
            "user_id": str(user_id),
            "username": username,
            "tokens_balance": 0,
            "settings": {
                "model": settings.default_model,
                "system_prompt": None,
                "temperature": settings.default_temperature,
            },
            "offset": 0,
            "allowed_topics": {},
        }
        return doc

    def set_system_prompt(self, user_id: int, prompt: str | None):
        user_info = self.get_user(user_id)
        user_info["settings"]["system_prompt"] = prompt
        self.update_user(user_info)

    def clear_system_prompt(self, user_id: int):
        self.set_system_prompt(user_id, None)

    def get_system_prompt(self, user_id: int):
        user_info = self.get_user_settings(user_id)
        prompt = user_info["system_prompt"]
        if prompt is None:
            return ""
        return prompt

    def set_temperature(self, user_id: int, temperature: float) -> None:
        if temperature and temperature > 1:
            temperature = 1
        elif temperature and temperature < 0:
            temperature = 0
        user_info = self.get_user(user_id)
        user_info["settings"]["temperature"] = temperature
        self.update_user(user_info)

    def reset_temperature(self, user_id: int):
        self.set_temperature(user_id, settings.default_temperature)

    def change_model(self, user_id: int, model: ModelParam) -> None:
        user_info = self.get_user(user_id)
        user_info["settings"]["model"] = model
        self.update_user(user_info)

    def update_user(self, user_info: UserInfo):
        self.__db_provider.update_user(user_info)
