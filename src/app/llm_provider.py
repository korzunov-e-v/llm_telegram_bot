from abc import ABC, abstractmethod

from anthropic import Anthropic
from anthropic.types import MessageParam, TextBlockParam
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionContentPartTextParam,
    ChatCompletion,
)

from src.config import settings


class LlmProvider(ABC):
    @abstractmethod
    def send_messages(
        self,
        model: str,
        messages: list,
        user_id: int,
        system_prompt: str = None,
        temp: float = settings.default_temperature,
        max_tokens: int = settings.default_max_tokens,
        cache: bool = False,
    ):
        raise NotImplementedError()

    def count_tokens(self, model: str, messages: list):
        raise NotImplementedError()

    def get_models(self):
        raise NotImplementedError()


class OpenAiLlmProvider(LlmProvider):
    def __init__(self, api_key: str):
        self._client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        self.__api_key = api_key

    def send_messages(
        self,
        model: str,
        messages: list[ChatCompletionMessageParam],
        user_id: int,
        system_prompt: str = None,
        temp: float = settings.default_temperature,
        max_tokens: int = settings.default_max_tokens,
        cache: bool = False,
    ):
        system_message = ChatCompletionSystemMessageParam(content=[ChatCompletionContentPartTextParam(text=system_prompt, type="text")],
                                                          role="system")
        messages = [system_message] + messages

        extra_headers = None  # TODO

        completion: ChatCompletion = self._client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            metadata={"user_id": str(user_id)},
            temperature=temp,
            extra_headers=extra_headers,
        )
        message = completion.choices[0].message
        print(completion.choices[0].message.content)  # todo
        return message

    # not working
    def count_tokens(self, model: str, messages: list[MessageParam]):
        if len(messages) == 0:
            return 0
        response_count = self._client.messages.count_tokens(
            model=model,
            messages=messages,
        )
        input_tokens = response_count.input_tokens
        return input_tokens


class AnthropicLlmProvider(LlmProvider):
    def __init__(self, api_key: str):
        self._client = Anthropic(api_key=api_key)

    def send_messages(
        self,
        model: str,
        messages: list[MessageParam],
        user_id: int,
        system_prompt: str = None,
        temp: float = settings.default_temperature,
        max_tokens: int = settings.default_max_tokens,
        cache: bool = False,
    ):
        if cache:
            extra_headers = {"anthropic-beta": "prompt-caching-2024-07-31"}
        else:
            extra_headers = None

        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            metadata={"user_id": str(user_id)},
            system=[TextBlockParam(text=system_prompt, type="text")] if system_prompt else "",
            temperature=temp,
            extra_headers=extra_headers,
        )
        return response

    def count_tokens(self, model: str, messages: list[MessageParam]):
        if len(messages) == 0:
            return 0
        response_count = self._client.messages.count_tokens(
            model=model,
            messages=messages,
        )
        input_tokens = response_count.input_tokens
        return input_tokens
