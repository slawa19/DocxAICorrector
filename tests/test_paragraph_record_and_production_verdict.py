"""Spec 061 user stories 4 and 5 — one record per paragraph, and a verdict built from state.

US4 (FR-014/015/016/017). The late phases rebuilt the paragraph registry from the assembly
entries with ``build_generated_paragraph_registry_from_entries``, and ``FinalAssemblyEntry``
had no field for what became of the paragraph. So the registry reader cleanup hands to the
narration projection carried no ``paragraph_status`` and no
``controlled_fallback_narration_excluded``, and the projection's two filters could never
fire in production; the only test of them fed hand-written dicts. Every registry here is
built by the production writers and the production builder.

US5 (FR-019). The production acceptance context wrote ``"result": "succeeded"`` and an
empty ``reader_cleanup_evidence``, so ``pipeline_succeeded`` and
``reader_cleanup_stage_completed`` could only pass. They are NOT-APPLICABLE in production
now; the harness, which owns both inputs, still judges them. FR-018 (the blocked paths) is
tested beside the other finalize-gate tests in
``tests/test_late_phases_finalize_gate_persistence.py``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.block_execution as block_execution
import docxaicorrector.pipeline.narration_postprocess as narration_postprocess
import docxaicorrector.pipeline.output_validation as output_validation
import docxaicorrector.pipeline.quality_gate as quality_gate
import docxaicorrector.pipeline.reader_cleanup_rebuild as reader_cleanup_rebuild
from docxaicorrector.pipeline.contracts import LatePhaseStopped
from docxaicorrector.ui import i18n
from docxaicorrector.generation._generation import (
    MarkerPreservedBlockText,
    ParagraphDisposition,
)
from docxaicorrector.validation.acceptance import (
    PRODUCTION_ACCEPTANCE_CHECK_NAMES,
    build_acceptance_verdict,
)


# ---------------------------------------------------------------------------------------
# the production chain: block_execution writers -> assembly -> builder -> projection
# ---------------------------------------------------------------------------------------


def _block(*dispositions: ParagraphDisposition) -> MarkerPreservedBlockText:
    return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


def _append_marker_registry_entries(**kwargs) -> None:
    block_execution.append_marker_registry_entries(
        **kwargs,
        build_processed_paragraph_registry_entries_fn=block_execution.build_processed_paragraph_registry_entries,
    )


def _write_block(state, *, index: int, payload, processed_chunk: str, fallback: tuple[str, bool] | None = None) -> None:
    """Write one block's registry entries exactly as ``block_execution`` does in production."""
    common = {
        "context": SimpleNamespace(uploaded_filename="report.docx"),
        "dependencies": SimpleNamespace(log_event=lambda *args, **kwargs: None),
        "state": state,
        "initialization": SimpleNamespace(job_count=3),
        "index": index,
        "payload": payload,
        "processed_chunk": processed_chunk,
    }
    if fallback is None:
        _append_marker_registry_entries(**common)
        return
    rejection_kind, narration_excluded = fallback
    block_execution.append_controlled_fallback_registry_entries(
        **common,
        rejection_kind=rejection_kind,
        append_marker_registry_entries_fn=_append_marker_registry_entries,
        narration_excluded=narration_excluded,
    )


def _final_registry(processed_chunks: Sequence[str], state) -> tuple[tuple[output_validation.FinalAssemblyEntry, ...], list[dict[str, object]]]:
    assembly_result = output_validation.assemble_final_markdown(
        processed_chunks=list(processed_chunks),
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=None,
    )
    return assembly_result.entries, output_validation.build_generated_paragraph_registry_from_entries(
        assembly_result.entries
    )


def _project(
    registry: Sequence[Mapping[str, object]], *, job_count: int, processing_operation: str = "translate"
) -> list[str]:
    return narration_postprocess._project_final_cleanup_narration_chunks(
        context=SimpleNamespace(
            processing_operation=processing_operation, jobs=[{"narration_include": True}] * job_count
        ),
        final_generated_paragraph_registry=list(registry),
    )


