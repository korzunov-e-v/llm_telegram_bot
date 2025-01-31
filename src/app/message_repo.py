from datetime import datetime

from anthropic.types import MessageParam

from src.models import MessageRecord
from src.app.database import MongoManager


class MessageRepository:
    def __init__(self, db_provider: MongoManager):  # todo: abstract
        self.__db_provider = db_provider

    def add_message_to_db(
        self,
        user_id: int,
        message: MessageParam,
        context: list[MessageParam],
        model: str,
        tokens: int,
        tokens_plus: int,
        timestamp: datetime,
    ) -> None:
        message = MessageRecord(
            message_param=message,
            context=context,
            model=model,
            tokens=tokens,
            tokens_plus=tokens_plus,
            timestamp=timestamp,
        )
        self.__db_provider.add_chat_message_record(user_id, message)

    def get_messages_from_db(self, user_id: int, offset: int = 0, sort=None) -> list[MessageRecord]:
        messages_res = self.__db_provider.get_chat_message_records(user_id, offset, sort)
        return messages_res
