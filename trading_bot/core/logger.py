"""Structured JSON and human-readable logging with secret redaction and rotation."""

import json
import logging
import logging.handlers
import os
import re
from datetime import datetime, timezone
from typing import Any

# Patterns to sanitize from log output
SENSITIVE_PATTERNS = [
    re.compile(r"(api[-_]?key|secret|token|password|auth|bearer)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-]{8,})['\"]?", re.IGNORECASE),
    re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{8,}", re.IGNORECASE),
]


class SecretSanitizingFilter(logging.Filter):
    """Filter to ensure sensitive API keys and tokens are never leaked into logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self.sanitize(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self.sanitize(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(self.sanitize(v) if isinstance(v, str) else v for v in record.args)
        return True

    @staticmethod
    def sanitize(text: str) -> str:
        sanitized = text
        for pattern in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(r"\1=[REDACTED]", sanitized)
        return sanitized


class JsonFormatter(logging.Formatter):
    """Format log records into structured JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_obj.update(record.extra_fields)
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    rotation_max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    json_format: bool = True,
    console_output: bool = True,
) -> None:
    """Configure system-wide root logger with file rotation and console output."""
    os.makedirs(log_dir, exist_ok=True)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    root_logger.handlers.clear()

    sanitizer = SecretSanitizingFilter()

    # File Handler (JSON rotated)
    file_path = os.path.join(log_dir, "trading_bot.log")
    file_handler = logging.handlers.RotatingFileHandler(
        file_path,
        maxBytes=rotation_max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.addFilter(sanitizer)
    if json_format:
        file_handler.setFormatter(JsonFormatter())
    else:
        file_handler.setFormatter(
            logging.Formatter("[%(asctime)s UTC] [%(levelname)s] [%(name)s:%(lineno)d] %(message)s")
        )
    root_logger.addHandler(file_handler)

    # Console Handler (Human-readable)
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.addFilter(sanitizer)
        console_handler.setFormatter(
            logging.Formatter("\033[90m%(asctime)s\033[0m [%(levelname)s] \033[36m%(name)s\033[0m: %(message)s")
        )
        root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Retrieve named logger."""
    return logging.getLogger(name)
