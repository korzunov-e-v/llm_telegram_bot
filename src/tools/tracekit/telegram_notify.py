from __future__ import annotations
from telegram.constants import ParseMode
from telegram import Bot
import time, random

def _escape_inline(s: str) -> str:
    # Минимальное экранирование для заголовков MarkdownV2
    return s.replace("_", "\\_").replace("*", "\\*").replace("[", "\\[").replace("`", "\\`")

def build_md_message(short_text: str, req_id: str) -> str:
    # Внутри ``` не экранируем, только защищаем ```
    safe_block = short_text.replace("```", "`\u200b``")
    return (
        f"*Error* \\(req\\_id: `{_escape_inline(req_id)}`\\)\n"
        "```text\n" + safe_block + "\n```"
    )

# Примитивный rate limit — N сообщений в минуту на процесс
_last_minute = int(time.time() // 60)
_count = 0

def _allow_send(max_per_minute: int) -> bool:
    global _last_minute, _count
    now_min = int(time.time() // 60)
    if now_min != _last_minute:
        _last_minute, _count = now_min, 0
    if _count < max_per_minute:
        _count += 1
        return True
    return False

async def send_markdown_v2(bot: Bot, chat_id: int, text: str, max_per_minute: int, sample_rate: float = 1.0):
    if sample_rate < 1.0 and random.random() > sample_rate:
        return
    if not _allow_send(max_per_minute):
        return
    await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN_V2)
