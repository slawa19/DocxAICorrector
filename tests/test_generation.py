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


def test_generate_markdown_block_raises_on_empty_model_output():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="```\n\n```"))
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
    else:
        raise AssertionError("Expected RuntimeError for a collapsed model response")


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


def test_generate_markdown_block_raises_on_missing_output_text():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace())
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


def test_generate_markdown_block_raises_on_unsupported_response_shape_in_output_items():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: SimpleNamespace(
                output=[SimpleNamespace(content=[SimpleNamespace(type="refusal", text="not supported")])]
            )
        )
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
        assert "unsupported_response_shape" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for unsupported response output shape")


def test_generate_markdown_block_raises_when_supported_response_output_collapses_after_normalization():
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: SimpleNamespace(
                output=[SimpleNamespace(content=[SimpleNamespace(type="output_text", text="```markdown\n   \n```")])]
            )
        )
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
