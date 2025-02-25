from datetime import datetime

from src.models import MessageRecord, MessageModel
from src.app.database import MongoManager


class MessageRepository:
    def __init__(self, db_provider: MongoManager):  # todo: abstract
        self.__db_provider = db_provider

    async def add_message_to_db(
        self,
        chat_id: int,
        topic_id: int,
        user_id: int,
        message: MessageModel,
        context_n: int,
        model: str,
        tokens_message: int,
        tokens_from_prov: int,
        timestamp: datetime,
    ) -> None:
        if topic_id is None:
            topic_id = 1
        message = MessageRecord(
            message_param=message,
            context_n=context_n,
            model=model,
            user_id=user_id,
            tokens_message=tokens_message,
            tokens_from_prov=tokens_from_prov,
            timestamp=timestamp,
        )
        await self.__db_provider.add_chat_message_record(message, chat_id, topic_id)

    async def get_messages_from_db(self, chat_id: int, topic_id: int = 0, offset: int = 0, sort=None) -> list[MessageRecord]:
        messages_res = await self.__db_provider.get_chat_message_records(chat_id, topic_id, offset, sort)
        return messages_res
