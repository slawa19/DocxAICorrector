from types import SimpleNamespace
from typing import Any, cast

from PIL import Image

import generation
import image_shared
from image_generation import _normalize_generated_document_background


def _as_openai_client(client: object) -> Any:
    return cast(Any, client)


class RetryableError(Exception):
    status_code = 429


def test_generate_markdown_block_retries_once_then_returns(monkeypatch):
    attempts = []
    sleep_calls = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            raise RetryableError("rate limited")
        return SimpleNamespace(output_text="```markdown\nИсправленный текст\n```")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="   ",
        context_after="\n\t",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    user_payload = attempts[0]["input"][1]["content"][0]["text"]
    assert "[CONTEXT BEFORE]\n[контекст отсутствует]" in user_payload
    assert "[TARGET BLOCK]\ntarget" in user_payload
    assert "[CONTEXT AFTER]\n[контекст отсутствует]" in user_payload
    assert attempts[0]["max_output_tokens"] >= 512


def test_generate_markdown_block_retries_on_empty_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(output_text="")
        return SimpleNamespace(output_text="Исправленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-empty",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert len(logged_events) == 1
    assert logged_events[0][0][1] == "model_empty_response_shape"
    assert logged_events[0][1]["error_code"] == "empty_response"


def test_generate_markdown_block_retries_on_incomplete_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])
        return SimpleNamespace(status="completed", output_text="Исправленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-incomplete",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert attempts[0]["max_output_tokens"] == 512
    assert attempts[1]["max_output_tokens"] == 1024
    assert logged_events[0][0][1] == "model_empty_response_shape"
    assert logged_events[0][1]["error_code"] == "incomplete_response"


def test_generate_markdown_block_uses_degraded_prompt_after_persistent_empty_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) <= 2:
            return SimpleNamespace(output_text="")
        return SimpleNamespace(output_text="Восстановленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-empty-recovery",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Восстановленный текст"
    assert len(attempts) == 3
    assert sleep_calls == [1]
    assert "[TARGET BLOCK ONLY]\ntarget" in attempts[-1]["input"][1]["content"][0]["text"]
    assert "[CONTEXT BEFORE]" not in attempts[-1]["input"][1]["content"][0]["text"]
    assert logged_events[-1][0][1] == "markdown_empty_response_recovery_started"


def test_generate_markdown_block_raises_on_empty_model_output(monkeypatch):
    logged_events = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="```\n\n```"))
    )
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-collapsed",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "collapsed_output" in str(exc)
        assert logged_events[0][1]["error_code"] == "collapsed_output"
    else:
        raise AssertionError("Expected RuntimeError for a collapsed model response")


def test_generate_markdown_block_retries_on_collapsed_output(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(output_text="```markdown\n   \n```")
        return SimpleNamespace(output_text="Итоговый текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-collapsed-retry",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Итоговый текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert len(logged_events) == 1
    assert logged_events[0][1]["error_code"] == "collapsed_output"


def test_generate_markdown_block_retries_without_max_output_tokens_when_sdk_rejects_it():
    calls = []

    def create_response(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise TypeError("unexpected keyword argument 'max_output_tokens'")
        return SimpleNamespace(output_text="ok")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=1,
    )

    assert result == "ok"
    assert "max_output_tokens" in calls[0]
    assert "max_output_tokens" not in calls[1]


def test_generate_markdown_block_raises_after_persistent_empty_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        return SimpleNamespace(output_text="")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-persistent-empty",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=3,
        )
    except RuntimeError as exc:
        assert "empty_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when all attempts return an empty response")

    assert len(attempts) == 4
    assert sleep_calls == [1, 2]
    assert len(logged_events) == 5
    assert any(args[1] == "markdown_empty_response_recovery_started" for args, _ in logged_events)


def test_generate_markdown_block_falls_back_to_source_after_persistent_incomplete_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-persistent-incomplete",
    )

    target_text = "Короткий исходный абзац, который должен сохраниться без падения пайплайна."
    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text=target_text,
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == target_text
    assert len(attempts) == 3
    assert sleep_calls == [1]
    assert attempts[0]["max_output_tokens"] == 512
    assert attempts[1]["max_output_tokens"] == 1024
    assert attempts[2]["max_output_tokens"] == 1536
    assert any(args[1] == "markdown_empty_response_recovery_started" for args, _ in logged_events)
    assert logged_events[-1][0][1] == "markdown_incomplete_response_source_fallback"


