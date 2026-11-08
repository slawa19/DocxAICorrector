"""Spec 063 FR-005 / FR-006: a footnote reference the import recognised survives the model.

Unit tests of ``pipeline/footnote_markers.py``, its wiring into ``process_single_block`` and
its run counters, plus an opt-in replay over the recorded 2026-11-07 translate runs.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from docxaicorrector.core.model_accounting import run_model_accounting_scope, snapshot_run_model_accounting
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    PARAGRAPH_STATUS_OMITTED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
    marker_paragraph_dispositions,
)
from docxaicorrector.pipeline.block_execution import (
    build_processed_paragraph_registry_entries,
    process_single_block,
)
from docxaicorrector.pipeline.footnote_markers import (
    PLACEMENT_CONVERTED,
    PLACEMENT_PARAGRAPH_END,
    PLACEMENT_SENTENCE,
    preserve_footnote_markers_for_block,
    restore_block_footnote_markers,
    restore_lost_footnote_markers,
    superscript_markers,
)

# The form of Rethinking Money p0163 (pair idx 137 of the 2026-11-07 run), in synthetic text:
# four sentences, references after the second and the third, an abbreviation "U.S." and
# money amounts inside them. The model dropped both references.
_RM_P0163_SOURCE = (
    "Sailors owe more on harbour tolls than on lantern oil. The sum of unpaid "
    "harbour tolls has passed $1 trillion, a first in living memory.¹² The average "
    "U.S. river pilot now carries over $25,000 of debt at retirement.¹³ With this toll "
    "load, a young sailor is forced into finding longer-distance work."
)
_RM_P0163_TRANSLATION = (
    "Моряки должны по портовым сборам больше, чем по лампадному маслу. Общая "
    "сумма непогашенных портовых сборов впервые на памяти превысила 1 триллион "
    "долларов. Среднестатистический американский речной лоцман к моменту выхода на пенсию имеет "
    "долг более 25 000 долларов. С такой нагрузкой по сборам молодой моряк вынужден искать "
    "работу на дальних рейсах."
)


def test_rm_p0163_both_lost_references_return_to_their_sentences() -> None:
    outcome = restore_lost_footnote_markers(_RM_P0163_SOURCE, _RM_P0163_TRANSLATION)

    assert outcome.restored_markers == ("¹²", "¹³")
    assert outcome.placement == PLACEMENT_SENTENCE
    assert "превысила 1 триллион долларов.¹² Среднестатистический" in outcome.text
    assert "долг более 25 000 долларов.¹³ С такой" in outcome.text
    assert outcome.source_marker_count == 2
    assert outcome.kept_marker_count == 0


def test_paragraph_without_references_is_returned_unchanged() -> None:
    # Anti-vacuum: no glyph in the source, nothing to compare and nothing touched.
    translation = "Перевод без ссылок. Вторая фраза."

    outcome = restore_lost_footnote_markers("A source with no references. Another.", translation)

    assert outcome.text is translation
    assert outcome.restored_markers == ()
    assert outcome.source_marker_count == 0


def test_superscript_the_translation_introduced_is_not_a_loss() -> None:
    # "м²" for "m2": a superscript that was never in the source is not compared at all.
    translation = "Площадь — 40 м². Цена растёт."

    outcome = restore_lost_footnote_markers("The area is 40 m2. The price rises.", translation)

    assert outcome.text is translation
    assert outcome.restored_markers == ()


def test_kept_references_leave_the_paragraph_unchanged() -> None:
    translation = "Первая фраза.¹² Вторая фраза.¹³"

    outcome = restore_lost_footnote_markers("First one.¹² Second one.¹³", translation)

    assert outcome.text is translation
    assert outcome.kept_marker_count == 2
    assert outcome.restored_markers == ()


def test_reference_moved_to_another_sentence_is_not_restored_twice() -> None:
    # A multiset comparison: the reference is in the paragraph, just not where it was.
    translation = "Первая фраза. Вторая фраза.¹²"

    outcome = restore_lost_footnote_markers("First one.¹² Second one.", translation)

    assert outcome.text is translation
    assert outcome.restored_markers == ()


def test_different_sentence_count_sends_the_reference_to_the_paragraph_end() -> None:
    # The model joined two sentences: no ordinal to trust, so the paragraph end.
    outcome = restore_lost_footnote_markers(
        "First one.¹² Second one. Third one.",
        "Первая и вторая фразы вместе. Третья фраза.",
    )

    assert outcome.placement == PLACEMENT_PARAGRAPH_END
    assert outcome.text == "Первая и вторая фразы вместе. Третья фраза.¹²"


def test_reference_kept_in_plain_digits_is_turned_back_into_the_glyph() -> None:
    # Money and Sustainability p0458: the model KEPT the reference but wrote "»34.".
    # Inserting a glyph would print the reference twice.
    outcome = restore_lost_footnote_markers(
        "…renegotiations of their harbour charters.”³⁴ There are no historical precedents.",
        "…пересмотреть свои портовые уставы»34. В истории нет прецедентов.",
    )

    assert outcome.placement == PLACEMENT_CONVERTED
    assert outcome.text == "…пересмотреть свои портовые уставы»³⁴. В истории нет прецедентов."
    assert outcome.restored_markers == ("³⁴",)


def test_ordinary_number_equal_to_the_reference_is_not_converted() -> None:
    # Anti-vacuum: "34 страны" is a number after a space, not a welded reference — the
    # reference is inserted at its sentence end and the number stays.
    outcome = restore_lost_footnote_markers(
        "Thirty-four countries signed.³⁴ Others did not.",
        "Подписали 34 страны. Остальные — нет.",
    )

    assert outcome.text == "Подписали 34 страны.³⁴ Остальные — нет."
    assert outcome.placement == PLACEMENT_SENTENCE


@pytest.mark.parametrize(
    ("source", "translation", "expected"),
    [
        # Codex acceptance finding 2: the source wrote the number in words, so the
        # source-side spelling guard cannot see it; the translation's digits are a time.
        (
            "At twelve thirty-six the train left.³⁶",
            "Поезд отправился в 12:36.",
            "Поезд отправился в 12:36.³⁶",
        ),
        # A decimal comma the translation turned into a point.
        ("Le prix est 2,36 euros.³⁶", "The price is 2.36 euros.", "The price is 2.36 euros.³⁶"),
        ("See volume 3.14 of the series.¹⁴", "См. том 3.14 серии.", "См. том 3.14 серии.¹⁴"),
    ],
)
def test_digits_after_a_separator_that_follows_a_digit_are_a_number_not_a_reference(
    source: str, translation: str, expected: str
) -> None:
    outcome = restore_lost_footnote_markers(source, translation)

    assert outcome.placement == PLACEMENT_SENTENCE
    assert outcome.text == expected


def test_reference_welded_to_a_period_after_a_word_is_still_converted() -> None:
    # Anti-vacuum for the guard above: the separator follows a LETTER, so the digits are
    # the model's plain-digit copy of the reference.
    outcome = restore_lost_footnote_markers(
        "It rose to £30,000, well above average earnings.³⁹ Nobody noticed.",
        "Она выросла до 30 000 фунтов, намного выше средних доходов.39 Никто не заметил.",
    )

    assert outcome.placement == PLACEMENT_CONVERTED
    assert outcome.text == "Она выросла до 30 000 фунтов, намного выше средних доходов.³⁹ Никто не заметил."


def test_abbreviation_does_not_count_as_a_sentence_end() -> None:
    # "U.S. river" stays one sentence; otherwise the counts differ and the reference
    # would fall to the paragraph end.
    outcome = restore_lost_footnote_markers(
        "The average U.S. river pilot owes money.¹³ This is new.",
        "Средний лоцман в США должен деньги. Это новое явление.",
    )

    assert outcome.text == "Средний лоцман в США должен деньги.¹³ Это новое явление."


def test_restored_reference_next_to_a_kept_one_stays_a_separate_reference() -> None:
    outcome = restore_lost_footnote_markers("Only one sentence.¹²,¹³", "Одна фраза.¹²")

    assert superscript_markers(outcome.text) == ["¹²", "¹³"]


def _marker_block(*dispositions: ParagraphDisposition) -> MarkerPreservedBlockText:
    return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


_SOURCE_WITH_MARKERS = (
    "[[DOCX_PARA_p1]]\nFirst sentence.¹ Second sentence.\n\n"
    "[[DOCX_PARA_p2]]\nNo references here.\n\n"
    "[[DOCX_PARA_p3]]\nOmitted paragraph.²"
)


def test_block_restoration_keeps_the_per_paragraph_record_in_step() -> None:
    chunk = _marker_block(
        ParagraphDisposition("p1", "Первая фраза. Вторая фраза.", PARAGRAPH_STATUS_ACCEPTED),
        ParagraphDisposition("p2", "Здесь ссылок нет.", PARAGRAPH_STATUS_ACCEPTED),
        ParagraphDisposition("p3", "Omitted paragraph.²", PARAGRAPH_STATUS_OMITTED),
    )

    outcome = restore_block_footnote_markers(
        chunk, source_text_with_markers=_SOURCE_WITH_MARKERS, paragraph_ids=["p1", "p2", "p3"]
    )

    dispositions = marker_paragraph_dispositions(outcome.processed_chunk)
    assert dispositions is not None
    assert [item.text for item in dispositions] == [
        "Первая фраза.¹ Вторая фраза.",
        "Здесь ссылок нет.",
        "Omitted paragraph.²",
    ]
    assert [item.status for item in dispositions] == [
        PARAGRAPH_STATUS_ACCEPTED,
        PARAGRAPH_STATUS_ACCEPTED,
        PARAGRAPH_STATUS_OMITTED,
    ]
    # The registry builder raises if text and record disagree; it must not.
    entries = build_processed_paragraph_registry_entries(
        block_index=1, paragraph_ids=["p1", "p2", "p3"], processed_chunk=outcome.processed_chunk
    )
    assert entries[0]["text"] == "Первая фраза.¹ Вторая фраза."
    # Only accepted paragraphs are the model's text to repair and to count.
    assert outcome.source_marker_count == 1
    assert outcome.restored_marker_count == 1


def test_block_without_a_loss_is_returned_as_the_same_object() -> None:
    chunk = _marker_block(
        ParagraphDisposition("p1", "Первая фраза.¹ Вторая фраза.", PARAGRAPH_STATUS_ACCEPTED),
        ParagraphDisposition("p2", "Здесь ссылок нет.", PARAGRAPH_STATUS_ACCEPTED),
        ParagraphDisposition("p3", "Omitted paragraph.²", PARAGRAPH_STATUS_OMITTED),
    )

    outcome = restore_block_footnote_markers(
        chunk, source_text_with_markers=_SOURCE_WITH_MARKERS, paragraph_ids=["p1", "p2", "p3"]
    )

    assert outcome.processed_chunk is chunk


def test_plain_string_block_is_left_alone() -> None:
    # No per-paragraph record, no paragraph to compare against.
    outcome = restore_block_footnote_markers(
        "Первая фраза. Вторая фраза.",
        source_text_with_markers="[[DOCX_PARA_p1]]\nFirst sentence.¹ Second sentence.",
        paragraph_ids=["p1"],
    )

    assert outcome.processed_chunk == "Первая фраза. Вторая фраза."
    assert outcome.paragraphs == ()


def _payload() -> SimpleNamespace:
    return SimpleNamespace(
        paragraph_ids=["p1", "p2", "p3"], target_text_with_markers=_SOURCE_WITH_MARKERS
    )


def _lossy_block() -> MarkerPreservedBlockText:
    return _marker_block(
        ParagraphDisposition("p1", "Первая фраза. Вторая фраза.", PARAGRAPH_STATUS_ACCEPTED),
        ParagraphDisposition("p2", "Здесь ссылок нет.", PARAGRAPH_STATUS_ACCEPTED),
        ParagraphDisposition("p3", "Omitted paragraph.²", PARAGRAPH_STATUS_OMITTED),
    )


def test_pipeline_entry_point_counts_and_names_the_paragraph() -> None:
    events: list[tuple[int, str, dict[str, object]]] = []

    def log_event(level: int, event_id: str, _message: str, **context: object) -> None:
        events.append((level, event_id, context))

    with run_model_accounting_scope(run_id="run", source_token="src"):
        result = preserve_footnote_markers_for_block(
            processed_chunk=_lossy_block(),
            payload=_payload(),
            processing_operation="translate",
            block_index=7,
            log_event=log_event,
        )
        snapshot = snapshot_run_model_accounting()

    assert result.startswith("Первая фраза.¹ Вторая фраза.")
    assert snapshot["footnote_marker_source_count"] == 1
    assert snapshot["footnote_marker_kept_count"] == 0
    assert snapshot["footnote_marker_restored_count"] == 1
    assert snapshot["footnote_marker_delivered_count"] == 1
    assert [(level, event_id) for level, event_id, _ in events] == [
        (logging.WARNING, "footnote_markers_restored")
    ]
    assert events[0][2]["paragraph_id"] == "p1"
    assert events[0][2]["block_index"] == 7
    assert events[0][2]["restored_markers"] == ["¹"]


def test_narration_operation_is_never_touched() -> None:
    # The audiobook prompt orders footnote markers REMOVED (operation_audiobook.txt, rule 1).
    chunk = _lossy_block()

    with run_model_accounting_scope(run_id="run", source_token="src"):
        result = preserve_footnote_markers_for_block(
            processed_chunk=chunk,
            payload=_payload(),
            processing_operation="audiobook",
            block_index=1,
            log_event=None,
        )
        snapshot = snapshot_run_model_accounting()

    assert result is chunk
    assert snapshot["footnote_marker_source_count"] == 0


def test_process_single_block_commits_the_restored_text() -> None:
    """The hook sits before the block is committed: what lands in ``processed_chunks`` — the
    preview and, through the registry built from the same value, the DOCX — carries it."""
    state = SimpleNamespace(
        processed_chunks=[],
        narration_chunks=[],
        excluded_narration_block_count=0,
        generated_paragraph_registry=[],
        started_at=0.0,
    )
    payload = SimpleNamespace(
        job_kind="llm",
        toc_dominant=False,
        target_text="First sentence.¹ Second sentence.\n\nNo references here.\n\nOmitted paragraph.²",
        target_text_with_markers=_SOURCE_WITH_MARKERS,
        narration_include=False,
        paragraph_ids=["p1", "p2", "p3"],
    )
    registered: list[str] = []

    def append_marker_registry_entries_fn(*, processed_chunk: str, **_kwargs: object) -> None:
        registered.append(processed_chunk)

    def _no_op(**_kwargs: object) -> None:
        return None

    outcome = process_single_block(
        context=SimpleNamespace(processing_operation="translate"),
        dependencies=SimpleNamespace(),
        emitters=SimpleNamespace(),
        state=state,
        initialization=SimpleNamespace(job_count=1),
        index=1,
        job=object(),
        parse_processing_job_fn=lambda *, job: payload,
        handle_invalid_processing_job_fn=_no_op,
        emit_block_started_fn=_no_op,
        is_marker_mode_enabled_fn=lambda _context, _payload: True,
        execute_processing_block_fn=lambda **_kwargs: (_lossy_block(), True),
        handle_block_generation_failure_fn=_no_op,
        classify_processed_block_fn=lambda *_args, **_kwargs: "valid",
        handle_processed_block_rejection_fn=_no_op,
        append_marker_registry_entries_fn=append_marker_registry_entries_fn,
        handle_marker_registry_failure_fn=_no_op,
        emit_block_completed_fn=_no_op,
    )

    assert outcome is None
    assert state.processed_chunks[0].startswith("Первая фраза.¹ Вторая фраза.")
    assert registered == [state.processed_chunks[0]]
    assert marker_paragraph_dispositions(registered[0]) is not None


# --- Opt-in replay over the recorded 2026-11-07 translate runs ---------------------------
#
# Evidence, not a CI test: the runs live OUTSIDE the repository. Point
# ``DOCXAI_TRANSLATE_REPLAY_ROOT`` at the directory holding ``<book>/pairs.jsonl`` (the same
# variable the spec 063 P0 replay uses); without it, or with a book missing, the test skips.
#
# On every accepted, non-fallback pair the model's own translation is fed to the production
# check. Measured 2026-11-07: of 215/152/214/252 references in the sources the model lost
# 8/5/22/26, and every one is restored — 11 of them (all 8 on Money) by turning the model's
# plain-digit copy back into the glyph, the rest at their sentence end or the paragraph end.
_TRANSLATE_REPLAY_ROOT_ENV = "DOCXAI_TRANSLATE_REPLAY_ROOT"
_TRANSLATE_REPLAY_ROOT = os.environ.get(_TRANSLATE_REPLAY_ROOT_ENV, "").strip()
# (book directory, references in the source, lost by the model)
_TRANSLATE_REPLAY_BOOKS = [
    ("money_sustainability", 215, 8),
    ("creating_wealth", 152, 5),
    ("rethinking_money", 214, 22),
    ("value_of_everything", 252, 26),
]


@pytest.mark.skipif(
    not _TRANSLATE_REPLAY_ROOT,
    reason=f"Set {_TRANSLATE_REPLAY_ROOT_ENV} to the recorded translate-run directory to replay FR-005.",
)
@pytest.mark.parametrize(
    ("book", "source_count", "lost_count"),
    _TRANSLATE_REPLAY_BOOKS,
    ids=[book[0] for book in _TRANSLATE_REPLAY_BOOKS],
)
def test_footnote_marker_restoration_replay_on_recorded_translate_runs(
    book: str, source_count: int, lost_count: int
) -> None:
    pairs_path = Path(_TRANSLATE_REPLAY_ROOT) / book / "pairs.jsonl"
    if not pairs_path.is_file():
        pytest.skip(f"{pairs_path} is absent")
    source = kept = restored = 0
    for line in pairs_path.read_text(encoding="utf-8").splitlines():
        pair = json.loads(line)
        if (
            pair.get("paragraph_status") != PARAGRAPH_STATUS_ACCEPTED
            or pair.get("controlled_fallback")
            or not pair.get("target_text")
        ):
            continue
        outcome = restore_lost_footnote_markers(pair["source_text"], pair["target_text"])
        source += outcome.source_marker_count
        kept += outcome.kept_marker_count
        restored += len(outcome.restored_markers)
        # Delivered = every source reference, and nothing was added beyond them.
        assert sorted(superscript_markers(outcome.text)) == sorted(
            superscript_markers(pair["target_text"]) + list(outcome.restored_markers)
        )
        if not outcome.restored_markers:
            assert outcome.text == pair["target_text"]
    print(f"{book}: source={source} kept={kept} restored={restored}")
    assert source == source_count
    assert source - kept == lost_count
    assert restored == lost_count
