"""Spec 061 P1-3 (User Story 3) and FR-022: one response shape, typed failure classes, and a
stop check before every model call inside one block.

Every test here is deterministic: the provider is a stub, no model is called.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from anthropic.types import Message as AnthropicMessage
from anthropic.types import TextBlock as AnthropicTextBlock
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice as ChatChoice
from openai.types.responses import Response as ResponsesResponse

import docxaicorrector.core.model_accounting as model_accounting
import docxaicorrector.generation._generation as generation
import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.generation.model_response import (
    CollapsedOutput,
    EmptyResponse,
    IncompleteResponse,
    ModelResponse,
    ModelResponseError,
    NonCompletedResponse,
)
from docxaicorrector.pipeline.contracts import LatePhaseStopped

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


def test_anthropic_context_window_stop_reason_reads_as_incomplete():
    """``model_context_window_exceeded`` stops the answer mid-text exactly as ``max_tokens``
    does; it is in the installed SDK's ``StopReason`` and was read as a complete answer."""
    response = AnthropicMessage.model_construct(
        content=[AnthropicTextBlock.model_construct(type="text", text="Обрезанный")],
        stop_reason="model_context_window_exceeded",
    )

    assert generation._read_anthropic_model_response(response) == ModelResponse(
        text="Обрезанный", incomplete=True, stop_reason="model_context_window_exceeded"
    )
    with pytest.raises(IncompleteResponse):
        generation._extract_anthropic_message_markdown(response)


def test_completion_is_defined_positively_against_the_sdk_literals():
    """The complete sets are read from the SDK, not invented, and EVERY other reason the SDK
    can report reads as incomplete — so a reason added to the SDK later is incomplete until
    someone decides otherwise, instead of silently accepted."""
    from typing import get_args

    from anthropic.types.stop_reason import StopReason
    from openai.types.chat.chat_completion import Choice

    from docxaicorrector.generation.model_response import (
        ANTHROPIC_COMPLETE_STOP_REASONS,
        CHAT_COMPLETIONS_COMPLETE_FINISH_REASONS,
        anthropic_stop_is_complete,
        chat_completion_finish_is_complete,
    )

    anthropic_reasons = set(get_args(StopReason))
    chat_reasons = set(get_args(Choice.model_fields["finish_reason"].annotation))
    assert ANTHROPIC_COMPLETE_STOP_REASONS <= anthropic_reasons
    assert CHAT_COMPLETIONS_COMPLETE_FINISH_REASONS <= chat_reasons
    assert {reason for reason in anthropic_reasons if anthropic_stop_is_complete(reason)} == {
        "end_turn",
        "stop_sequence",
    }
    assert {reason for reason in chat_reasons if chat_completion_finish_is_complete(reason)} == {"stop"}
    # A provider that reports no reason has not said the answer was cut off.
    assert anthropic_stop_is_complete(None) and chat_completion_finish_is_complete(None)


@pytest.mark.parametrize("finish_reason", ["content_filter", "tool_calls", "function_call"])
def test_a_non_normal_chat_finish_with_text_reads_as_incomplete(finish_reason):
    response = ChatCompletion.model_construct(
        choices=[
            ChatChoice.model_construct(
                index=0,
                finish_reason=finish_reason,
                message=ChatCompletionMessage.model_construct(role="assistant", content="Частичный ответ"),
            )
        ]
    )

    assert generation._read_chat_completion_model_response(response) == ModelResponse(
        text="Частичный ответ", incomplete=True, stop_reason=finish_reason
    )


@pytest.mark.parametrize("stop_reason", ["refusal", "tool_use", "pause_turn"])
def test_a_non_normal_anthropic_stop_with_text_reads_as_incomplete(stop_reason):
    response = AnthropicMessage.model_construct(
        content=[AnthropicTextBlock.model_construct(type="text", text="Частичный ответ")],
        stop_reason=stop_reason,
    )

    assert generation._read_anthropic_model_response(response) == ModelResponse(
        text="Частичный ответ", incomplete=True, stop_reason=stop_reason
    )


