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
        narration_excluded_omitted_paragraph_count=0,
        narration_excluded_omitted_chars=0,
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


# --- spec 056 E: a typed disposition per paragraph, consumed by the registry --------


def _disposition_block(*pairs: tuple[str, str, str]):
    """Build the generator's return value for a block: (paragraph_id, text, status)."""
    from docxaicorrector.generation._generation import MarkerPreservedBlockText, ParagraphDisposition

    dispositions = [
        ParagraphDisposition(paragraph_id=paragraph_id, text=text, status=status)
        for paragraph_id, text, status in pairs
    ]
    return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


def test_registry_reads_the_paragraph_record_instead_of_re_splitting() -> None:
    """Block 274, the worked example: nine translations kept, one paragraph typed.

    Re-splitting the joined string can only recover the TEXT, never the reason it is there,
    so a paragraph the model returned nothing for was indistinguishable from one it
    translated — and the only way to express the difference was to discard the whole block.
    """
    processed_chunk = _disposition_block(
        *[(f"p{1333 + index}", f"Перевод абзаца {index}.", "accepted") for index in range(3)],
        ("p1336", "14", "omitted"),
        *[(f"p{1333 + index}", f"Перевод абзаца {index}.", "accepted") for index in range(4, 10)],
    )

    entries = block_execution.build_processed_paragraph_registry_entries(
        block_index=274,
        paragraph_ids=[f"p{1333 + index}" for index in range(10)],
        processed_chunk=processed_chunk,
    )

    assert len(entries) == 10
    assert [entry["paragraph_status"] for entry in entries].count("accepted") == 9
    assert entries[3] == {
        "block_index": 274,
        "paragraph_id": "p1336",
        "text": "14",
        "paragraph_status": "omitted",
    }


def test_registry_still_re_splits_a_plain_string_and_still_fails_on_a_count_mismatch() -> None:
    entries = block_execution.build_processed_paragraph_registry_entries(
        block_index=1,
        paragraph_ids=["p0001", "p0002"],
        processed_chunk="Первый.\n\nВторой.",
    )
    assert [entry["paragraph_id"] for entry in entries] == ["p0001", "p0002"]
    assert "paragraph_status" not in entries[0]

    import pytest

    with pytest.raises(RuntimeError) as exc_info:
        block_execution.build_processed_paragraph_registry_entries(
            block_index=1,
            paragraph_ids=["p0001", "p0002"],
            processed_chunk="Только один абзац.",
        )
    assert "paragraph_marker_registry_mismatch" in str(exc_info.value)


def test_registry_rejects_a_record_whose_ids_do_not_match_the_block() -> None:
    import pytest

    with pytest.raises(RuntimeError) as exc_info:
        block_execution.build_processed_paragraph_registry_entries(
            block_index=5,
            paragraph_ids=["p0001", "p0002"],
            processed_chunk=_disposition_block(("p0001", "Первый.", "accepted")),
        )
    assert "paragraph_marker_registry_mismatch" in str(exc_info.value)


def test_an_omitted_paragraph_stays_in_the_docx_and_leaves_the_narration() -> None:
    processed_chunk = _disposition_block(
        ("p1335", "Как нам справиться с безработицей?", "accepted"),
        ("p1336", "14", "omitted"),
        ("p1337", "Почему бы не задействовать фонд?", "accepted"),
    )

    # The document keeps every paragraph — losing one would break the paragraph-per-marker
    # mapping the formatting restorer depends on.
    assert processed_chunk == "Как нам справиться с безработицей?\n\n14\n\nПочему бы не задействовать фонд?"
    # The narration keeps only what the model actually spoke for.
    assert block_execution.narration_text_for_processed_block(processed_chunk) == (
        "Как нам справиться с безработицей?\n\nПочему бы не задействовать фонд?"
    )


def test_a_block_without_a_paragraph_record_is_narrated_unchanged() -> None:
    assert block_execution.narration_text_for_processed_block("Обычный блок.") == "Обычный блок."


