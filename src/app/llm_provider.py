from anthropic import Anthropic
from anthropic.types import MessageParam, TextBlockParam

from src.config import settings


class LLMProvider:
    def __init__(self, api_key):
        self._client = Anthropic(api_key=api_key)   # todo: move

    def send_messages(
        self,
        model: str,
        messages: list[MessageParam],
        user_id: int,
        system_prompt: str = None,
        temp: float = settings.default_temp,
        max_tokens: int = settings.default_max_tokens
    ):
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            metadata={"user_id": str(user_id)},
            system=[TextBlockParam(text=system_prompt, type="text")] if system_prompt else "",
            temperature=temp,
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
