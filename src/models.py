import datetime
from typing import TypedDict, NotRequired, Optional, Literal

from anthropic.types import ModelParam
from bson import ObjectId
from pydantic_ai.messages import ModelResponse
from pydantic_ai.usage import Usage
from telegram.constants import ParseMode


class Settings(TypedDict):
    offset: int
    model: str
    system_prompt: Optional[str]
    temperature: float
    parse_pdf: Optional[bool]
    md_mode: ParseMode


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
    is_admin: NotRequired[bool]
    dt_created: NotRequired[datetime.datetime]


class MessageModel(TypedDict):
    content: str
    role: Literal["assistant", "user"]


class MessageRecord(TypedDict):
    _id: NotRequired[ObjectId]
    message_param: MessageModel
    context_n: int
    model: ModelParam
    tokens_message: int
    tokens_from_prov: int
    user_id: int
    timestamp: datetime.datetime


class LlmProviderSendResponse(TypedDict):
    model_response: ModelResponse
    usage: Usage


class AvailableModel(TypedDict):
    display_name: str
    name: str
