from __future__ import annotations
import traceback, json
from .redact import safe_locals
from .config import TraceKitConfig

def format_exception_with_locals(exc: BaseException, cfg: TraceKitConfig) -> str:
    tb = exc.__traceback__
    parts: list[str] = []
    for i, (frame, lineno) in enumerate(traceback.walk_tb(tb), 1):
        code = frame.f_code
        parts.append(f"Frame #{i}: {code.co_name} @ {code.co_filename}:{lineno}")
        if cfg.capture_locals:
            sl = safe_locals(frame.f_locals, cfg.redact_patterns)
            parts.append("locals: " + json.dumps(sl, ensure_ascii=False)[: cfg.max_per_frame_json])
    parts.append(f"{exc.__class__.__name__}: {exc}")
    if cfg.include_stack_text:
        parts.append("".join(traceback.format_exception(type(exc), exc, tb)))
    text = "\n".join(parts)
    return text
