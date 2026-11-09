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

import pytest

import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.pipeline.block_execution import process_single_block
from docxaicorrector.pipeline.contracts import ProcessingState


def _make_state() -> ProcessingState:
    return ProcessingState(started_at=0.0)


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

    # Spec 059 A-I: the classifier now also takes the job's language pair, keyword-only.
    def classify_processed_block_fn(target_text: str, chunk: str, **_kwargs: object) -> str:
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


# --- spec 054 -> spec 070: what a controlled fallback does to the narration ---------------
#
# Until spec 070 a block whose model output was rejected and replaced by its own SOURCE text
# was kept out of the narration: the audiobook then translated, so the source was the wrong
# language (2026-08-04, Money & Sustainability: six such blocks, 20 597 characters of English
# in a Russian audiobook). Spec 070 made the audiobook a same-language pass (D-1) and removed
# the narration from ``translate``/``edit`` (FR-002), so research R7 turns the rule around:
# the audiobook NARRATES such a block from its own source, with ``needs_review``
# ``source_fallback`` on each narrated paragraph; ``translate``/``edit`` narrate nothing and
# keep their registry mark exactly as before.

_ENGLISH_SOURCE_BLOCK = (
    "Many tides ago, in a small hamlet by the old Saltmarsh, sailors used tallies for all their "
    "cargoes. On every harbour day, sailors walked around with nets, ropes, lamps and "
    "barrels, and engaged in prolonged bargaining among themselves to exchange what they "
    "needed for the coming voyage."
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


def _llm_payload(
    *,
    target_text: str,
    narration_include: bool = True,
    paragraph_regions: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=target_text,
        target_text_with_markers=f"[[DOCX_PARA_p0001]]{target_text}",
        paragraph_ids=["p0001"],
        # Spec 059 A-II. Defaults to APPARATUS, because every fixture in this module is about
        # the controlled-fallback mechanics themselves, and after FR-A8 a block of PROSE
        # delivered as its own source no longer takes that path at all — it fails the run.
        # Where a fixture wants the prose behaviour it says so.
        paragraph_regions=paragraph_regions if paragraph_regions is not None else ["back_matter"],
        narration_include=narration_include,
        target_chars=len(target_text),
        context_chars=0,
    )


def _audiobook_context() -> SimpleNamespace:
    return SimpleNamespace(
        processing_operation="audiobook",
        # Spec 070 FR-001: the audiobook knows no language pair; a pair left in the session by
        # another operation must not change anything, so the fixture leaves one in.
        source_language="en",
        target_language="ru",
        uploaded_filename="book.docx",
        runtime=object(),
        on_progress=lambda **_kwargs: None,
    )


def _texts(state: ProcessingState) -> dict[str, str]:
    return {record.paragraph_id: record.text for record in state.narration_paragraphs}


def _reasons(state: ProcessingState) -> dict[str, tuple[str, ...]]:
    return {record.paragraph_id: record.needs_review_reasons for record in state.narration_paragraphs}


def test_source_text_fallback_block_is_narrated_from_its_source_and_kept_in_the_docx(monkeypatch) -> None:
    """Spec 070 R7, rewritten from spec 054's exclusion: the audiobook narrates the fallback."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, events = _recording_run_harness()

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK),
        context=_audiobook_context(),
        # The controlled fallback delivers the block's own source text verbatim.
        processed_chunk=_ENGLISH_SOURCE_BLOCK,
        classification="source_text_fallback",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None  # the run continues; this is a controlled fallback, not a failure
    assert state.processed_chunks == [_ENGLISH_SOURCE_BLOCK]  # the DOCX keeps the source
    assert _texts(state) == {"p0001": _ENGLISH_SOURCE_BLOCK}  # ...and so does the narration
    assert _reasons(state) == {"p0001": ("source_fallback",)}
    assert state.narration_expected_paragraph_ids == ["p0001"]
    fallback_events = [context for event, context in events if event == "block_controlled_fallback"]
    assert len(fallback_events) == 1
    # Not a language-changing job: the spec 054 registry mark stays off.
    assert fallback_events[0]["narration_excluded_by_source_fallback"] is False


def test_translate_source_text_fallback_keeps_its_registry_mark_and_narrates_nothing(monkeypatch) -> None:
    """The translate side of the same fallback is unchanged: the mark is set, nothing is narrated."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, events = _recording_run_harness()
    context = _audiobook_context()
    context.processing_operation = "translate"

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK),
        context=context,
        processed_chunk=_ENGLISH_SOURCE_BLOCK,
        classification="source_text_fallback",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None
    assert state.processed_chunks == [_ENGLISH_SOURCE_BLOCK]
    assert state.narration_paragraphs == []
    assert state.narration_expected_paragraph_ids == []
    fallback_events = [context for event, context in events if event == "block_controlled_fallback"]
    assert fallback_events[0]["narration_excluded_by_source_fallback"] is True


