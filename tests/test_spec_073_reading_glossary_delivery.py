"""Spec 073 WP-F: the reading glossary is wired into the run and delivered to each block (FR-004, SC-007).

The step itself (candidates, batches, retries, the section of one block) is WP-E's and is tested in
``tests/test_spec_073_reading_glossary.py``. Here: the phase runs once, after the run glossary of 063
and before the first block; an unavailable model fails the run the way an unrecoverable block call
does; every audiobook block gets ONLY its own entries at the end of its system prompt, and its repair
call gets byte-for-byte the same section; translate and edit are untouched.

Block-level tests drive ``block_execution.process_single_block`` with the REAL execution path
(``execute_processing_block`` -> ``_generate_block_chunk`` -> finalize -> the repair call) and a
double for the block generator and for the SDK client of the repair. Run-level tests drive
``run_document_processing`` with a double for ``request_text_completion`` of the step.

All texts are invented, of the same FORM as book text (Constitution VII).
"""

from __future__ import annotations

import json
import re
from functools import partial
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest

import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.block_execution as block_execution
import docxaicorrector.pipeline.reading_glossary as reading_glossary
from docxaicorrector.core import model_accounting
from docxaicorrector.generation._generation import MarkerPreservedBlockText, ParagraphDisposition
from docxaicorrector.generation.output_budget import MODEL_OUTPUT_BUDGET_MULTIPLIERS
from docxaicorrector.pipeline.contracts import BlockExecutionPayload, ProcessingInitialization, ProcessingState
from docxaicorrector.pipeline.job_parsing import is_marker_mode_enabled
from docxaicorrector.pipeline.output_validation import classify_processed_block
from docxaicorrector.pipeline.reading_glossary import (
    READING_GLOSSARY_SECTION_HEADER,
    ReadingEntry,
    ReadingGlossary,
)
from docxaicorrector.pipeline.support import resolve_system_prompt
from docxaicorrector.text.glossary_pass import glossary_max_output_tokens

_MARKER = re.compile(r"\[\[DOCX_PARA_([A-Za-z0-9_]+)\]\]")

_READING_ABC = "эй-би-си"
_READING_XYZ = "икс-уай-зед"  # spec 074 FR-303: the letter-name convention (a model answer in it is not rewritten)

_SECTION_ABC = f"{READING_GLOSSARY_SECTION_HEADER}\n- ABC -> {_READING_ABC}"
_SECTION_XYZ = f"{READING_GLOSSARY_SECTION_HEADER}\n- XYZ -> {_READING_XYZ}"

_ABC_PROSE = "Совет ABC собрался в гавани Квазибурга ранним утром."
_ABC_DIGITS = "В 1999 году совет ABC собрал 300 рыбаков Квазибурга."
_XYZ_PROSE = "Отчёт XYZ лежал на столе у смотрителя маяка."
_PLAIN_PROSE = "Третий абзац продолжает рассказ о долгой зиме в посёлке."


# --------------------------------------------------------------------------------------------
# block harness
# --------------------------------------------------------------------------------------------


def _payload(*paragraphs: tuple[str, str]) -> BlockExecutionPayload:
    ids = [pid for pid, _ in paragraphs]
    texts = [text for _, text in paragraphs]
    return BlockExecutionPayload(
        job_kind="llm",
        target_chars=sum(len(text) for text in texts),
        context_chars=0,
        target_text="\n\n".join(texts),
        target_text_with_markers="\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in paragraphs),
        paragraph_ids=ids,
        context_before="",
        context_after="",
        structural_roles=["body"] * len(ids),
        paragraph_regions=["prose"] * len(ids),
        narration_include=True,
        paragraph_count=len(ids),
        narration_exclusion_reasons=list[str | None]([None] * len(ids)),
    )