_SOURCE_FALLBACK_TEXT = "Once upon a time, in a small village in the Outback."
_ACCEPTED_TEXT = "Почему бы не задействовать фонд?"
_OMITTED_SOURCE_TEXT = "Footnote 14, see Appendix A for the full dataset."
_PLAIN_TEXT = "Однажды в маленькой деревне люди обменивались товарами."


def test_production_registry_carries_both_dispositions_and_the_projection_honours_them() -> None:
    """US4 scenario 1: a controlled-fallback block and an ``omitted`` paragraph are dropped
    by the projection when the registry is the one production builds (FR-014, FR-015)."""
    state = SimpleNamespace(generated_paragraph_registry=[])
    omitted_block = _block(
        ParagraphDisposition(paragraph_id="p0002", text=_ACCEPTED_TEXT, status="accepted"),
        ParagraphDisposition(paragraph_id="p0003", text=_OMITTED_SOURCE_TEXT, status="omitted"),
    )
    _write_block(
        state,
        index=1,
        payload=SimpleNamespace(job_kind="llm", paragraph_ids=["p0001"]),
        processed_chunk=_SOURCE_FALLBACK_TEXT,
        fallback=("source_text_fallback", True),
    )
    _write_block(
        state,
        index=2,
        payload=SimpleNamespace(job_kind="llm", paragraph_ids=["p0002", "p0003"]),
        processed_chunk=omitted_block,
    )

    entries, registry = _final_registry([_SOURCE_FALLBACK_TEXT, omitted_block], state)

    by_id = {str(entry["paragraph_id"]): entry for entry in registry}
    assert by_id["p0001"]["controlled_fallback_narration_excluded"] is True
    assert by_id["p0002"]["paragraph_status"] == "accepted"
    assert by_id["p0003"]["paragraph_status"] == "omitted"
    assert [entry.paragraph_status for entry in entries] == [None, "accepted", "omitted"]
    assert _project(registry, job_count=2) == [_ACCEPTED_TEXT]


def test_production_builder_without_a_fallback_leaves_the_paragraph_narratable() -> None:
    """Anti-vacuum for FR-014/016: no substitution, ``accepted`` status — the builder sets no
    exclusion, and the paragraph is spoken. A filter that dropped everything would pass the
    test above; it cannot pass this one."""
    state = SimpleNamespace(generated_paragraph_registry=[])
    accepted_block = _block(
        ParagraphDisposition(paragraph_id="p0001", text=_PLAIN_TEXT, status="accepted")
    )
    _write_block(
        state,
        index=1,
        payload=SimpleNamespace(job_kind="llm", paragraph_ids=["p0001"]),
        processed_chunk=accepted_block,
    )

    entries, registry = _final_registry([accepted_block], state)

    assert len(entries) == 1
    assert entries[0].narration_excluded is False
    assert entries[0].paragraph_status == "accepted"
    assert "controlled_fallback_narration_excluded" not in registry[0]
    assert _project(registry, job_count=1) == [_PLAIN_TEXT]


def test_merge_entry_pair_keeps_the_disposition_of_two_withheld_halves() -> None:
    """``_merge_entry_pair`` only ever sees two halves on the SAME side of the narration
    boundary (its caller refuses a mixed pair, below). Two withheld halves weld into a
    withheld paragraph: a status other than ``accepted`` wins, the exclusion is OR."""
    omitted = output_validation.FinalAssemblyEntry(
        text="First half of the source sentence", block_index=1, paragraph_id="p1", paragraph_status="omitted"
    )
    restored = output_validation.FinalAssemblyEntry(
        text="and its untranslated tail.",
        block_index=1,
        paragraph_id="p2",
        paragraph_status="source_restored",
        narration_excluded=True,
    )

    merged = output_validation._merge_entry_pair(omitted, restored)

    assert merged.paragraph_status == "omitted"
    assert merged.narration_excluded is True
    both_accepted = output_validation._merge_entry_pair(
        output_validation.FinalAssemblyEntry(
            text="Первая половина предложения", block_index=1, paragraph_id="p1", paragraph_status="accepted"
        ),
        output_validation.FinalAssemblyEntry(
            text="и её переведённый хвост.", block_index=1, paragraph_id="p2", paragraph_status="accepted"
        ),
    )
    assert both_accepted.paragraph_status == "accepted"
    assert both_accepted.narration_excluded is False


