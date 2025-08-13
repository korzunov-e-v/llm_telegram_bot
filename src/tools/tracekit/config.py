from __future__ import annotations
from dataclasses import dataclass, field
import re

@dataclass
class TraceKitConfig:
    admin_chat_id: int
    sample_rate: float = 1.0
    enable_telegram_notify: bool = True
    enable_json_logs: bool = True
    capture_locals: bool = True
    max_tg_len: int = 3800               # запас против экранирования
    max_log_len: int = 100_000
    max_per_frame_json: int = 5000
    redact_patterns: re.Pattern = field(default_factory=lambda: re.compile(r"(token|password|secret|key|cookie|auth|session|bearer)", re.I))
    rate_limit_per_minute: int = 20      # простая защита от спама
    include_stack_text: bool = True      # добавлять обычный traceback