def _split_marked(text: str) -> list[tuple[str, str]]:
    matches = list(_MARKER.finditer(text))
    return [
        (match.group(1), text[match.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip())
        for i, match in enumerate(matches)
    ]


class _Generator:
    """Block generator double: echoes each sent paragraph back (marker mode) and records the call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if kwargs.get("expected_paragraph_ids") is None:
            return kwargs["target_text"]
        sources = dict(_split_marked(kwargs["target_text"]))
        dispositions = [
            ParagraphDisposition(paragraph_id=pid, text=sources[pid], status="accepted")
            for pid in kwargs["expected_paragraph_ids"]
        ]
        return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


def _words_for_digits(paragraphs: list[tuple[str, str]]) -> str:
    return "\n\n".join(
        f"[[DOCX_PARA_{pid}]]\n{re.sub(r'[0-9]+', 'сколько-то', text).replace('ABC', _READING_ABC)}"
        for pid, text in paragraphs
    )


class _RepairClient:
    """The SDK double the repair call goes through (the real ``request_text_completion``)."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        prompt = str(kwargs["input"][-1]["content"][0]["text"])
        target = prompt.split("[TARGET BLOCK WITH MARKERS]", 1)[1].split("[CONTEXT AFTER]", 1)[0]
        return SimpleNamespace(
            status="completed",
            output_text=_words_for_digits(_split_marked(target)),
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, cost=0.001),
        )

    @staticmethod
    def system_prompt(request: dict[str, Any]) -> str:
        return str(request["input"][0]["content"][0]["text"])


def _unexpected(**kwargs: Any) -> None:
    raise AssertionError(f"unexpected failure path: {kwargs.get('exc') or kwargs.get('rejection_kind')}")


def _no_op(*_args: Any, **_kwargs: Any) -> None:
    return None


def _run_block(
    payload: BlockExecutionPayload,
    *,
    state: ProcessingState,
    index: int,
    generator: _Generator,
    repair_client: _RepairClient | None = None,
    operation: str = "audiobook",
    job_count: int = 2,
) -> _RepairClient:
    client = repair_client if repair_client is not None else _RepairClient()
    dependencies = SimpleNamespace(
        generate_markdown_block=generator,
        log_event=lambda *_args, **_kwargs: None,
        should_stop_processing=lambda _runtime: False,
        load_system_prompt=lambda **kwargs: f"FIXTURE PROMPT {kwargs.get('prompt_variant', 'default')}",
    )
    emitters = SimpleNamespace(emit_status=_no_op, emit_state=_no_op, emit_log=_no_op)
    context = SimpleNamespace(
        processing_operation=operation,
        model="fixture-model",
        model_id="fixture-model",
        model_selector="fixture-model",
        canonical_model_selector="fixture-model",
        model_provider="openai",
        max_retries=1,
        runtime=object(),
        uploaded_filename="book.docx",
        on_progress=lambda **_kwargs: None,
        app_config={},
        source_language=None if operation == "audiobook" else "ru",
        target_language=None if operation == "audiobook" else "ru",
        document_segments=(),
        run_id="run-073",
    )
    initialization = ProcessingInitialization(
        client=client, job_count=job_count, text_client=client, text_model_id="fixture-model"
    )
    with model_accounting.run_model_accounting_scope(run_id="run-073"):
        outcome = block_execution.process_single_block(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            job=object(),
            parse_processing_job_fn=lambda *, job: payload,
            handle_invalid_processing_job_fn=_unexpected,
            emit_block_started_fn=_no_op,
            is_marker_mode_enabled_fn=is_marker_mode_enabled,
            execute_processing_block_fn=partial(
                block_execution.execute_processing_block,
                is_marker_mode_enabled_fn=is_marker_mode_enabled,
                resolve_system_prompt_fn=resolve_system_prompt,
            ),
            handle_block_generation_failure_fn=_unexpected,
            classify_processed_block_fn=lambda target, chunk, **kw: classify_processed_block(target, chunk, **kw),
            handle_processed_block_rejection_fn=_unexpected,
            append_marker_registry_entries_fn=partial(
                block_execution.append_marker_registry_entries,
                build_processed_paragraph_registry_entries_fn=block_execution.build_processed_paragraph_registry_entries,
            ),
            handle_marker_registry_failure_fn=_unexpected,
            emit_block_completed_fn=_no_op,
        )
    assert outcome is None
    return client


@pytest.fixture(autouse=True)
def _no_fallback_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)


def _glossary(*pairs: tuple[str, str]) -> ReadingGlossary:
    return ReadingGlossary(status="built", entries=tuple(ReadingEntry(abbreviation=a, reading=r) for a, r in pairs))


# --------------------------------------------------------------------------------------------
# T-F1: what must NOT change (green before and after WP-F)
# --------------------------------------------------------------------------------------------

# The block prompt of an audiobook block with the fixture loader: no segment focus, no summary, no
# apparatus part. Recorded on the base of WP-F (16ccf47).
_AUDIOBOOK_BLOCK_PROMPT_SNAPSHOT = "FIXTURE PROMPT default"
_AUDIOBOOK_REPAIR_PROMPT_SNAPSHOT = "FIXTURE PROMPT repair"


