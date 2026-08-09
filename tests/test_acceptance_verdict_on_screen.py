"""Spec 059 part B — the production acceptance verdict reaches the screen.

Until this spec the verdict was computed (``validation/acceptance.build_acceptance_verdict``),
serialized into ``quality_report["acceptance_verdict"]`` and written to
``.run/quality_reports/*.json`` — and stopped there: ``grep -rni acceptance
src/docxaicorrector/ui/`` returned nothing, in the code and in both locale catalogs.
Three of the four books of the recorded corpus fail acceptance and the screen said
"Документ обработан."

Every test here keys on DATA the pipeline computed — ``acceptance_verdict.passed``, the
per-paragraph disposition status of the DELIVERED block — never on a word from a book and
never on a threshold (Constitution VII).
"""

from __future__ import annotations

import ast
import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

import docxaicorrector.generation._generation as generation
import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.block_execution as block_execution
import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.pipeline.quality_gate as quality_gate
import docxaicorrector.ui._ui as ui
import docxaicorrector.validation.acceptance as acceptance
from conftest import SessionState as SessionState  # noqa: F811
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    PARAGRAPH_STATUS_OMITTED,
    PARAGRAPH_STATUS_SOURCE_RESTORED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
)
from docxaicorrector.validation.acceptance import (
    PRODUCTION_ACCEPTANCE_CHECK_NAMES,
    build_acceptance_verdict,
    production_reportable_failed_checks,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO_ROOT / "artifacts"


@pytest.fixture(autouse=True)
def _session_state_factory(make_session_state):
    globals()["SessionState"] = make_session_state


# --------------------------------------------------------------------------------------
# recorded-run baselines (Constitution IV/VIII: the numbers come from the committed runs)
# --------------------------------------------------------------------------------------


def _run_summary(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


GREEN_RUN_SUMMARY = ARTIFACTS / "audiobook_final_run" / "money_translate_docx" / "run_summary.txt"
FOUR_BOOK_RUN_DIR = ARTIFACTS / "audiobook_four_book_run"
FOUR_BOOK_NAMES = ("creating_wealth", "money_sustainability", "rethinking_money", "value_of_everything")


def _block(*dispositions: ParagraphDisposition) -> MarkerPreservedBlockText:
    return MarkerPreservedBlockText(
        "\n\n".join(disposition.text for disposition in dispositions), dispositions
    )


def _accepted(paragraph_id: str, text: str) -> ParagraphDisposition:
    return ParagraphDisposition(paragraph_id=paragraph_id, text=text, status=PARAGRAPH_STATUS_ACCEPTED)


def _restored(paragraph_id: str, text: str) -> ParagraphDisposition:
    return ParagraphDisposition(
        paragraph_id=paragraph_id, text=text, status=PARAGRAPH_STATUS_SOURCE_RESTORED
    )


def _omitted(paragraph_id: str, text: str) -> ParagraphDisposition:
    return ParagraphDisposition(paragraph_id=paragraph_id, text=text, status=PARAGRAPH_STATUS_OMITTED)


# --------------------------------------------------------------------------------------
# FR-B3 — the check names are a CLOSED enumeration owned by validation/acceptance.py
# --------------------------------------------------------------------------------------


def _production_verdict_over_a_rich_report() -> dict[str, object]:
    report = {
        "result": "succeeded",
        "runtime_config": {"effective": {"processing_operation": "translate"}},
        "translation_quality_report": {"quality_status": "pass", "gate_reasons": []},
        "formatting_diagnostics": [{"unmapped_source_ids": [], "caption_heading_conflicts": []}],
        "output_artifacts": {"output_docx_openable": True},
        "runtime": {},
        "reader_cleanup_evidence": {},
        "preparation_diagnostic_snapshot": {},
    }
    return build_acceptance_verdict(
        report,
        mismatch_threshold=3,
        unmapped_target_threshold=3,
        require_no_toc_body_concat=True,
        structural_checks_builder=None,
    )


def test_production_check_enumeration_is_closed_over_the_emitted_names() -> None:
    """The enumeration is a STRUCTURAL fact, not a hand-kept list that drifts."""
    verdict = _production_verdict_over_a_rich_report()
    emitted = {str(check["name"]) for check in verdict["checks"]}  # type: ignore[index]

    assert emitted == set(PRODUCTION_ACCEPTANCE_CHECK_NAMES)


def test_a_name_outside_the_enumeration_never_kills_the_run(monkeypatch) -> None:
    """The enumeration REPORTS; it must not gate.

    ``build_acceptance_verdict`` runs at FINALIZATION — ``late_phases`` builds it at
    ``:674``, ``:910`` and ``:1027``, and none of the three sits inside a ``try/except`` — so
    an exception raised here loses the book and the money already spent on it, on the very
    last stage. That is the delivery gate FR-B8 and Constitution VII forbid, in its worst
    form, because it destroys the artifact as well. The unknown name is logged and kept out
    of the reportable set instead.
    """
    events: list[dict[str, object]] = []

    def _log_event(level, event_id, message, **context):
        events.append({"level": level, "event_id": event_id, "context": context})
        return message

    monkeypatch.setattr(acceptance, "log_event", _log_event)
    # Shrink the declared enumeration so the verdict's own real names become "unknown".
    monkeypatch.setattr(
        acceptance, "_PRODUCTION_ACCEPTANCE_CHECK_NAME_SET", frozenset({"pipeline_succeeded"})
    )

    verdict = _production_verdict_over_a_rich_report()

    # 1. It did not raise, and the record stays complete — the roll-up is unchanged.
    assert {str(check["name"]) for check in verdict["checks"]} == set(  # type: ignore[index]
        PRODUCTION_ACCEPTANCE_CHECK_NAMES
    )
    # 2. Every unknown name was named in the log (Constitution V).
    outside = [
        event for event in events if event["event_id"] == "acceptance_check_outside_enumeration"
    ]
    assert {str(_context(event)["name"]) for event in outside} == set(
        PRODUCTION_ACCEPTANCE_CHECK_NAMES
    ) - {"pipeline_succeeded"}
    assert all(event["level"] == logging.WARNING for event in outside)
    # 3. And a name genuinely outside the enumeration still cannot reach the screen — the
    #    screen filter is what protects the user, not an exception at finalization.
    assert acceptance.production_reportable_failed_checks(
        {"failed_checks": ["a_check_nobody_declared", "pipeline_succeeded"]}
    ) == ["pipeline_succeeded"]


def test_a_known_enumeration_emits_no_warning(monkeypatch) -> None:
    """Anti-vacuum: a warning raised on every run is a warning nobody reads."""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        acceptance,
        "log_event",
        lambda level, event_id, message, **context: events.append({"event_id": event_id}),
    )

    _production_verdict_over_a_rich_report()

    assert not [
        event for event in events if event["event_id"] == "acceptance_check_outside_enumeration"
    ]


def test_harness_only_failed_checks_are_not_reportable() -> None:
    """``key_headings_preserved`` is a HARNESS check: production owns no source DOCX
    (``quality_gate.build_report_acceptance_verdict`` passes ``structural_checks_builder=None``),
    so a name production cannot evaluate must never reach the screen."""
    reportable = production_reportable_failed_checks(
        {
            "passed": False,
            "failed_checks": [
                "false_fragment_headings_present",
                "key_headings_preserved",
                "mixed_script_terms_present",
            ],
        }
    )

    assert reportable == ["false_fragment_headings_present", "mixed_script_terms_present"]


# --------------------------------------------------------------------------------------
# FR-B1 / FR-B2 — the verdict crosses the boundary as DATA, in EVERY mode
# --------------------------------------------------------------------------------------


def test_verdict_notice_is_silent_when_the_verdict_passed() -> None:
    notice = quality_gate.build_acceptance_verdict_notice(
        {"quality_status": "pass", "acceptance_verdict": {"passed": True, "failed_checks": []}}
    )

    assert notice is None


def test_verdict_notice_is_silent_when_there_is_no_verdict() -> None:
    assert quality_gate.build_acceptance_verdict_notice({"quality_status": "pass"}) is None


def test_verdict_notice_is_silent_when_every_failed_check_is_harness_only() -> None:
    """Anti-vacuum: a verdict red ONLY on a check production cannot evaluate has
    nothing production may say."""
    notice = quality_gate.build_acceptance_verdict_notice(
        {
            "quality_status": "pass",
            "acceptance_verdict": {"passed": False, "failed_checks": ["key_headings_preserved"]},
        }
    )

    assert notice is None


def test_verdict_notice_carries_failed_checks_as_data_with_a_pass_quality_status() -> None:
    """FR-B2: the trigger is ``acceptance_verdict.passed is False`` — NOT ``quality_status``
    and NOT ``gate_reasons``, both of which stay clean outside ``translate``."""
    notice = quality_gate.build_acceptance_verdict_notice(
        {
            "quality_status": "pass",
            "gate_reasons": [],
            "acceptance_verdict": {
                "passed": False,
                "failed_checks": ["false_fragment_headings_present", "mixed_script_terms_present"],
            },
        }
    )

    assert notice is not None
    assert notice["kind"] == "acceptance"
    assert notice["level"] == "warning"
    assert notice["message_key"] == "result.acceptance_not_passed"
    assert notice["failed_checks"] == [
        "false_fragment_headings_present",
        "mixed_script_terms_present",
    ]
    assert dict(notice["params"])["count"] == 2  # type: ignore[arg-type]


def test_recorded_green_run_maps_to_verdict_silence() -> None:
    """Anti-vacuum, direction 1 — ``money_translate_docx`` is the corpus' ONE green run."""
    summary = _run_summary(GREEN_RUN_SUMMARY)
    assert summary["acceptance_passed"] == "True"
    assert summary["acceptance_failed_checks"] == ""
    assert summary["translation_quality_false_fragment_heading_count"] == "0"
    assert summary["translation_quality_list_fragment_regression_count"] == "0"
    assert summary["translation_quality_mixed_script_term_count"] == "0"

    notice = quality_gate.build_acceptance_verdict_notice(
        {"acceptance_verdict": {"passed": True, "failed_checks": []}}
    )

    assert notice is None


@pytest.mark.parametrize("book", FOUR_BOOK_NAMES)
def test_recorded_red_books_map_to_verdict_speech(book: str) -> None:
    """Anti-vacuum, direction 2 — all four recorded books are red, and stay red once the
    harness-only ``key_headings_preserved`` is dropped."""
    summary = _run_summary(FOUR_BOOK_RUN_DIR / book / "run_summary.txt")
    assert summary["acceptance_passed"] == "False"
    # The gate is silent on every one of them: it lives under ``processing_operation ==
    # "translate"`` and these are audiobook runs.
    assert summary["translation_quality_status"] == "pass"
    assert summary["translation_quality_gate_reasons"] == ""
    failed = [name for name in summary["acceptance_failed_checks"].split(",") if name]
    assert "key_headings_preserved" in failed

    notice = quality_gate.build_acceptance_verdict_notice(
        {"quality_status": "pass", "acceptance_verdict": {"passed": False, "failed_checks": failed}}
    )

    assert notice is not None
    assert "key_headings_preserved" not in list(notice["failed_checks"])  # type: ignore[arg-type]
    assert list(notice["failed_checks"])  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# FR-B4 / FR-B5 — untranslated source text in the DOCX is a fact of its own, with anchors
# --------------------------------------------------------------------------------------


def test_source_text_delivery_is_silent_on_a_fully_accepted_block() -> None:
    facts = quality_gate.build_source_text_delivery_facts(
        [_block(_accepted("p1", "Первый абзац."), _accepted("p2", "Второй абзац."))]
    )

    assert facts["paragraph_count"] == 0
    assert facts["block_count"] == 0
    assert facts["chars"] == 0
    assert (
        quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
        is None
    )


def test_source_text_delivery_counts_blocks_paragraphs_and_chars_with_anchors() -> None:
    facts = quality_gate.build_source_text_delivery_facts(
        [
            _block(_accepted("p1", "Первый абзац.")),
            _block(
                _restored("p2", "Once upon a time in a small village."),
                _accepted("p3", "Третий абзац."),
            ),
        ]
    )

    assert facts["block_count"] == 1
    assert facts["paragraph_count"] == 1
    assert facts["chars"] == len("Once upon a time in a small village.")
    assert facts["anchors"] == ["Once upon a time in a small village."]
    assert facts["unanchored_paragraph_count"] == 0

    notice = quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
    assert notice is not None
    assert notice["kind"] == "translation"
    assert notice["level"] == "warning"
    assert notice["message_key"] == "result.source_text_delivered"
    assert notice["anchors"] == ["Once upon a time in a small village."]


def test_source_text_delivery_covers_omitted_paragraphs_too() -> None:
    """``omitted`` leaves the paragraph's own SOURCE text in the DOCX exactly like
    ``source_restored`` does (``_generation.PARAGRAPH_STATUS_OMITTED`` docstring) — the DOCX
    fact is the union, not one of the two."""
    facts = quality_gate.build_source_text_delivery_facts(
        [_block(_omitted("p1", "The monetary system remains unchanged."))]
    )

    assert facts["paragraph_count"] == 1
    assert facts["status_counts"] == {"omitted": 1, "source_restored": 0}


def test_source_text_delivery_never_invents_an_anchor() -> None:
    """Anti-regression #14: a paragraph with nothing searchable is COUNTED, not printed as
    an empty row, and an internal ``[[DOCX_PARA_…]]`` id never reaches the anchor."""
    facts = quality_gate.build_source_text_delivery_facts(
        [
            _block(
                _restored("p1", "### "),
                _restored("p2", "[[DOCX_PARA_p2]] Barter Systems Inc."),
            )
        ]
    )

    assert facts["paragraph_count"] == 2
    assert facts["unanchored_paragraph_count"] == 1
    assert facts["anchors"] == ["Barter Systems Inc."]
    assert all("DOCX_PARA" not in anchor for anchor in facts["anchors"])  # type: ignore[union-attr]

    notice = quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
    assert notice is not None
    assert notice["message_key"] == "result.source_text_delivered_with_unanchored"


def test_anchor_is_what_the_reader_sees_in_word_not_the_markdown() -> None:
    """The importer BAKES emphasis into the paragraph text — ``***``/``**``/``*``, then
    ``<u>``/``<sup>``/``<sub>`` (``document/extraction.py:1381-1394``) — and the DOCX is
    built from that markdown by Pandoc, so Word shows the text WITHOUT any of it. An anchor
    carrying the markup sends the reader to Ctrl+F for ``**Important**``, which the document
    never contains: the address would be wrong on every emphasised paragraph. Spec 057 paid
    for this exact lesson (``docs/WHERE_WE_ARE.md:117``).
    """
    facts = quality_gate.build_source_text_delivery_facts(
        [
            _block(
                _restored("p1", "**Important passage** with *emphasis* and <u>underline</u>."),
                _restored("p2", "***Both*** plus <sup>3</sup> and <sub>2</sub> markers."),
            )
        ]
    )

    assert facts["anchors"] == [
        "Important passage with emphasis and underline.",
        "Both plus 3 and 2 markers.",
    ]
    assert facts["unanchored_paragraph_count"] == 0


def test_anchor_that_is_only_markup_is_counted_not_printed() -> None:
    """Unwrapping can take an anchor BELOW the usability floor. It must then go to the
    counter, exactly like any other paragraph with nothing searchable — not to an empty «»."""
    facts = quality_gate.build_source_text_delivery_facts(
        [_block(_restored("p1", "**a**"), _restored("p2", "<u>*b*</u>"))]
    )

    assert facts["paragraph_count"] == 2
    assert facts["anchors"] == []
    assert facts["unanchored_paragraph_count"] == 2

    notice = quality_gate.build_source_text_delivery_notice(
        facts, processing_operation="translate"
    )
    assert notice is not None
    assert notice["message_key"] == "result.source_text_delivered_without_anchors"


def test_anchor_absent_from_the_delivered_markdown_is_not_offered() -> None:
    """Anti-regression #14, hardest form: the facts are read off ``state.processed_chunks``,
    which is the PRE-reader-cleanup material, while the DOCX is built from the post-cleanup
    markdown (``late_phases`` reassigns ``runtime_display_markdown``). Cleanup can delete,
    merge, split or rewrite a paragraph, so an anchor is offered only when it is still
    findable in what was actually DELIVERED. An address that does not exist is the worst
    kind of invented address, because the reader will go looking for it."""
    chunks = [
        _block(
            _restored("p1", "**Survived** the cleanup pass untouched."),
            _restored("p2", "Deleted by the cleanup pass entirely."),
        )
    ]
    delivered = "Survived the cleanup pass untouched.\n\nSomething else."

    facts = quality_gate.build_source_text_delivery_facts(chunks, delivered_markdown=delivered)

    assert facts["paragraph_count"] == 2
    assert facts["anchors"] == ["Survived the cleanup pass untouched."]
    assert facts["unanchored_paragraph_count"] == 1
    assert facts["anchors_dropped_not_in_delivered"] == 1


def test_delivered_markdown_check_compares_visible_text_on_both_sides() -> None:
    """Anti-vacuum for the check above: the delivered markdown still CARRIES the markup, so
    comparing a stripped anchor against the raw markdown would drop every emphasised
    paragraph and the channel would go silent exactly where it matters most."""
    chunks = [_block(_restored("p1", "**Important passage** with *emphasis*."))]
    delivered = "Some text.\n\n**Important passage** with *emphasis*.\n\nMore text."

    facts = quality_gate.build_source_text_delivery_facts(chunks, delivered_markdown=delivered)

    assert facts["anchors"] == ["Important passage with emphasis."]
    assert facts["anchors_dropped_not_in_delivered"] == 0


@pytest.mark.parametrize(
    ("operation", "expected_key"),
    [
        ("translate", "result.source_text_delivered"),
        ("audiobook", "result.source_text_delivered"),
        ("edit", "result.unedited_text_delivered"),
    ],
)
def test_the_notice_tells_the_truth_in_each_operation(operation: str, expected_key: str) -> None:
    """``edit`` rewrites text that is ALREADY in the target language, so calling a Russian
    paragraph "untranslated source text" is simply false. The fact there is that the model's
    edit was discarded. The condition comes from the JOB — the operation the run was started
    with — never from the shape of the paragraph (Constitution VII)."""
    facts = quality_gate.build_source_text_delivery_facts(
        [_block(_restored("p1", "Абзац, для которого вывод модели был отброшен."))]
    )

    notice = quality_gate.build_source_text_delivery_notice(
        facts, processing_operation=operation
    )

    assert notice is not None
    assert notice["message_key"] == expected_key


def test_source_text_delivery_ignores_a_block_without_a_per_paragraph_record() -> None:
    """A passthrough block is a plain ``str``: no record, no claim (Constitution VII)."""
    facts = quality_gate.build_source_text_delivery_facts(["Обычный блок без записи."])

    assert facts["paragraph_count"] == 0
    assert (
        quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
        is None
    )


def test_recorded_discard_reason_counts_are_not_the_alarm_trigger() -> None:
    """Third point of silence, found on the recorded corpus and NOT written in the spec.

    ``rethinking_money`` carries a NON-EMPTY ``model_output_discarded_reason_counts`` beside
    ``model_output_discarded_block_count=0``: the dict counts EVENTS
    (``core/model_accounting.record_model_output_discarded`` does
    ``_discard_reason_counts[reason] += 1``), and ``marker_chunk_collapse`` files itself with
    ``paragraph_count=2, block_count=0`` (``generation/_generation.py``). Keying the alarm on
    that dict would announce "1" of nothing at all. The trigger is the DELIVERED paragraph's
    own status, so a run whose blocks are all ``accepted`` stays silent no matter what the
    run-level reason dict says.
    """
    summary = _run_summary(FOUR_BOOK_RUN_DIR / "rethinking_money" / "run_summary.txt")
    assert summary["model_accounting_model_output_discarded_block_count"] == "0"
    assert json.loads(summary["model_accounting_model_output_discarded_reason_counts"]) == {
        "marker_chunk_collapse": 1
    }
    assert summary["narration_excluded_source_fallback_block_count"] == "0"

    facts = quality_gate.build_source_text_delivery_facts(
        [_block(_accepted("p1", "Переведённый абзац."))]
    )

    assert (
        quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
        is None
    )


# --------------------------------------------------------------------------------------
# Does the per-paragraph record actually SURVIVE to ``state.processed_chunks``?
#
# ``MarkerPreservedBlockText`` is a ``str`` subclass and its own docstring warns that any
# string operation — ``.strip()``, a slice, an f-string — returns a plain ``str`` and the
# record is gone SILENTLY, because the paragraph COUNT still matches afterwards. That is how
# a review once found English being read aloud with every check green. The alarm channel
# reads exactly that record, so the trace from where ``source_restored`` is stamped
# (``_generation.py:814``) to ``state.processed_chunks`` is either intact or the channel is
# blind. These tests walk it with the PRODUCTION collapse function rather than a hand-built
# fixture, so they also pin the collapse itself.
# --------------------------------------------------------------------------------------

# Long enough for the restorer to look at (>= 40 visible chars), and the neighbour grows by
# the whole of it, which is more than the required half.
_COLLAPSE_SOURCE_RU_A = (
    "Первый абзац, который модель схлопнула в соседний вместо того, чтобы обработать его отдельно."
)
_COLLAPSE_SOURCE_RU_B = (
    "Второй абзац, поглотивший текст первого целиком и потому заметно выросший в ответе модели."
)
_COLLAPSE_SOURCE_EN_A = (
    "Once upon a time, in a small village in the Outback, people used barter for all of their "
    "everyday transactions with one another."
)
_COLLAPSE_SOURCE_EN_B = (
    "On every market day they walked around the square with chickens, eggs and freshly baked "
    "breads to trade for whatever they needed."
)


def _collapsed_model_answer(source_a: str, source_b: str) -> str:
    """The shape the model really produces on a merge: an invented stub for the emptied
    marker, and the neighbour holding both paragraphs."""
    return (
        f"[[DOCX_PARA_p1]]\n(Пусто)\n\n[[DOCX_PARA_p2]]\n{source_b} {source_a}"
    )


def _restored_block(source_a: str, source_b: str) -> str:
    """Run the PRODUCTION marker path over a collapsed answer and return what it delivers."""
    return generation._strip_and_validate_paragraph_markers(
        _collapsed_model_answer(source_a, source_b),
        ["p1", "p2"],
        marker_mode=True,
        source_paragraph_chunks=[source_a, source_b],
    )


def test_collapse_restore_really_stamps_source_restored_on_both_paragraphs() -> None:
    """Step 1 of the trace: the production path produces the record at all.

    This is the ``marker_chunk_collapse`` class — the one the recorded ``rethinking_money``
    run carries — and it files itself as ``paragraph_count=2, block_count=0``, which is why
    the run-level dict says "1" of neither.
    """
    delivered = _restored_block(_COLLAPSE_SOURCE_RU_A, _COLLAPSE_SOURCE_RU_B)

    dispositions = quality_gate.marker_paragraph_dispositions(delivered)
    assert dispositions is not None, "the collapse path returned a bare str: the record is lost"
    assert [d.status for d in dispositions] == [
        PARAGRAPH_STATUS_SOURCE_RESTORED,
        PARAGRAPH_STATUS_SOURCE_RESTORED,
    ]
    assert [d.text for d in dispositions] == [_COLLAPSE_SOURCE_RU_A, _COLLAPSE_SOURCE_RU_B]


def test_collapse_record_survives_the_accepted_block_path_into_the_alarm() -> None:
    """Step 2a: the block is classified ``valid``, so it takes the ordinary append
    (``block_execution.py:1205``). The alarm must see two paragraphs."""
    runtime = {"state": {}}
    events, log_event = _capture_log_events()

    result = _run_two_paragraph_pipeline(
        runtime=runtime,
        log_event=log_event,
        source_a=_COLLAPSE_SOURCE_RU_A,
        source_b=_COLLAPSE_SOURCE_RU_B,
        processing_operation="edit",
    )

    assert result == "succeeded"
    delivered = [n for n in _notices(runtime) if n.get("kind") == "translation"]
    assert len(delivered) == 1, "the per-paragraph record did not reach state.processed_chunks"
    assert dict(delivered[0]["params"])["count"] == 2  # type: ignore[arg-type]
    assert dict(delivered[0]["params"])["blocks"] == 1  # type: ignore[arg-type]
    assert [
        event for event in events if event["event_id"] == "source_text_delivered_to_document"
    ]


def test_collapse_record_survives_the_controlled_fallback_path_into_the_alarm() -> None:
    """Step 2b: the SAME collapse in English is classified ``source_text_fallback`` (the
    restored text IS the source), so the block takes the controlled-fallback append
    (``block_execution.py:974``) with ``rejection_decision["fallback_markdown"]``. That value
    comes from ``_fallback_markdown_for_processed_block_rejection``, which returns the
    processed chunk itself for this kind — so the record rides along here too."""
    runtime = {"state": {}}
    events, log_event = _capture_log_events()

    result = _run_two_paragraph_pipeline(
        runtime=runtime,
        log_event=log_event,
        source_a=_COLLAPSE_SOURCE_EN_A,
        source_b=_COLLAPSE_SOURCE_EN_B,
        processing_operation="translate",
    )

    assert result == "succeeded"
    delivered = [n for n in _notices(runtime) if n.get("kind") == "translation"]
    assert len(delivered) == 1, "the per-paragraph record did not survive the controlled fallback"
    assert dict(delivered[0]["params"])["count"] == 2  # type: ignore[arg-type]
    assert [
        event for event in events if event["event_id"] == "source_text_delivered_to_document"
    ]


def test_empty_rejection_kinds_lose_the_record_and_the_alarm_goes_blind() -> None:
    """The one hole this trace found, pinned as a WITNESS rather than repaired.

    ``_fallback_markdown_for_processed_block_rejection`` (``block_execution.py:93-96``) has
    two outcomes. For every kind but two it returns the processed chunk, so the record rides
    along. For ``empty`` / ``empty_processed_block`` it returns ``payload.target_text`` — a
    plain ``str`` built long before any disposition existed — and the record is simply not
    there to lose. The block still delivers the source text into the DOCX, and this channel
    cannot see it.

    Not repaired here: the only place that could carry the record through is
    ``block_execution.py``, which spec 059 part A owns. Recorded so the blindness is a known
    hole with an address rather than a silent zero.
    """
    payload = SimpleNamespace(target_text="Исходный текст блока, доставленный как есть.")
    restored = _restored_block(_COLLAPSE_SOURCE_RU_A, _COLLAPSE_SOURCE_RU_B)

    kept = block_execution._fallback_markdown_for_processed_block_rejection(
        payload=payload, processed_chunk=restored, rejection_kind="source_text_fallback"
    )
    lost = block_execution._fallback_markdown_for_processed_block_rejection(
        payload=payload, processed_chunk=restored, rejection_kind="empty"
    )

    assert quality_gate.marker_paragraph_dispositions(kept) is not None
    assert quality_gate.marker_paragraph_dispositions(lost) is None
    # The consequence, said out loud: the alarm counts nothing for the blind kind.
    assert quality_gate.build_source_text_delivery_facts([lost])["paragraph_count"] == 0
    assert quality_gate.build_source_text_delivery_facts([kept])["paragraph_count"] == 2


@pytest.mark.parametrize("book", ("creating_wealth", "value_of_everything"))
def test_recorded_clean_books_map_to_alarm_silence(book: str) -> None:
    summary = _run_summary(FOUR_BOOK_RUN_DIR / book / "run_summary.txt")
    assert json.loads(summary["model_accounting_model_output_discarded_reason_counts"]) == {}
    assert summary["narration_excluded_source_fallback_block_count"] == "0"


def test_recorded_green_run_still_has_one_discarded_block() -> None:
    """Anti-vacuum #12 read in the OTHER direction on the SAME run: the verdict channel is
    silent on ``money_translate_docx`` and the alarm channel must speak about exactly one
    block."""
    summary = _run_summary(GREEN_RUN_SUMMARY)
    assert summary["model_accounting_model_output_discarded_block_count"] == "1"
    assert json.loads(summary["model_accounting_model_output_discarded_reason_counts"]) == {
        "incomplete_response_source_fallback": 1
    }
    assert summary["narration_artifact"] == "not_reported"

    facts = quality_gate.build_source_text_delivery_facts(
        [
            _block(_accepted("p1", "Переведённый абзац.")),
            _block(
                _restored("p2", "Once upon a time, in a small village in the Outback."),
                _restored("p3", "People used barter for all their transactions."),
            ),
        ]
    )

    assert facts["block_count"] == 1
    assert facts["paragraph_count"] == 2
    assert (
        quality_gate.build_source_text_delivery_notice(facts, processing_operation="translate")
        is not None
    )


# --------------------------------------------------------------------------------------
# Anti-regression #16 — the review block still draws nothing on a clean run
# --------------------------------------------------------------------------------------


def test_result_quality_warning_stays_none_on_pass() -> None:
    """Adding a verdict channel must not make the formatting-review block render with zero
    items — that is the forbidden vacuum."""
    assert (
        quality_gate._build_result_quality_warning(
            quality_report={
                "quality_status": "pass",
                "acceptance_verdict": {"passed": False, "failed_checks": ["mixed_script_terms_present"]},
            },
            latest_result_notice=None,
        )
        is None
    )


# --------------------------------------------------------------------------------------
# FR-B1 — the UI renders DATA; it never imports the verdict module
# --------------------------------------------------------------------------------------


def test_ui_package_never_imports_the_acceptance_module() -> None:
    offenders = []
    for path in sorted((REPO_ROOT / "src" / "docxaicorrector" / "ui").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name.startswith("docxaicorrector.validation") for alias in node.names
            ):
                offenders.append(path.name)
            if isinstance(node, ast.ImportFrom) and str(node.module or "").startswith(
                "docxaicorrector.validation"
            ):
                offenders.append(path.name)
    assert not offenders, f"ui modules import the validation layer: {sorted(set(offenders))}"


# --------------------------------------------------------------------------------------
# FR-B7 — a dropped notice is never silent
# --------------------------------------------------------------------------------------


def _capture_ui_events(monkeypatch) -> list[dict[str, object]]:
    captured: list[dict[str, object]] = []

    def _log_event(level, event_id, message, **context):
        captured.append({"level": level, "event_id": event_id, "context": context})
        return message

    monkeypatch.setattr(ui, "log_event", _log_event)
    return captured


def _context(event: Mapping[str, object]) -> Mapping[str, object]:
    context = event["context"]
    assert isinstance(context, Mapping)
    return context


def _render_with_notices(monkeypatch, notices: Sequence[Mapping[str, object]]) -> list[str]:
    warnings: list[str] = []

    class FakeColumn:
        def download_button(self, *args, **kwargs):
            return None

    monkeypatch.setattr(ui.st, "success", lambda message: None)
    monkeypatch.setattr(ui.st, "info", lambda message: None)
    monkeypatch.setattr(ui.st, "error", lambda message, *args, **kwargs: None)
    monkeypatch.setattr(ui.st, "warning", lambda message: warnings.append(message))
    monkeypatch.setattr(ui.st, "caption", lambda message: None)
    monkeypatch.setattr(ui.st, "columns", lambda count: [FakeColumn() for _ in range(count)])
    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="report.docx",
        success_message="Документ обработан.",
        result_notices=list(notices),
    )
    return warnings


