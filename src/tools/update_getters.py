from typing import Optional

from telegram import Update, ChatMemberUpdated, ChatMember


async def get_ids(update: Update) -> tuple[str, str, int, int, int | None, str | None]:
    """
    Возвращает tuple с информацией о пользователе/чате/топике.

    :return: username, full_name, user_id, chat_id, topic_id, msg_text
    """
    username = update.effective_user.username
    full_name = update.effective_user.full_name
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    if update.effective_message.is_topic_message:
        topic_id = update.effective_message.message_thread_id
    else:
        topic_id = None
    if update.message and update.message.text:
        msg_text = update.message.text
    else:
        msg_text = None
    return username, full_name, user_id, chat_id, topic_id, msg_text


def extract_status_change(chat_member_update: ChatMemberUpdated) -> Optional[tuple[bool, bool]]:
    """
    Принимает ChatMemberUpdated и извлекает, был ли "old_chat_member" участником чата и
    является ли "new_chat_member" участником чата. Возвращает None, если статус не изменился.

    :returns: was_member: bool, is_member: bool
    """
    status_change = chat_member_update.difference().get("status")
    old_is_member, new_is_member = chat_member_update.difference().get("is_member", (None, None))

    if status_change is None:
        return None

    old_status, new_status = status_change
    was_member = old_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (old_status == ChatMember.RESTRICTED and old_is_member is True)
    is_member = new_status in [
        ChatMember.MEMBER,
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
    ] or (new_status == ChatMember.RESTRICTED and new_is_member is True)

    return was_member, is_member
