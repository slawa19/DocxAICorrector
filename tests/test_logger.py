import logging
from pathlib import Path
from typing import cast
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
import openai
import pytest

import docxaicorrector.core.logger as logger
from docxaicorrector.core.logger import _WSLSafeRotatingFileHandler


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
    assert logger.extract_exception_message(cast(Exception, body_exc)) == "body message"

    response_exc = SimpleNamespace(response=SimpleNamespace(json=lambda: {"error": {"message": "response message"}}))
    assert logger.extract_exception_message(cast(Exception, response_exc)) == "response message"


def test_format_user_error_maps_status_code_and_runtime_errors():
    class RateLimitedError(Exception):
        pass

    rate_exc = RateLimitedError("slow down")
    object.__setattr__(rate_exc, "status_code", 429)
    assert "ограничил запросы" in logger.format_user_error(rate_exc)

    runtime_exc = RuntimeError("custom runtime")
    assert logger.format_user_error(runtime_exc) == "custom runtime"


def _sdk_status_error(status_code: int, url: str) -> Exception:
    request = httpx2.Request("POST", url)
    response = httpx2.Response(status_code, request=request, json={"error": {"message": "provider said no"}})
    return openai.APIStatusError("provider said no", response=response, body=None)


_OPENROUTER_URL = "https://openrouter.ai/api/v1/responses"


@pytest.fixture
def shipped_config(monkeypatch):
    import docxaicorrector.core.config as config

    monkeypatch.setattr(config, "CONFIG_PATH", config.CONFIG_PATH)
    config.reset_app_config_cache()
    yield config
    config.reset_app_config_cache()


@pytest.mark.parametrize("status_code", [401, 402, 429])
def test_openrouter_errors_name_openrouter_not_openai(shipped_config, status_code):
    # Spec 061 FR-023 / User Story 6-4. OpenRouter is reached through the openai SDK, so the
    # exception class alone says "openai"; the request host is what identifies it.
    text = logger.format_user_error(_sdk_status_error(status_code, _OPENROUTER_URL))

    assert text.startswith("OpenRouter ")
    assert "OpenAI" not in text


def test_http_402_explains_exhausted_credits(shipped_config):
    text = logger.format_user_error(_sdk_status_error(402, _OPENROUTER_URL))

    assert "закончились кредиты" in text
    assert "402" in text


def test_openai_host_errors_still_name_openai(shipped_config):
    # Anti-vacuum: the substitution must not turn every provider into OpenRouter.
    text = logger.format_user_error(_sdk_status_error(401, "https://api.openai.com/v1/responses"))

    assert text == "OpenAI отклонил запрос из-за неверного или отсутствующего API-ключа."


def test_connection_errors_name_the_provider_of_the_request(shipped_config):
    request = httpx2.Request("POST", _OPENROUTER_URL)

    assert logger.format_user_error(openai.APIConnectionError(request=request)).startswith(
        "Не удалось подключиться к OpenRouter."
    )
    assert logger.format_user_error(openai.APITimeoutError(request=request)).startswith("OpenRouter не ответил")


def test_configured_display_name_is_used(monkeypatch, tmp_path):
    import docxaicorrector.core.config as config

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[providers.openrouter]\nenabled = true\napi_key_env = "OPENROUTER_API_KEY"\n'
        'base_url = "https://openrouter.ai/api/v1"\ndisplay_name = "Шлюз OpenRouter"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", config_path)
    config.reset_app_config_cache()
    try:
        text = logger.format_user_error(_sdk_status_error(429, _OPENROUTER_URL))
    finally:
        config.reset_app_config_cache()

    assert text.startswith("Шлюз OpenRouter временно ограничил запросы.")


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