def test_notice_of_an_unknown_kind_is_logged_not_dropped_silently(monkeypatch) -> None:
    events = _capture_ui_events(monkeypatch)

    rendered = _render_with_notices(
        monkeypatch,
        [{"kind": "brand_new", "level": "warning", "message_key": "result.narration_omitted"}],
    )

    assert rendered == []
    dropped = [event for event in events if event["event_id"] == "result_notice_dropped"]
    assert len(dropped) == 1
    assert dropped[0]["level"] == logging.WARNING
    assert _context(dropped[0])["kind"] == "brand_new"
    assert _context(dropped[0])["message_key"] == "result.narration_omitted"
    assert _context(dropped[0])["drop_reason"] == "unsupported_kind"


def test_notice_with_unusable_params_is_logged_not_dropped_silently(monkeypatch) -> None:
    events = _capture_ui_events(monkeypatch)

    rendered = _render_with_notices(
        monkeypatch,
        [
            {
                "kind": "persistence",
                "level": "warning",
                "message_key": "result.notice_review",
                "params": ["secret"],
            }
        ],
    )

    assert rendered == []
    dropped = [event for event in events if event["event_id"] == "result_notice_dropped"]
    assert len(dropped) == 1
    assert _context(dropped[0])["drop_reason"] == "unusable_params"
    assert _context(dropped[0])["message_key"] == "result.notice_review"
    # The rejected value itself is never logged: it is user content.
    assert "secret" not in json.dumps(dict(_context(dropped[0])), default=str)


