from datetime import datetime

from anthropic.types import MessageParam

from src.models import MessageRecord
from src.app.database import MongoManager


class MessageRepository:
    def __init__(self, db_provider: MongoManager):  # todo: abstract
        self.__db_provider = db_provider

    def add_message_to_db(
        self,
        chat_id: int,
        topic_id: int,
        user_id: int,
        message: MessageParam,
        context_n: int,
        model: str,
        tokens_message: int,
        tokens_from_prov: int,
        timestamp: datetime,
    ) -> None:
        message = MessageRecord(
            message_param=message,
            context_n=context_n,
            model=model,
            user_id=user_id,
            tokens_message=tokens_message,
            tokens_from_prov=tokens_from_prov,
            timestamp=timestamp,
        )
        self.__db_provider.add_chat_message_record(message, chat_id, topic_id)

    def get_messages_from_db(self, chat_id: int, topic_id: int = 0, offset: int = 0, sort=None) -> list[MessageRecord]:
        messages_res = self.__db_provider.get_chat_message_records(chat_id, topic_id, offset, sort)
        return messages_res
