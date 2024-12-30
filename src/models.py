import datetime
from typing import TypedDict, NotRequired, Optional

from anthropic.types import MessageParam, ModelParam
from bson import ObjectId


class UserSettings(TypedDict):
    model: str
    system_prompt: Optional[str]


class UserInfo(TypedDict):
    _id: NotRequired[ObjectId]
    user_id: str
    username: str
    tokens_balance: int
    offset: int
    settings: UserSettings


class MessageRecord(TypedDict):
    _id: NotRequired[ObjectId]
    message_param: MessageParam
    context: list[MessageParam]
    model: ModelParam
    tokens: int
    tokens_plus: int
    timestamp: datetime.datetime