def test_notice_whose_localization_raises_is_logged_not_dropped_silently(monkeypatch) -> None:
    events = _capture_ui_events(monkeypatch)

    real_t = ui.t

    def _boom(key, **kwargs):
        if key == "result.narration_omitted":
            raise RuntimeError("catalog exploded")
        return real_t(key, **kwargs)

    monkeypatch.setattr(ui, "t", _boom)
    rendered = _render_with_notices(
        monkeypatch,
        [{"kind": "narration", "level": "warning", "message_key": "result.narration_omitted"}],
    )

    assert rendered == []
    dropped = [event for event in events if event["event_id"] == "result_notice_dropped"]
    assert len(dropped) == 1
    assert _context(dropped[0])["drop_reason"] == "localization_failed"


def test_existing_notice_kinds_are_still_rendered_unchanged(monkeypatch) -> None:
    """Anti-regression #15."""
    _capture_ui_events(monkeypatch)
    monkeypatch.setattr(ui, "t", lambda key, **kwargs: f"localized:{key}")

    rendered = _render_with_notices(
        monkeypatch,
        [
            {"kind": "cleanup", "level": "warning", "message_key": "result.cleanup_advisory_failed"},
            {"kind": "narration", "level": "warning", "message_key": "result.narration_omitted"},
            {"kind": "persistence", "level": "warning", "message_key": "result.primary_artifacts_not_saved"},
        ],
    )

    assert rendered == [
        "localized:result.cleanup_advisory_failed",
        "localized:result.narration_omitted",
        "localized:result.primary_artifacts_not_saved",
    ]


