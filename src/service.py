import datetime
import os

from anthropic import Anthropic
from anthropic.types import MessageParam, ModelParam, TextBlockParam
from dotenv import load_dotenv

from src.tools.custom_logging import get_logger
from src.models import MessageRecord
from src.user_manager import UserManager

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")


class Service:
    def __init__(self):
        self.logger = get_logger(__name__)
        self._user_contexts = UserManager()
        self._client = Anthropic(api_key=api_key)

    def handle_text_message(self, user_id: int, message: str) -> str:
        client_info = self._user_contexts.get_or_create_user(user_id)
        messages = self._user_contexts.get_messages_from_db(user_id)
        self.logger.info(messages)
        user_message = MessageParam(role="user", content=message)
        input_tokens = self.count_tokens(
            model=client_info["settings"]["model"],
            messages=messages + [user_message],
        )
        u_dt = datetime.datetime.now(datetime.UTC)
        response = self.send_message(
            model=client_info["settings"]["model"],
            messages=messages + [user_message],
            user_id=user_id,
        )
        a_dt = datetime.datetime.now(datetime.UTC)
        llm_resp_text = response.content[0].text
        llm_message = MessageParam(
            content=[m.model_dump() for m in response.content],
            role=response.role,
        )

        llm_record = MessageRecord(
            message_param=llm_message,
            context=messages,
            model=response.model,
            tokens=response.usage.output_tokens,
            tokens_plus=response.usage.output_tokens,
            timestamp=a_dt,
        )

        user_record = MessageRecord(
            message_param=user_message,
            context=messages + [user_message],
            model=response.model,
            tokens=input_tokens,
            tokens_plus=response.usage.input_tokens,
            timestamp=u_dt,
        )

        self._user_contexts.add_message_to_db(user_id, user_record)
        self._user_contexts.add_message_to_db(user_id, llm_record)

        return llm_resp_text

    def send_message(self, model: str, messages: list[MessageParam], user_id: int):
        user_info = self._user_contexts.get_or_create_user(user_id)
        system_prompt = user_info["settings"]["system_prompt"]
        response = self._client.messages.create(
            model=model,
            max_tokens=4096,
            messages=messages,
            metadata={"user_id": str(user_id)},
            system=[TextBlockParam(text=system_prompt, type="text")] if system_prompt else "",
            temperature=user_info["settings"].get("temperature") or self._user_contexts.default_temperature,
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

    def count_tokens_of_user_context(self, user_id: int):
        client_info = self.get_or_create_user(user_id)
        messages = self._user_contexts.get_messages_from_db(user_id)
        return self.count_tokens(
            model=client_info["settings"]["model"],
            messages=messages,
        )

    def set_system_prompt(self, user_id: int, prompt: str):
        self._user_contexts.set_system_prompt(user_id, prompt)

    def clear_system_prompt(self, user_id: int):
        self._user_contexts.set_system_prompt(user_id, None)

    def get_system_prompt(self, user_id: int):
        return self._user_contexts.get_system_prompt(user_id)

    def set_temperature(self, user_id: int, temperature: float):
        self._user_contexts.set_temperature(user_id, temperature)

    def reset_temperature(self, user_id: int):
        self._user_contexts.set_temperature(user_id, None)


    def clear_context(self, user_id: int):
        self._user_contexts.clear_context(user_id)

    def change_model(self, user_id: int, model: ModelParam):
        self._user_contexts.change_model(user_id, model)

    def get_or_create_user(self, user_id: int, username: str = "None"):
        return self._user_contexts.get_or_create_user(user_id, username)

    def get_user_info_message(self, user_id):
        user_info = self._user_contexts.get_or_create_user(user_id)
        message_templ = (
            "Инфо:\n"
            "\n"
            "Модель: {model}\n"
            'Промпт: "{prompt}"\n'
            "Температура (от 0 до 1): {temp}\n"
            "Токены: {tokens}\n"
            "Контекст:\n"
            "    сообщений: {context_len}\n"
            "    токенов: {context_tokens}\n"
        )
        messages = self._user_contexts.get_messages_from_db(user_id)
        context_len = len(messages)
        context_tokens = self.count_tokens(user_info["settings"]["model"], messages)

        message = message_templ.format(
            model=user_info["settings"]["model"],
            prompt=user_info["settings"]["system_prompt"] or "",
            temp=user_info["settings"].get("temperature") or self._user_contexts.default_temperature,
            tokens=user_info["tokens_balance"],
            context_len=context_len,
            context_tokens=context_tokens,
        )
        return message
