from __future__ import annotations
import logging, json
from logging.handlers import QueueHandler, QueueListener
from queue import Queue
from .request_context import req_id_var

_listener: QueueListener | None = None

def install_json_logging(logger_name: str = "ptb-tracekit", level: int = logging.INFO) -> logging.Logger:
    global _listener
    q = Queue(-1)
    qh = QueueHandler(q)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers[:] = [qh]

    class JsonSink(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            try:
                payload = {
                    "level": record.levelname,
                    "message": record.getMessage(),
                    "logger": record.name,
                    "req_id": getattr(record, "req_id", req_id_var.get("-")),
                }
                extra = getattr(record, "extra", None)
                if extra is not None:
                    payload["extra"] = extra
                print(json.dumps(payload, ensure_ascii=False))  # замените на отправку в агент/файл
            except Exception:
                pass

    _listener = QueueListener(q, JsonSink())
    _listener.start()
    return logging.getLogger(logger_name)

def get_logger(name: str = "ptb-tracekit") -> logging.Logger:
    return logging.getLogger(name)
