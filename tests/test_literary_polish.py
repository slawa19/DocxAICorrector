"""Spec 069 FR-004: the literary polish (second) pass inside block execution (WP-6).

Every test drives blocks through the ORDINARY entry -- ``_pipeline._initialize_processing_run``
(which builds the second-pass client) and ``_pipeline._run_block_processing_phase`` (which runs
``process_single_block`` with the production wiring) -- with a double of the generator in place
of the model. All texts are invented (Constitution VII); the shapes are those of the bake-off
rollbacks (research R1), never their words.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import docxaicorrector.core.config as core_config
import docxaicorrector.core.constants as constants
import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.core.model_accounting import run_model_accounting_scope
from docxaicorrector.core.models import ImageMode
from docxaicorrector.core.translation_modes import EffectiveTranslationConfig, TranslationPassSpec
from docxaicorrector.generation._generation import (
    MarkerPreservedBlockText,
    ParagraphDisposition,
    _record_paragraph_dispositions,
    marker_paragraph_dispositions,
)
from docxaicorrector.pipeline.literary_polish import select_polish_paragraphs
from docxaicorrector.pipeline.contracts import (
    LatePhaseStopped,
    ProcessingContext,
    ProcessingEmitters,
    ProcessingInitialization,
    ProcessingState,
    build_processing_dependencies,
)

FIRST_PASS_MODEL = "test-vendor/first-pass-model"
POLISH_MODEL = "test-vendor/polish-model"
TEXT_CLIENT = object()
_MARKER = re.compile(r"\[\[DOCX_PARA_([A-Za-z0-9_]+)\]\]\n")


# --- the generator double ---------------------------------------------------------------------


def _polish_by_default(_paragraph_id: str, text: str) -> tuple[str, str]:
    return text.replace("первого прохода", "после шлифовки"), "accepted"


def _split_marked(target_text: str) -> list[tuple[str, str]]:
    parts = _MARKER.split(target_text)
    # ['', id1, text1, id2, text2, ...]
    return [(parts[index], parts[index + 1].strip()) for index in range(1, len(parts), 2)]


class _Generator:
    """Answers first-pass calls from a table and second-pass calls from ``polish``.

    Like the real generator's ``_deliver_marker_preserved_block``, every marker-mode answer
    records its paragraph dispositions once, so the run's counters see exactly what the real
    product would book.
    """

    def __init__(
        self,
        *,
        first_pass: dict[str, tuple[str, str]],
        unmarked: dict[str, str] | None = None,
        polish: Any = _polish_by_default,
        polish_model: str = POLISH_MODEL,
    ) -> None:
        self.first_pass = first_pass
        self.unmarked = unmarked or {}
        self.polish: Any = polish
        self.polish_model = polish_model
        self.calls: list[dict[str, Any]] = []

    @property
    def first_pass_calls(self) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["model"] != self.polish_model]

    @property
    def polish_calls(self) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["model"] == self.polish_model]

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if kwargs["model"] == self.polish_model:
            return self._answer_polish(kwargs)
        if not kwargs.get("marker_mode"):
            return self.unmarked[kwargs["target_text"]]
        dispositions = tuple(
            ParagraphDisposition(paragraph_id, *self.first_pass[paragraph_id])
            for paragraph_id in kwargs["expected_paragraph_ids"]
        )
        _record_paragraph_dispositions(dispositions)
        return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)

    def _answer_polish(self, kwargs: dict[str, Any]) -> str:
        if getattr(self.polish, "raw", False):
            answer: Any = self.polish(kwargs)
            return answer
        return _polish_answer(kwargs, self.polish)


def _polish_answer(kwargs: dict[str, Any], polish: Any = _polish_by_default) -> str:
    """A second-pass answer built paragraph by paragraph, booked like the real generator's."""

    dispositions = tuple(
        ParagraphDisposition(paragraph_id, *polish(paragraph_id, text))
        for paragraph_id, text in _split_marked(kwargs["target_text"])
    )
    _record_paragraph_dispositions(dispositions)
    return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


def _raw(function: Any) -> Any:
    """Mark a polish double that answers the whole call itself (block-level shapes)."""

    function.raw = True
    return function


# --- jobs and run configuration ------------------------------------------------------------------


def _job(paragraphs: list[tuple[str, str]], **extra: Any) -> dict[str, Any]:
    target_text = "\n\n".join(text for _paragraph_id, text in paragraphs)
    job: dict[str, Any] = {
        "job_kind": "llm",
        "target_text": target_text,
        "target_text_with_markers": "\n\n".join(
            f"[[DOCX_PARA_{paragraph_id}]]\n{text}" for paragraph_id, text in paragraphs
        ),
        "paragraph_ids": [paragraph_id for paragraph_id, _text in paragraphs],
        "paragraph_regions": ["prose"] * len(paragraphs),
        "context_before": "",
        "context_after": "",
        "target_chars": len(target_text),
        "context_chars": 0,
    }
    job.update(extra)
    return job


def _mode_fields(
    mode: str,
    *,
    first_pass_reasoning: str | None = None,
    polish_reasoning: str | None = None,
    first_pass_model: str = FIRST_PASS_MODEL,
    polish_model: str = POLISH_MODEL,
) -> dict[str, object]:
    """The ``translation_*`` keys ``apply_effective_translation_config`` writes (WP-1)."""

    polish_pass = TranslationPassSpec(model=polish_model, reasoning_effort=polish_reasoning) if mode == "standard" else None
    return EffectiveTranslationConfig(
        mode=mode,  # type: ignore[arg-type]
        first_pass=TranslationPassSpec(
            model=first_pass_model, editorial_intensity="literary", reasoning_effort=first_pass_reasoning
        ),
        polish_pass=polish_pass,
        overridden_settings=(),
        origin="ui",
    ).to_runtime_fields()


def _app_config(mode: str | None, *, markers: bool = True, **mode_kwargs: Any) -> dict[str, object]:
    app_config: dict[str, object] = {"enable_paragraph_markers": markers}
    if mode is not None:
        app_config.update(_mode_fields(mode, **mode_kwargs))
    return app_config