_CONTINUED_HEAD = "Первая половина предложения"
_CONTINUED_TAIL = "и её хвост, который модель вернула отдельно."


def _assemble_continuation(left_status: str, right_status: str) -> output_validation.FinalMarkdownAssemblyResult:
    """One marker block whose two paragraphs are a sentence broken across a paragraph break —
    the shape boundary recovery (``_recover_adjacent_entries``) welds back together."""
    state = SimpleNamespace(generated_paragraph_registry=[])
    block = _block(
        ParagraphDisposition(paragraph_id="p0001", text=_CONTINUED_HEAD, status=left_status),
        ParagraphDisposition(paragraph_id="p0002", text=_CONTINUED_TAIL, status=right_status),
    )
    _write_block(
        state,
        index=1,
        payload=SimpleNamespace(job_kind="llm", paragraph_ids=["p0001", "p0002"]),
        processed_chunk=block,
    )
    return output_validation.assemble_final_markdown(
        processed_chunks=[block],
        generated_paragraph_registry=state.generated_paragraph_registry,
        source_paragraphs=None,
    )


def test_boundary_recovery_refuses_to_weld_accepted_text_to_withheld_text() -> None:
    """The review finding (F2): recovery used to weld A=``accepted`` and B=``omitted`` into ONE
    record carrying B's status, and the late projection then withheld both — A's translation
    vanished from the narration and no counter knew. The pair now stays two paragraphs, is
    recorded as a refused merge rather than a repaired boundary, A is spoken and B withheld
    with its own address."""
    result = _assemble_continuation("accepted", "omitted")

    assert [(entry.paragraph_id, entry.paragraph_status) for entry in result.entries] == [
        ("p0001", "accepted"),
        ("p0002", "omitted"),
    ]
    assert result.diagnostics.accepted_merges == 0
    assert [decision.reason for decision in result.diagnostics.merge_decisions] == [
        "narration_admissibility_boundary"
    ]
    registry = output_validation.build_generated_paragraph_registry_from_entries(result.entries)
    assert _project(registry, job_count=1) == [_CONTINUED_HEAD]


def test_boundary_recovery_still_welds_two_withheld_halves() -> None:
    result = _assemble_continuation("omitted", "source_restored")

    assert len(result.entries) == 1
    assert result.entries[0].paragraph_status == "omitted"
    assert result.diagnostics.accepted_merges == 1
    registry = output_validation.build_generated_paragraph_registry_from_entries(result.entries)
    assert _project(registry, job_count=1) == []


def test_boundary_recovery_still_welds_two_accepted_halves() -> None:
    """Anti-vacuum: the refusal is about the boundary, not about merging — two accepted halves
    of one sentence are still welded and spoken as one paragraph."""
    result = _assemble_continuation("accepted", "accepted")

    assert len(result.entries) == 1
    assert result.entries[0].paragraph_status == "accepted"
    assert result.diagnostics.accepted_merges == 1
    registry = output_validation.build_generated_paragraph_registry_from_entries(result.entries)
    assert _project(registry, job_count=1) == [result.entries[0].text]


_RESTORED_SOURCE_TEXT = "People used barter for all their transactions."


def _restored_registry() -> list[dict[str, object]]:
    state = SimpleNamespace(generated_paragraph_registry=[])
    block = _block(
        ParagraphDisposition(paragraph_id="p0001", text=_ACCEPTED_TEXT, status="accepted"),
        ParagraphDisposition(paragraph_id="p0002", text=_RESTORED_SOURCE_TEXT, status="source_restored"),
        ParagraphDisposition(paragraph_id="p0003", text=_OMITTED_SOURCE_TEXT, status="omitted"),
    )
    _write_block(
        state,
        index=1,
        payload=SimpleNamespace(job_kind="llm", paragraph_ids=["p0001", "p0002", "p0003"]),
        processed_chunk=block,
    )
    _entries, registry = _final_registry([block], state)
    return registry


