import os
from collections import defaultdict

from anthropic.types import MessageParam
from pymongo import MongoClient
from telegram import User

mongo_url = os.getenv("MONGO_URL")


class UserContextManager:
    def __init__(self):
        self.user_contexts: defaultdict[User.id, list[MessageParam]] = defaultdict(list)

    def add(self, user_id: int, message: MessageParam):
        self.user_contexts[user_id].append(message)

    def get(self, user_id: int):
        self.verify(user_id)
        messages = self.user_contexts[user_id]
        return messages

    def clear(self, user_id: int):
        self.user_contexts[user_id] = []

    def verify(self, user_id: int):
        messages = self.user_contexts[user_id]
        if not messages:
            return
        first_mes_role = messages[0]["role"]
        last_mes_role = messages[-1]["role"]

        assert first_mes_role == "user"
        assert last_mes_role == "assistant"