def _fake_loader(**kwargs: Any) -> str:
    return (
        f"SYSTEM[{kwargs.get('operation')}|{kwargs.get('prompt_variant', 'default')}]"
        f"|{kwargs.get('document_context_prompt', '')}"
    )


def _run_blocks(
    jobs: list[dict[str, Any]],
    *,
    generator: Any,
    app_config: dict[str, object],
    operation: str = "translate",
    should_stop: Any = None,
    load_system_prompt: Any = _fake_loader,
    run_id: str = "run-polish",
    client: object = TEXT_CLIENT,
) -> SimpleNamespace:
    events: list[dict[str, Any]] = []
    runtime: dict[str, Any] = {"state": {}, "finalize": [], "log": [], "status": []}

    def log_event(level: int, event_id: str, message: str, **context: Any) -> None:
        events.append({"level": level, "event_id": event_id, "message": message, "context": context})

    client_requests: list[str] = []

    def get_client() -> object:
        client_requests.append("default")
        return client

    dependencies = build_processing_dependencies(
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=get_client,
        ensure_pandoc_available=lambda: None,
        load_system_prompt=load_system_prompt,
        log_event=log_event,
        present_error=lambda code, exc, title, **_kwargs: f"{title}: {exc}",
        should_stop_processing=cast(Any, should_stop or (lambda _runtime: False)),
        generate_markdown_block=generator,
        process_document_images=lambda **_kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **_kwargs: {},
        write_segment_result_registry=lambda **_kwargs: {},
    )
    def emit_state(runtime: Any, **values: object) -> None:
        runtime["state"].update(values)

    def emit_finalize(runtime: Any, stage: str, detail: str, progress: float, terminal_kind: str | None = None) -> None:
        runtime["finalize"].append((stage, detail, progress, terminal_kind))

    def emit_log(runtime: Any, **payload: object) -> None:
        runtime["log"].append(payload)

    def emit_status(runtime: Any, **payload: object) -> None:
        runtime["status"].append(payload)

    emitters = ProcessingEmitters(
        emit_state=emit_state, emit_finalize=emit_finalize, emit_log=emit_log, emit_status=emit_status
    )
    context = ProcessingContext(
        uploaded_file="book.docx",
        uploaded_filename="book.docx",
        source_token="src-token",
        run_id=run_id,
        jobs=jobs,
        selected_segment_ids=None,
        document_segments=(),
        segment_selection_mode="all",
        output_mode="legacy_full_document",
        include_front_matter=False,
        include_toc=False,
        source_paragraphs=[],
        image_assets=[],
        image_mode=ImageMode.NO_CHANGE.value,
        app_config=app_config,
        model=FIRST_PASS_MODEL,
        max_retries=2,
        processing_operation=operation,
        source_language="en",
        target_language="ru",
        on_progress=lambda **_kwargs: None,
        runtime=runtime,
        model_id=FIRST_PASS_MODEL,
        document_context_prompt="КОНТЕКСТ ДОКУМЕНТА: заглушка" if operation == "translate" else "",
    )
    with run_model_accounting_scope(run_id=run_id, source_token="src-token") as ledger:
        initialization = document_pipeline._initialize_processing_run(
            context=context, dependencies=dependencies, emitters=emitters
        )
        assert isinstance(initialization, ProcessingInitialization)
        state = ProcessingState()
        outcome = document_pipeline._run_block_processing_phase(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
        )
        snapshot = ledger.snapshot()
    return SimpleNamespace(
        outcome=outcome,
        state=state,
        initialization=initialization,
        snapshot=snapshot,
        events=events,
        runtime=runtime,
        generator=generator,
        client_requests=client_requests,
    )


def _registry_texts(state: ProcessingState) -> list[str]:
    return [str(entry["text"]) for entry in state.generated_paragraph_registry]


# Two blocks, three paragraphs, all accepted by the first pass.
_SOURCE_BLOCKS = [
    [("p0001", "The first paragraph of the source, about the harbour."), ("p0002", "The second paragraph, about the market.")],
    [("p0003", "The third paragraph, about the river and the mill.")],
]
_FIRST_PASS = {
    "p0001": ("Первый абзац в переводе первого прохода, о гавани.", "accepted"),
    "p0002": ("Второй абзац в переводе первого прохода, о рынке.", "accepted"),
    "p0003": ("Третий абзац в переводе первого прохода, о реке и мельнице.", "accepted"),
}


def _two_blocks() -> list[dict[str, Any]]:
    return [_job(block) for block in _SOURCE_BLOCKS]


# --- T6.1 / T6.2: what must stay as it was (characterisation, green before the change) ----------


@pytest.mark.parametrize(
    ("operation", "app_config"),
    [
        ("edit", _app_config(None)),
        ("audiobook", _app_config(None)),
        ("translate", _app_config("single")),
        # A stale ``standard`` key set on an operation that is not ``translate`` changes nothing.
        ("edit", _app_config("standard")),
        ("audiobook", _app_config("standard")),
    ],
    ids=["edit", "audiobook", "translate-single", "edit-with-stale-standard", "audiobook-with-stale-standard"],
)
def test_single_edit_and_audiobook_blocks_are_delivered_as_before(operation: str, app_config: dict[str, object]) -> None:
    generator = _Generator(first_pass=_FIRST_PASS)

    run = _run_blocks(_two_blocks(), generator=generator, app_config=app_config, operation=operation)

    assert run.outcome is None
    assert [str(chunk) for chunk in run.state.processed_chunks] == [
        "Первый абзац в переводе первого прохода, о гавани.\n\nВторой абзац в переводе первого прохода, о рынке.",
        "Третий абзац в переводе первого прохода, о реке и мельнице.",
    ]
    assert _registry_texts(run.state) == [text for text, _status in _FIRST_PASS.values()]
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == ["accepted"] * 3
    assert run.snapshot["paragraph_disposition_counts"] == {
        "accepted": 3,
        "omitted": 0,
        "retry_required": 0,
        "source_restored": 0,
    }
    # One call per block, and nothing in it names a second pass or a request profile: the
    # request of these runs is the request of before spec 069 (SC-006).
    assert len(generator.calls) == 2
    assert all(call["model"] == FIRST_PASS_MODEL for call in generator.calls)
    assert all("request_profile" not in call for call in generator.calls)
    assert run.client_requests == ["default"]
    assert run.snapshot["literary_polish"]["counters"] == {}