def test_an_audiobook_fallback_narrates_the_source_not_the_rejected_output(monkeypatch) -> None:
    """R7: the rejection means the model's text may have LOST something, so the narration and
    the DOCX take the paragraph's own source, whatever the rejected output looked like."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    model_output = "Компании постоянно сталкиваются с нехваткой персонала, отмечает cash flow отчёт."

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK),
        context=_audiobook_context(),
        processed_chunk=model_output,
        classification="english_residual_output",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None
    assert _texts(state) == {"p0001": _ENGLISH_SOURCE_BLOCK}
    assert _reasons(state) == {"p0001": ("source_fallback",)}
    assert state.processed_chunks == [_ENGLISH_SOURCE_BLOCK]


def test_a_normal_block_still_reaches_the_narration() -> None:
    """Anti-vacuum, the plain case: an accepted block is narrated as answered, unmarked. The
    audiobook's input is already in the book's language; the answer only writes a year out."""
    source = "Нынешнюю денежную систему в 2007 году почти все воспринимали как нечто само собой разумеющееся."
    russian = "Нынешнюю денежную систему в две тысячи седьмом году почти все воспринимали как нечто само собой разумеющееся."

    outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=source),
        context=_audiobook_context(),
        processed_chunk=russian,
    )

    assert outcome is None
    assert state.processed_chunks == [russian]
    assert _texts(state) == {"p0001": russian}
    assert _reasons(state) == {"p0001": ()}


def test_a_block_the_document_layer_keeps_out_is_not_narrated(monkeypatch) -> None:
    """``narration_include=False`` without per-paragraph reasons (a producer before spec 070):
    nothing of the block is narrated or counted in the denominator, and the fallback still ships."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()

    _outcome, state, _classifier_calls = _run_single_block(
        payload=_llm_payload(target_text=_ENGLISH_SOURCE_BLOCK, narration_include=False),
        context=_audiobook_context(),
        processed_chunk=_ENGLISH_SOURCE_BLOCK,
        classification="source_text_fallback",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert state.processed_chunks == [_ENGLISH_SOURCE_BLOCK]
    assert state.narration_paragraphs == []
    assert state.narration_expected_paragraph_ids == []

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


# --- spec 056 E / 061 -> spec 070: an omitted or restored paragraph -------------------------
#
# Until spec 070 the narration WITHHELD a paragraph the model returned nothing for
# (``omitted``) on every operation, and a ``source_restored`` one in a language-changing
# operation, because its text is the paragraph's SOURCE. The audiobook no longer changes the
# language, so that source is the right text: it is narrated, with ``needs_review`` and the
# paragraph's address (research R7, Edge Cases). ``translate`` and ``edit`` narrate nothing;
# their DOCX keeps every paragraph exactly as before.


def _omitted_block():
    return _disposition_block(
        ("p1335", "Как нам справиться с безработицей?", "accepted"),
        ("p1336", "Что мешает начать прямо сейчас", "omitted"),
        ("p1337", "Почему бы не задействовать фонд?", "accepted"),
    )


def _omitted_payload() -> SimpleNamespace:
    texts = ("How do we deal with unemployment?", "Что мешает начать прямо сейчас", "Why not use the fund?")
    return SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text="\n\n".join(texts),
        target_text_with_markers="\n\n".join(
            f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(("p1335", "p1336", "p1337"), texts)
        ),
        paragraph_ids=["p1335", "p1336", "p1337"],
        narration_include=True,
        target_chars=sum(len(text) for text in texts),
        context_chars=0,
    )


def test_an_omitted_paragraph_is_narrated_from_its_source_in_the_audiobook(monkeypatch) -> None:
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()

    _outcome, state, _classifier_calls = _run_single_block(
        payload=_omitted_payload(),
        context=_audiobook_context(),
        processed_chunk=_omitted_block(),
        dependencies=dependencies,
        emitters=emitters,
    )

    # The DOCX keeps every paragraph; the narration keeps them too, the empty answer addressed.
    assert state.processed_chunks == [
        "Как нам справиться с безработицей?\n\nЧто мешает начать прямо сейчас\n\nПочему бы не задействовать фонд?"
    ]
    assert list(_texts(state)) == ["p1335", "p1336", "p1337"]
    assert _texts(state)["p1336"] == "Что мешает начать прямо сейчас"
    assert _reasons(state) == {"p1335": (), "p1336": ("empty_answer",), "p1337": ()}
    # The denominator is the three narrated ids, whatever the model answered.
    assert state.narration_expected_paragraph_ids == ["p1335", "p1336", "p1337"]


@pytest.mark.parametrize("operation", ["edit", "translate"])
def test_translate_and_edit_keep_an_omitted_paragraph_in_the_docx_and_narrate_nothing(operation: str) -> None:
    context = _audiobook_context()
    context.processing_operation = operation

    _outcome, state, _classifier_calls = _run_single_block(
        payload=_omitted_payload(), context=context, processed_chunk=_omitted_block()
    )

    assert state.processed_chunks == [_omitted_block()]
    assert state.narration_paragraphs == []
    assert state.narration_expected_paragraph_ids == []


_ENGLISH_OMITTED_PARAGRAPH = (
    "This chapter discusses ordinary market institutions and the mobilisation of capital."
)