# --------------------------------------------------------------------------------------
# FR-B3 — the screen names the failed checks in words, in the active locale
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "expected_fragment"),
    [("ru", "ложные заголовки"), ("en", "false fragment headings")],
)
def test_acceptance_notice_names_its_checks_in_words(
    monkeypatch, language: str, expected_fragment: str
) -> None:
    monkeypatch.setattr(ui.st, "session_state", SessionState(ui_language=language))
    _capture_ui_events(monkeypatch)

    rendered = _render_with_notices(
        monkeypatch,
        [
            {
                "kind": "acceptance",
                "level": "warning",
                "message_key": "result.acceptance_not_passed",
                "params": {"count": 1},
                "failed_checks": ["false_fragment_headings_present"],
            }
        ],
    )

    assert len(rendered) == 1
    assert "{" not in rendered[0]
    assert "false_fragment_headings_present" not in rendered[0]
    assert expected_fragment in rendered[0].lower()


def test_source_text_notice_prints_its_anchors(monkeypatch) -> None:
    monkeypatch.setattr(ui.st, "session_state", SessionState(ui_language="ru"))
    _capture_ui_events(monkeypatch)

    rendered = _render_with_notices(
        monkeypatch,
        [
            {
                "kind": "translation",
                "level": "warning",
                "message_key": "result.source_text_delivered",
                "params": {"count": 1, "blocks": 1, "chars": 36},
                "anchors": ["Once upon a time in a small village."],
            }
        ],
    )

    assert len(rendered) == 1
    assert "{" not in rendered[0]
    assert "Once upon a time in a small village." in rendered[0]


