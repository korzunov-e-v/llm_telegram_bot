import re

from telegram import Message
from telegram.constants import ChatType
from telegram.ext.filters import MessageFilter

from src.app.service import message_processing_facade as service


class TopicFilter(MessageFilter):
    def filter(self, message: Message):
        if message.chat.is_forum and message.chat.type == ChatType.SUPERGROUP:
            chat_id = message.chat_id
            chat_id_minus = -1000000000000 - chat_id
            chat_id = min(chat_id, chat_id_minus)
            thread_id = message.message_thread_id
            if not (
                thread_id in service.user_manager.get_allowed_topics(chat_id)
                or thread_id in service.user_manager.get_allowed_topics(chat_id_minus)
            ):
                return False
        return True


class InviteLinkFilter(MessageFilter):
    def filter(self, message: Message):
        topic_invite_pattern = re.compile(r'https?://t.me/\w+/(\d+)/(\d+)')
        match = re.match(topic_invite_pattern, message.text)
        if match:
            return True
        return False