def test_an_audiobook_fallback_narrates_every_paragraph_of_the_block_from_its_source(monkeypatch) -> None:
    """rev41 P0-1's fixture under R7: the block holding an ``omitted`` paragraph went down the
    controlled fallback. Every narrated paragraph is now its own source, marked
    ``source_fallback``; no paragraph is withheld and the denominator stays whole."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    dependencies, emitters, _events = _recording_run_harness()
    russian = "Почему вообще следует мобилизовать капитал?"
    processed_chunk = _disposition_block(
        ("p0001", _ENGLISH_OMITTED_PARAGRAPH, "omitted"),
        ("p0002", russian, "accepted"),
    )
    source_second = "Why should capital be mobilised at all?"
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=f"{_ENGLISH_OMITTED_PARAGRAPH}\n\n{source_second}",
        target_text_with_markers=(
            f"[[DOCX_PARA_p0001]]\n{_ENGLISH_OMITTED_PARAGRAPH}\n\n[[DOCX_PARA_p0002]]\n{source_second}"
        ),
        paragraph_ids=["p0001", "p0002"],
        narration_include=True,
        target_chars=160,
        context_chars=0,
    )

    outcome, state, _classifier_calls = _run_single_block(
        payload=payload,
        context=_audiobook_context(),
        processed_chunk=processed_chunk,
        classification="english_residual_output",
        dependencies=dependencies,
        emitters=emitters,
    )

    assert outcome is None
    assert _texts(state) == {"p0001": _ENGLISH_OMITTED_PARAGRAPH, "p0002": source_second}
    assert _reasons(state) == {"p0001": ("source_fallback",), "p0002": ("source_fallback",)}
    assert state.narration_expected_paragraph_ids == ["p0001", "p0002"]
    assert state.processed_chunks == [f"{_ENGLISH_OMITTED_PARAGRAPH}\n\n{source_second}"]


_ENGLISH_RESTORED_PARAGRAPH = (
    "See, for example, the grey ledger on options for steering a systemic port crisis."
)


def _run_restored_paragraph_block(*, operation: str, classification: str):
    dependencies, emitters, _events = _recording_run_harness()
    processed_chunk = _disposition_block(
        ("p0001", "Переведённый абзац.", "accepted"),
        ("p0002", _ENGLISH_RESTORED_PARAGRAPH, "source_restored"),
    )
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text=f"Source paragraph.\n\n{_ENGLISH_RESTORED_PARAGRAPH}",
        target_text_with_markers=(
            f"[[DOCX_PARA_p0001]]\nSource paragraph.\n\n[[DOCX_PARA_p0002]]\n{_ENGLISH_RESTORED_PARAGRAPH}"
        ),
        paragraph_ids=["p0001", "p0002"],
        narration_include=True,
        target_chars=120,
        context_chars=0,
    )
    context = _audiobook_context()
    context.processing_operation = operation
    _outcome, state, _classifier_calls = _run_single_block(
        payload=payload,
        context=context,
        processed_chunk=processed_chunk,
        classification=classification,
        dependencies=dependencies,
        emitters=emitters,
    )
    return state


def test_a_restored_paragraph_is_narrated_and_addressed_in_the_audiobook(monkeypatch) -> None:
    """Spec 061 FR-006 withheld it as source-language text; under R7 it is the book's own text."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)

    state = _run_restored_paragraph_block(operation="audiobook", classification="valid")

    assert state.processed_chunks == [f"Переведённый абзац.\n\n{_ENGLISH_RESTORED_PARAGRAPH}"]
    assert _texts(state) == {"p0001": "Переведённый абзац.", "p0002": _ENGLISH_RESTORED_PARAGRAPH}
    assert _reasons(state) == {"p0001": (), "p0002": ("source_restored",)}


def test_a_restored_paragraph_in_a_rejected_audiobook_block_is_a_source_fallback(monkeypatch) -> None:
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)

    state = _run_restored_paragraph_block(operation="audiobook", classification="english_residual_output")

    assert _texts(state) == {"p0001": "Source paragraph.", "p0002": _ENGLISH_RESTORED_PARAGRAPH}
    assert _reasons(state) == {"p0001": ("source_fallback",), "p0002": ("source_fallback",)}


@pytest.mark.parametrize("classification", ["valid", "english_residual_output"])
@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_a_restored_paragraph_stays_in_the_docx_and_nothing_is_narrated(
    monkeypatch, operation: str, classification: str
) -> None:
    """``translate``/``edit``: the DOCX is the one of before; no narration state is written."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)

    state = _run_restored_paragraph_block(operation=operation, classification=classification)

    assert state.processed_chunks == [f"Переведённый абзац.\n\n{_ENGLISH_RESTORED_PARAGRAPH}"]
    assert state.narration_paragraphs == []
    assert state.narration_exclusions == []


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
            # Spec 059 FR-A5: the pair rule only means "untranslated" where the JOB
            # changes language, so every fixture that exercises it has to say so.
            source_language="en",
            target_language="ru",
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