# --------------------------------------------------------------------------------------
# FR-B6 — ``latest_controlled_block_fallback_artifact`` is READ
# --------------------------------------------------------------------------------------


def test_controlled_block_fallback_artifact_is_rendered_beside_the_alarm(monkeypatch) -> None:
    captions: list[str] = []

    class FakeColumn:
        def download_button(self, *args, **kwargs):
            return None

    monkeypatch.setattr(ui.st, "session_state", SessionState(ui_language="ru"))
    monkeypatch.setattr(ui.st, "success", lambda message: None)
    monkeypatch.setattr(ui.st, "warning", lambda message: None)
    monkeypatch.setattr(ui.st, "caption", lambda message: captions.append(message))
    monkeypatch.setattr(ui.st, "columns", lambda count: [FakeColumn() for _ in range(count)])
    _capture_ui_events(monkeypatch)

    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="report.docx",
        success_message="Документ обработан.",
        controlled_block_fallback_artifact=".run/block_fallbacks/report_block_7_abcdef12.json",
        result_notices=[
            {
                "kind": "translation",
                "level": "warning",
                "message_key": "result.source_text_delivered",
                "params": {"count": 1, "blocks": 1, "chars": 36},
                "anchors": ["Once upon a time."],
            }
        ],
    )

    assert any(".run/block_fallbacks/report_block_7_abcdef12.json" in caption for caption in captions)