def test_the_system_prompt_cache_of_the_existing_variants_is_unchanged() -> None:
    loads: list[dict[str, Any]] = []

    def resolve(loader: Any, **arguments: Any) -> str:
        loads.append(arguments)
        return loader(**arguments)

    context = SimpleNamespace(
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        app_config={"editorial_intensity_default": "literary"},
        document_context_prompt="КОНТЕКСТ",
    )
    dependencies = SimpleNamespace(load_system_prompt=_fake_loader)
    # A state without any spec-069 field still caches both existing variants.
    state = SimpleNamespace(system_prompt=None, toc_system_prompt=None)

    prompts = [
        block_execution._get_cached_system_prompt(
            context=context, dependencies=dependencies, state=state, resolve_system_prompt_fn=resolve, prompt_variant=variant
        )
        for variant in ("default", "toc_translate", "default", "toc_translate")
    ]

    assert prompts == [
        "SYSTEM[translate|default]|КОНТЕКСТ",
        "SYSTEM[translate|toc_translate]|КОНТЕКСТ",
        "SYSTEM[translate|default]|КОНТЕКСТ",
        "SYSTEM[translate|toc_translate]|КОНТЕКСТ",
    ]
    assert [load.get("prompt_variant", "default") for load in loads] == ["default", "toc_translate"]
    assert state.system_prompt == prompts[0] and state.toc_system_prompt == prompts[1]


def test_processing_state_and_initialization_build_without_spec_069_arguments() -> None:
    state = ProcessingState()
    initialization = ProcessingInitialization(client=TEXT_CLIENT, job_count=1)

    assert state.system_prompt is None and state.toc_system_prompt is None
    assert state.processed_chunks == []
    assert initialization.text_client is None and initialization.openai_client is None


# --- helpers of the new behaviour ---------------------------------------------------------------

_SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent
    / "specs"
    / "069-translation-modes"
    / "contracts"
    / "literary-polish-rollbacks.schema.json"
)


