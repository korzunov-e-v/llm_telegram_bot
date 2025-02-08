import re

from telegram import Message
from telegram.constants import ChatType
from telegram.ext.filters import MessageFilter

from src.app.service import message_processing_facade as service


class TopicFilter(MessageFilter):
    """
    Фильтр сообщений по топику.

    Сообщение принимается, если:
        * Если топик в списке разрешённых для чата
        * Если сообщение не в групповом чате
    """
    def filter(self, message: Message):
        if message.chat.is_forum and message.chat.type in (ChatType.SUPERGROUP, ChatType.GROUP):
            chat_id = message.chat_id
            chat_id_minus = -1000000000000 - chat_id
            chat_id = min(chat_id, chat_id_minus)
            thread_id = message.message_thread_id
            if thread_id is None:
                thread_id = 1
            user_id = message.from_user.id
            allowed = service.chat_manager.get_allowed_topics(chat_id, user_id)
            if not (thread_id in allowed):
                return False
        return True


class InviteLinkFilter(MessageFilter):
    """
    Фильтр сообщений со ссылкой-приглашением.

    Сообщение принимается, если содержит только ссылку приглашение вида

    `https://t.me/c/123/45`
    """
    def filter(self, message: Message):
        topic_invite_pattern = re.compile(r'https?://t.me/\w+/(\d+)/(\d+)')
        match = re.match(topic_invite_pattern, message.text)
        if match:
            return True
        return False
