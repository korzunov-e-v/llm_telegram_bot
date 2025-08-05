import logging
import sys
import time

from telegram import Update

from src.tools.update_getters import get_update_info

logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)
logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    encoding="utf-8",
    level=logging.INFO,
)


def get_logger(name: str):
    logger = logging.getLogger(name)
    logger.handlers.clear()
    logger.propagate = False

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(logging.INFO)
    logger.addHandler(stream_handler)

    file_handler_e = logging.FileHandler(filename="error.log", encoding="utf-8")
    file_handler_e.setLevel(logging.WARNING)
    logger.addHandler(file_handler_e)

    return logger


def log_decorator(func):
    async def wrap(*args, **kwargs):
        logger = get_logger(__name__)

        if isinstance(args[0], Update):
            update = args[0]
            context = args[1]
        else:
            context = args[0]
            msg_text = args[1]
            update = context.job.data["update"]

        update_info = await get_update_info(update)
        username, full_name, user_id, chat_id, topic_id, msg_text = update_info.__dict__.values()
        ts1 = time.time_ns()
        result = await func(*args, **kwargs)
        ts2 = time.time_ns()
        req_time = (ts2 - ts1) / 10 ** 6
        logger.info(f"{func.__name__} called ({req_time}ms). {username=}, {full_name=}, {user_id=}, {chat_id=}, {topic_id=}, {msg_text=}")
        return result

    return wrap