@pytest.fixture
def run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Moves ``.run/`` of the pass's artifact family into the test's directory."""

    monkeypatch.setattr(constants, "RUN_DIR", tmp_path)
    return tmp_path


def _rollback_rows(run_dir: Path, run_id: str = "run-polish") -> list[dict[str, Any]]:
    path = run_dir / "literary_polish_rollbacks" / f"{run_id}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _assert_rows_match_the_contract(rows: list[dict[str, Any]]) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for row in rows:
        validator.validate(row)


def _events(run: SimpleNamespace, event_id: str) -> list[dict[str, Any]]:
    return [event for event in run.events if event["event_id"] == event_id]


def _one_paragraph_block(first_pass_text: str, *, paragraph_id: str = "p0001", source: str | None = None) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str]]]:
    source_text = source or "A paragraph of the source about the harbour and the market."
    return [_job([(paragraph_id, source_text)])], {paragraph_id: (first_pass_text, "accepted")}


def _polish_with(candidate: str, status: str = "accepted") -> Any:
    return lambda _paragraph_id, _text: (candidate, status)


# --- T6.3: an accepted polish is what ships, and what every later step reads -------------------


def test_an_accepted_polish_is_delivered_and_read_by_the_registry(run_dir: Path) -> None:
    generator = _Generator(first_pass=_FIRST_PASS)

    run = _run_blocks(_two_blocks(), generator=generator, app_config=_app_config("standard"))

    polished = [text.replace("первого прохода", "после шлифовки") for text, _status in _FIRST_PASS.values()]
    assert run.outcome is None
    assert [str(chunk) for chunk in run.state.processed_chunks] == [f"{polished[0]}\n\n{polished[1]}", polished[2]]
    # The paragraph registry (the DOCX) reads the polished text (spec 070 FR-002: a translate
    # run builds no narration, so there is no projection to read it any more)...
    assert not run.state.narration_paragraphs
    assert _registry_texts(run.state) == polished
    # ...under the FIRST pass's statuses, carried on the delivered record.
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == ["accepted"] * 3
    record = marker_paragraph_dispositions(run.state.processed_chunks[0])
    assert record is not None and [item.paragraph_id for item in record] == ["p0001", "p0002"]
    assert len(generator.polish_calls) == 2
    assert _rollback_rows(run_dir) == []


def test_footnote_restoration_reads_the_polished_text(run_dir: Path) -> None:
    # The first pass dropped the source's reference; the polish (which never saw it) is
    # accepted, and the restoration that runs AFTER the hook puts the reference into ITS text.
    jobs, first_pass = _one_paragraph_block(
        "Гавань в переводе первого прохода росла год за годом.",
        source="The harbour grew year after year.¹",
    )
    generator = _Generator(first_pass=first_pass)

    run = _run_blocks(jobs, generator=generator, app_config=_app_config("standard"))

    delivered = str(run.state.processed_chunks[0])
    assert "после шлифовки" in delivered and "первого прохода" not in delivered
    assert "¹" in delivered
    assert _registry_texts(run.state) == [delivered]


# --- T6.4: what is sent ---------------------------------------------------------------------------


def test_only_accepted_paragraphs_in_the_target_script_are_sent(run_dir: Path) -> None:
    paragraphs = [
        ("p0001", "The first paragraph of the source, about the harbour."),
        ("p0002", "A short line."),
        ("p0003", "Another short line."),
        ("p0004", "Grey, A. The Long Quay. Northport: Invented Press, 1999."),
        ("p0005", "The fifth paragraph of the source, about the river."),
    ]
    first_pass = {
        "p0001": ("Первый абзац в переводе первого прохода, о гавани.", "accepted"),
        "p0002": ("Короткая строка первого прохода.", "omitted"),
        "p0003": ("Ещё одна короткая строка первого прохода.", "source_restored"),
        # A reference left in its own script by rule D1 is ``accepted`` too (plan O-1).
        "p0004": ("Grey, A. The Long Quay. Northport: Invented Press, 1999, перевод первого прохода.", "accepted"),
        "p0005": ("Пятый абзац в переводе первого прохода, о реке.", "accepted"),
    }
    generator = _Generator(first_pass=first_pass)

    run = _run_blocks([_job(paragraphs)], generator=generator, app_config=_app_config("standard"))

    assert len(generator.polish_calls) == 1
    call = generator.polish_calls[0]
    assert call["expected_paragraph_ids"] == ["p0001", "p0005"]
    assert "[[DOCX_PARA_p0002]]" not in call["target_text"] and "Grey" not in call["target_text"]
    texts = _registry_texts(run.state)
    assert texts[0].endswith("после шлифовки, о гавани.") and texts[4].endswith("после шлифовки, о реке.")
    # Not sent means not changed: the text and the status are the first pass's.
    assert texts[1:4] == [first_pass[pid][0] for pid in ("p0002", "p0003", "p0004")]
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [
        first_pass[pid][1] for pid, _text in paragraphs
    ]
    counters = run.snapshot["literary_polish"]["counters"]
    assert counters["skipped_paragraph_counts.not_accepted"] == 2
    assert counters["skipped_paragraph_counts.non_target_script"] == 1
    assert counters["sent_paragraph_count"] == 2


def test_select_polish_paragraphs_leaves_policy_kept_and_restored_paragraphs_alone() -> None:
    record = (
        ParagraphDisposition("p1", "Абзац перевода о мельнице и реке.", "accepted"),
        ParagraphDisposition("p2", "Invented, B. A Title. Somewhere, 2001.", "policy_kept_source"),
        ParagraphDisposition("p3", "Source sentence restored.", "source_restored"),
        ParagraphDisposition("p4", "Omitted source sentence.", "omitted"),
        ParagraphDisposition("p5", "12, 14, 19.", "accepted"),
    )
    chunk = MarkerPreservedBlockText("\n\n".join(item.text for item in record), record)

    selection = select_polish_paragraphs(chunk, paragraph_ids=["p1", "p2", "p3", "p4", "p5"], target_language="ru")

    assert [item.paragraph_id for item in selection.selected] == ["p1"]
    assert selection.skipped_counts == {"not_accepted": 3, "non_target_script": 1}


def test_an_unmarked_block_is_polished_only_when_it_is_one_paragraph(run_dir: Path) -> None:
    single = _job([("p0001", "One unmarked paragraph of the source about the harbour.")])
    several = _job(
        [("p0002", "The first of two unmarked paragraphs."), ("p0003", "The second of two unmarked paragraphs.")]
    )
    generator = _Generator(
        first_pass={},
        unmarked={
            single["target_text"]: "Один абзац без маркеров в переводе первого прохода, о гавани.",
            several["target_text"]: "Первый из двух абзацев первого прохода.\n\nВторой из двух абзацев первого прохода.",
        },
    )

    run = _run_blocks([single, several], generator=generator, app_config=_app_config("standard", markers=False))

    assert run.outcome is None
    assert len(generator.polish_calls) == 1
    assert generator.polish_calls[0]["expected_paragraph_ids"] == ["p0001"]
    assert generator.polish_calls[0]["target_text"].startswith("[[DOCX_PARA_p0001]]\n")
    assert str(run.state.processed_chunks[0]) == "Один абзац без маркеров в переводе после шлифовки, о гавани."
    # The first pass had no record, so the delivered block has none either.
    assert marker_paragraph_dispositions(run.state.processed_chunks[0]) is None
    assert "первого прохода" in str(run.state.processed_chunks[1])
    counters = run.snapshot["literary_polish"]["counters"]
    assert counters["skipped_unmarked_block_count"] == 1
    assert counters["skipped_paragraph_counts.unmarked_block"] == 2


# --- T6.5: rollbacks by form, by status and by block shape ----------------------------------------

_PREDICATE_CASES = [
    ("numbers_changed", "В 1923 году в городе было 23 моста через реку.", "В 1932 году в городе было 23 моста через реку."),
    ("new_non_target_script_word", "Он сказал, что придёт к вечеру на пристань.", "Он сказал, что will придёт к вечеру на пристань."),
    (
        "lost_non_target_script_word",
        "Книга Silver Quay вышла позже, чем ожидали её читатели.",
        "Книга «Серебряная пристань» вышла позже, чем ожидали её читатели.",
    ),
    ("mixed_script_word", "Город быстро рос вдоль старой широкой реки.", "Гoрод быстро рос вдоль старой широкой реки."),
    ("list_prefix_changed", "- Первый шаг важнее всех остальных шагов.", "Первый шаг важнее всех остальных шагов."),
    ("footnote_marker_lost", "Это было важно для всей гавани.¹", "Это было очень важно для всей гавани."),
    (
        "length_ratio_out_of_bounds",
        "Короткая фраза о гавани и рынке.",
        "Короткая фраза о гавани и рынке, к которой добавлено длинное продолжение, которого не было.",
    ),
]


@pytest.mark.parametrize(("reason", "first_pass_text", "candidate"), _PREDICATE_CASES, ids=[case[0] for case in _PREDICATE_CASES])
def test_each_predicate_rolls_the_paragraph_back_and_is_recorded(
    run_dir: Path, reason: str, first_pass_text: str, candidate: str
) -> None:
    source = "This mattered to the whole harbour.¹" if reason == "footnote_marker_lost" else None
    jobs, first_pass = _one_paragraph_block(first_pass_text, source=source)
    generator = _Generator(first_pass=first_pass, polish=_polish_with(candidate))

    run = _run_blocks(jobs, generator=generator, app_config=_app_config("standard"))

    assert run.outcome is None
    assert _registry_texts(run.state) == [first_pass_text]
    rows = _rollback_rows(run_dir)
    assert len(rows) == 1
    _assert_rows_match_the_contract(rows)
    row = rows[0]
    assert row["scope"] == "paragraph" and row["paragraph_id"] == "p0001" and row["block_index"] == 1
    assert reason in row["reasons"]
    assert (row["first_pass_text"], row["candidate_text"], row["final_text"]) == (first_pass_text, candidate, first_pass_text)
    assert row["polish_model"] == POLISH_MODEL and row["run_id"] == "run-polish"
    events = _events(run, "literary_polish_paragraph_rolled_back")
    assert len(events) == 1 and events[0]["level"] == logging.WARNING
    context = events[0]["context"]
    assert reason in context["reasons"] and context["paragraph_id"] == "p0001"
    assert context["artifact_path"] == str(run_dir / "literary_polish_rollbacks" / "run-polish.jsonl")
    # LOGGING §1.5: texts only in the artifact.
    logged = json.dumps(context, ensure_ascii=False)
    assert first_pass_text not in logged and candidate not in logged
    counters = run.snapshot["literary_polish"]["counters"]
    assert counters["rolled_back_paragraph_count"] == 1
    assert counters[f"rollback_reason_counts.{reason}"] == 1
    assert "accepted_paragraph_count" not in counters


def test_an_answer_that_is_not_accepted_is_rolled_back(run_dir: Path) -> None:
    jobs, first_pass = _one_paragraph_block("Абзац о гавани в переводе первого прохода.")
    generator = _Generator(first_pass=first_pass, polish=_polish_with("Абзац о гавани в переводе первого прохода.", "omitted"))

    run = _run_blocks(jobs, generator=generator, app_config=_app_config("standard"))

    rows = _rollback_rows(run_dir)
    _assert_rows_match_the_contract(rows)
    assert [row["reasons"] for row in rows] == [["not_accepted"]]
    assert rows[0]["details"] == {"candidate_status": "omitted"}
    assert _registry_texts(run.state) == ["Абзац о гавани в переводе первого прохода."]
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == ["accepted"]


@_raw
def _answer_missing_a_paragraph(kwargs: dict[str, Any]) -> str:
    first_id = kwargs["expected_paragraph_ids"][0]
    record = (ParagraphDisposition(first_id, "Только первый абзац после шлифовки.", "accepted"),)
    return MarkerPreservedBlockText(record[0].text, record)


@_raw
def _answer_out_of_order(kwargs: dict[str, Any]) -> str:
    record = tuple(
        ParagraphDisposition(paragraph_id, f"Абзац {paragraph_id} после шлифовки, без изменений смысла.", "accepted")
        for paragraph_id in reversed(kwargs["expected_paragraph_ids"])
    )
    return MarkerPreservedBlockText("\n\n".join(item.text for item in record), record)


@_raw
def _answer_without_a_record(kwargs: dict[str, Any]) -> str:
    return "Ответ шлифовки без записи по абзацам."


@_raw
def _answer_that_splits_a_paragraph(kwargs: dict[str, Any]) -> str:
    record = tuple(
        ParagraphDisposition(paragraph_id, "Половина абзаца.\n\nВторая половина абзаца.", "accepted")
        for paragraph_id in kwargs["expected_paragraph_ids"]
    )
    return MarkerPreservedBlockText("\n\n".join(item.text for item in record), record)


@pytest.mark.parametrize(
    "answer",
    [_answer_missing_a_paragraph, _answer_out_of_order, _answer_without_a_record, _answer_that_splits_a_paragraph],
    ids=["missing", "out-of-order", "no-record", "split-paragraph"],
)
def test_a_block_whose_paragraphs_do_not_match_is_rolled_back_whole(run_dir: Path, answer: Any) -> None:
    generator = _Generator(first_pass=_FIRST_PASS, polish=answer)

    run = _run_blocks([_job(_SOURCE_BLOCKS[0])], generator=generator, app_config=_app_config("standard"))

    assert run.outcome is None
    assert _registry_texts(run.state) == [_FIRST_PASS["p0001"][0], _FIRST_PASS["p0002"][0]]
    rows = _rollback_rows(run_dir)
    _assert_rows_match_the_contract(rows)
    assert len(rows) == 1
    assert rows[0]["scope"] == "block" and rows[0]["paragraph_id"] is None
    assert rows[0]["reasons"] == ["block_marker_mismatch"]
    failed = _events(run, "literary_polish_block_failed")
    assert len(failed) == 1 and failed[0]["context"]["reason"] == "block_marker_mismatch"
    counters = run.snapshot["literary_polish"]["counters"]
    assert counters["block_rollback_count"] == 1
    assert counters["rolled_back_paragraph_count"] == 2
    assert counters["rollback_reason_counts.block_marker_mismatch"] == 1


# --- T6.6: a failed or stopped pass keeps the first pass -------------------------------------------


def test_a_failing_pass_keeps_the_first_pass_and_warns(run_dir: Path) -> None:
    @_raw
    def failing(_kwargs: dict[str, Any]) -> str:
        raise RuntimeError("provider unavailable")

    generator = _Generator(first_pass=_FIRST_PASS, polish=failing)

    run = _run_blocks(_two_blocks(), generator=generator, app_config=_app_config("standard"))

    assert run.outcome is None
    assert _registry_texts(run.state) == [text for text, _status in _FIRST_PASS.values()]
    failed = _events(run, "literary_polish_block_failed")
    assert [event["context"]["block_index"] for event in failed] == [1, 2]
    assert all(event["level"] == logging.WARNING for event in failed)
    assert {(event["context"]["reason"], event["context"]["error_class"]) for event in failed} == {("error", "RuntimeError")}
    rows = _rollback_rows(run_dir)
    _assert_rows_match_the_contract(rows)
    assert [row["reasons"] for row in rows] == [["pass_failed"], ["pass_failed"]]
    # "Answer or raise": the pass never asks the generator for its ladder or its source fallback.
    call = generator.polish_calls[0]
    assert call["allow_controlled_source_fallback"] is False
    assert call["marker_mode"] is True and call["context_after"] == ""
    assert call["request_profile"].usage_stage == "literary_polish"
    counters = run.snapshot["literary_polish"]["counters"]
    assert counters["failed_block_count"] == 2 and counters["failed_reason_counts.error"] == 2


@pytest.mark.parametrize("stop_on_block", [1, 2], ids=["middle-block", "last-block"])
def test_stop_during_the_pass_delivers_the_first_pass_and_stops_the_run(run_dir: Path, stop_on_block: int) -> None:
    @_raw
    def stop_on(kwargs: dict[str, Any]) -> str:
        if kwargs["block_index"] == stop_on_block:
            raise LatePhaseStopped()
        return _polish_answer(kwargs)

    generator = _Generator(first_pass=_FIRST_PASS, polish=stop_on)

    run = _run_blocks(_two_blocks(), generator=generator, app_config=_app_config("standard"))

    assert run.outcome == "stopped"
    assert run.state.stopped_during_polish is True
    # The stopped block IS delivered -- with its first pass -- and nothing after it ran.
    assert len(run.state.processed_chunks) == stop_on_block
    stopped_block = str(run.state.processed_chunks[stop_on_block - 1])
    assert "первого прохода" in stopped_block and "после шлифовки" not in stopped_block
    assert len(generator.first_pass_calls) == stop_on_block
    failed = _events(run, "literary_polish_block_failed")
    assert [(event["context"]["reason"], event["context"]["block_index"]) for event in failed] == [("stopped", stop_on_block)]
    assert [row["reasons"] for row in _rollback_rows(run_dir)] == [["stopped"]]
    assert run.runtime["finalize"][-1][3] == "stopped"


# --- T6.7: counted once ---------------------------------------------------------------------------


def _polish_rolling_back_p0002(paragraph_id: str, text: str) -> tuple[str, str]:
    if paragraph_id == "p0002":
        return text.replace("о рынке", "о рынке 1923 года"), "accepted"  # a number appears: P1
    return _polish_by_default(paragraph_id, text)


def test_first_pass_dispositions_are_counted_once_and_the_pass_has_its_own_section(run_dir: Path) -> None:
    with_polish = _run_blocks(
        _two_blocks(),
        generator=_Generator(first_pass=_FIRST_PASS, polish=_polish_rolling_back_p0002),
        app_config=_app_config("standard"),
    )
    without_polish = _run_blocks(_two_blocks(), generator=_Generator(first_pass=_FIRST_PASS), app_config=_app_config("single"))

    # The run-wide counters are the first pass's, with the second pass or without it.
    for key in ("paragraph_disposition_counts", "api_path_counts", "retry_attempt_count", "text_removal_event_count"):
        assert with_polish.snapshot[key] == without_polish.snapshot[key], key
    section = with_polish.snapshot["literary_polish"]
    # What the generator booked during the pass is in the pass's own section.
    assert section["generator_counters"]["paragraph_disposition_counts"]["accepted"] == 3
    assert section["counters"] == {
        "accepted_paragraph_count": 2,
        "rollback_reason_counts.numbers_changed": 1,
        "rolled_back_paragraph_count": 1,
        "sent_block_count": 2,
        "sent_paragraph_count": 3,
    }
    completed = _events(with_polish, "literary_polish_completed")
    assert len(completed) == 1 and completed[0]["level"] == logging.INFO
    context = completed[0]["context"]
    assert context["sent_paragraph_count"] == 3 and context["accepted_paragraph_count"] == 2
    assert context["rollback_reason_counts"] == {"numbers_changed": 1}
    assert context["skipped_paragraph_counts"] == {} and context["failed_block_count"] == 0
    assert context["artifact_path"] == str(run_dir / "literary_polish_rollbacks" / "run-polish.jsonl")
    assert context["polish_model"] == POLISH_MODEL
    assert _events(without_polish, "literary_polish_completed") == []


# --- T6.8: the pass's prompt and context ----------------------------------------------------------


def test_the_polish_prompt_is_its_own_cached_variant_with_the_document_context(run_dir: Path) -> None:
    variants: list[str] = []

    def counting_loader(
        *,
        operation: str = "edit",
        source_language: str = "en",
        target_language: str = "ru",
        editorial_intensity: str = "literary",
        prompt_variant: str = "default",
        document_context_prompt: str = "",
    ) -> str:
        variants.append(prompt_variant)
        return core_config.load_system_prompt(
            operation=operation,
            source_language=source_language,
            target_language=target_language,
            editorial_intensity=editorial_intensity,
            prompt_variant=prompt_variant,
            document_context_prompt=document_context_prompt,
        )

    jobs = _two_blocks()
    jobs[1]["context_before"] = "x" * 24
    generator = _Generator(first_pass=_FIRST_PASS)

    run = _run_blocks(jobs, generator=generator, app_config=_app_config("standard"), load_system_prompt=counting_loader)

    assert variants.count("literary_polish") == 1 and variants.count("default") == 1
    polish_prompts = {call["system_prompt"] for call in generator.polish_calls}
    assert polish_prompts == {run.state.polish_system_prompt}
    polish_prompt = run.state.polish_system_prompt
    assert polish_prompt != run.state.system_prompt
    assert "Не переводите его заново" in polish_prompt
    # Operation ``translate``: the document context (and with it the run glossary) is rendered.
    assert "КОНТЕКСТ ДОКУМЕНТА: заглушка" in polish_prompt
    # O-7: before -- the tail of the previous block's DELIVERED text, as long as the block's
    # own context before; after -- nothing.
    first_call, second_call = generator.polish_calls
    assert first_call["context_before"] == "" and second_call["context_after"] == ""
    delivered_first_block = str(run.state.processed_chunks[0])
    assert delivered_first_block.endswith(second_call["context_before"])
    assert 0 < len(second_call["context_before"]) <= 24
    assert "после шлифовки" in delivered_first_block


# --- T6.9: who carries which request profile -------------------------------------------------------


@pytest.mark.parametrize(
    ("operation", "mode"), [("translate", "single"), ("edit", "standard"), ("audiobook", "quality")]
)
def test_single_edit_and_audiobook_call_no_second_pass_and_pass_no_profile(run_dir: Path, operation: str, mode: str) -> None:
    generator = _Generator(first_pass=_FIRST_PASS)

    run = _run_blocks(_two_blocks(), generator=generator, app_config=_app_config(mode), operation=operation)

    assert generator.polish_calls == []
    assert all("request_profile" not in call for call in generator.calls)
    assert run.initialization.polish_client is None and run.initialization.polish_model_id is None


def test_quality_first_pass_calls_carry_the_mode_reasoning_and_the_model_multiplier(run_dir: Path) -> None:
    generator = _Generator(first_pass=_FIRST_PASS)
    app_config = _app_config("quality", first_pass_reasoning="low", first_pass_model="openrouter:anthropic/claude-haiku-5.5")

    _run_blocks(_two_blocks(), generator=generator, app_config=app_config)

    assert generator.polish_calls == []
    profiles = [call["request_profile"] for call in generator.calls]
    assert len(profiles) == 2
    assert {(p.reasoning_effort, p.output_budget_multiplier, p.usage_stage) for p in profiles} == {
        ("low", 3.0, "text_generation")
    }


def test_standard_first_pass_has_no_reasoning_and_the_polish_has_its_own_profile(run_dir: Path) -> None:
    generator = _Generator(first_pass=_FIRST_PASS, polish_model="openrouter:anthropic/claude-haiku-5.5")
    app_config = _app_config("standard", polish_model="openrouter:anthropic/claude-haiku-5.5", polish_reasoning="low")

    run = _run_blocks(_two_blocks(), generator=generator, app_config=app_config)

    first = {(c["request_profile"].reasoning_effort, c["request_profile"].usage_stage) for c in generator.first_pass_calls}
    assert first == {(None, "text_generation")}
    second = {
        (c["request_profile"].reasoning_effort, c["request_profile"].output_budget_multiplier, c["request_profile"].usage_stage)
        for c in generator.polish_calls
    }
    assert second == {("low", 3.0, "literary_polish")}
    assert run.initialization.polish_model_id == "openrouter:anthropic/claude-haiku-5.5"
    assert run.client_requests == ["default", "default"]


def test_a_toc_block_and_a_passthrough_block_are_never_polished(run_dir: Path) -> None:
    passthrough = _job([("p0009", "Figure 3")], job_kind="passthrough")
    toc = _job(
        [("p0010", "Chapter One. The Harbour"), ("p0011", "Chapter Two. The Market")],
        toc_dominant=True,
        structural_roles=["toc_entry", "toc_entry"],
    )
    first_pass = dict(_FIRST_PASS)
    first_pass["p0010"] = ("Глава первая. Гавань первого прохода", "accepted")
    first_pass["p0011"] = ("Глава вторая. Рынок первого прохода", "accepted")
    generator = _Generator(first_pass=first_pass)

    run = _run_blocks([passthrough, toc, _job(_SOURCE_BLOCKS[1])], generator=generator, app_config=_app_config("standard"))

    assert run.outcome is None
    assert str(run.state.processed_chunks[0]) == "Figure 3"
    assert "первого прохода" in str(run.state.processed_chunks[1])
    assert [call["expected_paragraph_ids"] for call in generator.polish_calls] == [["p0003"]]


# --- T6.10 / T6.11: retention and the prompt's rules -----------------------------------------------


def test_rollback_artifacts_follow_the_marker_attempts_retention(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import docxaicorrector.pipeline.literary_polish as literary_polish
    import docxaicorrector.runtime.artifact_retention as artifact_retention

    assert artifact_retention.LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS == 7 * 24 * 60 * 60
    assert artifact_retention.LITERARY_POLISH_ROLLBACKS_MAX_COUNT == 400
    assert (
        artifact_retention.LITERARY_POLISH_ROLLBACKS_MAX_AGE_SECONDS
        == artifact_retention.MARKER_ATTEMPT_ARTIFACTS_MAX_AGE_SECONDS
    )
    monkeypatch.setattr(literary_polish, "LITERARY_POLISH_ROLLBACKS_MAX_COUNT", 2)
    family = run_dir / "literary_polish_rollbacks"
    family.mkdir()
    now = time.time()
    # Three recent files of earlier runs and one too old to keep: the age limit takes the old
    # one, the count limit (2 here) the two oldest recent ones.
    for name, age_seconds in (("expired", 8 * 24 * 3600), ("older-run-0", 300), ("older-run-1", 200), ("older-run-2", 100)):
        old = family / f"{name}.jsonl"
        old.write_text("{}\n", encoding="utf-8")
        os.utime(old, (now - age_seconds, now - age_seconds))
    jobs, first_pass = _one_paragraph_block("В 1923 году в городе было 23 моста через реку.")
    generator = _Generator(first_pass=first_pass, polish=_polish_with("В 1932 году в городе было 23 моста через реку."))

    _run_blocks(jobs, generator=generator, app_config=_app_config("standard"))

    assert sorted(path.name for path in family.glob("*.jsonl")) == ["older-run-2.jsonl", "run-polish.jsonl"]


def test_a_failed_artifact_write_is_a_warning_and_the_block_ships(run_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import docxaicorrector.pipeline.literary_polish as literary_polish

    blocked = run_dir / "not-a-directory"
    blocked.write_text("", encoding="utf-8")
    monkeypatch.setattr(literary_polish, "resolve_literary_polish_rollbacks_dir", lambda: blocked / "family")
    jobs, first_pass = _one_paragraph_block("В 1923 году в городе было 23 моста через реку.")
    generator = _Generator(first_pass=first_pass, polish=_polish_with("В 1932 году в городе было 23 моста через реку."))

    run = _run_blocks(jobs, generator=generator, app_config=_app_config("standard"))

    assert run.outcome is None
    assert _registry_texts(run.state) == ["В 1923 году в городе было 23 моста через реку."]
    failures = _events(run, "literary_polish_artifact_write_failed")
    assert len(failures) == 1 and failures[0]["level"] == logging.WARNING
    assert _events(run, "literary_polish_paragraph_rolled_back")[0]["context"]["artifact_path"] is None


def test_the_polish_prompt_states_the_three_rules_of_form() -> None:
    core_config.load_system_prompt.cache_clear()
    try:
        prompt = core_config.load_system_prompt(
            operation="translate", source_language="en", target_language="ru", prompt_variant="literary_polish"
        )
    finally:
        core_config.load_system_prompt.cache_clear()

    assert "Записывайте числа так же, как в тексте: цифры — цифрами, слова — словами" in prompt
    assert "Маркеры абзацев и номера пунктов списка не меняйте" in prompt
    assert "Фрагменты на другом письме (имена, названия, ссылки, адреса) не переводите и не транслитерируйте" in prompt


# --- the same contract through the REAL generator ---------------------------------------------------


class _MarkerAnsweringClient:
    """A Responses client: translates first-pass blocks from a table, polishes second-pass ones.

    It answers what the real generator actually sent -- the target section of the user message --
    so the keyword contract of the second-pass call is checked against production code.
    """

    def __init__(self, translations: dict[str, str]) -> None:
        self.translations = translations
        self.requests: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    @staticmethod
    def is_polish(request: dict[str, Any]) -> bool:
        return "Не переводите его заново" in str(request["input"][0]["content"][0]["text"])

    def _create(self, **request: Any) -> SimpleNamespace:
        self.requests.append(request)
        user_text = str(request["input"][1]["content"][0]["text"])
        target = user_text.split("[TARGET BLOCK WITH MARKERS]\n", 1)[1].split("\n\n[CONTEXT AFTER]", 1)[0]
        answer = "\n\n".join(
            f"[[DOCX_PARA_{paragraph_id}]]\n"
            + (text.replace("первого прохода", "после шлифовки") if self.is_polish(request) else self.translations[paragraph_id])
            for paragraph_id, text in _split_marked(target)
        )
        return SimpleNamespace(
            status="completed",
            output_text=answer,
            usage=SimpleNamespace(prompt_tokens=40, completion_tokens=30, cost=0.0001),
        )


def test_the_real_generator_runs_the_pass_and_books_it_in_its_own_section(run_dir: Path) -> None:
    from docxaicorrector.generation._generation import generate_markdown_block

    client = _MarkerAnsweringClient({pid: text for pid, (text, _status) in _FIRST_PASS.items()})

    run = _run_blocks(
        _two_blocks(),
        generator=generate_markdown_block,
        app_config=_app_config("standard", polish_reasoning="low"),
        load_system_prompt=core_config.load_system_prompt,
        client=client,
    )

    polished = [text.replace("первого прохода", "после шлифовки") for text, _status in _FIRST_PASS.values()]
    assert run.outcome is None
    assert _registry_texts(run.state) == polished
    polish_requests = [request for request in client.requests if client.is_polish(request)]
    first_pass_requests = [request for request in client.requests if not client.is_polish(request)]
    assert len(polish_requests) == 2 and len(first_pass_requests) == 2
    # FR-003 on the wire: the pass's level on its own calls, nothing on the first pass of
    # ``standard``.
    assert all(request["reasoning"] == {"effort": "low"} for request in polish_requests)
    assert all("reasoning" not in request for request in first_pass_requests)
    # FR-004 (6): the run-wide record is the first pass's; the pass's calls and counters are its own.
    snapshot = run.snapshot
    assert snapshot["paragraph_disposition_counts"]["accepted"] == 3
    assert sum(snapshot["api_path_counts"].values()) == 2
    assert snapshot["stages"]["literary_polish"]["model_call_count"] == 2
    assert snapshot["stages"]["text_generation"]["model_call_count"] == 2
    generator_counters = snapshot["literary_polish"]["generator_counters"]
    assert generator_counters["paragraph_disposition_counts"]["accepted"] == 3
    assert sum(generator_counters["api_path_counts"].values()) == 2
    assert snapshot["literary_polish"]["counters"]["accepted_paragraph_count"] == 3


class _StopPressedDuringPolishClient(_MarkerAnsweringClient):
    """Answers the pass's request with a VALID polished text, and the user presses Stop meanwhile."""

    def __init__(self, translations: dict[str, str], stop_flag: dict[str, bool]) -> None:
        super().__init__(translations)
        self.stop_flag = stop_flag
        self.responses = SimpleNamespace(create=self._create_and_stop)

    def _create_and_stop(self, **request: Any) -> SimpleNamespace:
        if self.is_polish(request):
            self.stop_flag["stop"] = True
        return self._create(**request)