def test_generate_markdown_block_falls_back_to_source_after_persistent_incomplete_response_for_long_block(monkeypatch):
    attempts = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-persistent-incomplete-long",
    )

    target_text = "Длинный блок. " * 150
    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text=target_text,
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == target_text
    assert len(attempts) == 3
    assert logged_events[-1][0][1] == "markdown_incomplete_response_source_fallback"


def test_generate_markdown_block_passthrough_for_image_only_target(monkeypatch):
    logged_events = []
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(AssertionError("must not call API"))))
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-image-only",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="[[DOCX_IMAGE_img_001]]",
        context_before="before",
        context_after="after",
        max_retries=1,
    )

    assert result == "[[DOCX_IMAGE_img_001]]"
    assert logged_events[0][0][1] == "image_only_target_passthrough"


def test_generate_markdown_block_passthrough_for_placeholder_only_marker_target(monkeypatch):
    logged_events = []
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(AssertionError("must not call API"))))
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-placeholder-only",
    )

    target_text = "[[DOCX_PARA_p0001]]\n[[DOCX_IMAGE_img_001]]"
    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text=target_text,
        context_before="before",
        context_after="after",
        max_retries=1,
        expected_paragraph_ids=["p0001"],
        marker_mode=True,
    )

    assert result == target_text
    assert logged_events[0][0][1] == "image_only_target_passthrough"


def test_generate_markdown_block_raises_on_missing_output_text(monkeypatch):
    logged_events = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace())
    )
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-missing-output",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "empty_response" in str(exc)
        assert logged_events[0][1]["error_code"] == "empty_response"
    else:
        raise AssertionError("Expected RuntimeError when output_text is missing")


def test_extract_response_output_text_falls_back_to_supported_response_output_items():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(type="output_text", text="Структурированный ответ")]
            )
        ]
    )

    assert generation._extract_response_output_text(response) == "Структурированный ответ"


def test_extract_response_output_text_reads_supported_nested_text_value_from_response_output():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text=SimpleNamespace(value="Ответ из value-поля"),
                    )
                ]
            )
        ]
    )

    assert generation._extract_response_output_text(response) == "Ответ из value-поля"


def test_generate_markdown_block_raises_on_unsupported_response_shape_in_output_items(monkeypatch):
    sleep_calls = []
    attempts = []

    def create_response(**_):
        attempts.append("call")
        return SimpleNamespace(
            output=[SimpleNamespace(content=[SimpleNamespace(type="refusal", text="not supported")])]
        )

    client = SimpleNamespace(
        responses=SimpleNamespace(create=create_response)
    )
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "unsupported_response_shape" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for unsupported response output shape")

    assert attempts == ["call"]
    assert sleep_calls == []


def test_generate_markdown_block_raises_when_supported_response_output_collapses_after_normalization(monkeypatch):
    logged_events = []
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: SimpleNamespace(
                output=[SimpleNamespace(content=[SimpleNamespace(type="output_text", text="```markdown\n   \n```")])]
            )
        )
    )
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-supported-collapse",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "collapsed_output" in str(exc)
        assert logged_events[0][1]["error_code"] == "collapsed_output"
    else:
        raise AssertionError("Expected RuntimeError when normalized fallback output collapses")


def test_generate_markdown_block_raises_on_non_string_output_text():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text=["invalid"]))
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "неподдерживаемом формате" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when output_text is not a string")


def test_generate_markdown_block_rejects_max_retries_less_than_one():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="unused"))
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=0,
        )
    except ValueError as exc:
        assert "max_retries" in str(exc)
    else:
        raise AssertionError("Expected ValueError when max_retries is less than 1")


def test_generate_markdown_block_rejects_non_integer_max_retries():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="unused"))
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=cast(int, 1.5),
        )
    except TypeError as exc:
        assert "max_retries" in str(exc)
    else:
        raise AssertionError("Expected TypeError when max_retries is not an integer")


def test_extract_normalized_markdown_logs_empty_response_shape(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-empty-shape",
    )

    try:
        generation._extract_normalized_markdown(SimpleNamespace())
    except RuntimeError as exc:
        assert "empty_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for empty response shape")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "empty_response"
    assert kwargs["raw_output_len"] == 0


def test_extract_normalized_markdown_raises_on_incomplete_response(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-incomplete-shape",
    )

    try:
        generation._extract_normalized_markdown(
            SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])
        )
    except RuntimeError as exc:
        assert "incomplete_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for incomplete response")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "incomplete_response"


