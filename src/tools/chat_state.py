import enum


class ChatState(enum.Enum):
    PROMPT = "prompt"
    """Изменение системного промпта для чата, ожидание сообщения с текстом промпта."""

    TEMPERATURE = "temperature"
    """Изменение параметра температуры для чата, ожидание сообщения с числом."""


def get_state_key(chat_id: int, topic_id: int) -> str:
    """
    Составной ключ для словаря состояний чатов/топиков.

    :param chat_id: id чата в tg
    :param topic_id: id топика/темы в чате в tg
    :return: строка `f"{chat_id}+{topic_id}"`
    """
    return f"chat_{chat_id}+topic_{topic_id}"


state: dict[str, ChatState] = {}  # {f"{chat_id}+{topic_id}": "state"}
"""Хранит состояния чатов."""