def test_late_projection_withholds_source_restored_in_a_language_changing_operation() -> None:
    """FR-006 on the cleaned-translate path: ``source_restored`` is the paragraph's own source
    text, which in ``translate`` is the other language — withheld beside ``omitted``, exactly
    as ``block_execution.narration_projection_for_processed_block`` does on the standalone
    path. Anti-vacuum: the accepted paragraph is spoken."""
    assert _project(_restored_registry(), job_count=1, processing_operation="translate") == [_ACCEPTED_TEXT]


def test_late_projection_speaks_source_restored_on_edit() -> None:
    """FR-007: on ``edit`` the source IS target-language text, so a restored paragraph is a real
    paragraph of the book and is spoken; ``omitted`` stays withheld on every operation."""
    assert _project(_restored_registry(), job_count=1, processing_operation="edit") == [
        _ACCEPTED_TEXT,
        _RESTORED_SOURCE_TEXT,
    ]


def _join(
    current_extra: Mapping[str, object], next_extra: Mapping[str, object]
) -> tuple[list[dict[str, object]], Mapping[str, object]]:
    registry = [
        {"block_index": 1, "paragraph_id": "p0001", "text": "First fragment", **current_extra},
        {"block_index": 2, "paragraph_id": "p0002", "text": "second fragment", **next_extra},
    ]
    derived, diagnostics = reader_cleanup_rebuild._derive_reader_cleanup_generated_paragraph_registry(
        generated_paragraph_registry=registry,
        cleanup_report={
            "accepted_cleanup_operations": [
                {
                    "id": "b_000000",
                    "operation": "join_fragmented_paragraph",
                    "next_id": "b_000001",
                    "expected_after_preview": "First fragment second fragment",
                }
            ]
        },
        raw_markdown="First fragment\n\nsecond fragment",
    )
    assert derived is not None
    return derived, diagnostics


_EXCLUDED_FALLBACK = {
    "paragraph_status": "accepted",
    "controlled_fallback": True,
    "controlled_fallback_narration_excluded": True,
}


@pytest.mark.parametrize(
    "withheld_extra",
    [{"paragraph_status": "omitted"}, {"paragraph_status": "source_restored"}, _EXCLUDED_FALLBACK],
    ids=["omitted", "source_restored", "excluded_fallback"],
)
def test_cleanup_join_refuses_to_weld_accepted_text_to_withheld_text(monkeypatch, withheld_extra) -> None:
    """The review finding (F2) on the cleanup path: the join welded A=``accepted`` and a
    withheld B into one record with B's disposition, and the projection then withheld both.
    A join across the narration-admissibility boundary is now refused for the registry:
    counted as a skipped operation, logged with its reason, A spoken, B withheld with its own
    paragraph id and text (its address)."""
    events: list[tuple[str, Mapping[str, object]]] = []
    monkeypatch.setattr(
        reader_cleanup_rebuild,
        "log_event",
        lambda level, event_id, message, **context: events.append((event_id, context)),
    )

    derived, diagnostics = _join({"paragraph_status": "accepted"}, withheld_extra)

    assert [entry["paragraph_id"] for entry in derived] == ["p0001", "p0002"]
    assert derived[1]["text"] == "second fragment"
    assert derived[1]["paragraph_status"] == withheld_extra["paragraph_status"]
    assert diagnostics["joined_registry_entry_count"] == 0
    assert diagnostics["skipped_operation_count"] == 1
    assert diagnostics["refused_join_narration_admissibility_count"] == 1
    assert [(event_id, context["reason"]) for event_id, context in events] == [
        ("reader_cleanup_join_refused", "join_refused_narration_admissibility")
    ]
    assert _project(derived, job_count=2) == ["First fragment"]