def test_extract_normalized_markdown_raises_hard_on_non_completed_response(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-non-completed-shape",
    )

    try:
        generation._extract_normalized_markdown(SimpleNamespace(status="failed"))
    except RuntimeError as exc:
        assert "non_completed_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for non-completed response")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "non_completed_response"


def test_incomplete_response_is_retryable():
    assert generation._is_retryable_empty_generation_error(RuntimeError("incomplete_response")) is True


def test_non_completed_response_is_not_retryable():
    assert generation._is_retryable_empty_generation_error(RuntimeError("non_completed_response")) is False


def test_extract_normalized_markdown_logs_collapsed_output_shape(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-collapsed-shape",
    )

    try:
        generation._extract_normalized_markdown(SimpleNamespace(output_text="```markdown\n\n```") )
    except RuntimeError as exc:
        assert "collapsed_output" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for collapsed response shape")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "collapsed_output"
    assert kwargs["raw_output_len"] > 0


def test_ensure_pandoc_available_converts_os_error(monkeypatch):
    def raise_os_error():
        raise OSError("pandoc missing")

    generation.ensure_pandoc_available.cache_clear()
    monkeypatch.setattr(generation.pypandoc, "get_pandoc_version", raise_os_error)

    try:
        generation.ensure_pandoc_available()
    except RuntimeError as exc:
        assert "WSL runtime" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when pandoc is unavailable")
    finally:
        generation.ensure_pandoc_available.cache_clear()


def test_convert_markdown_to_docx_bytes_calls_pandoc_and_reads_output(monkeypatch, tmp_path):
    monkeypatch.setattr(generation, "ensure_pandoc_available", lambda: None)

    def fake_convert_file(source_path, *, to, format, outputfile, extra_args):
        assert source_path.endswith("result.md")
        assert to == "docx"
        assert format == "md"
        assert any(str(argument).startswith("--reference-doc=") for argument in extra_args)
        with open(outputfile, "wb") as file_handle:
            file_handle.write(b"docx-bytes")

    monkeypatch.setattr(generation.pypandoc, "convert_file", fake_convert_file)

    result = generation.convert_markdown_to_docx_bytes("# Title")

    assert result == b"docx-bytes"


def test_normalize_model_output_strips_any_code_fence_language_tag():
    assert generation.normalize_model_output("```python\nprint(1)\n```") == "print(1)"


def test_normalize_model_output_returns_empty_for_whitespace_only_fenced_block():
    assert generation.normalize_model_output("```markdown\n   \n\t\n```") == ""


def test_parse_json_object_with_backtick_in_content():
    result = image_shared.parse_json_object(
        '```json\n{"key": "val`ue"}\n```',
        empty_message="empty",
        no_json_message="nojson",
    )

    assert result == {"key": "val`ue"}


def test_parse_json_object_fence_without_newline():
    result = image_shared.parse_json_object(
        '```{"key": 1}```',
        empty_message="empty",
        no_json_message="nojson",
    )

    assert result == {"key": 1}


def test_call_responses_create_with_retry_retries_without_timeout_on_final_attempt():
    calls = []

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise TypeError("unexpected keyword argument 'timeout'")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
    )

    assert result.output_text == "ok"
    assert calls == [
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        {"model": "gpt-5.4", "input": []},
    ]


def test_call_responses_create_with_retry_does_not_double_consume_budget_after_timeout_removal():
    class BudgetExceeded(RuntimeError):
        pass

    class Budget:
        def __init__(self):
            self.used_calls = 0

        def consume(self, operation_name):
            if self.used_calls >= 1:
                raise BudgetExceeded("exhausted")
            self.used_calls += 1

    calls = []
    budget = Budget()

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise TypeError("unexpected keyword argument 'timeout'")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
        budget=budget,
    )

    assert result.output_text == "ok"
    assert budget.used_calls == 1
    assert calls == [
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        {"model": "gpt-5.4", "input": []},
    ]


def test_call_responses_create_with_retry_consumes_budget_only_after_retryable_success():
    class Budget:
        def __init__(self):
            self.used_calls = 0

        def ensure_available(self, operation_name):
            return None

        def consume(self, operation_name):
            self.used_calls += 1

    calls = []
    budget = Budget()

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise RetryableError("rate limited")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5.4", "input": []},
        max_retries=2,
        retryable_error_predicate=lambda exc: isinstance(exc, RetryableError),
        budget=budget,
    )

    assert result.output_text == "ok"
    assert len(calls) == 2
    assert budget.used_calls == 1