def test_redirect_log_file_sends_each_block_to_its_own_file_and_restores_the_shared_one(monkeypatch, tmp_path):
    """Spec 067 FR-013: two runs in one process write two files; the shared log keeps neither."""
    _reset_named_logger(monkeypatch)
    shared_log = tmp_path / "shared" / "app.log"
    monkeypatch.setattr(logger, "RUN_DIR", shared_log.parent)
    monkeypatch.setattr(logger, "APP_LOG_PATH", shared_log)
    configured_logger = logger.get_logger()
    capture_handler = logging.StreamHandler()
    configured_logger.addHandler(capture_handler)
    handlers_before = list(configured_logger.handlers)

    run_a_log = tmp_path / "runs" / "run-a" / "app.log"
    run_b_log = tmp_path / "runs" / "run-b" / "app.log"
    with logger.redirect_log_file(run_a_log) as returned_path:
        assert returned_path == run_a_log
        # The non-file handler stays attached; only the file destination is swapped.
        assert capture_handler in configured_logger.handlers
        logger.log_event(logging.WARNING, "marker_paragraph_omitted", "run a", run_marker="run-a")
    with pytest.raises(SystemExit):
        with logger.redirect_log_file(run_b_log):
            logger.log_event(logging.WARNING, "marker_paragraph_omitted", "run b", run_marker="run-b")
            raise SystemExit(1)
    logger.log_event(logging.INFO, "after_runs", "back to the shared log")
    for handler in configured_logger.handlers:
        handler.flush()

    run_a_text = run_a_log.read_text(encoding="utf-8")
    run_b_text = run_b_log.read_text(encoding="utf-8")
    shared_text = shared_log.read_text(encoding="utf-8")
    assert '"run_marker": "run-a"' in run_a_text and "run-b" not in run_a_text
    assert '"run_marker": "run-b"' in run_b_text and "run-a" not in run_b_text
    assert "run_marker" not in shared_text
    assert "after_runs" in shared_text and "after_runs" not in run_a_text + run_b_text
    assert "| WARNING |" in run_a_text
    # A failing run (SystemExit) still gives the shared handler back.
    assert set(configured_logger.handlers) == set(handlers_before)
    configured_logger.removeHandler(capture_handler)


def _spawn_child_log_event(run_marker: str) -> None:
    """Run ``log_event`` in a REAL ``spawn``ed child, as the PDF parse child runs."""
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=logger.log_event,
        args=(logging.WARNING, "pdf_image_extraction_summary", "child record"),
        kwargs={"run_marker": run_marker},
    )
    process.start()
    process.join(timeout=60)
    assert process.exitcode == 0


def test_redirect_log_file_reaches_a_spawned_child_process(monkeypatch, tmp_path):
    """Spec 067 FR-013 (Codex acceptance P1): the PDF parse runs in a ``spawn``ed child
    (``processing_runtime._run_pdf_parse_stages_with_deadline``); its records must land in the
    run's file, and without a redirect the child keeps writing where it did before."""
    _reset_named_logger(monkeypatch)
    shared_dir = tmp_path / "shared"
    shared_log = shared_dir / "app.log"
    # The child resolves its run dir from the environment at import, like production.
    monkeypatch.setenv("DOCX_AI_RUN_DIR", str(shared_dir))
    monkeypatch.delenv(logger.RUN_LOG_FILE_ENV_VAR, raising=False)
    monkeypatch.setattr(logger, "RUN_DIR", shared_dir)
    monkeypatch.setattr(logger, "APP_LOG_PATH", shared_log)
    logger.get_logger()
    run_log = tmp_path / "runs" / "run-a" / "app.log"

    with logger.redirect_log_file(run_log):
        assert logger.os.environ[logger.RUN_LOG_FILE_ENV_VAR] == str(run_log.absolute())
        _spawn_child_log_event("child-inside-run")
    assert logger.RUN_LOG_FILE_ENV_VAR not in logger.os.environ
    _spawn_child_log_event("child-outside-run")

    run_text = run_log.read_text(encoding="utf-8")
    shared_text = shared_log.read_text(encoding="utf-8")
    assert '"run_marker": "child-inside-run"' in run_text
    assert "child-inside-run" not in shared_text
    assert '"run_marker": "child-outside-run"' in shared_text
    assert "child-outside-run" not in run_text


def test_redirect_log_file_restores_an_outer_run_log_variable(monkeypatch, tmp_path):
    _reset_named_logger(monkeypatch)
    monkeypatch.setattr(logger, "RUN_DIR", tmp_path)
    monkeypatch.setattr(logger, "APP_LOG_PATH", tmp_path / "app.log")
    monkeypatch.setenv(logger.RUN_LOG_FILE_ENV_VAR, str(tmp_path / "outer.log"))

    with logger.redirect_log_file(tmp_path / "inner" / "app.log"):
        assert logger.os.environ[logger.RUN_LOG_FILE_ENV_VAR] == str((tmp_path / "inner" / "app.log").absolute())
    assert logger.os.environ[logger.RUN_LOG_FILE_ENV_VAR] == str(tmp_path / "outer.log")