def test_process_single_block_narrates_the_block_without_its_omitted_paragraph(monkeypatch) -> None:
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    processed_chunk = _disposition_block(
        ("p0001", "Переведённый абзац.", "accepted"),
        ("p0002", "14", "omitted"),
    )
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text="Source paragraph.\n\n14",
        target_text_with_markers="[[DOCX_PARA_p0001]]\nSource paragraph.\n\n[[DOCX_PARA_p0002]]\n14",
        paragraph_ids=["p0001", "p0002"],
        narration_include=True,
        target_chars=20,
        context_chars=0,
    )

    _outcome, state, _classifier_calls = _run_single_block(
        payload=payload,
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=processed_chunk,
        classification="valid",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert state.processed_chunks == ["Переведённый абзац.\n\n14"]
    assert state.narration_chunks == ["Переведённый абзац."]


# --- rev41 P0-1: the controlled-fallback path bypassed the per-paragraph filter ------
#
# The filter was applied only on the happy path. A block holding an ``omitted`` paragraph
# keeps that paragraph's SOURCE text, which makes the block likelier to be classified
# ``english_residual_output`` — and the rejection then routed it down the controlled-fallback
# path, which appended the RAW chunk and read the English aloud. The defect fed itself: the
# substitution caused the classification that bypassed the filter that would have removed the
# substitution. Reproduced by execution in ``.run/rev41_attack7.py``.

_ENGLISH_OMITTED_PARAGRAPH = (
    "This chapter discusses ordinary market institutions and the mobilisation of capital."
)


def test_controlled_fallback_does_not_narrate_an_omitted_paragraphs_source(monkeypatch) -> None:
    """`.run/rev41_attack7.py`, as a test. Before the fix the English was read aloud."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    russian = "Почему вообще следует мобилизовать капитал?"
    processed_chunk = _disposition_block(
        ("p0001", _ENGLISH_OMITTED_PARAGRAPH, "omitted"),
        ("p0002", russian, "accepted"),
    )
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=f"{_ENGLISH_OMITTED_PARAGRAPH}\n\nWhy should capital be mobilised at all?",
        target_text_with_markers=(
            f"[[DOCX_PARA_p0001]]\n{_ENGLISH_OMITTED_PARAGRAPH}\n\n"
            "[[DOCX_PARA_p0002]]\nWhy should capital be mobilised at all?"
        ),
        paragraph_ids=["p0001", "p0002"],
        narration_include=True,
        target_chars=160,
        context_chars=0,
    )

    outcome, state, _classifier_calls = _run_single_block(
        payload=payload,
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=processed_chunk,
        # The classification the substituted English source itself provokes.
        classification="english_residual_output",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None
    # The DOCX keeps every paragraph; the narration keeps only the spoken one.
    assert state.processed_chunks == [f"{_ENGLISH_OMITTED_PARAGRAPH}\n\n{russian}"]
    # ANTI-VACUUM: the accepted Russian neighbour is still narrated. A rule that subtracts
    # must be shown not to subtract everything.
    assert state.narration_chunks == [russian]
    assert _ENGLISH_OMITTED_PARAGRAPH not in "\n".join(state.narration_chunks)
    # The loss is counted in CHARACTERS, the unit spec 054's metric is expressed in.
    assert state.narration_excluded_omitted_paragraph_count == 1
    assert state.narration_excluded_omitted_chars == len(_ENGLISH_OMITTED_PARAGRAPH)
    # This is not the block-level exclusion; the two answer different questions.
    assert state.narration_excluded_source_fallback_block_count == 0


def test_controlled_fallback_with_no_omitted_paragraph_narrates_the_whole_block(monkeypatch) -> None:
    """ANTI-VACUUM for the filter on this path: nothing else stops being narrated."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    processed_chunk = _disposition_block(
        ("p0001", "Первый абзац переведён.", "accepted"),
        ("p0002", "Второй абзац переведён.", "accepted"),
    )
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text="First paragraph.\n\nSecond paragraph.",
        target_text_with_markers="[[DOCX_PARA_p0001]]\nFirst paragraph.\n\n[[DOCX_PARA_p0002]]\nSecond paragraph.",
        paragraph_ids=["p0001", "p0002"],
        narration_include=True,
        target_chars=40,
        context_chars=0,
    )

    _outcome, state, _classifier_calls = _run_single_block(
        payload=payload,
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=processed_chunk,
        classification="english_residual_output",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert state.narration_chunks == ["Первый абзац переведён.\n\nВторой абзац переведён."]
    assert state.narration_excluded_omitted_paragraph_count == 0
    assert state.narration_excluded_omitted_chars == 0


def test_the_happy_path_counts_the_characters_it_withholds(monkeypatch) -> None:
    """The counters must be fed from BOTH narration call sites, not only the fallback one."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    processed_chunk = _disposition_block(
        ("p0001", "Переведённый абзац.", "accepted"),
        ("p0002", _ENGLISH_OMITTED_PARAGRAPH, "omitted"),
    )
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=f"Source paragraph.\n\n{_ENGLISH_OMITTED_PARAGRAPH}",
        target_text_with_markers=(
            f"[[DOCX_PARA_p0001]]\nSource paragraph.\n\n[[DOCX_PARA_p0002]]\n{_ENGLISH_OMITTED_PARAGRAPH}"
        ),
        paragraph_ids=["p0001", "p0002"],
        narration_include=True,
        target_chars=120,
        context_chars=0,
    )

    _outcome, state, _classifier_calls = _run_single_block(
        payload=payload,
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=processed_chunk,
        classification="valid",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert state.narration_chunks == ["Переведённый абзац."]
    assert state.narration_excluded_omitted_paragraph_count == 1
    assert state.narration_excluded_omitted_chars == len(_ENGLISH_OMITTED_PARAGRAPH)


# --- run-level accounting for the pipeline half of the loss -------------------------
#
# ``CONTROLLED_BLOCK_FAILURE_POLICY`` splits block failures into two decisions, and until
# these counters existed only one half was countable. ``fallback_continue`` wrote a
# per-block diagnostic under ``.run/`` and a log line, neither of which a run report adds
# up: the names ``english_residual_output``, ``heading_only_output`` and ``toc_body_concat``
# appear nowhere in ``artifacts/``, not once, across five recorded runs. So the run-level
# ``model_output_discarded_*`` numbers — fed only by the generator — were a lower bound that
# nothing labelled as one.


def _fallback_block(
    *,
    classification: str,
    processed_chunk: str,
    target_text: str = _ENGLISH_SOURCE_BLOCK,
    monkeypatch,
):
    """Push ONE block through ``process_single_block`` with the given classifier verdict."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    return _run_single_block(
        payload=_llm_payload(target_text=target_text),
        context=SimpleNamespace(
            processing_operation="audiobook",
            uploaded_filename="book.docx",
            runtime=object(),
            on_progress=lambda **_kwargs: None,
        ),
        processed_chunk=processed_chunk,
        classification=classification,
        dependencies=dependencies,
        emitters=emitters,
    )


