from typing import assert_never

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolResultBlockParam, TextBlockParam, ToolUseBlockParam
from pydantic_ai.messages import ModelMessage, ModelRequest, SystemPromptPart, UserPromptPart, ToolReturnPart, RetryPromptPart, \
    ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelName, _guard_tool_call_id  # noqa
from httpx import AsyncClient as AsyncHTTPClient


class AnthropicModelCustom(AnthropicModel):
    def __init__(
        self,
        model_name: AnthropicModelName,
        *,
        api_key: str | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        http_client: AsyncHTTPClient | None = None,
    ):
        super().__init__(model_name, api_key=api_key, anthropic_client=anthropic_client, http_client=http_client)

    def _map_message(self, messages: list[ModelMessage]) -> tuple[str, list[MessageParam]]:
        """Just maps a `pydantic_ai.Message` to a `anthropic.types.MessageParam`."""
        system_prompt: str = ''
        anthropic_messages: list[MessageParam] = []
        for m in messages:
            if isinstance(m, ModelRequest):
                for part in m.parts:
                    if isinstance(part, SystemPromptPart):
                        system_prompt += part.content
                    elif isinstance(part, UserPromptPart):
                        anthropic_messages.append(MessageParam(role='user', content=[TextBlockParam(text=str(part.content), type="text")]))
                    elif isinstance(part, ToolReturnPart):
                        anthropic_messages.append(
                            MessageParam(
                                role='user',
                                content=[
                                    ToolResultBlockParam(
                                        tool_use_id=_guard_tool_call_id(t=part, model_source='Anthropic'),
                                        type='tool_result',
                                        content=part.model_response_str(),
                                        is_error=False,
                                    )
                                ],
                            )
                        )
                    elif isinstance(part, RetryPromptPart):
                        if part.tool_name is None:
                            anthropic_messages.append(MessageParam(role='user', content=part.model_response()))
                        else:
                            anthropic_messages.append(
                                MessageParam(
                                    role='user',
                                    content=[
                                        ToolResultBlockParam(
                                            tool_use_id=_guard_tool_call_id(t=part, model_source='Anthropic'),
                                            type='tool_result',
                                            content=part.model_response(),
                                            is_error=True,
                                        ),
                                    ],
                                )
                            )
            elif isinstance(m, ModelResponse):
                content: list[TextBlockParam | ToolUseBlockParam] = []
                for item in m.parts:
                    if isinstance(item, TextPart):
                        content.append(TextBlockParam(text=item.content, type='text'))
                    else:
                        assert isinstance(item, ToolCallPart)
                        content.append(self._map_tool_call(item))
                anthropic_messages.append(MessageParam(role='assistant', content=content))
            else:
                assert_never(m)
        return system_prompt, anthropic_messages
