from datetime import datetime, UTC

from anthropic.types import MessageParam, TextBlockParam

from src.app.database import MongoManager
from src.app.llm_provider import LLMProvider
from src.app.message_repo import MessageRepository
from src.config import settings
from src.app.user_manager import UserManager


class MessageProcessingFacade:
    def __init__(
        self,
        llm_provider: LLMProvider,
        user_manager: UserManager,
        message_repo: MessageRepository,
    ):
        self.llm_provider: LLMProvider = llm_provider
        self.user_manager: UserManager = user_manager
        self.message_repo: MessageRepository = message_repo

    def process_message(self, user_id: int, message_text: str, username: str = ""):
        user_info = self.user_manager.get_user(user_id, username)
        user_settings = user_info["settings"]
        context = self.user_manager.get_context(user_id, user_info["offset"])

        user_message = MessageParam(
            content=TextBlockParam(text=message_text, type="text"),
            role="user"
        )
        messages = context + [user_message]
        input_sing_tokens_count = self.llm_provider.count_tokens(user_settings["model"], user_message)

        u_dt = datetime.now(UTC)
        response = self.llm_provider.send_messages(
            model=user_settings["model"],
            messages=messages,
            user_id=user_id,
            system_prompt=user_settings["system_prompt"],
            temp=user_settings["temperature"],
        )

        a_dt = datetime.now(UTC)
        llm_resp_text = response.content[0].text
        llm_message = MessageParam(
            content=[m.model_dump() for m in response.content],
            role=response.role,
        )

        self.message_repo.add_message_to_db(  # llm
            user_id=user_id,
            message=llm_message,
            context=messages,
            model=response.model,
            tokens=response.usage.output_tokens,
            tokens_plus=response.usage.output_tokens,
            timestamp=a_dt,
        )
        self.message_repo.add_message_to_db(  # user
            user_id=user_id,
            message=user_message,
            context=messages + [user_message],
            model=response.model,
            tokens=input_sing_tokens_count,
            tokens_plus=response.usage.input_tokens,
            timestamp=u_dt,
        )
        return llm_resp_text

    def get_user_info_message(self, user_id) -> str:
        user_info = self.user_manager.get_user(user_id)
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
        messages = self.user_manager.get_context(user_id, offset=user_info["offset"])
        context_len = len(messages)
        context_tokens = self.llm_provider.count_tokens(user_info["settings"]["model"], messages)
        message = message_templ.format(
            model=user_info["settings"]["model"],
            prompt=user_info["settings"]["system_prompt"] or "",
            temp=user_info["settings"].get("temperature") or settings.default_temperature,
            tokens=user_info["tokens_balance"],
            context_len=context_len,
            context_tokens=context_tokens,
        )
        return message


db_provider = MongoManager(settings.mongo_url)
user_manager = UserManager(db_provider)
message_repo = MessageRepository(db_provider)
llm_provider = LLMProvider(settings.anthropic_api_key)
message_processing_facade = MessageProcessingFacade(
    llm_provider=llm_provider,
    message_repo=message_repo,
    user_manager=user_manager,
)
