from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from itertools import groupby
from typing import Type, List

import aiohttp
import tiktoken
from anthropic import Anthropic, AsyncAnthropic
from anthropic.types import MessageParam
from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart, ModelResponse, TextPart, ModelMessage
from pydantic_ai.models import ModelRequestParameters, Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from src.config import settings, LlmProviderType
from src.models import MessageModel, LlmProviderSendResponse, AvailableModel, ModelCache, GenerationInfo


class AbstractLlmProvider(ABC):
    @abstractmethod
    async def send_messages(
        self,
        model: str,
        messages: list[MessageModel],
        user_id: int,
        system_prompt: str = None,
        temp: float = settings.default_temperature,
        max_tokens: int = settings.default_max_tokens,
        cache: bool = False,
    ) -> LlmProviderSendResponse:
        raise NotImplementedError()

    @abstractmethod
    async def count_tokens(self, model: str, messages: list) -> int:
        raise NotImplementedError()

    @abstractmethod
    async def get_providers_models(self) -> dict[str, list[AvailableModel]]:
        raise NotImplementedError()

    @abstractmethod
    async def get_models(self) -> list[AvailableModel]:
        raise NotImplementedError()

    @abstractmethod
    async def ping(self, model: str | None = None) -> LlmProviderSendResponse:
        raise NotImplementedError()


class BaseLlmProvider(AbstractLlmProvider):
    def __init__(self, api_key: str, base_url: str, model_class: Type[OpenAIModel] | Type[AnthropicModel]):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") if base_url else None
        self._ai_model_class = model_class
        self.models_cache: ModelCache = ModelCache()

    @abstractmethod
    def _get_ai_instance(self, model: str) -> Model:
        raise NotImplementedError()

    @abstractmethod
    def _get_default_model_name(self) -> str:
        raise NotImplementedError()

    async def send_messages(
        self,
        model: str,
        messages: list[MessageModel],
        user_id: int,
        system_prompt: str = None,
        temp: float = settings.default_temperature,
        max_tokens: int = settings.default_max_tokens,
        cache: bool = False,  # todo cache
        extra_headers: dict = settings.extra_headers,
    ) -> LlmProviderSendResponse:
        ai_model = self._get_ai_instance(model=model)

        grouped_messages: list[list[MessageModel]] = [list(group) for key, group in groupby(messages, lambda x: x.role)]

        messages_to_send: List[ModelMessage] = []
        for group in grouped_messages:
            if group[0].role == "user":
                parts = [UserPromptPart(content=m.content) for m in group]
                messages_to_send.append(ModelRequest(parts=parts))
            else:
                parts = [TextPart(content=m.content, part_kind="text") for m in group]
                messages_to_send.append(ModelResponse(parts=parts, kind="response"))

        if system_prompt:
            system_prompt_part = SystemPromptPart(content=system_prompt)
            messages_to_send[0].parts.insert(0, system_prompt_part)

        model_settings = ModelSettings(max_tokens=max_tokens, temperature=temp)
        if extra_headers:
            model_settings["extra_headers"] = extra_headers

        response: ModelResponse = await ai_model.request(
            messages=messages_to_send,
            model_settings=model_settings,
            model_request_parameters=ModelRequestParameters(),
        )
        return LlmProviderSendResponse(model_response=response, usage=response.usage)

    @abstractmethod
    async def count_tokens(self, model: str, messages: list[MessageModel]) -> int:
        raise NotImplementedError()

    async def get_models(self) -> list[AvailableModel]:
        if not (
            self.models_cache.models
            or self.models_cache.updated_at < datetime.now(UTC) - timedelta(seconds=settings.model_cache_ttl_sec)
        ):
            await self._update_models_cache()
        return self.models_cache.models

    @abstractmethod
    async def _update_models_cache(self) -> None:
        raise NotImplementedError()

    async def get_model_id_by_hash(self, model_hash: str) -> str:
        for m in await self.get_models():
            if m.id_hash == model_hash:
                return m.id
        raise Exception("broken")

    async def ping(self, model: str | None = None) -> LlmProviderSendResponse:
        res = await self.send_messages(
            model=self._get_default_model_name(),
            messages=[MessageModel(content="На связи?", role="user")],
            temp=1,
            max_tokens=10,
            user_id=0,
        )
        return res


class AnthropicLlmProvider(BaseLlmProvider):
    def __init__(self, api_key: str, base_url: str = None):
        model_class = AnthropicModel
        super().__init__(api_key, base_url, model_class)
        self.extra_headers_cache = {"anthropic-beta": "prompt-caching-2024-07-31"}

    def _get_ai_instance(self, model: str) -> AnthropicModel:
        model = model.removeprefix("anthropic/")
        return AnthropicModel(
            model_name=model,
            provider=AnthropicProvider(
                anthropic_client=AsyncAnthropic(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
            )
        )

    def _get_default_model_name(self) -> str:
        return "claude-3-5-haiku-latest"

    async def count_tokens(self, model: str, messages: list[MessageModel]) -> int:
        if len(messages) == 0:
            return 0
        ai_model = self._get_ai_instance(model)
        message_to_send = [MessageParam(content=mes.content, role=mes.role) for mes in messages]
        res = await ai_model.client.messages.count_tokens(
            messages=message_to_send,
            model=model,
        )
        return res.input_tokens

    async def _update_models_cache(self) -> None:
        ai = Anthropic(api_key=self._api_key, base_url=self._base_url)
        models = ai.models.list()
        self.models_cache.models = [
            AvailableModel(
                id=f"anthropic/{model.id}",
                name=model.display_name,
                created=model.created_at,
            )
            for model in models
        ]

    async def get_providers_models(self) -> dict[str, list[AvailableModel]]:
        return {'anthropic': await self.get_models()}


class OpenAiLlmProvider(BaseLlmProvider):
    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL):
        model_class = OpenAIModel
        super().__init__(api_key, base_url, model_class)

    # noinspection PyTypeChecker
    def _get_ai_instance(self, model: str) -> OpenAIModel:
        return OpenAIModel(
            model_name=model,
            provider=OpenAIProvider(
                base_url=self._base_url,
                api_key=self._api_key,
            )
        )

    def _get_default_model_name(self) -> str:
        return "openai/gpt-4.1-nano"

    async def count_tokens(self, model: str, messages: list[MessageModel]) -> int:
        enc = tiktoken.encoding_for_model("gpt-4.1")
        enc_res = enc.encode_batch([mes.content for mes in messages])
        return sum(map(len, enc_res))

    async def get_generation(self, gen_id: int) -> GenerationInfo:
        url = f'{self._base_url}/generation'
        params = {"id": gen_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                data = await response.json()
                gen_info = GenerationInfo.model_validate(data["data"])
                return gen_info

    async def _update_models_cache(self) -> None:
        resp = await self.__fetch_models()
        models = resp["data"]
        self.models_cache.models = [AvailableModel.model_validate(model) for model in models]

    async def get_providers_models(self) -> dict[str, list[AvailableModel]]:
        models = await self.get_models()
        models_d = defaultdict(list)
        for model in models:
            models_d[model.id.split('/')[0]].append(model)
        return models_d

    async def __fetch_models(self) -> dict:
        url = f'{self._base_url}/models'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                return data


def get_llm_provider(provider_type: LlmProviderType, api_key: str):
    if provider_type == LlmProviderType.ANTHROPIC:
        return AnthropicLlmProvider(api_key=api_key)
    elif provider_type == LlmProviderType.OPENAI:
        return OpenAiLlmProvider(api_key=api_key)
