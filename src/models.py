import datetime
from typing import TypedDict, NotRequired, Optional

from anthropic.types import MessageParam, ModelParam
from bson import ObjectId


class Settings(TypedDict):
    offset: int
    model: str
    system_prompt: Optional[str]
    temperature: float


class ChatInfo(TypedDict):
    _id: NotRequired[ObjectId]
    owner: ObjectId
    topics: Optional[dict]


class UserInfo(TypedDict):
    _id: NotRequired[ObjectId]
    user_id: int
    username: str
    tokens_balance: int
    chats: list[ChatInfo]


class MessageRecord(TypedDict):
    _id: NotRequired[ObjectId]
    message_param: MessageParam
    context: list[MessageParam]
    model: ModelParam
    tokens_message: int
    tokens_context: int
    timestamp: datetime.datetime
