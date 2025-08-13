from __future__ import annotations
import uuid
from telegram.ext import Application, ApplicationHandlerStop, TypeHandler
from telegram import Update
from .request_context import req_id_var
from .config import TraceKitConfig
from .trace import format_exception_with_locals
from .logger import get_logger, install_json_logging
from .telegram_notify import build_md_message, send_markdown_v2

log = get_logger("ptb-tracekit")

async def _on_update(update: Update, context):
    # присваиваем req_id каждому апдейту
    rid = str(uuid.uuid4())
    req_id_var.set(rid)
    log.info("update received", extra={"req_id": rid})

async def _on_error(update: object, context):
    cfg: TraceKitConfig = context.application.bot_data.get("_tracekit_cfg")
    if cfg is None:
        return  # не настроено
    rid = req_id_var.get("-")
    exc = context.error
    dump = format_exception_with_locals(exc, cfg)

    # лог в JSON
    if cfg.enable_json_logs:
        short_for_log = dump[: cfg.max_log_len]
        log.error("exception", extra={"req_id": rid, "extra": {"trace": short_for_log}})

    # уведомление в TG
    if cfg.enable_telegram_notify and cfg.admin_chat_id:
        short_for_tg = dump[: cfg.max_tg_len]
        md = build_md_message(short_for_tg, rid)
        try:
            await send_markdown_v2(context.bot, cfg.admin_chat_id, md, cfg.rate_limit_per_minute, cfg.sample_rate)
        except Exception as e:
            log.error("notify_failed", extra={"req_id": rid, "extra": {"reason": str(e)}})

def install_tracekit(app: Application, cfg: TraceKitConfig) -> None:
    # регистрируем ранний хендлер и error handler
    if cfg.enable_json_logs:
        install_json_logging()
    app.bot_data["_tracekit_cfg"] = cfg
    app.add_handler(TypeHandler(Update, _on_update), group=-10_000)
    app.add_error_handler(_on_error)
