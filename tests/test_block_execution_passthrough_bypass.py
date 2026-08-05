"""Spec 039 (C) anti-regression for the passthrough classifier bypass (commit ``c7a5283``) in
``pipeline/block_execution.py::process_single_block``.

A GENUINE passthrough block (``job_kind == "passthrough"`` and ``_should_route_toc_through_llm``
False) is emitted as VERBATIM source markdown with no LLM call, so the LLM-output-quality classifier
(``heading_only_output`` / untranslated / ...) must NOT gate it — otherwise passthrough-heavy real
documents hard-failed and produced empty DOCX (round-5 finding 1). A TOC block routed through the LLM
is genuinely processed and still goes through the classifier.

This guards the bypass with a fast, deterministic unit test instead of relying only on the ~25-min
real-document gate.
"""

from __future__ import annotations

from types import SimpleNamespace

import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.pipeline.block_execution import process_single_block


def _make_state() -> SimpleNamespace:
    return SimpleNamespace(
        processed_chunks=[],
        narration_chunks=[],
        excluded_narration_block_count=0,
        narration_excluded_source_fallback_block_count=0,
        narration_excluded_source_fallback_chars=0,
        generated_paragraph_registry=[],
        started_at=0.0,
    )


def _no_op(**_kwargs: object) -> None:
    return None


def _run_single_block(
    *,
    payload: SimpleNamespace,
    context: SimpleNamespace,
    processed_chunk: str,
    classification: str = "valid",
    dependencies: SimpleNamespace | None = None,
    emitters: SimpleNamespace | None = None,
):
    """Invoke process_single_block with the surrounding orchestration stubbed to no-ops, wiring a
    recording classifier so we can assert whether the bypass skipped it."""
    state = _make_state()
    classifier_calls: list[tuple[str, str]] = []

    def classify_processed_block_fn(target_text: str, chunk: str) -> str:
        classifier_calls.append((target_text, chunk))
        return classification

    def parse_processing_job_fn(*, job: object) -> SimpleNamespace:
        return payload

    def execute_processing_block_fn(**_kwargs: object) -> tuple[str, bool]:
        return processed_chunk, False

    outcome = process_single_block(
        context=context,
        dependencies=dependencies if dependencies is not None else SimpleNamespace(),
        emitters=emitters if emitters is not None else SimpleNamespace(),
        state=state,
        initialization=SimpleNamespace(job_count=1),
        index=1,
        job=object(),
        parse_processing_job_fn=parse_processing_job_fn,
        handle_invalid_processing_job_fn=_no_op,
        emit_block_started_fn=_no_op,
        is_marker_mode_enabled_fn=lambda _context, _payload: False,
        execute_processing_block_fn=execute_processing_block_fn,
        handle_block_generation_failure_fn=_no_op,
        classify_processed_block_fn=classify_processed_block_fn,
        handle_processed_block_rejection_fn=_no_op,
        append_marker_registry_entries_fn=_no_op,
        handle_marker_registry_failure_fn=_no_op,
        emit_block_completed_fn=_no_op,
    )
    return outcome, state, classifier_calls


def test_genuine_passthrough_heading_only_block_bypasses_classifier() -> None:
    # job_kind == "passthrough" and NOT toc-routed -> genuine passthrough bypass.
    payload = SimpleNamespace(
        job_kind="passthrough",
        toc_dominant=False,
        target_text="# Chapter One",
        narration_include=True,
        paragraph_ids=[],
    )
    context = SimpleNamespace(processing_operation="translate")

    outcome, state, classifier_calls = _run_single_block(
        payload=payload,
        context=context,
        processed_chunk="# Chapter One",  # heading-only output
    )

    assert outcome is None  # block accepted, no rejection/failure path
    assert classifier_calls == []  # bypass: classifier was NOT invoked
    assert state.processed_chunks == ["# Chapter One"]  # marked valid and retained verbatim


def test_toc_block_routed_through_llm_still_invokes_classifier() -> None:
    # processing_operation == "translate" and payload.toc_dominant -> _should_route_toc_through_llm
    # True, so even a "passthrough" job_kind is NOT a genuine passthrough and MUST be classified.
    payload = SimpleNamespace(
        job_kind="passthrough",
        toc_dominant=True,
        target_text="Contents",
        narration_include=True,
        paragraph_ids=[],
    )
    context = SimpleNamespace(processing_operation="translate")

    outcome, state, classifier_calls = _run_single_block(
        payload=payload,
        context=context,
        processed_chunk="Содержание",
    )

    assert outcome is None
    assert classifier_calls == [("Contents", "Содержание")]  # classifier WAS invoked
    assert state.processed_chunks == ["Содержание"]