@pytest.mark.parametrize(
    "glossary",
    [None, _glossary(("XYZ", _READING_XYZ))],
    ids=["no_glossary", "glossary_without_entries_of_the_block"],
)
def test_audiobook_block_and_repair_prompts_without_entries_are_byte_identical(glossary):
    state = ProcessingState()
    state.audiobook_reading_glossary = glossary
    generator = _Generator()

    client = _run_block(_payload(("p1", _ABC_DIGITS), ("p2", _PLAIN_PROSE)), state=state, index=1, generator=generator)

    assert [call["system_prompt"] for call in generator.calls] == [_AUDIOBOOK_BLOCK_PROMPT_SNAPSHOT]
    assert len(client.calls) == 1, "the digits must leave residue: the repair prompt is part of the snapshot"
    assert client.system_prompt(client.calls[0]) == _AUDIOBOOK_REPAIR_PROMPT_SNAPSHOT
    assert state.audiobook_reading_glossary_block_indexes == set()


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_block_prompt_ignores_a_glossary_in_the_state(operation):
    state = ProcessingState()
    state.audiobook_reading_glossary = _glossary(("ABC", _READING_ABC))
    generator = _Generator()

    _run_block(_payload(("p1", _ABC_PROSE)), state=state, index=1, generator=generator, operation=operation)

    (call,) = generator.calls
    assert READING_GLOSSARY_SECTION_HEADER not in call["system_prompt"]
    assert _READING_ABC not in call["system_prompt"]
    assert state.audiobook_reading_glossary_block_indexes == set()


# --------------------------------------------------------------------------------------------
# run harness
# --------------------------------------------------------------------------------------------


def _runtime() -> dict[str, Any]:
    return {"state": {}, "finalize": [], "log": [], "status": []}


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _emit_finalize(runtime, stage, detail, progress, terminal_kind=None):
    runtime.setdefault("finalize", []).append((stage, detail, progress, terminal_kind))


def _emit_log(runtime, **payload):
    runtime.setdefault("log", []).append(payload)


def _emit_status(runtime, **payload):
    runtime.setdefault("status", []).append(payload)


class _Http503(Exception):
    status_code = 503


class _Completion:
    """``request_text_completion`` double of the step: answers every candidate, or raises ``error``."""

    def __init__(self, *, error: Exception | None = None, on_call: Callable[[], None] | None = None) -> None:
        self.error = error
        self.on_call = on_call
        self.calls: list[dict[str, Any]] = []

    def __call__(self, client: object, request: dict[str, Any], *, usage_stage: str, should_stop: object = None) -> str:
        self.calls.append(dict(request))
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        candidates = json.loads(request["input"][1]["content"][0]["text"])["candidates"]
        readings = {"ABC": _READING_ABC, "XYZ": _READING_XYZ}
        return json.dumps(
            {"readings": [{"abbreviation": c["abbreviation"], "reading": readings.get(c["abbreviation"], "чтение")} for c in candidates]},
            ensure_ascii=False,
        )


def _wire_step(monkeypatch: pytest.MonkeyPatch, completion: _Completion) -> list[dict[str, object]]:
    """Feeds the run's reading-glossary phase the step doubles, through the production wiring."""

    artifacts: list[dict[str, object]] = []

    def write_artifact(payload: dict[str, object], *, context: object) -> str:
        artifacts.append(payload)
        return f"/fake/run_glossaries/{len(artifacts)}.json"

    monkeypatch.setattr(
        document_pipeline,
        "_run_reading_glossary_phase_impl",
        partial(
            reading_glossary.run_reading_glossary_phase,
            request_text_completion_fn=completion,
            sleep_fn=lambda _seconds: None,
            write_artifact_fn=write_artifact,
        ),
    )
    return artifacts


def _audiobook_job(text: str) -> dict[str, object]:
    return {"target_text": text, "context_before": "", "context_after": "", "target_chars": len(text), "context_chars": 0, "narration_include": True}


