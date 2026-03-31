import logging
import sys
import json
from datetime import datetime
from typing import Any, Mapping


class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs log records as JSON strings.
    Includes timestamp, level, logger name, message and any extra fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Base log record
        log_record: Mapping[str, Any] = {
            "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include any extra attributes passed via the `extra` argument
        if record.__dict__.get("extra"):
            log_record.update(record.__dict__["extra"])

        # Merge any custom attributes that are not part of the standard LogRecord
        for key, value in record.__dict__.items():
            if key not in (
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "extra",
            ):
                log_record[key] = value

        return json.dumps(log_record)


def get_logger(name: str = "laundrypool") -> logging.Logger:
    """
    Returns a configured logger instance.
    The logger writes JSON‑formatted logs to stdout.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        # Logger already configured
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(JSONFormatter())

    logger.addHandler(handler)
    logger.propagate = False
    return logger


# Export a module‑level logger for convenience
logger = get_logger()