def test_cleanup_join_still_welds_two_withheld_halves() -> None:
    derived, diagnostics = _join({"paragraph_status": "omitted"}, {"paragraph_status": "source_restored"})

    assert diagnostics["joined_registry_entry_count"] == 1
    assert diagnostics["refused_join_narration_admissibility_count"] == 0
    assert len(derived) == 1
    assert derived[0]["paragraph_status"] == "omitted"
    assert _project(derived, job_count=2) == []
    excluded_pair, _ = _join(_EXCLUDED_FALLBACK, {"paragraph_status": "omitted"})
    assert len(excluded_pair) == 1
    assert excluded_pair[0]["paragraph_status"] == "omitted"
    assert excluded_pair[0]["controlled_fallback_narration_excluded"] is True


def test_cleanup_join_of_two_accepted_paragraphs_stays_narratable() -> None:
    """Anti-vacuum: two accepted halves are still joined into one narratable paragraph."""
    derived, diagnostics = _join({"paragraph_status": "accepted"}, {"paragraph_status": "accepted"})

    assert diagnostics["joined_registry_entry_count"] == 1
    assert diagnostics["refused_join_narration_admissibility_count"] == 0
    assert len(derived) == 1
    assert derived[0]["paragraph_status"] == "accepted"
    assert "controlled_fallback_narration_excluded" not in derived[0]
    assert _project(derived, job_count=2) == ["First fragment second fragment"]


# ---------------------------------------------------------------------------------------
# end to end: translate + reader cleanup + the optional post-pass
# ---------------------------------------------------------------------------------------


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _capture_log_events():
    captured: list[dict[str, object]] = []

    def log_event(level, event_id, message, **context):
        captured.append({"level": level, "event_id": event_id, "message": message, "context": context})

    return captured, log_event


def _persisting_writer(tmp_path: Path):
    def _write(**_kwargs):
        markdown_path = tmp_path / "report.result.md"
        docx_path = tmp_path / "report.result.docx"
        markdown_path.write_text("result", encoding="utf-8")
        docx_path.write_bytes(b"PK\x03\x04 result")
        return {
            "markdown_path": str(markdown_path),
            "docx_path": str(docx_path),
            "tts_text_path": str(tmp_path / "report.result.tts.txt"),
        }

    return _write


def _run(
    tmp_path: Path,
    *,
    processing_operation: str,
    app_config: dict[str, object],
    jobs,
    generate,
    log_event,
    runtime,
    should_stop_processing=lambda runtime: False,
):
    return document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=jobs,
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config=app_config,
        model="gpt-5.4",
        max_retries=1,
        processing_operation=processing_operation,
        source_language="en" if processing_operation == "translate" else "ru",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **kwargs: f"system:{kwargs['operation']}",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=lambda runtime, stage, detail, progress, terminal_kind=None: None,
        emit_log=lambda runtime, **payload: None,
        emit_status=lambda runtime, **payload: None,
        should_stop_processing=should_stop_processing,
        generate_markdown_block=generate,
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=lambda markdown_text: markdown_text.encode("utf-8"),
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=_persisting_writer(tmp_path),
    )


