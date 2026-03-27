import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import logger
from logger import _WSLSafeRotatingFileHandler


def _reset_named_logger(monkeypatch):
    named_logger = logging.getLogger("docxaicorrector")
    for handler in list(named_logger.handlers):
        handler.close()
        named_logger.removeHandler(handler)
    named_logger.setLevel(logging.NOTSET)
    named_logger.propagate = True
    monkeypatch.setattr(logger, "_LOGGER", None)
    return named_logger


def test_log_event_initializes_logger_lazily(monkeypatch):
    calls = []

    class FakeLogger:
        def log(self, level, message):
            calls.append(("log", level, message))

        def exception(self, message):
            calls.append(("exception", message))

    monkeypatch.setattr(logger, "_LOGGER", None)
    monkeypatch.setattr(logger, "setup_logger", lambda: calls.append(("setup",)) or FakeLogger())

    assert calls == []
    logger.log_event(20, "evt", "message", filename="report.docx")

    assert calls[0] == ("setup",)
    assert calls[1][0] == "log"


def test_extract_exception_message_prefers_structured_body_and_response():
    body_exc = SimpleNamespace(body={"error": {"message": "body message"}})
    assert logger.extract_exception_message(body_exc) == "body message"

    response_exc = SimpleNamespace(response=SimpleNamespace(json=lambda: {"error": {"message": "response message"}}))
    assert logger.extract_exception_message(response_exc) == "response message"


def test_format_user_error_maps_status_code_and_runtime_errors():
    class RateLimitedError(Exception):
        pass

    rate_exc = RateLimitedError("slow down")
    rate_exc.status_code = 429
    assert "ограничил запросы" in logger.format_user_error(rate_exc)

    runtime_exc = RuntimeError("custom runtime")
    assert logger.format_user_error(runtime_exc) == "custom runtime"


def test_format_user_error_normalizes_heading_only_runtime_error():
    runtime_exc = RuntimeError(
        "Модель вернула только заголовок при наличии основного текста во входном блоке (heading_only_output)."
    )

    assert logger.format_user_error(runtime_exc) == (
        "Модель вернула неполный результат для одного из блоков документа: "
        "вместо основного текста остался только заголовок. "
        "Это ошибка обработки блока, а не исходного файла. Попробуйте запустить обработку ещё раз."
    )


def test_present_error_hides_log_id_from_user_message(monkeypatch):
    monkeypatch.setattr(logger, "log_exception", lambda *args, **kwargs: "evt-123")

    message = logger.present_error(
        "structurally_insufficient_processed_block",
        RuntimeError("Модель вернула пустой Markdown-блок после успешного вызова (empty_processed_block)."),
        "Критическая ошибка обработки блока",
    )

    assert message == (
        "Модель вернула пустой результат для одного из блоков документа. "
        "Попробуйте запустить обработку ещё раз."
    )
    assert "[log:" not in message


def test_sanitize_log_context_serializes_nested_values(tmp_path):
    payload = {
        "path": tmp_path / "file.txt",
        "nested": {"items": [1, Path("demo.txt"), {"flag": True}]},
    }

    result = logger.sanitize_log_context(payload)

    assert result == {
        "path": str(tmp_path / "file.txt"),
        "nested": {"items": [1, "demo.txt", {"flag": True}]},
    }


def test_wsl_safe_rotating_handler_falls_back_to_copy_truncate_on_rename_failure(tmp_path):
    """When os.rename fails (WSL/Windows NTFS lock), rotate() falls back to copy+truncate."""
    source = tmp_path / "app.log"
    dest = tmp_path / "app.log.1"

    content = "old log content\n" * 100
    source.write_text(content, encoding="utf-8")
    assert source.stat().st_size > 0

    handler = _WSLSafeRotatingFileHandler(str(source), maxBytes=1, backupCount=1, encoding="utf-8")

    # Simulate rename failing (mimics Windows NTFS via WSL behaviour).
    with patch("logging.handlers.RotatingFileHandler.rotate", side_effect=OSError("Permission denied")):
        handler.rotate(str(source), str(dest))

    # dest should now contain the original content (copy succeeded).
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == content

    # source should be truncated (empty) so the handler can resume writing.
    assert source.stat().st_size == 0


def test_resolve_log_level_defaults_to_info_when_env_absent(monkeypatch):
    monkeypatch.delenv("DOCX_AI_LOG_LEVEL", raising=False)

    level, warning = logger._resolve_log_level()

    assert level == logging.INFO
    assert warning is None


def test_resolve_log_level_supports_case_insensitive_values(monkeypatch):
    monkeypatch.setenv("DOCX_AI_LOG_LEVEL", "dEbUg")

    level, warning = logger._resolve_log_level()

    assert level == logging.DEBUG
    assert warning is None


def test_setup_logger_uses_info_when_invalid_env_and_logs_one_warning(monkeypatch, tmp_path):
    named_logger = _reset_named_logger(monkeypatch)
    monkeypatch.setenv("DOCX_AI_LOG_LEVEL", "verbose")
    monkeypatch.setattr(logger, "RUN_DIR", tmp_path)
    monkeypatch.setattr(logger, "APP_LOG_PATH", tmp_path / "app.log")

    configured_logger = logger.setup_logger()

    assert configured_logger is named_logger
    assert configured_logger.level == logging.INFO
    assert len(configured_logger.handlers) == 1

    log_text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert log_text.count("Invalid DOCX_AI_LOG_LEVEL='verbose'; falling back to INFO.") == 1
    assert "Supported values: DEBUG, INFO, WARNING, ERROR, CRITICAL." in log_text
    assert "| WARNING |" in log_text


def test_setup_logger_writes_debug_events_when_env_requests_debug(monkeypatch, tmp_path):
    named_logger = _reset_named_logger(monkeypatch)
    monkeypatch.setenv("DOCX_AI_LOG_LEVEL", "debug")
    monkeypatch.setattr(logger, "RUN_DIR", tmp_path)
    monkeypatch.setattr(logger, "APP_LOG_PATH", tmp_path / "app.log")

    configured_logger = logger.setup_logger()
    configured_logger.debug("debug event visible")
    for handler in configured_logger.handlers:
        handler.flush()

    assert configured_logger is named_logger
    assert configured_logger.level == logging.DEBUG
    log_text = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "debug event visible" in log_text


def test_setup_logger_does_not_reconfigure_existing_logger(monkeypatch, tmp_path):
    named_logger = _reset_named_logger(monkeypatch)
    existing_handler = logging.StreamHandler()
    named_logger.addHandler(existing_handler)
    named_logger.setLevel(logging.ERROR)
    monkeypatch.setenv("DOCX_AI_LOG_LEVEL", "debug")
    monkeypatch.setattr(logger, "RUN_DIR", tmp_path)
    monkeypatch.setattr(logger, "APP_LOG_PATH", tmp_path / "app.log")

    configured_logger = logger.setup_logger()

    assert configured_logger is named_logger
    assert configured_logger.level == logging.ERROR
    assert configured_logger.handlers == [existing_handler]

    named_logger.removeHandler(existing_handler)
    existing_handler.close()
