import datetime
from typing import TypedDict, NotRequired, Optional

from anthropic.types import MessageParam, ModelParam
from bson import ObjectId


class Settings(TypedDict):
    offset: int
    model: str
    system_prompt: Optional[str]
    temperature: float


class TopicInfo(TypedDict):
    _id: NotRequired[ObjectId]
    chat_id: int
    topic_id: int
    settings: Settings


class ChatInfo(TypedDict):
    _id: NotRequired[ObjectId]
    chat_id: int
    owner_user_id: int
    allowed_topics: dict


class UserInfo(TypedDict):
    _id: NotRequired[ObjectId]
    user_id: int
    username: str
    full_name: str
    tokens_balance: int


class MessageRecord(TypedDict):
    _id: NotRequired[ObjectId]
    message_param: MessageParam
    context_n: int
    model: ModelParam
    tokens_message: int
    tokens_from_prov: int
    user_id: int
    timestamp: datetime.datetime