def test_cleaned_translate_post_pass_never_receives_an_omitted_paragraph(tmp_path) -> None:
    """US4 scenario 1 through the real late phases: the registry built at
    ``late_phases`` from the assembly entries is the one reader cleanup returns as FINAL and
    the projection reads. Before FR-014 it had no ``paragraph_status`` and the omitted
    paragraph's source text went to the audiobook post-pass."""
    runtime: dict[str, object] = {"state": {}}
    events, log_event = _capture_log_events()
    post_pass_inputs: list[str] = []
    omitted_text = "14"

    def generate(**kwargs):
        system_prompt = str(kwargs["system_prompt"])
        if system_prompt.startswith("You are cleaning translated book Markdown"):
            return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)
        if system_prompt == "system:audiobook":
            post_pass_inputs.append(str(kwargs["target_text"]))
            return "[thoughtful] Почему бы не задействовать фонд?"
        return _block(
            ParagraphDisposition(paragraph_id="p0001", text=_ACCEPTED_TEXT, status="accepted"),
            ParagraphDisposition(paragraph_id="p0002", text=omitted_text, status="omitted"),
        )

    target_text = f"Why not use the fund?\n\n{omitted_text}"
    result = _run(
        tmp_path,
        processing_operation="translate",
        app_config={
            "enable_paragraph_markers": True,
            "reader_cleanup_enabled": True,
            "reader_cleanup_policy": "advisory",
            "audiobook_postprocess_enabled": True,
        },
        jobs=[
            {
                "target_text": target_text,
                "target_text_with_markers": (
                    "[[DOCX_PARA_p0001]]\nWhy not use the fund?\n\n"
                    f"[[DOCX_PARA_p0002]]\n{omitted_text}"
                ),
                "paragraph_ids": ["p0001", "p0002"],
                "context_before": "",
                "context_after": "",
                "target_chars": len(target_text),
                "context_chars": 0,
                "narration_include": True,
            }
        ],
        generate=generate,
        log_event=log_event,
        runtime=runtime,
    )

    assert result == "succeeded"
    assert post_pass_inputs, [event["event_id"] for event in events]
    post_pass_text = "\n\n".join(post_pass_inputs)
    # Anti-vacuum: the accepted paragraph IS narrated...
    assert _ACCEPTED_TEXT in post_pass_text
    # ...the omitted one is not, while the DOCX branch still carries it.
    assert omitted_text not in post_pass_text.split("\n\n")
    session_state = cast(Mapping[str, object], runtime["state"])
    assert omitted_text in str(session_state["latest_markdown"]).split("\n\n")
    final_registry = cast(
        Sequence[Mapping[str, object]], session_state["final_generated_paragraph_registry"]
    )
    statuses = {str(entry["paragraph_id"]): entry.get("paragraph_status") for entry in final_registry}
    assert statuses == {"p0001": "accepted", "p0002": "omitted"}


# ---------------------------------------------------------------------------------------
# FR-017 (narrowed): the post-pass answer with fewer paragraphs is never silent
# ---------------------------------------------------------------------------------------


def _run_edit_post_pass(tmp_path: Path, *, post_pass_answer: str):
    runtime: dict[str, object] = {"state": {}}
    events, log_event = _capture_log_events()

    def generate(**kwargs):
        if kwargs["system_prompt"] == "system:audiobook":
            return post_pass_answer
        return "Первый абзац главы.\n\nВторой абзац главы."

    result = _run(
        tmp_path,
        processing_operation="edit",
        app_config={"audiobook_postprocess_enabled": True},
        jobs=[
            {
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
                "narration_include": True,
            }
        ],
        generate=generate,
        log_event=log_event,
        runtime=runtime,
    )
    return result, runtime, events


def _saved_context(events: Sequence[Mapping[str, object]]) -> Mapping[str, object]:
    saved = next(event for event in events if event["event_id"] == "ui_audiobook_artifact_saved")
    context = saved["context"]
    assert isinstance(context, Mapping)
    return context


def test_post_pass_answer_with_a_paragraph_missing_is_marked_for_review(tmp_path) -> None:
    result, runtime, events = _run_edit_post_pass(
        tmp_path, post_pass_answer="[thoughtful] Первый абзац главы."
    )

    assert result == "succeeded"
    shortfalls = [
        event for event in events if event["event_id"] == "audiobook_postprocess_paragraph_shortfall"
    ]
    assert len(shortfalls) == 1
    assert shortfalls[0]["level"] == logging.WARNING
    context = shortfalls[0]["context"]
    assert isinstance(context, Mapping)
    assert context["needs_review"] is True
    assert context["sent_paragraph_count"] == 2
    assert context["returned_paragraph_count"] == 1
    assert context["missing_paragraph_count"] == 1
    saved = _saved_context(events)
    assert saved["postprocess_paragraph_shortfall_group_count"] == 1
    assert saved["postprocess_paragraph_shortfall_paragraph_count"] == 1
    # Delivered, not replaced: the check reports, it does not rewrite the answer.
    assert "Первый абзац главы." in str(cast(Mapping[str, object], runtime["state"])["latest_narration_text"])
    # ...and the reader is told, once, with the counts the template prints.
    notices = _shortfall_notices(runtime)
    assert len(notices) == 1
    assert notices[0]["level"] == "warning"
    assert notices[0]["params"] == {"count": 1, "paragraphs": 1}
    for language in ("ru", "en"):
        catalog = json.loads(
            (Path(i18n.__file__).resolve().parent / "locales" / f"{language}.json").read_text(encoding="utf-8")
        )
        rendered = catalog["result.narration_postprocess_paragraph_shortfall"].format(count=1, paragraphs=1)
        assert "{" not in rendered


