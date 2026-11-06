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

import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.block_execution as block_execution
import docxaicorrector.pipeline.narration_postprocess as narration_postprocess
import docxaicorrector.pipeline.output_validation as output_validation
import docxaicorrector.pipeline.quality_gate as quality_gate
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


def _project(registry: Sequence[Mapping[str, object]], *, job_count: int) -> list[str]:
    return narration_postprocess._project_final_cleanup_narration_chunks(
        context=SimpleNamespace(jobs=[{"narration_include": True}] * job_count),
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


def test_a_merged_entry_keeps_the_disposition_of_either_half() -> None:
    """Boundary recovery may weld two entries into one paragraph of text. If either half is
    source text kept out of the narration, the welded paragraph carries it too, so the
    disposition survives the merge rather than belonging to the left half only."""
    left = output_validation.FinalAssemblyEntry(
        text="Первая половина предложения", block_index=1, paragraph_id="p1", paragraph_status="accepted"
    )
    right = output_validation.FinalAssemblyEntry(
        text="and its untranslated tail.",
        block_index=1,
        paragraph_id="p2",
        paragraph_status="omitted",
        narration_excluded=True,
    )

    merged = output_validation._merge_entry_pair(left, right)

    assert merged.paragraph_status == "omitted"
    assert merged.narration_excluded is True
    both_accepted = output_validation._merge_entry_pair(
        left,
        output_validation.FinalAssemblyEntry(
            text="и её переведённый хвост.", block_index=1, paragraph_id="p2", paragraph_status="accepted"
        ),
    )
    assert both_accepted.paragraph_status == "accepted"
    assert both_accepted.narration_excluded is False


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


def _run(tmp_path: Path, *, processing_operation: str, app_config: dict[str, object], jobs, generate, log_event, runtime):
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
        should_stop_processing=lambda runtime: False,
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
