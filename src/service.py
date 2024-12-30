import datetime
import os

from anthropic import Anthropic
from anthropic.types import MessageParam
from dotenv import load_dotenv

from src.models import MessageRecord
from src.user_manager import UserManager

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")


class Service:
    def __init__(self):
        self._user_contexts = UserManager()
        self._client = Anthropic(api_key=api_key)

    def handle_text_message(self, user_id: int, message: str) -> str:
        client_info = self._user_contexts.get_or_create_user(user_id)
        messages = self._user_contexts.get_messages(user_id)
        user_message = MessageParam(role="user", content=message)
        input_tokens = self.count_tokens(
            model=client_info["settings"]["model"],
            messages=messages + [user_message],
        )
        u_dt = datetime.datetime.now(datetime.UTC)
        response = self.send_message(
            model=client_info["settings"]["model"],
            messages=messages + [user_message],
        )
        a_dt = datetime.datetime.now(datetime.UTC)
        llm_resp_text = response.content[0].text
        llm_message = MessageParam(
            content=[m.model_dump() for m in response.content],
            role=response.role,
        )

        llm_record = MessageRecord(
            message_param=llm_message,
            timestamp=a_dt,
            tokens=response.usage.output_tokens,
            tokens_plus=response.usage.output_tokens,
        )

        user_record = MessageRecord(
            message_param=user_message,
            timestamp=u_dt,
            tokens=input_tokens,
            tokens_plus=response.usage.input_tokens,
        )

        self._user_contexts.add_message(user_id, user_record)
        self._user_contexts.add_message(user_id, llm_record)

        return llm_resp_text

    def send_message(self, model: str, messages: list[MessageParam]):
        response = self._client.messages.create(
            model=model,  # claude-3-5-sonnet-20241022
            max_tokens=4096,
            messages=messages
        )
        return response

    def count_tokens(self, model: str, messages: list[MessageParam]):
        response_count = self._client.messages.count_tokens(
            model=model,
            messages=messages,
        )
        input_tokens = response_count.input_tokens
        return input_tokens

    def clear_context(self, user_id: int):
        self._user_contexts.clear_context(user_id)


'''
user
    tokens-balance
    settings
        model
        system-prompt

{
  _id: ObjectId(),
  role: "user",
  # content: {"type": "text", "source": {"data": base64_data, media_type: "image/jpeg", "type": "base64}},
  content: {},
  timestamp: time
  tokens: 1234
  tokens_plus: 4321
}

'''
