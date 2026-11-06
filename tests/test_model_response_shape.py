"""Spec 061 P1-3 (User Story 3): one response shape and typed failure classes.

Every test here is deterministic: the provider is a stub, no model is called.
"""

from types import SimpleNamespace
from typing import Any

import pytest
from anthropic.types import Message as AnthropicMessage
from anthropic.types import TextBlock as AnthropicTextBlock
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice as ChatChoice
from openai.types.responses import Response as ResponsesResponse

import docxaicorrector.core.model_accounting as model_accounting
import docxaicorrector.generation._generation as generation
from docxaicorrector.generation.model_response import (
    CollapsedOutput,
    EmptyResponse,
    IncompleteResponse,
    ModelResponse,
    ModelResponseError,
    NonCompletedResponse,
)

_SOURCE = "[[DOCX_PARA_p0001]]\nSource paragraph one.\n\n[[DOCX_PARA_p0002]]\nSource paragraph two."
_EXPECTED_IDS = ["p0001", "p0002"]
# Both markers intact and in order: by the marker contract alone this answer would be accepted.
_TRUNCATED_BUT_MARKER_VALID = "[[DOCX_PARA_p0001]]\nПервый абзац.\n\n[[DOCX_PARA_p0002]]\nВторой абз"
_COMPLETE_ANSWER = "[[DOCX_PARA_p0001]]\nПервый абзац.\n\n[[DOCX_PARA_p0002]]\nВторой абзац."


@pytest.fixture(autouse=True)
def _quiet_generation(monkeypatch):
    monkeypatch.setattr(generation.time, "sleep", lambda *_: None)
    monkeypatch.setattr(generation, "log_event", lambda *args, **kwargs: None)
    model_accounting.reset_run_model_accounting()


def _openrouter_chat_only_client(answers: list[tuple[str, str]], chat_calls: list[dict[str, Any]]) -> Any:
    """An OpenRouter client whose Responses endpoint is rejected, so Chat Completions serves."""

    class UnsupportedResponsesError(Exception):
        status_code = 400

    def responses_create(**_kwargs):
        raise UnsupportedResponsesError("Responses API unsupported for this model; use chat.completions instead.")

    def chat_create(**kwargs):
        chat_calls.append(dict(kwargs))
        content, finish_reason = answers[min(len(chat_calls), len(answers)) - 1]
        return ChatCompletion.model_construct(
            choices=[
                ChatChoice.model_construct(
                    index=0,
                    finish_reason=finish_reason,
                    message=ChatCompletionMessage.model_construct(role="assistant", content=content),
                )
            ]
        )

    return SimpleNamespace(
        base_url="https://openrouter.ai/api/v1",
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )


def _anthropic_client(answers: list[tuple[str, str]], calls: list[dict[str, Any]]) -> Any:
    def create_message(**kwargs):
        calls.append(dict(kwargs))
        text, stop_reason = answers[min(len(calls), len(answers)) - 1]
        return AnthropicMessage.model_construct(
            content=[AnthropicTextBlock.model_construct(type="text", text=text)],
            stop_reason=stop_reason,
        )

    return SimpleNamespace(messages=SimpleNamespace(create=create_message))


def _generate_marker_block(client: Any, *, max_retries: int = 2, **extra: Any) -> str:
    return generation.generate_markdown_block(
        client=client,
        model="some-model",
        system_prompt="system",
        target_text=_SOURCE,
        context_before="",
        context_after="",
        max_retries=max_retries,
        expected_paragraph_ids=_EXPECTED_IDS,
        marker_mode=True,
        **extra,
    )


# --- FR-010: the three extractors produce ONE shape, read from the SDK's own fields ------


def test_chat_completions_length_finish_reason_reads_as_incomplete():
    response = ChatCompletion.model_construct(
        choices=[
            ChatChoice.model_construct(
                index=0,
                finish_reason="length",
                message=ChatCompletionMessage.model_construct(role="assistant", content="Обрезанный"),
            )
        ]
    )

    assert generation._read_chat_completion_model_response(response) == ModelResponse(
        text="Обрезанный", incomplete=True, stop_reason="length"
    )


def test_anthropic_max_tokens_stop_reason_reads_as_incomplete():
    response = AnthropicMessage.model_construct(
        content=[AnthropicTextBlock.model_construct(type="text", text="Обрезанный")],
        stop_reason="max_tokens",
    )

    assert generation._read_anthropic_model_response(response) == ModelResponse(
        text="Обрезанный", incomplete=True, stop_reason="max_tokens"
    )