def test_stop_pressed_during_a_successful_polish_request_keeps_the_first_pass(run_dir: Path) -> None:
    """Codex acceptance review of spec 069, finding 2: the answer is valid, Stop was pressed in flight."""

    from docxaicorrector.generation._generation import generate_markdown_block

    stop_flag = {"stop": False}
    client = _StopPressedDuringPolishClient({pid: text for pid, (text, _status) in _FIRST_PASS.items()}, stop_flag)

    run = _run_blocks(
        _two_blocks(),
        generator=generate_markdown_block,
        app_config=_app_config("standard", polish_reasoning="low"),
        load_system_prompt=core_config.load_system_prompt,
        client=client,
        should_stop=lambda _runtime: stop_flag["stop"],
    )

    assert run.outcome == "stopped"
    assert run.state.stopped_during_polish is True
    first_block = str(run.state.processed_chunks[0])
    assert "первого прохода" in first_block and "после шлифовки" not in first_block
    failed = _events(run, "literary_polish_block_failed")
    assert [(event["context"]["reason"], event["context"]["block_index"]) for event in failed] == [("stopped", 1)]
    assert [row["reasons"] for row in _rollback_rows(run_dir)] == [["stopped"]]
    counters = run.snapshot["literary_polish"]["counters"]
    assert counters.get("accepted_paragraph_count", 0) == 0
