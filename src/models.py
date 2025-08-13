import hashlib
from datetime import datetime, UTC
from typing import Optional, Literal, Any, TypeAlias

from anthropic.types import ModelParam
from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, model_validator
from pydantic_ai.messages import ModelResponse
from pydantic_ai.usage import Usage
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, ExtBot

from src.config import settings

PTBContext: TypeAlias = CallbackContext[ExtBot, dict[str, Any], dict[str, Any], dict[str, Any]]


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
    username: str | None
    full_name: str | None
    tokens_balance: int = Field(0)
    is_admin: bool = Field(False)
    dt_created: datetime = Field(datetime.now(UTC))


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
    timestamp: datetime


class PromptModel(BaseModel):
    prompt: str
    timestamp: datetime = datetime.now(UTC)


class LlmProviderSendResponse(BaseModel):
    model_response: ModelResponse
    usage: Usage


class AvailableModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    class ModelArchitecture(BaseModel):
        model_config = ConfigDict(extra="allow")

        modality: str
        input_modalities: list[str]
        output_modalities: list[str]
        tokenizer: str
        instruct_type: str | None

    class TopProvider(BaseModel):
        model_config = ConfigDict(extra="allow")

        is_moderated: bool
        context_length: int | None
        max_completion_tokens: int | None

    class Pricing(BaseModel):
        model_config = ConfigDict(extra="allow")

        prompt: float
        completion: float
        image: float | dict[str, int | float] | None = None
        request: float | dict[str, int | float] | None = None
        web_search: float | dict[str, int | float] | None = None
        internal_reasoning: float | dict[str, int | float] | None = None
        input_cache_read: float | None = None
        input_cache_write: float | None = None

    id: str
    canonical_slug: str | None = None
    hugging_face_id: str | None = None
    name: str
    created: datetime
    description: str | None = None
    context_length: int | None = None
    architecture: ModelArchitecture | None = None
    pricing: Pricing | None = None
    top_provider: TopProvider | None = None
    per_request_limits: dict | None = None
    supported_parameters: list[str] | None = None

    id_hash: str = None

    @staticmethod
    def get_hash(text):
        return hashlib.md5(text.encode()).hexdigest()[:8]

    def model_post_init(self, __context: Any) -> None:
        self.id_hash = self.get_hash(self.id)


class ModelCache(BaseModel):
    updated_at: datetime = datetime.now(UTC)
    models: list[AvailableModel] = []

    class Config:
        validate_assignment = True

    @model_validator(mode='after')
    @classmethod
    def update_updated_at(cls, obj: "ModelCache") -> "ModelCache":
        """Обновить поле updated_at при изменении поля models."""
        obj.model_config["validate_assignment"] = False
        obj.updated_at = datetime.now(UTC)
        obj.model_config["validate_assignment"] = True
        return obj


class GenerationInfo(BaseModel):
    id: str
    total_cost: float
    created_at: datetime
    model: str
    origin: str
    usage: float
    is_byok: bool
    upstream_id: str | None = None
    cache_discount: float | None = None
    upstream_inference_cost: float | None = None
    app_id: int | None = None
    streamed: bool | None = None
    cancelled: bool | None = None
    provider_name: str | None = None
    latency: int | None = None
    moderation_latency: int | None = None
    generation_time: int | None = None
    finish_reason: str | None = None
    native_finish_reason: str | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    native_tokens_prompt: int | None = None
    native_tokens_completion: int | None = None
    native_tokens_reasoning: int | None = None
    num_media_prompt: int | None = None
    num_media_completion: int | None = None
    num_search_results: int | None = None