def _run_document(
    *,
    operation: str = "audiobook",
    jobs: list[dict[str, object]] | None = None,
    generate_markdown_block: Callable[..., Any] | None = None,
    should_stop: Any = None,
    max_retries: int = 2,
) -> SimpleNamespace:
    runtime = _runtime()
    blocks: list[dict[str, Any]] = []
    writer_calls: list[dict[str, Any]] = []
    presented: list[str] = []

    def generate(**kwargs: Any) -> str:
        blocks.append(kwargs)
        if generate_markdown_block is not None:
            return generate_markdown_block(**kwargs)
        return "Совет эй-би-си собрался в гавани."

    def write_ui_result_artifacts(**kwargs: Any) -> dict[str, str]:
        writer_calls.append(kwargs)
        return {}

    def present_error(code, exc, title, **kwargs):
        presented.append(code)
        return f"{title}: {exc}"

    result = document_pipeline.run_document_processing(
        uploaded_file="book.docx",
        jobs=jobs if jobs is not None else [_audiobook_job(_ABC_PROSE), _audiobook_job(_XYZ_PROSE)],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="fixture-model",
        max_retries=max_retries,
        processing_operation=operation,
        source_language="en" if operation == "translate" else "ru",
        target_language="ru",
        on_progress=lambda **_kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=lambda *_args, **_kwargs: None,
        present_error=present_error,
        emit_state=_emit_state,
        emit_finalize=_emit_finalize,
        emit_log=_emit_log,
        emit_status=_emit_status,
        should_stop_processing=should_stop or (lambda runtime: False),
        generate_markdown_block=generate,
        process_document_images=lambda **_kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=write_ui_result_artifacts,
    )
    return SimpleNamespace(
        result=result, runtime=runtime, blocks=blocks, writer_calls=writer_calls, presented=presented
    )


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_runs_never_build_a_reading_glossary(monkeypatch, operation):
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(reading_glossary, "run_reading_glossary", lambda **kwargs: calls.append(kwargs))

    run = _run_document(operation=operation)

    assert calls == []
    assert run.blocks, "the run reached its blocks"
    assert all(READING_GLOSSARY_SECTION_HEADER not in call["system_prompt"] for call in run.blocks)


# --------------------------------------------------------------------------------------------
# T-F2 / T-F3 / T-F4: the section of each block, main call and repair (SC-007)
# --------------------------------------------------------------------------------------------


def test_each_block_prompt_carries_only_its_own_entries():
    state = ProcessingState()
    state.audiobook_reading_glossary = _glossary(("ABC", _READING_ABC), ("XYZ", _READING_XYZ))
    generator = _Generator()

    _run_block(_payload(("p1", _ABC_PROSE)), state=state, index=1, generator=generator)
    _run_block(_payload(("p2", _XYZ_PROSE)), state=state, index=2, generator=generator)

    first, second = (call["system_prompt"] for call in generator.calls)
    assert f"- ABC -> {_READING_ABC}" in first and "XYZ" not in first
    assert f"- XYZ -> {_READING_XYZ}" in second and "ABC" not in second
    # The section ends the prompt, after every other part, separated by an empty line.
    assert first == f"{_AUDIOBOOK_BLOCK_PROMPT_SNAPSHOT}\n\n{_SECTION_ABC}"
    assert second == f"{_AUDIOBOOK_BLOCK_PROMPT_SNAPSHOT}\n\n{_SECTION_XYZ}"


def test_repair_prompt_ends_with_the_same_section_as_the_main_call():
    state = ProcessingState()
    state.audiobook_reading_glossary = _glossary(("ABC", _READING_ABC), ("XYZ", _READING_XYZ))
    generator = _Generator()

    client = _run_block(_payload(("p1", _ABC_DIGITS), ("p2", _PLAIN_PROSE)), state=state, index=1, generator=generator)

    main_prompt = generator.calls[0]["system_prompt"]
    assert len(client.calls) == 1
    repair_prompt = client.system_prompt(client.calls[0])
    assert main_prompt.endswith(_SECTION_ABC)
    assert repair_prompt == f"{_AUDIOBOOK_REPAIR_PROMPT_SNAPSHOT}\n\n{_SECTION_ABC}"
    assert main_prompt[len(_AUDIOBOOK_BLOCK_PROMPT_SNAPSHOT) :] == repair_prompt[len(_AUDIOBOOK_REPAIR_PROMPT_SNAPSHOT) :]
    assert "XYZ" not in repair_prompt