def test_post_pass_answer_with_every_paragraph_is_not_reported(tmp_path) -> None:
    """Anti-vacuum: a full answer raises nothing, and the counters say zero."""
    result, _runtime, events = _run_edit_post_pass(
        tmp_path,
        post_pass_answer="[thoughtful] Первый абзац главы.\n\nВторой абзац главы.",
    )

    assert result == "succeeded"
    assert not [
        event for event in events if event["event_id"] == "audiobook_postprocess_paragraph_shortfall"
    ]
    saved = _saved_context(events)
    assert saved["postprocess_paragraph_shortfall_group_count"] == 0
    assert saved["postprocess_paragraph_shortfall_paragraph_count"] == 0
    assert _shortfall_notices(_runtime) == []


def test_stop_pressed_during_a_post_pass_call_is_honoured_inside_it(tmp_path) -> None:
    """FR-022 in the late passes: the post-pass hands ``generate_markdown_block`` the run's
    Stop predicate, so a Stop pressed after the call began stops its NEXT model call. The
    double stands in for the real generator's retry loop, which asks ``should_stop`` before
    every attempt (``_generation._raise_if_stop_requested``)."""
    runtime: dict[str, object] = {"state": {}}
    _events, log_event = _capture_log_events()
    stop_requested = {"value": False}
    post_pass_attempts: list[int] = []

    def generate(**kwargs):
        if kwargs["system_prompt"] != "system:audiobook":
            return "Первый абзац главы."
        should_stop = kwargs["should_stop"]
        for attempt in (1, 2):
            if should_stop():
                raise LatePhaseStopped()
            post_pass_attempts.append(attempt)
            stop_requested["value"] = True  # the user presses Stop during attempt 1
        return "[thoughtful] Первый абзац главы."

    result = _run(
        tmp_path,
        processing_operation="edit",
        app_config={"audiobook_postprocess_enabled": True},
        jobs=[
            {
                "target_text": "block",
                "context_before": "",
                "context_after": "",
                "target_chars": 5,
                "context_chars": 0,
                "narration_include": True,
            }
        ],
        generate=generate,
        log_event=log_event,
        runtime=runtime,
        should_stop_processing=lambda runtime: stop_requested["value"],
    )

    assert post_pass_attempts == [1]
    assert result == "stopped"


def test_stop_pressed_during_a_reader_cleanup_call_is_honoured_inside_it(tmp_path) -> None:
    runtime: dict[str, object] = {"state": {}}
    _events, log_event = _capture_log_events()
    stop_requested = {"value": False}
    cleanup_attempts: list[int] = []

    def generate(**kwargs):
        if not str(kwargs["system_prompt"]).startswith("You are cleaning translated book Markdown"):
            return "Первый абзац главы."
        should_stop = kwargs["should_stop"]
        for attempt in (1, 2):
            if should_stop():
                raise LatePhaseStopped()
            cleanup_attempts.append(attempt)
            stop_requested["value"] = True
        return json.dumps({"cleanup_operations": [], "warnings": []}, ensure_ascii=False)

    result = _run(
        tmp_path,
        processing_operation="translate",
        app_config={"reader_cleanup_enabled": True, "reader_cleanup_policy": "advisory"},
        jobs=[
            {
                "target_text": "First paragraph of the chapter.",
                "context_before": "",
                "context_after": "",
                "target_chars": 31,
                "context_chars": 0,
                "narration_include": True,
            }
        ],
        generate=generate,
        log_event=log_event,
        runtime=runtime,
        should_stop_processing=lambda runtime: stop_requested["value"],
    )

    assert cleanup_attempts == [1]
    assert result == "stopped"