def test_controlled_block_fallback_artifact_is_silent_without_the_alarm(monkeypatch) -> None:
    """Anti-vacuum: a path shown on every run is noise."""
    captions: list[str] = []

    class FakeColumn:
        def download_button(self, *args, **kwargs):
            return None

    monkeypatch.setattr(ui.st, "session_state", SessionState(ui_language="ru"))
    monkeypatch.setattr(ui.st, "success", lambda message: None)
    monkeypatch.setattr(ui.st, "caption", lambda message: captions.append(message))
    monkeypatch.setattr(ui.st, "columns", lambda count: [FakeColumn() for _ in range(count)])
    _capture_ui_events(monkeypatch)

    ui.render_result_bundle(
        docx_bytes=b"docx",
        markdown_text="markdown",
        original_filename="report.docx",
        success_message="Документ обработан.",
        controlled_block_fallback_artifact=".run/block_fallbacks/report_block_7_abcdef12.json",
        result_notices=[],
    )

    assert captions == []


def test_result_bundle_carries_the_controlled_block_fallback_artifact() -> None:
    from docxaicorrector.processing.processing_runtime import build_result_bundle

    bundle = build_result_bundle(
        source_name="report.docx",
        source_token="token",
        docx_bytes=b"docx",
        markdown_text="markdown",
        controlled_block_fallback_artifact=".run/block_fallbacks/report_block_7.json",
    )

    assert bundle["controlled_block_fallback_artifact"] == ".run/block_fallbacks/report_block_7.json"


