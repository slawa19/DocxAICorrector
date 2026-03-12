from pathlib import Path
from types import SimpleNamespace

import logger


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
    body_exc = RuntimeError("fallback")
    body_exc.body = {"error": {"message": "body message"}}
    assert logger.extract_exception_message(body_exc) == "body message"

    response_exc = RuntimeError("fallback")
    response_exc.response = SimpleNamespace(json=lambda: {"error": {"message": "response message"}})
    assert logger.extract_exception_message(response_exc) == "response message"


def test_format_user_error_maps_status_code_and_runtime_errors():
    rate_exc = RuntimeError("slow down")
    rate_exc.status_code = 429
    assert "ограничил запросы" in logger.format_user_error(rate_exc)

    runtime_exc = RuntimeError("custom runtime")
    assert logger.format_user_error(runtime_exc) == "custom runtime"


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