def test_a_content_filtered_chat_answer_with_intact_markers_is_retried_not_accepted():
    """Review finding F3: the filtered answer is non-empty and its markers are intact, so by
    the marker contract alone it would ship. It is retried and the clean answer is kept."""
    chat_calls: list[dict[str, Any]] = []
    client = _openrouter_chat_only_client(
        [(_COMPLETE_ANSWER.replace("Второй абзац.", "Отфильтровано."), "content_filter"), (_COMPLETE_ANSWER, "stop")],
        chat_calls,
    )

    result = _generate_marker_block(client)

    assert len(chat_calls) == 2
    assert "Второй абзац." in str(result)
    assert "Отфильтровано." not in str(result)
    assert model_accounting.snapshot_run_model_accounting()["retry_reason_counts"] == {
        "incomplete_response": 1
    }


def test_an_anthropic_refusal_with_intact_markers_is_retried_not_accepted():
    calls: list[dict[str, Any]] = []
    client = _anthropic_client(
        [(_COMPLETE_ANSWER.replace("Второй абзац.", "Не могу."), "refusal"), (_COMPLETE_ANSWER, "end_turn")],
        calls,
    )

    result = _generate_marker_block(client)

    assert len(calls) == 2
    assert "Второй абзац." in str(result)
    assert "Не могу." not in str(result)


def test_a_normal_finish_is_accepted_on_the_first_call_on_both_paths():
    """Anti-vacuum for the two tests above: ``stop`` and ``end_turn`` cost one call each."""
    chat_calls: list[dict[str, Any]] = []
    anthropic_calls: list[dict[str, Any]] = []

    chat_result = _generate_marker_block(_openrouter_chat_only_client([(_COMPLETE_ANSWER, "stop")], chat_calls))
    anthropic_result = _generate_marker_block(_anthropic_client([(_COMPLETE_ANSWER, "end_turn")], anthropic_calls))

    assert (len(chat_calls), len(anthropic_calls)) == (1, 1)
    assert "Второй абзац." in str(chat_result) and "Второй абзац." in str(anthropic_result)


def test_a_chat_answer_with_no_choices_takes_the_empty_response_road():
    """Review finding F4 (second half): no choice at all is an EMPTY answer, typed, so the
    retry / recovery / controlled-fallback road handles it instead of the run ending."""
    with pytest.raises(EmptyResponse):
        generation._read_chat_completion_model_response(ChatCompletion.model_construct(choices=[]))


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


# --- FR-022: Stop is honoured before every model call inside one block -------------------


def _counting_empty_client(calls: list[int]) -> Any:
    def create(**_kwargs):
        calls.append(1)
        return SimpleNamespace(status="completed", output_text="")

    return SimpleNamespace(responses=SimpleNamespace(create=create))


def test_stop_after_the_first_call_prevents_the_retry():
    calls: list[int] = []

    with pytest.raises(LatePhaseStopped):
        generation.generate_markdown_block(
            client=_counting_empty_client(calls),
            model="m",
            system_prompt="system",
            target_text="Исходный абзац.",
            context_before="",
            context_after="",
            max_retries=3,
            should_stop=lambda: len(calls) >= 1,
        )

    assert calls == [1]


def test_stop_after_the_last_attempt_prevents_the_recovery_call():
    calls: list[int] = []

    with pytest.raises(LatePhaseStopped):
        generation.generate_markdown_block(
            client=_counting_empty_client(calls),
            model="m",
            system_prompt="system",
            target_text="Исходный абзац.",
            context_before="",
            context_after="",
            max_retries=1,
            should_stop=lambda: len(calls) >= 1,
        )

    assert calls == [1]
    assert model_accounting.snapshot_run_model_accounting()["retry_reason_counts"] == {}