def test_blocks_with_a_section_are_counted_once():
    state = ProcessingState()
    state.audiobook_reading_glossary = _glossary(("ABC", _READING_ABC))
    generator = _Generator()

    _run_block(_payload(("p1", _ABC_PROSE)), state=state, index=1, generator=generator)
    _run_block(_payload(("p2", _PLAIN_PROSE)), state=state, index=2, generator=generator)
    # A second main call of block 1 (as a retry path would make) does not count it twice.
    block_execution._generate_block_chunk(
        context=SimpleNamespace(
            processing_operation="audiobook", model="m", model_id="m", max_retries=1, runtime=object(),
            app_config={}, document_segments=(),
        ),
        dependencies=SimpleNamespace(generate_markdown_block=generator, should_stop_processing=lambda _r: False),
        state=state,
        initialization=ProcessingInitialization(client=object(), job_count=2, text_client=object(), text_model_id="m"),
        index=1,
        payload=_payload(("p1", _ABC_PROSE)),
        marker_mode_enabled=True,
        system_prompt="base",
    )

    assert generator.calls[-1]["system_prompt"] == f"base\n\n{_SECTION_ABC}"
    assert state.audiobook_reading_glossary_block_indexes == {1}


# --------------------------------------------------------------------------------------------
# T-F5 / T-F5a: the phase in the run
# --------------------------------------------------------------------------------------------


def test_reading_glossary_phase_runs_once_after_the_run_glossary_and_before_the_blocks():
    from docxaicorrector.pipeline.setup import execute_processing_run

    order: list[str] = []
    initialization = SimpleNamespace(job_count=2)

    def record(name: str, result: object = None) -> Callable[..., object]:
        def call(**_kwargs: object) -> object:
            order.append(name)
            return result

        return call

    def glossary_063(**kwargs: Any) -> Any:
        order.append("run_glossary")
        return kwargs["context"]

    outcome = execute_processing_run(
        context=SimpleNamespace(runtime=object()),
        dependencies=SimpleNamespace(should_stop_processing=lambda _runtime: False),
        emitters=SimpleNamespace(),
        initialize_processing_run_fn=lambda **_kwargs: initialization,
        fail_empty_processing_plan_fn=cast(Any, record("empty_plan", "failed")),
        processing_state_factory_fn=ProcessingState,
        run_block_processing_phase_fn=cast(Any, record("blocks", "stopped")),
        run_image_processing_phase_fn=cast(Any, record("images")),
        emit_stopped_result_fn=cast(Any, record("stopped_result", "stopped")),
        current_markdown_fn=lambda chunks: "",
        validate_placeholder_integrity_phase_fn=cast(Any, record("placeholders", True)),
        run_docx_build_phase_fn=cast(Any, record("docx")),
        finalize_processing_success_fn=cast(Any, record("success", "succeeded")),
        initialization_type=SimpleNamespace,
        run_glossary_phase_fn=glossary_063,
        run_reading_glossary_phase_fn=cast(Any, record("reading_glossary")),
    )

    assert outcome == "stopped"
    assert order == ["run_glossary", "reading_glossary", "blocks"]


def test_a_failed_reading_glossary_outcome_is_returned_before_any_block():
    from docxaicorrector.pipeline.setup import execute_processing_run

    blocks: list[object] = []
    outcome = execute_processing_run(
        context=SimpleNamespace(runtime=object()),
        dependencies=SimpleNamespace(should_stop_processing=lambda _runtime: False),
        emitters=SimpleNamespace(),
        initialize_processing_run_fn=lambda **_kwargs: SimpleNamespace(job_count=1),
        fail_empty_processing_plan_fn=cast(Any, lambda **_kwargs: "failed"),
        processing_state_factory_fn=ProcessingState,
        run_block_processing_phase_fn=cast(Any, lambda **kwargs: blocks.append(kwargs)),
        run_image_processing_phase_fn=cast(Any, lambda **_kwargs: None),
        emit_stopped_result_fn=cast(Any, lambda **_kwargs: "stopped"),
        current_markdown_fn=lambda chunks: "",
        validate_placeholder_integrity_phase_fn=cast(Any, lambda **_kwargs: True),
        run_docx_build_phase_fn=cast(Any, lambda **_kwargs: None),
        finalize_processing_success_fn=cast(Any, lambda **_kwargs: "succeeded"),
        initialization_type=SimpleNamespace,
        run_reading_glossary_phase_fn=cast(Any, lambda **_kwargs: "failed"),
    )

    assert outcome == "failed"
    assert blocks == []


def test_audiobook_run_builds_the_glossary_once_and_each_block_gets_its_section(monkeypatch):
    """Anti-vacuum of T-F5a: an available model -- the blocks run and the run succeeds."""

    completion = _Completion()
    artifacts = _wire_step(monkeypatch, completion)

    run = _run_document()

    assert run.result == "succeeded"
    assert len(completion.calls) == 1
    assert len(artifacts) == 1
    first, second = (call["system_prompt"] for call in run.blocks)
    assert first.endswith(_SECTION_ABC) and "XYZ" not in first
    assert second.endswith(_SECTION_XYZ) and "ABC" not in second