def _shortfall_notices(runtime: Mapping[str, object]) -> list[Mapping[str, object]]:
    notices = cast(Mapping[str, object], runtime["state"]).get("latest_result_notices") or []
    assert isinstance(notices, Sequence)
    return [
        notice
        for notice in notices
        if isinstance(notice, Mapping)
        and notice.get("message_key") == "result.narration_postprocess_paragraph_shortfall"
    ]


# ---------------------------------------------------------------------------------------
# FR-019: the production context fakes no input; the harness still judges both checks
# ---------------------------------------------------------------------------------------


def _checks_by_name(verdict: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    checks = verdict["checks"]
    assert isinstance(checks, Sequence)
    return {str(check["name"]): check for check in checks if isinstance(check, Mapping)}


def _failed(verdict: Mapping[str, object]) -> list[str]:
    failed = verdict["failed_checks"]
    assert isinstance(failed, Sequence)
    return [str(name) for name in failed]


def _production_verdict(quality_report: Mapping[str, object]) -> dict[str, object]:
    context = quality_gate._build_report_context_for_acceptance(
        context=SimpleNamespace(processing_operation="translate"),
        quality_report=quality_report,
        formatting_diagnostics_payloads=[{"unmapped_source_ids": [], "caption_heading_conflicts": []}],
        output_artifacts={"output_docx_openable": True},
    )
    assert "result" not in context
    assert "reader_cleanup_evidence" not in context
    return quality_gate.build_report_acceptance_verdict(context, require_no_toc_body_concat=True)


def test_production_verdict_does_not_judge_inputs_it_does_not_have() -> None:
    verdict = _production_verdict({"quality_status": "pass", "gate_reasons": []})

    by_name = _checks_by_name(verdict)
    # The enumeration is unchanged: the checks are still reported, as NOT-APPLICABLE.
    assert set(by_name) == set(PRODUCTION_ACCEPTANCE_CHECK_NAMES)
    assert by_name["pipeline_succeeded"]["applicable"] is False
    assert by_name["pipeline_succeeded"]["reason"] == "pipeline_result_not_in_report"
    assert by_name["reader_cleanup_stage_completed"]["applicable"] is False
    assert by_name["reader_cleanup_stage_completed"]["reason"] == "reader_cleanup_evidence_not_in_report"
    assert "pipeline_succeeded" not in _failed(verdict)
    assert "reader_cleanup_stage_completed" not in _failed(verdict)


def test_production_verdict_still_fails_on_a_check_it_can_measure() -> None:
    """Anti-vacuum: excluding two checks did not quiet the verdict. A failed quality report
    is an input production DOES have, and it still turns the verdict red."""
    verdict = _production_verdict({"quality_status": "fail", "gate_reasons": ["untranslated_body_text_above_threshold"]})

    assert verdict["passed"] is False
    assert "translation_quality_report_not_failed" in _failed(verdict)


def test_harness_verdict_still_judges_pipeline_result_and_reader_cleanup() -> None:
    """The harness writes both keys from the real run, so both checks stay applicable there
    and still fail on the evidence that should fail them."""
    report = {
        "result": "failed",
        "runtime_config": {"effective": {"processing_operation": "translate"}},
        "translation_quality_report": {"quality_status": "pass", "gate_reasons": []},
        "formatting_diagnostics": [{"unmapped_source_ids": [], "caption_heading_conflicts": []}],
        "output_artifacts": {"output_docx_openable": True},
        "runtime": {},
        "reader_cleanup_evidence": {"stage_status": "failed", "failed_chunk_count": 2, "cleanup_chunk_count": 2},
        "preparation_diagnostic_snapshot": {},
    }

    verdict = build_acceptance_verdict(report, structural_checks_builder=None)

    by_name = _checks_by_name(verdict)
    assert by_name["pipeline_succeeded"]["applicable"] is True
    assert by_name["reader_cleanup_stage_completed"]["applicable"] is True
    assert {"pipeline_succeeded", "reader_cleanup_stage_completed"} <= set(_failed(verdict))
