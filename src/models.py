import datetime
from typing import Optional, Literal

from anthropic.types import ModelParam
from bson import ObjectId
from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelResponse
from pydantic_ai.usage import Usage
from telegram.constants import ParseMode

from src.config import settings


class BaseMongoModel(BaseModel):
    id: ObjectId = Field(None, alias="_id", exclude=True)

    class Config:
        validate_by_name = True
        arbitrary_types_allowed = True


class Settings(BaseModel):
    offset: int = Field(0)
    model: str = Field(settings.default_model)
    system_prompt: Optional[str] = Field(None)
    temperature: float = Field(0.7)
    parse_pdf: Optional[bool] = Field(False)
    md_mode: ParseMode = Field(ParseMode.MARKDOWN)


class TopicInfo(BaseMongoModel):
    chat_id: int
    topic_id: int
    settings: Settings


class ChatInfo(BaseMongoModel):
    chat_id: int
    owner_user_id: int
    allowed_topics: dict = Field(dict())


class UserInfo(BaseMongoModel):
    user_id: int
    username: str
    full_name: str
    tokens_balance: int = Field(0)
    is_admin: bool = Field(False)
    dt_created: datetime.datetime = Field(datetime.datetime.now(datetime.UTC))


class MessageModel(BaseModel):
    content: str
    role: Literal["assistant", "user"]


class MessageRecord(BaseMongoModel):
    message_param: MessageModel
    context_n: int
    model: ModelParam
    tokens_message: int
    tokens_from_prov: int
    user_id: int
    timestamp: datetime.datetime


class LlmProviderSendResponse(BaseModel):
    model_response: ModelResponse
    usage: Usage


class AvailableModel(BaseModel):
    display_name: str
    name: str
