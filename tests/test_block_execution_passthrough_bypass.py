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

from docxaicorrector.pipeline.block_execution import process_single_block


def _make_state() -> SimpleNamespace:
    return SimpleNamespace(
        processed_chunks=[],
        narration_chunks=[],
        excluded_narration_block_count=0,
        generated_paragraph_registry=[],
    )


def _no_op(**_kwargs: object) -> None:
    return None


def _run_single_block(*, payload: SimpleNamespace, context: SimpleNamespace, processed_chunk: str):
    """Invoke process_single_block with the surrounding orchestration stubbed to no-ops, wiring a
    recording classifier so we can assert whether the bypass skipped it."""
    state = _make_state()
    classifier_calls: list[tuple[str, str]] = []

    def classify_processed_block_fn(target_text: str, chunk: str) -> str:
        classifier_calls.append((target_text, chunk))
        return "valid"

    def parse_processing_job_fn(*, job: object) -> SimpleNamespace:
        return payload

    def execute_processing_block_fn(**_kwargs: object) -> tuple[str, bool]:
        return processed_chunk, False

    outcome = process_single_block(
        context=context,
        dependencies=SimpleNamespace(),
        emitters=SimpleNamespace(),
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