# --------------------------------------------------------------------------------------
# FR-B2 / FR-B4 wiring — both channels reach session state on a NON-translate run
# --------------------------------------------------------------------------------------


def _emit_state(runtime, **values):
    runtime.setdefault("state", {}).update(values)


def _run_pipeline(*, runtime, log_event, generate, processing_operation: str):
    return document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": "Once upon a time in a small village.",
                "target_text_with_markers": "Once upon a time in a small village.",
                "paragraph_ids": ["p0001"],
                "context_before": "",
                "context_after": "",
                "target_chars": 36,
                "context_chars": 0,
                "narration_include": True,
            }
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={},
        model="gpt-5.4",
        max_retries=1,
        processing_operation=processing_operation,
        source_language="auto",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
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
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: {},
    )


def _run_two_paragraph_pipeline(
    *, runtime, log_event, source_a: str, source_b: str, processing_operation: str
):
    """One marker block of TWO paragraphs whose model answer collapsed the first into the
    second. The generator stub runs the real marker path, so what enters the pipeline is
    what production would have produced."""
    target_text = f"{source_a}\n\n{source_b}"
    return document_pipeline.run_document_processing(
        uploaded_file="report.docx",
        jobs=[
            {
                "target_text": target_text,
                "target_text_with_markers": (
                    f"[[DOCX_PARA_p1]]\n{source_a}\n\n[[DOCX_PARA_p2]]\n{source_b}"
                ),
                "paragraph_ids": ["p1", "p2"],
                "context_before": "",
                "context_after": "",
                "target_chars": len(target_text),
                "context_chars": 0,
                "narration_include": True,
            }
        ],
        source_paragraphs=[],
        image_assets=[],
        image_mode="safe",
        app_config={"enable_paragraph_markers": True},
        model="gpt-5.4",
        max_retries=1,
        processing_operation=processing_operation,
        source_language="auto",
        target_language="ru",
        on_progress=lambda **kwargs: None,
        runtime=runtime,
        resolve_uploaded_filename=lambda uploaded_file: str(uploaded_file),
        get_client=lambda: object(),
        ensure_pandoc_available=lambda: None,
        load_system_prompt=lambda **_kw: "system",
        log_event=log_event,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        emit_state=_emit_state,
        emit_finalize=lambda runtime, stage, detail, progress, terminal_kind=None: None,
        emit_log=lambda runtime, **payload: None,
        emit_status=lambda runtime, **payload: None,
        should_stop_processing=lambda runtime: False,
        generate_markdown_block=lambda **kwargs: _restored_block(source_a, source_b),
        process_document_images=lambda **kwargs: [],
        inspect_placeholder_integrity=lambda markdown_text, image_assets: {},
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        write_ui_result_artifacts=lambda **kwargs: {},
    )