def test_stop_raised_during_the_phase_runs_no_block(monkeypatch):
    stop = {"raised": False}
    completion = _Completion(on_call=lambda: stop.update(raised=True))
    _wire_step(monkeypatch, completion)

    run = _run_document(should_stop=lambda runtime: stop["raised"])

    assert len(completion.calls) == 1
    assert run.result == "stopped"
    assert run.blocks == []
    assert run.writer_calls == []


def _failure_observables(run: SimpleNamespace) -> dict[str, object]:
    state = run.runtime["state"]
    return {
        "result": run.result,
        "last_error_set": bool(state.get("last_error")),
        "latest_docx_bytes": state.get("latest_docx_bytes", "absent"),
        "terminal": [(stage, kind) for stage, _detail, _progress, kind in run.runtime["finalize"]][-1:],
        "delivered": run.writer_calls,
    }


def test_unavailable_reading_glossary_model_fails_the_run_like_an_unrecoverable_block_call(monkeypatch):
    block_phase_calls: list[object] = []
    real_block_phase = document_pipeline._run_block_processing_phase

    def counting_block_phase(**kwargs: Any) -> Any:
        block_phase_calls.append(kwargs)
        return real_block_phase(**kwargs)

    monkeypatch.setattr(document_pipeline, "_run_block_processing_phase", counting_block_phase)

    # The step's model is unavailable: every attempt is a retryable transport error.
    unavailable = _Completion(error=_Http503("service unavailable"))
    _wire_step(monkeypatch, unavailable)
    glossary_failed = _run_document(max_retries=2)

    assert len(unavailable.calls) == 2
    assert block_phase_calls == []
    assert glossary_failed.blocks == []
    assert glossary_failed.presented == ["audiobook_reading_glossary_failed"]
    assert "service unavailable" in str(glossary_failed.runtime["state"]["last_error"])

    # The reference: the step answers, and the model call of block 1 fails beyond repair.
    _wire_step(monkeypatch, _Completion())

    def failing_block(**_kwargs: Any) -> str:
        raise RuntimeError("block model down")

    block_failed = _run_document(generate_markdown_block=failing_block, max_retries=2)

    assert block_failed.presented == ["block_failed"]
    assert _failure_observables(glossary_failed) == _failure_observables(block_failed)
    assert _failure_observables(glossary_failed) == {
        "result": "failed",
        "last_error_set": True,
        "latest_docx_bytes": None,
        "terminal": [("Ошибка обработки", "error")],
        "delivered": [],
    }


# --------------------------------------------------------------------------------------------
# Orchestrator decision (WP-E question 9): the step's answer is sized for the model that answers
# --------------------------------------------------------------------------------------------


def test_the_step_budget_carries_the_output_multiplier_of_the_run_model():
    model, multiplier = next((name, value) for name, value in MODEL_OUTPUT_BUDGET_MULTIPLIERS.items() if value > 1)
    from docxaicorrector.pipeline.reading_glossary import run_reading_glossary_phase

    context = SimpleNamespace(
        processing_operation="audiobook",
        jobs=[{"target_text": _ABC_PROSE, "target_chars": 1, "context_chars": 0, "context_before": "", "context_after": ""}],
        max_retries=1,
        model=model,
        uploaded_filename="book.docx",
        run_id="run-073",
        runtime=object(),
    )
    completion = _Completion()
    state = ProcessingState()

    outcome = run_reading_glossary_phase(
        context=context,
        dependencies=SimpleNamespace(
            log_event=lambda *_a, **_k: None, present_error=_unexpected, should_stop_processing=lambda _r: False
        ),
        emitters=SimpleNamespace(emit_status=_no_op, emit_state=_no_op),
        state=state,
        initialization=SimpleNamespace(text_client=object(), client=object(), text_model_id=model, job_count=1),
        emit_failed_result_fn=cast(Any, _unexpected),
        request_text_completion_fn=completion,
        sleep_fn=lambda _seconds: None,
        write_artifact_fn=lambda payload, *, context: "/fake.json",
    )

    assert outcome is None
    (request,) = completion.calls
    assert request["max_output_tokens"] == glossary_max_output_tokens(1, multiplier=multiplier)
    assert request["max_output_tokens"] > glossary_max_output_tokens(1)
    # The audiobook block call sends no reasoning parameter; neither does its glossary.
    assert "reasoning" not in request
