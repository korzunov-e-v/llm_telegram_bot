import logging
import sys

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
    logger.propagate = False
    # file_handler = logging.FileHandler(filename="search_log.log", encoding="utf-8")
    # file_handler.setLevel(logging.INFO)
    # file_handler.setFormatter(formatter)
    # logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.addFilter(lambda record: record.levelname != "ERROR")
    # stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler_e = logging.FileHandler(filename="error.log", encoding="utf-8")
    file_handler_e.setLevel(logging.ERROR)
    logger.addHandler(file_handler_e)

    return logger
