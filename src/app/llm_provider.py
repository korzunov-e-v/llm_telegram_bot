from abc import ABC, abstractmethod
from itertools import groupby
from typing import Type

import aiohttp
import tiktoken
from anthropic import Anthropic, AsyncAnthropic
from anthropic.types import MessageParam
from pydantic_ai.messages import ModelRequest, SystemPromptPart, UserPromptPart, ModelResponse, TextPart, ModelMessage
from pydantic_ai.models import ModelRequestParameters, Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.settings import ModelSettings

from src.config import settings
from src.models import MessageModel, LlmProviderSendResponse, AvailableModel
from src.tools.AnthropicModelCustom import AnthropicModelCustom


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
    async def get_models(self) -> list[AvailableModel]:
        raise NotImplementedError()


class BaseLlmProvider(AbstractLlmProvider):
    def __init__(self, api_key: str, base_url: str, model_class: Type[OpenAIModel] | Type[AnthropicModel]):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/") if base_url else None
        self._ai_model_class = model_class

    @abstractmethod
    def _get_ai_instance(self, model: str) -> Model:
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
    ) -> LlmProviderSendResponse:
        ai_model = self._get_ai_instance(model=model)

        grouped_messages: list[list[MessageModel]] = [list(group) for key, group in groupby(messages, lambda x: x["role"])]

        messages_to_send: list[ModelMessage] = []
        for group in grouped_messages:
            if group[0]["role"] == "user":
                parts = [UserPromptPart(content=m["content"]) for m in group]
                messages_to_send.append(ModelRequest(parts=parts))
            else:
                parts = [TextPart(content=m["content"], part_kind="text") for m in group]
                messages_to_send.append(ModelResponse(parts=parts, kind="response"))

        if system_prompt:
            system_prompt_part = SystemPromptPart(content=system_prompt)
            messages_to_send[0].parts.insert(0, system_prompt_part)

        model_settings = ModelSettings(max_tokens=max_tokens, temperature=temp)
        model_request_parameters = ModelRequestParameters(function_tools=[], allow_text_result=True, result_tools=[])

        response = await ai_model.request(
            messages=messages_to_send,
            model_settings=model_settings,
            model_request_parameters=model_request_parameters,
        )
        return LlmProviderSendResponse(model_response=response[0], usage=response[1])

    @abstractmethod
    async def count_tokens(self, model: str, messages: list[MessageModel]) -> int:
        raise NotImplementedError()

    @abstractmethod
    async def get_models(self) -> list[AvailableModel]:
        raise NotImplementedError()


class AnthropicLlmProvider(BaseLlmProvider):
    def __init__(self, api_key: str, base_url: str = None):
        model_class = AnthropicModel
        # base_url = "https://api.anthropic.com/v1"
        super().__init__(api_key, base_url, model_class)
        self.extra_headers_cache = {"anthropic-beta": "prompt-caching-2024-07-31"}

    def _get_ai_instance(self, model: str) -> AnthropicModel:
        return AnthropicModelCustom(model_name=model, anthropic_client=AsyncAnthropic(api_key=self._api_key, base_url=self._base_url))

    async def count_tokens(self, model: str, messages: list[MessageModel]) -> int:
        if len(messages) == 0:
            return 0
        ai_model = self._get_ai_instance(model)
        message_to_send = [MessageParam(content=mes["content"], role=mes["role"]) for mes in messages]
        res = await ai_model.client.messages.count_tokens(
            messages=message_to_send,
            model=model
        )
        return res.input_tokens

    async def get_models(self) -> list[AvailableModel]:
        ai = Anthropic(api_key=self._api_key, base_url=self._base_url)
        models = ai.models.list()
        return [AvailableModel(display_name=model.display_name, name=model.id) for model in models]


class OpenAiLlmProvider(BaseLlmProvider):
    def __init__(self, api_key: str, base_url: str):
        model_class = OpenAIModel
        super().__init__(api_key, base_url, model_class)

    def _get_ai_instance(self, model: str) -> OpenAIModel:
        return OpenAIModel(model_name=model, base_url=self._base_url, api_key=self._api_key)

    async def count_tokens(self, model: str, messages: list[MessageModel]) -> int:
        enc = tiktoken.encoding_for_model(model)
        enc_res = enc.encode_batch([mes["content"] for mes in messages])
        return sum(map(len, enc_res))

    async def get_models(self) -> list[AvailableModel]:
        resp = await self.__fetch_models()
        models = resp["data"]
        return [AvailableModel(name=model["id"], display_name=model["name"]) for model in models]

    async def __fetch_models(self) -> dict:
        url = f'{self._base_url}/models'

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                return data