def test_responses_incomplete_status_reads_as_incomplete_with_the_provider_reason():
    response = ResponsesResponse.model_construct(
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
        output=[],
    )

    assert generation._read_responses_model_response(response) == ModelResponse(
        text="", incomplete=True, stop_reason="max_output_tokens"
    )


def test_a_natural_stop_is_complete_on_every_path():
    """Anti-vacuum: the flag is not simply always set."""

    chat = ChatCompletion.model_construct(
        choices=[
            ChatChoice.model_construct(
                index=0,
                finish_reason="stop",
                message=ChatCompletionMessage.model_construct(role="assistant", content="Готово"),
            )
        ]
    )
    anthropic = AnthropicMessage.model_construct(
        content=[AnthropicTextBlock.model_construct(type="text", text="Готово")],
        stop_reason="end_turn",
    )
    responses = SimpleNamespace(status="completed", output_text="Готово")

    assert generation._read_chat_completion_model_response(chat) == ModelResponse("Готово", False, "stop")
    assert generation._read_anthropic_model_response(anthropic) == ModelResponse("Готово", False, "end_turn")
    assert generation._read_responses_model_response(responses) == ModelResponse("Готово", False, None)


# --- FR-011, US3 scenario 1: truncation is retried on chat.completions and Anthropic -----


def test_chat_completions_truncated_answer_with_valid_markers_is_retried_not_accepted():
    chat_calls: list[dict[str, Any]] = []
    client = _openrouter_chat_only_client(
        [(_TRUNCATED_BUT_MARKER_VALID, "length"), (_COMPLETE_ANSWER, "stop")], chat_calls
    )

    result = _generate_marker_block(client)

    assert len(chat_calls) == 2
    assert "Второй абзац." in str(result)
    assert "Второй абз\n" not in str(result) and not str(result).endswith("Второй абз")
    # The same budget boost the Responses path gets on ``incomplete_response``.
    assert chat_calls[1]["max_tokens"] > chat_calls[0]["max_tokens"]
    snapshot = model_accounting.snapshot_run_model_accounting()
    assert snapshot["retry_reason_counts"] == {"incomplete_response": 1}
    assert snapshot["api_path_counts"] == {"chat_completions": 2}


def test_anthropic_truncated_answer_with_valid_markers_is_retried_not_accepted():
    calls: list[dict[str, Any]] = []
    client = _anthropic_client([(_TRUNCATED_BUT_MARKER_VALID, "max_tokens"), (_COMPLETE_ANSWER, "end_turn")], calls)

    result = _generate_marker_block(client)

    assert len(calls) == 2
    assert "Второй абзац." in str(result)
    assert calls[1]["max_tokens"] > calls[0]["max_tokens"]
    snapshot = model_accounting.snapshot_run_model_accounting()
    assert snapshot["retry_reason_counts"] == {"incomplete_response": 1}
    assert snapshot["api_path_counts"] == {"anthropic": 2}


def test_a_complete_chat_answer_is_accepted_on_the_first_call():
    """Anti-vacuum for the two tests above: a natural stop costs exactly one call."""

    chat_calls: list[dict[str, Any]] = []
    client = _openrouter_chat_only_client([(_COMPLETE_ANSWER, "stop")], chat_calls)

    result = _generate_marker_block(client)

    assert len(chat_calls) == 1
    assert "Второй абзац." in str(result)
    assert model_accounting.snapshot_run_model_accounting()["retry_reason_counts"] == {}


def test_persistent_chat_truncation_takes_the_incomplete_response_source_fallback(monkeypatch):
    """The exhausted path is the one ``status == "incomplete"`` takes on Responses: recovery
    with a boosted budget, then the same controlled fallback with the same counter."""

    events: list[str] = []
    monkeypatch.setattr(generation, "log_event", lambda _level, event_id, *_a, **_k: events.append(event_id))
    chat_calls: list[dict[str, Any]] = []
    client = _openrouter_chat_only_client([("Обрезанный ответ", "length")], chat_calls)
    target_text = "Короткий исходный абзац, который должен сохраниться без падения пайплайна."

    result = generation.generate_markdown_block(
        client=client,
        model="some-model",
        system_prompt="system",
        target_text=target_text,
        context_before="",
        context_after="",
        max_retries=2,
    )

    assert result == target_text
    assert len(chat_calls) == 3
    assert [call["max_tokens"] for call in chat_calls] == [512, 1024, 1536]
    assert events[-1] == "markdown_incomplete_response_source_fallback"
    snapshot = model_accounting.snapshot_run_model_accounting()
    assert snapshot["model_output_discarded_reason_counts"] == {"incomplete_response_source_fallback": 1}


# --- FR-012, US3 scenario 3: the class is the TYPE, not a substring ----------------------