def test_stop_inside_the_ladder_is_not_swallowed_by_its_per_unit_fallback():
    """The ladder answers every per-unit failure by keeping that unit's source. A stop must
    not look like such a failure: it leaves the block, and no further unit is asked."""

    calls: list[int] = []

    def create(**_kwargs):
        calls.append(1)
        return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

    client = SimpleNamespace(responses=SimpleNamespace(create=create))

    with pytest.raises(LatePhaseStopped):
        generation.generate_markdown_block(
            client=cast(Any, client),
            model="m",
            system_prompt="system",
            target_text="Первый абзац исходника.\n\nВторой абзац исходника.",
            context_before="",
            context_after="",
            max_retries=1,
            # attempt (1) + recovery (2) + the ladder's first unit (3); stop before the 4th.
            should_stop=lambda: len(calls) >= 3,
        )

    assert calls == [1, 1, 1]


def test_a_predicate_that_never_stops_changes_nothing():
    calls: list[int] = []

    def create(**_kwargs):
        calls.append(1)
        return SimpleNamespace(status="completed", output_text="" if len(calls) == 1 else "Готово")

    result = generation.generate_markdown_block(
        client=cast(Any, SimpleNamespace(responses=SimpleNamespace(create=create))),
        model="m",
        system_prompt="system",
        target_text="Исходный абзац.",
        context_before="",
        context_after="",
        max_retries=2,
        should_stop=lambda: False,
    )

    assert result == "Готово"
    assert calls == [1, 1]


def test_block_layer_threads_the_runs_stop_predicate_into_the_generator():
    stop_state = {"stop": False}
    calls: list[int] = []

    def create(**_kwargs):
        calls.append(1)
        stop_state["stop"] = True  # Stop pressed while the provider was answering.
        return SimpleNamespace(status="completed", output_text="")

    runtime = object()
    seen_runtimes: list[object] = []

    def should_stop_processing(observed_runtime):
        seen_runtimes.append(observed_runtime)
        return stop_state["stop"]

    with pytest.raises(LatePhaseStopped):
        block_execution._generate_block_chunk(
            context=SimpleNamespace(
                processing_operation="edit", model_id=None, model="m", max_retries=3, runtime=runtime
            ),
            dependencies=SimpleNamespace(
                generate_markdown_block=generation.generate_markdown_block,
                should_stop_processing=should_stop_processing,
            ),
            state=SimpleNamespace(),
            initialization=SimpleNamespace(
                text_client=SimpleNamespace(responses=SimpleNamespace(create=create)),
                client=None,
                text_model_id=None,
            ),
            index=1,
            payload=SimpleNamespace(
                target_text="Исходный абзац.",
                target_text_with_markers="[[DOCX_PARA_p0001]]\nИсходный абзац.",
                context_before="",
                context_after="",
                paragraph_ids=["p0001"],
            ),
            marker_mode_enabled=False,
            system_prompt="system",
        )

    assert calls == [1]
    assert seen_runtimes and all(observed is runtime for observed in seen_runtimes)


def test_block_loop_maps_a_stop_raised_inside_a_block_to_the_stopped_result():
    stopped_calls: list[dict[str, Any]] = []
    processed: list[int] = []

    def process_single_block(**kwargs):
        processed.append(kwargs["index"])
        if kwargs["index"] == 2:
            raise LatePhaseStopped()
        return None

    result = block_execution.run_block_processing_phase(
        context=SimpleNamespace(jobs=["a", "b", "c"], runtime="rt"),
        dependencies=SimpleNamespace(should_stop_processing=lambda _runtime: False),
        emitters=SimpleNamespace(),
        state=SimpleNamespace(processed_chunks=["a"]),
        initialization=SimpleNamespace(job_count=3),
        emit_stopped_result_fn=lambda **kwargs: stopped_calls.append(kwargs) or "stopped",
        process_single_block_fn=process_single_block,
        current_markdown_fn=lambda chunks: "",
        emit_failed_result_fn=lambda **kwargs: cast(Any, "failed"),
    )

    assert result == "stopped"
    assert processed == [1, 2]
    assert len(stopped_calls) == 1
    assert stopped_calls[0]["block_index"] == 1
    assert stopped_calls[0]["block_count"] == 3
    assert stopped_calls[0]["progress"] == pytest.approx(1 / 3)
    assert stopped_calls[0]["runtime"] == "rt"