def _notices(runtime) -> list[Mapping[str, object]]:
    stored = runtime["state"].get("latest_result_notices") or []
    return [notice for notice in stored if isinstance(notice, Mapping)]


def _capture_log_events():
    captured: list[dict[str, object]] = []

    def log_event(level, event_id, message, **context):
        captured.append({"level": level, "event_id": event_id, "context": context})

    return captured, log_event


def test_edit_run_publishes_the_docx_source_text_notice_without_any_narration(monkeypatch) -> None:
    """FR-B4: ``narration_text is not None`` no longer governs the DOCX fact. ``edit`` is
    the DEFAULT mode (``resources/config.toml`` ``processing_operation_default``)."""
    runtime = {"state": {}}
    events, log_event = _capture_log_events()

    def generate(**kwargs):
        return _block(_restored("p0001", "Once upon a time in a small village."))

    result = _run_pipeline(
        runtime=runtime, log_event=log_event, generate=generate, processing_operation="edit"
    )

    assert result == "succeeded"
    assert runtime["state"]["latest_narration_text"] is None
    delivered = [
        notice for notice in _notices(runtime) if notice.get("kind") == "translation"
    ]
    assert len(delivered) == 1
    # This run is ``edit``, so the truthful wording is the unedited one (review finding 4).
    assert delivered[0]["message_key"] == "result.unedited_text_delivered"
    assert dict(delivered[0]["params"])["count"] == 1  # type: ignore[arg-type]
    assert list(delivered[0]["anchors"]) == ["Once upon a time in a small village."]  # type: ignore[arg-type]
    assert [
        event for event in events if event["event_id"] == "source_text_delivered_to_document"
    ]


def test_the_pipeline_hands_the_DELIVERED_markdown_to_the_facts_builder(monkeypatch) -> None:
    """The builder can only check an anchor against the delivered text if it is GIVEN it.

    ``state.processed_chunks`` is the pre-reader-cleanup material and ``runtime_display_markdown``
    is what the DOCX is built from; the two diverge exactly when cleanup does something. A unit
    test on the builder cannot see whether the pipeline actually threads it, so the wiring is
    pinned here — without this, dropping the argument in ``late_phases`` breaks nothing.
    """
    captured: dict[str, object] = {}
    real_builder = late_phases.build_source_text_delivery_facts

    def _spy(processed_chunks, **kwargs):
        captured.update(kwargs)
        captured["chunk_count"] = len(list(processed_chunks))
        return real_builder(processed_chunks, **kwargs)

    monkeypatch.setattr(late_phases, "build_source_text_delivery_facts", _spy)
    runtime = {"state": {}}
    _events, log_event = _capture_log_events()

    result = _run_pipeline(
        runtime=runtime,
        log_event=log_event,
        generate=lambda **kwargs: _block(_restored("p0001", "Once upon a time in a small village.")),
        processing_operation="edit",
    )

    assert result == "succeeded"
    assert captured["delivered_markdown"] == runtime["state"]["latest_markdown"]
    assert str(captured["delivered_markdown"]).strip()


def test_clean_edit_run_publishes_no_source_text_notice() -> None:
    runtime = {"state": {}}
    events, log_event = _capture_log_events()

    def generate(**kwargs):
        return _block(_accepted("p0001", "Однажды в маленькой деревне."))

    result = _run_pipeline(
        runtime=runtime, log_event=log_event, generate=generate, processing_operation="edit"
    )

    assert result == "succeeded"
    assert not [notice for notice in _notices(runtime) if notice.get("kind") == "translation"]
    assert not [
        event for event in events if event["event_id"] == "source_text_delivered_to_document"
    ]


def test_edit_run_publishes_the_acceptance_verdict_notice(monkeypatch) -> None:
    runtime = {"state": {}}
    events, log_event = _capture_log_events()
    monkeypatch.setattr(
        late_phases,
        "build_report_acceptance_verdict",
        lambda *args, **kwargs: {
            "passed": False,
            "failed_checks": ["mixed_script_terms_present", "key_headings_preserved"],
            "checks": [],
        },
    )

    result = _run_pipeline(
        runtime=runtime,
        log_event=log_event,
        generate=lambda **kwargs: _block(_accepted("p0001", "Однажды в маленькой деревне.")),
        processing_operation="edit",
    )

    assert result == "succeeded"
    verdict_notices = [n for n in _notices(runtime) if n.get("kind") == "acceptance"]
    assert len(verdict_notices) == 1
    assert verdict_notices[0]["failed_checks"] == ["mixed_script_terms_present"]
    # FR-B8: review data, never a delivery gate.
    assert dict(runtime["state"]["latest_delivery_disposition"])["status"] != "blocked"
    assert [
        event for event in events if event["event_id"] == "acceptance_verdict_not_passed"
    ]


def test_green_verdict_publishes_no_acceptance_notice(monkeypatch) -> None:
    runtime = {"state": {}}
    events, log_event = _capture_log_events()
    monkeypatch.setattr(
        late_phases,
        "build_report_acceptance_verdict",
        lambda *args, **kwargs: {"passed": True, "failed_checks": [], "checks": []},
    )

    result = _run_pipeline(
        runtime=runtime,
        log_event=log_event,
        generate=lambda **kwargs: _block(_accepted("p0001", "Однажды в маленькой деревне.")),
        processing_operation="edit",
    )

    assert result == "succeeded"
    assert not [n for n in _notices(runtime) if n.get("kind") == "acceptance"]
    assert not [
        event for event in events if event["event_id"] == "acceptance_verdict_not_passed"
    ]