def test_failure_classes_are_types_and_keep_their_code_in_the_message():
    for error_type, code in (
        (EmptyResponse, "empty_response"),
        (CollapsedOutput, "collapsed_output"),
        (IncompleteResponse, "incomplete_response"),
        (NonCompletedResponse, "non_completed_response"),
    ):
        assert issubclass(error_type, ModelResponseError)
        assert issubclass(error_type, RuntimeError)
        assert error_type.error_code == code


def test_a_message_that_merely_mentions_a_code_is_not_that_class():
    """The substring used to BE the class. A provider error quoting ``empty_response`` in
    its text must not be retried as an empty answer, and a typed one must be."""

    impostor = RuntimeError("upstream said: empty_response / incomplete_response / collapsed_output")

    assert not generation._is_retryable_empty_generation_error(impostor)
    assert not generation._is_incomplete_response_error(impostor)
    assert not generation._is_non_completed_response_error(RuntimeError("non_completed_response"))
    assert generation._classify_retry_reason(impostor) == "other"
    assert generation._is_retryable_empty_generation_error(CollapsedOutput("x"))
    assert generation._classify_retry_reason(CollapsedOutput("x")) == "empty_generation"
    assert generation._classify_retry_reason(IncompleteResponse("x")) == "incomplete_response"
    assert generation._classify_retry_reason(NonCompletedResponse("x")) == "non_completed_response"


def test_collapsed_recovery_answer_takes_the_empty_response_fallback_in_marker_mode():
    """US3 scenario 2 on a marker block: an empty code fence from the recovery call ends in
    the same controlled fallback, with the same per-paragraph record, as no answer at all."""

    def create(**_kwargs):
        return SimpleNamespace(status="completed", output_text="```markdown\n\n```")

    client = SimpleNamespace(responses=SimpleNamespace(create=create))

    result = _generate_marker_block(client, max_retries=1)

    dispositions = generation.marker_paragraph_dispositions(result)
    assert dispositions is not None
    assert [d.status for d in dispositions] == [generation.PARAGRAPH_STATUS_SOURCE_RESTORED] * 2
    snapshot = model_accounting.snapshot_run_model_accounting()
    assert snapshot["model_output_discarded_reason_counts"] == {"empty_response_source_fallback": 1}


# --- FR-013: an SDK item with an empty ``.text`` and no ``.get`` -------------------------


class _TextOnlyItem:
    """An SDK-like content item: it has ``.text`` and nothing else — no ``get``."""

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def test_an_item_with_empty_text_and_no_get_contributes_nothing_instead_of_raising():
    assert generation._response_item_text(_TextOnlyItem("")) == ""
    assert generation._response_item_text({"text": "из словаря"}) == "из словаря"

    anthropic = SimpleNamespace(content=[_TextOnlyItem(""), _TextOnlyItem("Текст")], stop_reason="end_turn")
    chat = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content=[_TextOnlyItem(""), _TextOnlyItem("Текст")]),
            )
        ]
    )

    assert generation._read_anthropic_model_response(anthropic).text == "Текст"
    assert generation._read_chat_completion_model_response(chat).text == "Текст"


def test_only_empty_items_is_an_empty_response_not_an_attribute_error():
    anthropic = SimpleNamespace(content=[_TextOnlyItem("")], stop_reason="end_turn")
    chat = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=[_TextOnlyItem("")]))]
    )

    with pytest.raises(EmptyResponse):
        generation._read_anthropic_model_response(anthropic)
    with pytest.raises(EmptyResponse):
        generation._read_chat_completion_model_response(chat)


# --- api_path accounting (spec 061 Assumptions) ------------------------------------------


def test_responses_path_is_counted_and_the_counter_is_always_published():
    assert model_accounting.snapshot_run_model_accounting()["api_path_counts"] == {}

    generation.generate_markdown_block(
        client=SimpleNamespace(responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="Готово"))),
        model="m",
        system_prompt="system",
        target_text="Исходный абзац.",
        context_before="",
        context_after="",
        max_retries=1,
    )

    assert model_accounting.snapshot_run_model_accounting()["api_path_counts"] == {"responses": 1}


def test_run_summary_prints_the_api_path_counter():
    import importlib.util
    from pathlib import Path

    harness_path = (
        Path(__file__).resolve().parent / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    )
    spec = importlib.util.spec_from_file_location("run_lietaer_validation_api_path_probe", harness_path)
    assert spec is not None and spec.loader is not None
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    lines = harness._build_model_accounting_summary_lines({"api_path_counts": {"chat_completions": 3, "responses": 97}})

    assert 'model_accounting_api_path_counts={"chat_completions": 3, "responses": 97}' in lines