# --- api_path accounting (spec 061 Assumptions) ------------------------------------------


def test_responses_path_is_counted_and_the_counter_is_always_published():
    assert model_accounting.snapshot_run_model_accounting()["api_path_counts"] == {}

    generation.generate_markdown_block(
        client=cast(Any, SimpleNamespace(responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="Готово")))),
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


# --- review findings F4 and F7 -----------------------------------------------------------


def test_incomplete_attempts_then_a_failed_recovery_take_the_controlled_fallback(monkeypatch):
    """Review finding F4. Every attempt came back ``incomplete``, then the recovery call came
    back ``status="failed"``. The non-completed fallback keyed on the ATTEMPTS' exception and
    could not see the recovery's, so the exception escaped and the run died after the blocks
    it had paid for. The recovery's non-completed answer now takes the same controlled
    fallback, with the same event and counter."""

    events: list[str] = []
    monkeypatch.setattr(generation, "log_event", lambda _level, event_id, *_a, **_k: events.append(event_id))
    calls: list[dict[str, Any]] = []
    max_retries = 2

    def create(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) <= max_retries:
            return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])
        return SimpleNamespace(status="failed", output=[])

    result = _generate_marker_block(SimpleNamespace(responses=SimpleNamespace(create=create)), max_retries=max_retries)

    assert len(calls) == max_retries + 1
    assert str(result) == "Source paragraph one.\n\nSource paragraph two."
    dispositions = generation.marker_paragraph_dispositions(result)
    assert dispositions is not None
    assert [item.status for item in dispositions] == ["source_restored", "source_restored"]
    assert "markdown_non_completed_response_source_fallback" in events
    snapshot = model_accounting.snapshot_run_model_accounting()
    assert snapshot["model_output_discarded_reason_counts"] == {"non_completed_response_source_fallback": 1}


def test_a_failed_recovery_with_the_fallback_off_still_raises():
    """Anti-vacuum for F4: the fallback is a CONTROLLED one — with fallbacks off (a ladder
    step) the non-completed recovery still raises, so a ladder can tell it from a translation."""
    calls: list[dict[str, Any]] = []

    def create(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) <= 1:
            return SimpleNamespace(status="incomplete", output=[])
        return SimpleNamespace(status="cancelled", output=[])

    with pytest.raises(NonCompletedResponse):
        generation.generate_markdown_block(
            client=cast(Any, SimpleNamespace(responses=SimpleNamespace(create=create))),
            model="some-model",
            system_prompt="system",
            target_text="Один абзац.",
            context_before="",
            context_after="",
            max_retries=1,
            allow_controlled_source_fallback=False,
        )


def test_a_chat_answer_with_no_choices_ends_in_the_empty_response_fallback_not_a_crash():
    """Review finding F4, second half, through the loop: an OpenRouter Chat Completions answer
    with no choices used to raise an untyped ``RuntimeError`` and take the run down."""

    class UnsupportedResponsesError(Exception):
        status_code = 400

    def responses_create(**_kwargs):
        raise UnsupportedResponsesError("Responses API unsupported for this model; use chat.completions instead.")

    chat_calls: list[dict[str, Any]] = []

    def chat_create(**kwargs):
        chat_calls.append(dict(kwargs))
        return ChatCompletion.model_construct(choices=[])

    client = SimpleNamespace(
        base_url="https://openrouter.ai/api/v1",
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )
    target_text = "Короткий исходный абзац, который должен сохраниться без падения пайплайна."

    result = generation.generate_markdown_block(
        client=cast(Any, client),
        model="some-model",
        system_prompt="system",
        target_text=target_text,
        context_before="",
        context_after="",
        max_retries=2,
    )

    assert result == target_text
    assert len(chat_calls) == 3
    assert model_accounting.snapshot_run_model_accounting()["model_output_discarded_reason_counts"] == {
        "empty_response_source_fallback": 1
    }