def test_normalize_generated_document_background_whitens_dark_border_only():
    image = Image.new("RGBA", (12, 12), (0, 0, 0, 255))
    for x_coord in range(3, 9):
        for y_coord in range(3, 9):
            image.putpixel((x_coord, y_coord), (200, 0, 0, 255))

    normalized = _normalize_generated_document_background(image)

    assert normalized.getpixel((0, 0)) == (255, 255, 255, 255)
    assert normalized.getpixel((5, 5)) == (200, 0, 0, 255)


def test_generate_markdown_block_strips_image_placeholders_from_context(monkeypatch):
    captured_inputs = []

    def create_response(**kwargs):
        captured_inputs.append(kwargs.get("input", []))
        return SimpleNamespace(output_text="Исправленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="Основной текст без placeholder'а",
        context_before="Предшествующий блок\n\n[[DOCX_IMAGE_img_001]]\n\nДополнительный текст",
        context_after="[[DOCX_IMAGE_img_002]] Следующий блок",
        max_retries=1,
    )

    assert result == "Исправленный текст"
    assert len(captured_inputs) == 1
    all_prompt_text = " ".join(
        item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
        for message in captured_inputs[0]
        for content_item in (
            message.get("content", []) if isinstance(message, dict) else getattr(message, "content", [])
        )
        for item in ([content_item] if isinstance(content_item, dict) else [])
    )
    assert "[[DOCX_IMAGE_img_" not in all_prompt_text


def test_generate_markdown_block_marker_mode_preserves_markers_and_returns_clean_markdown(monkeypatch):
    captured_inputs = []

    def create_response(**kwargs):
        captured_inputs.append(kwargs.get("input", []))
        return SimpleNamespace(
            output_text="[[DOCX_PARA_p0001]]\nИсправленный заголовок\n\n[[DOCX_PARA_p0002]]\nИсправленный абзац"
        )

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="[[DOCX_PARA_p0001]]\n# Заголовок\n\n[[DOCX_PARA_p0002]]\nАбзац",
        context_before="before",
        context_after="after",
        max_retries=1,
        expected_paragraph_ids=["p0001", "p0002"],
        marker_mode=True,
    )

    assert result == "Исправленный заголовок\n\nИсправленный абзац"
    prompt_text = captured_inputs[0][1]["content"][0]["text"]
    assert "[TARGET BLOCK WITH MARKERS]" in prompt_text
    assert "Сохрани каждый marker" in prompt_text


def test_generate_markdown_block_marker_mode_retries_and_recovers_when_markers_are_lost(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) <= 2:
            return SimpleNamespace(output_text="Маркеры потеряны")
        return SimpleNamespace(output_text="[[DOCX_PARA_p0001]]\nВосстановленный абзац")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-marker-recovery",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="[[DOCX_PARA_p0001]]\nАбзац",
        context_before="before",
        context_after="after",
        max_retries=2,
        expected_paragraph_ids=["p0001"],
        marker_mode=True,
    )

    assert result == "Восстановленный абзац"
    assert len(attempts) == 3
    assert sleep_calls == [1]
    assert logged_events[-1][0][1] == "markdown_empty_response_recovery_started"
    assert "[TARGET BLOCK WITH MARKERS ONLY]" in attempts[-1]["input"][1]["content"][0]["text"]


def test_detect_context_leakage_finds_verbatim_fragment_absent_from_target():
    leaked_fragment = generation._detect_context_leakage(
        response_text=(
            "Исправленный блок. Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние."
        ),
        target_text="Исправленный блок.",
        context_before=(
            "Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние."
        ),
        context_after="Следующий абзац без совпадений.",
    )

    assert leaked_fragment == "Возможно, вы взяли эту книгу, думая"


def test_generate_markdown_block_retries_on_context_leakage_and_reinforces_prompt(monkeypatch):
    attempts = []
    sleep_calls = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(
                output_text=(
                    "Исправленный блок. Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние."
                )
            )
        return SimpleNamespace(output_text="Исправленный блок.")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="Исправленный блок.",
        context_before="Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние.",
        context_after="Следующий абзац без совпадений.",
        max_retries=2,
    )

    assert result == "Исправленный блок."
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert generation._CONTEXT_LEAKAGE_RETRY_WARNING in attempts[1]["input"][1]["content"][0]["text"]


def test_strip_image_placeholders_removes_only_placeholder_tokens():
    result = generation._strip_image_placeholders(
        "Текст перед\n\n[[DOCX_IMAGE_img_001]]\n\nТекст после"
    )
    assert "[[DOCX_IMAGE_img_" not in result
    assert "Текст перед" in result
    assert "Текст после" in result