# --- spec 054: the narration artifact carries only speakable target-language text ---------
#
# A block whose model output was rejected and replaced by its own SOURCE text stays in the
# DOCX — that document is editable and a human meets the untranslated paragraph and fixes
# it — but it does not reach the narration, because nothing sits between the audiobook and
# the listener. Measured on the first live audiobook run (2026-08-04, Money & Sustainability,
# en→ru): six ``source_text_fallback`` blocks put 20 597 characters of English mid-chapter
# into a Russian audiobook, 4.47% of the artifact.

_ENGLISH_SOURCE_BLOCK = (
    "Once upon a time, in a small village in the Outback, people used barter for all their "
    "transactions. On every market day, people walked around with chickens, eggs, hams and "
    "breads, and engaged in prolonged negotiations among themselves to exchange what they "
    "needed for the coming week."
)


def _recording_run_harness():
    events: list[tuple[str, dict[str, object]]] = []

    dependencies = SimpleNamespace(
        log_event=lambda _level, event, _message, **context: events.append((event, context)),
    )
    emitters = SimpleNamespace(
        emit_state=lambda _runtime, **_kwargs: None,
        emit_status=lambda _runtime, **_kwargs: None,
        emit_activity=lambda _runtime, _message: None,
        emit_log=lambda _runtime, **_kwargs: None,
    )
    return dependencies, emitters, events


def _llm_payload(*, target_text: str, narration_include: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=target_text,
        target_text_with_markers=f"[[DOCX_PARA_p0001]]{target_text}",
        paragraph_ids=["p0001"],
        narration_include=narration_include,
        target_chars=len(target_text),
        context_chars=0,
    )


def test_source_text_fallback_block_is_absent_from_narration_but_present_in_the_docx(monkeypatch) -> None:
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, events = _recording_run_harness()

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK),
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        # The controlled fallback delivers the block's own source text verbatim.
        processed_chunk=_ENGLISH_SOURCE_BLOCK,
        classification="source_text_fallback",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None  # the run continues; this is a controlled fallback, not a failure
    assert state.processed_chunks == [_ENGLISH_SOURCE_BLOCK]  # DOCX branch keeps the source
    assert state.narration_chunks == []  # narration branch does not
    assert state.narration_excluded_source_fallback_block_count == 1
    assert state.narration_excluded_source_fallback_chars == len(_ENGLISH_SOURCE_BLOCK)
    # The document-layer counter answers a different question and must not absorb this one.
    assert state.excluded_narration_block_count == 0
    fallback_events = [context for event, context in events if event == "block_controlled_fallback"]
    assert len(fallback_events) == 1
    assert fallback_events[0]["narration_excluded_by_source_fallback"] is True


def test_controlled_fallback_that_keeps_model_output_still_reaches_the_narration(monkeypatch) -> None:
    """Anti-vacuum. The rule is "the source text came back", not "a block was rejected".

    A rejection whose fallback keeps the model's own target-language output — here an
    ``english_residual_output`` verdict on text that is otherwise Russian — is still
    narratable and must not be dropped "just in case".
    """
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, events = _recording_run_harness()
    model_output = "Компании постоянно сталкиваются с нехваткой персонала, отмечает cash flow отчёт."

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK),
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=model_output,
        classification="english_residual_output",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None
    assert state.processed_chunks == [model_output]
    assert state.narration_chunks == [model_output]
    assert state.narration_excluded_source_fallback_block_count == 0
    assert state.narration_excluded_source_fallback_chars == 0
    fallback_events = [context for event, context in events if event == "block_controlled_fallback"]
    assert fallback_events[0]["narration_excluded_by_source_fallback"] is False


def test_a_normal_block_still_reaches_the_narration() -> None:
    """Anti-vacuum, the plain case: nothing about an accepted block changed."""
    russian = "Нынешнюю денежную систему почти все воспринимают как нечто само собой разумеющееся."

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK),
        context=SimpleNamespace(processing_operation="audiobook"),
        processed_chunk=russian,
    )

    assert outcome is None
    assert state.processed_chunks == [russian]
    assert state.narration_chunks == [russian]
    assert state.narration_excluded_source_fallback_block_count == 0


def test_block_excluded_by_the_document_layer_is_counted_only_once(monkeypatch) -> None:
    """A block that was never going to the narration keeps its existing reason.

    ``narration_include=False`` is the document layer's decision (image-only, table of
    contents, reference region). It wins, so the spec-054 ``excluded_char_share``
    measurements keyed on ``excluded_narration_block_count`` do not shift under this change.
    """
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()

    _outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK, narration_include=False),
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=_ENGLISH_SOURCE_BLOCK,
        classification="source_text_fallback",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert state.narration_chunks == []
    assert state.excluded_narration_block_count == 1
    assert state.narration_excluded_source_fallback_block_count == 0