def test_stop_pressed_during_a_refused_responses_call_prevents_the_chat_fallback_call():
    """Review finding F7. The Chat Completions fallback is a second SDK call inside ONE
    generation attempt; Stop pressed while the first was being refused must stop it."""

    class UnsupportedResponsesError(Exception):
        status_code = 400

    stop = {"pressed": False}

    def responses_create(**_kwargs):
        stop["pressed"] = True
        raise UnsupportedResponsesError("Responses API unsupported for this model; use chat.completions instead.")

    chat_calls: list[dict[str, Any]] = []

    def chat_create(**kwargs):
        chat_calls.append(dict(kwargs))
        raise AssertionError("the chat fallback must not be called after Stop")

    client = SimpleNamespace(
        base_url="https://openrouter.ai/api/v1",
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )

    with pytest.raises(LatePhaseStopped):
        _generate_marker_block(client, should_stop=lambda: stop["pressed"])

    assert chat_calls == []


@pytest.mark.parametrize("path", ["chat", "anthropic"])
def test_stop_pressed_during_a_parameter_refusal_prevents_the_resend(path):
    """Review finding F7: the parameter-removal loop re-sends the request without the refused
    parameter — another paid SDK call — and checks Stop before each send."""

    stop = {"pressed": False}
    calls: list[dict[str, Any]] = []

    def create(**kwargs):
        calls.append(dict(kwargs))
        stop["pressed"] = True
        raise TypeError("create() got an unexpected keyword argument 'temperature'")

    if path == "chat":

        class UnsupportedResponsesError(Exception):
            status_code = 400

        def responses_create(**_kwargs):
            raise UnsupportedResponsesError("Responses API unsupported for this model; use chat.completions instead.")

        client: Any = SimpleNamespace(
            base_url="https://openrouter.ai/api/v1",
            responses=SimpleNamespace(create=responses_create),
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        )
    else:
        client = SimpleNamespace(messages=SimpleNamespace(create=create))

    with pytest.raises(LatePhaseStopped):
        _generate_marker_block(client, should_stop=lambda: stop["pressed"])

    assert len(calls) == 1


def test_a_compatibility_fallback_is_one_attempt_and_two_sdk_calls():
    """``max_model_calls_per_block`` counts GENERATION ATTEMPTS. On OpenRouter a Responses
    request refused for compatibility is re-sent to Chat Completions inside the same attempt:
    one attempt, two SDK calls, one served answer in ``api_path_counts``."""

    class UnsupportedResponsesError(Exception):
        status_code = 400

    sdk_calls: list[str] = []

    def responses_create(**_kwargs):
        sdk_calls.append("responses")
        raise UnsupportedResponsesError("Responses API unsupported for this model; use chat.completions instead.")

    def chat_create(**_kwargs):
        sdk_calls.append("chat")
        return ChatCompletion.model_construct(
            choices=[
                ChatChoice.model_construct(
                    index=0,
                    finish_reason="stop",
                    message=ChatCompletionMessage.model_construct(role="assistant", content=_COMPLETE_ANSWER),
                )
            ]
        )

    client = SimpleNamespace(
        base_url="https://openrouter.ai/api/v1",
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )

    _generate_marker_block(client, max_retries=1)

    assert sdk_calls == ["responses", "chat"]
    assert model_accounting.snapshot_run_model_accounting()["api_path_counts"] == {"chat_completions": 1}
