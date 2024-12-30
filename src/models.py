"""
{
    _id: ObjectId(),
    role: "user",
    # content: {"type": "text", "source": {"data": base64_data, media_type: "image/jpeg", "type": "base64}},
    content: {},
    timestamp: time
    tokens: 1234
    tokens_plus: 4321
}

user
    tokens-balance
    settings
        model
        system-prompt
        offset
"""
import datetime
from typing import TypedDict, Optional, NotRequired, Literal

from anthropic.types import MessageParam
from bson import ObjectId, Timestamp


class UserSettings(TypedDict):
    model: str
    system_prompt: str


class UserInfo(TypedDict):
    _id: NotRequired[ObjectId]
    user_id: str
    # username: str
    tokens_balance: int
    offset: int
    settings: UserSettings


class MessageRecord(TypedDict):
    _id: NotRequired[ObjectId]
    # role: Literal["user", "assistant"]
    # content: dict
    message_param: MessageParam
    timestamp: datetime.datetime
    tokens: int
    tokens_plus: int