def test_controlled_fallbacks_are_counted_per_kind_and_in_characters(monkeypatch) -> None:
    """One number would not answer the question: WHICH of the seven kinds, and how much text.

    Two blocks of two different kinds, and the two kinds must stay apart — a single total
    cannot tell a heading that replaced a page from a page that came back untranslated.
    Characters follow the DELIVERED text because that volume is the price of the defect.
    """
    from docxaicorrector.core import model_accounting

    heading_output = "## Глава третья"

    with model_accounting.run_model_accounting_scope(run_id="run-1", source_token="token-1") as ledger:
        _fallback_block(
            classification="source_text_fallback",
            processed_chunk=_ENGLISH_SOURCE_BLOCK,
            monkeypatch=monkeypatch,
        )
        _fallback_block(
            classification="heading_only_output",
            processed_chunk=heading_output,
            monkeypatch=monkeypatch,
        )
        snapshot = ledger.snapshot()

    assert snapshot["controlled_block_fallback_kind_counts"] == {
        "heading_only_output": 1,
        "source_text_fallback": 1,
    }
    assert snapshot["controlled_block_fallback_kind_chars"] == {
        "heading_only_output": len(heading_output),
        "source_text_fallback": len(_ENGLISH_SOURCE_BLOCK),
    }
    # The totals are the sums of the breakdown, so a reader can check the report's arithmetic.
    assert snapshot["controlled_block_fallback_block_count"] == 2
    assert snapshot["controlled_block_fallback_chars"] == len(_ENGLISH_SOURCE_BLOCK) + len(heading_output)
    # The generator's family is a DIFFERENT verdict on the same block and must not move:
    # nothing here ran the generator, so folding the two would have shown phantom discards.
    assert snapshot["model_output_discarded_block_count"] == 0
    assert snapshot["model_output_discarded_reason_counts"] == {}


def test_the_counted_kind_and_length_are_the_ones_actually_delivered(monkeypatch) -> None:
    """``empty`` delivers the block's SOURCE text under the name ``empty_processed_block``.

    Both halves matter: the kind recorded is the policy table's ``fallback_kind``, not the
    classifier's verdict, and the characters are the substituted text's — counting the empty
    model output would have reported this loss as zero, which is the vacuum this guards.
    """
    from docxaicorrector.core import model_accounting

    with model_accounting.run_model_accounting_scope(run_id="run-2", source_token="token-2") as ledger:
        _fallback_block(classification="empty", processed_chunk="", monkeypatch=monkeypatch)
        snapshot = ledger.snapshot()

    assert snapshot["controlled_block_fallback_kind_counts"] == {"empty_processed_block": 1}
    assert snapshot["controlled_block_fallback_chars"] == len(_ENGLISH_SOURCE_BLOCK)


