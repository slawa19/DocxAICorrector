import json
import logging
import os
import shutil
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from constants import APP_LOG_PATH, RUN_DIR


_LOGGER: logging.Logger | None = None
_SUPPORTED_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


class _WSLSafeRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler that works reliably on Windows filesystems mounted in WSL.

    On DrvFs (Windows NTFS via /mnt/...), ``os.rename`` can fail with
    ``PermissionError`` if any other process (e.g. VS Code) has the log file
    open for reading.  The default implementation leaves ``self.stream = None``
    after the failed rename, silently dropping all subsequent log records.

    This subclass catches the ``OSError`` in ``rotate()`` and falls back to
    ``shutil.copy2`` + truncation, which does not require an exclusive lock on
    the source file.
    """

    def rotate(self, source: str, dest: str) -> None:
        try:
            super().rotate(source, dest)
        except OSError:
            try:
                shutil.copy2(source, dest)
                with open(source, "w", encoding="utf-8"):
                    pass  # truncate source in place, preserving the open inode
            except OSError:
                pass  # last resort: skip rotation, handler stays alive


def _resolve_log_level() -> tuple[int, str | None]:
    raw_value = os.getenv("DOCX_AI_LOG_LEVEL")
    if raw_value is None:
        return logging.INFO, None

    normalized_value = raw_value.strip().upper()
    resolved_level = _SUPPORTED_LOG_LEVELS.get(normalized_value)
    if resolved_level is not None:
        return resolved_level, None

    warning_message = (
        f"Invalid DOCX_AI_LOG_LEVEL={raw_value!r}; "
        "falling back to INFO. Supported values: DEBUG, INFO, WARNING, ERROR, CRITICAL."
    )
    return logging.INFO, warning_message


def setup_logger() -> logging.Logger:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("docxaicorrector")
    if logger.handlers:
        return logger

    resolved_level, warning_message = _resolve_log_level()
    logger.setLevel(resolved_level)
    handler = _WSLSafeRotatingFileHandler(APP_LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    if warning_message is not None:
        logger.warning(warning_message)
    return logger


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = setup_logger()
    return _LOGGER


def make_event_id(prefix: str = "evt") -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def format_elapsed(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def sanitize_log_context(value: object) -> object:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): sanitize_log_context(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [sanitize_log_context(item) for item in value]
    return str(value)


def log_event(level: int, event: str, message: str, **context: object) -> str:
    event_id = make_event_id(event)
    payload = {
        "event_id": event_id,
        "event": event,
        "message": message,
        "context": sanitize_log_context(context),
    }
    get_logger().log(level, json.dumps(payload, ensure_ascii=False))
    return event_id


def extract_exception_message(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error_data = body.get("error")
        if isinstance(error_data, dict):
            message = error_data.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()

    response = getattr(exc, "response", None)
    if response is not None:
        response_json = getattr(response, "json", None)
        if callable(response_json):
            try:
                response_data = response_json()
                if isinstance(response_data, dict):
                    error_data = response_data.get("error")
                    if isinstance(error_data, dict):
                        message = error_data.get("message")
                        if isinstance(message, str) and message.strip():
                            return message.strip()
            except Exception:
                pass

    return str(exc).strip() or exc.__class__.__name__


def _normalize_runtime_error_message(message: str) -> str:
    lowered = message.lower()

    if "heading_only_output" in lowered or (
        "только заголовок" in lowered and "основного текста" in lowered
    ):
        return (
            "Модель вернула неполный результат для одного из блоков документа: "
            "вместо основного текста остался только заголовок. "
            "Это ошибка обработки блока, а не исходного файла. Попробуйте запустить обработку ещё раз."
        )

    if "empty_processed_block" in lowered or "пустой markdown-блок" in lowered:
        return (
            "Модель вернула пустой результат для одного из блоков документа. "
            "Попробуйте запустить обработку ещё раз."
        )

    return message


def format_user_error(exc: Exception) -> str:
    message = extract_exception_message(exc)
    status_code = getattr(exc, "status_code", None)
    lowered = message.lower()

    if "unsupported parameter" in lowered and "temperature" in lowered:
        return "Выбранная модель не поддерживает параметр temperature. Запрос отправлен с неподдерживаемой настройкой модели."
    if status_code == 400:
        return f"OpenAI отклонил запрос: {message}"
    if status_code == 401:
        return "OpenAI отклонил запрос из-за неверного или отсутствующего API-ключа."
    if status_code == 403:
        return "OpenAI отклонил запрос из-за ограничений доступа к модели или аккаунту."
    if status_code == 404:
        return f"Запрошенная модель или ресурс не найдены: {message}"
    if status_code == 408:
        return "Запрос к OpenAI превысил время ожидания. Попробуйте повторить запуск."
    if status_code == 409:
        return f"OpenAI вернул конфликт состояния запроса: {message}"
    if status_code == 429:
        return "OpenAI временно ограничил запросы. Попробуйте позже или уменьшите нагрузку."
    if isinstance(status_code, int) and status_code >= 500:
        return "OpenAI временно недоступен. Попробуйте повторить запуск позже."
    if exc.__class__.__name__ == "APIConnectionError":
        return "Не удалось подключиться к OpenAI. Проверьте интернет или сетевые ограничения."
    if exc.__class__.__name__ == "APITimeoutError":
        return "OpenAI не ответил вовремя. Попробуйте повторить запуск."
    if isinstance(exc, (RuntimeError, ValueError)):
        return _normalize_runtime_error_message(message)
    return f"Непредвиденная ошибка: {message}"


def log_exception(event: str, exc: Exception, message: str, **context: object) -> str:
    event_id = make_event_id(event)
    payload = {
        "event_id": event_id,
        "event": event,
        "message": message,
        "error_type": exc.__class__.__name__,
        "error_message": extract_exception_message(exc),
        "status_code": getattr(exc, "status_code", None),
        "context": sanitize_log_context(context),
    }
    get_logger().exception(json.dumps(payload, ensure_ascii=False))
    return event_id


def present_error(event: str, exc: Exception, message: str, **context: object) -> str:
    log_exception(event, exc, message, **context)
    return format_user_error(exc)


def fail_critical(event: str, message: str, **context: object) -> None:
    event_id = log_event(logging.CRITICAL, event, message, **context)
    raise RuntimeError(f"{message} [log: {event_id}]")