def test_an_accepted_block_leaves_the_fallback_counters_alone(monkeypatch) -> None:
    """ANTI-VACUUM. A counter that is never zero measures nothing either."""
    from docxaicorrector.core import model_accounting

    with model_accounting.run_model_accounting_scope(run_id="run-3", source_token="token-3") as ledger:
        _fallback_block(
            classification="valid",
            processed_chunk="Нынешнюю денежную систему почти все воспринимают как данность.",
            monkeypatch=monkeypatch,
        )
        snapshot = ledger.snapshot()

    assert snapshot["controlled_block_fallback_block_count"] == 0
    assert snapshot["controlled_block_fallback_chars"] == 0
    # Empty mappings beside zero totals, not absent keys: "no block took this path" is an
    # assertion the run report states, the same shape the discard family uses.
    assert snapshot["controlled_block_fallback_kind_counts"] == {}
    assert snapshot["controlled_block_fallback_kind_chars"] == {}


def test_a_structural_failure_is_not_a_controlled_fallback(monkeypatch) -> None:
    """ANTI-VACUUM, the other side: the table's OTHER decision must stay out.

    ``corrupted_block`` is one of the ten structural failures whose decision is ``fail`` —
    the run stops, no source is substituted, and nothing is delivered. Counting it here
    would inflate a measure of DELIVERED untranslated text with runs that delivered nothing.
    """
    from docxaicorrector.core import model_accounting

    with model_accounting.run_model_accounting_scope(run_id="run-4", source_token="token-4") as ledger:
        _outcome, state, _classifier_calls = _fallback_block(
            classification="corrupted_block",
            processed_chunk="какой-то повреждённый вывод",
            monkeypatch=monkeypatch,
        )
        snapshot = ledger.snapshot()

    assert state.processed_chunks == []  # the fallback path was not taken
    assert snapshot["controlled_block_fallback_block_count"] == 0
    assert snapshot["controlled_block_fallback_kind_counts"] == {}


def test_the_run_report_prints_the_pipeline_counters_beside_the_generator_ones() -> None:
    """The counters have to reach a human, and ``run_summary.txt`` is where he reads them."""
    import importlib.util
    from pathlib import Path

    harness_path = (
        Path(__file__).resolve().parent / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    )
    spec = importlib.util.spec_from_file_location("run_lietaer_validation_summary_probe", harness_path)
    assert spec is not None and spec.loader is not None
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    lines = harness._build_model_accounting_summary_lines(
        {
            "model_output_discarded_block_count": 2,
            "model_output_discarded_reason_counts": {"marker_validation_source_fallback": 2},
            "controlled_block_fallback_block_count": 2,
            "controlled_block_fallback_chars": 5581,
            "controlled_block_fallback_kind_counts": {"source_text_fallback": 2},
            "controlled_block_fallback_kind_chars": {"source_text_fallback": 5581},
        }
    )

    assert "model_accounting_controlled_block_fallback_block_count=2" in lines
    assert "model_accounting_controlled_block_fallback_chars=5581" in lines
    assert 'model_accounting_controlled_block_fallback_kind_counts={"source_text_fallback": 2}' in lines
    assert 'model_accounting_controlled_block_fallback_kind_chars={"source_text_fallback": 5581}' in lines
    # Beside, not instead of: the generator's half stays exactly where it was.
    assert "model_accounting_model_output_discarded_block_count=2" in lines


def test_a_record_that_no_longer_describes_its_text_is_refused_loudly() -> None:
    """rev41 P0-2, downstream half: a partial degradation must not pass as a whole one.

    A string operation that KEPT the subclass but changed the characters would leave every
    status attached to text it no longer belongs to, and the paragraph count would still
    match — the same silence that put source-language text into the narration under a green
    classification.
    """
    import pytest

    from docxaicorrector.generation._generation import MarkerPreservedBlockText, ParagraphDisposition

    desynchronised = MarkerPreservedBlockText(
        "Переведённый абзац.\n\nПодменённый текст.",
        [
            ParagraphDisposition(paragraph_id="p0001", text="Переведённый абзац.", status="accepted"),
            ParagraphDisposition(paragraph_id="p0002", text="14", status="omitted"),
        ],
    )

    with pytest.raises(RuntimeError) as exc_info:
        block_execution.build_processed_paragraph_registry_entries(
            block_index=7,
            paragraph_ids=["p0001", "p0002"],
            processed_chunk=desynchronised,
        )
    assert "paragraph_marker_registry_record_desynchronised" in str(exc_info.value)
