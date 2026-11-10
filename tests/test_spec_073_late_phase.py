"""Spec 073 WP-H: the late phase builds the book file and counts FR-010 (FR-007 integration, FR-008, FR-009, FR-010).

The chain under test is the product one, the same as spec 072 WP-H: narration records -> ``_build_narration_text``
(real, with the FR-006 scene-break marks) -> the late phase (``finalize_processing_success``, real) -> the narration
exports with the book file (``pipeline/narration_exports``, real; ``pipeline/narration_book``, real) -> ``emit_state`` /
the REAL result-group writer into ``tmp_path`` / the log. The harness is spec 072's (imported, not copied); the PDF
converter is replaced on ``pipeline.narration_exports`` (CI has no LibreOffice).

* T-H1 is a characterization test: green before and after -- ``translate`` / ``edit`` hand nobody a book file, and
  ``build_narration_exports`` without ``book_inputs`` builds what spec 072 built and logs what it logged.
* T-H2...T-H6 fail without the change: there is no ``book_json``, no writer argument, no book event fields, no FR-010
  counters, no ``runtime/build_info``.

All texts are invented, of the same FORM as book text; no book of the corpus is quoted (Constitution VII).
"""

from __future__ import annotations

import dataclasses
import importlib
import io
import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import docx
import pytest

import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.pipeline.narration_book as narration_book
import docxaicorrector.pipeline.narration_exports as narration_exports
from docxaicorrector.generation.narration_docx import render_narration_docx
from docxaicorrector.generation.narration_pdf import NarrationPdfOutcome
from docxaicorrector.pipeline.audiobook_pass import (
    AudiobookParagraphInput,
    NarrationParagraphRecord,
    audiobook_narration_summary,
    finalize_audiobook_block,
)
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.pipeline.narration_document import build_narration_document_plan
from docxaicorrector.pipeline.narration_postprocess import NarrationGroup
from docxaicorrector.pipeline.reading_glossary import (
    READING_REJECTION_REASONS,
    ReadingCandidate,
    ReadingEntry,
    ReadingGlossary,
)
from tests.test_spec_072_late_phase_exports import (
    _FAKE_PDF,
    _NEW_SAVED_EVENT_KEYS as _SPEC_072_SAVED_EVENT_KEYS,
    _SPEC_070_SAVED_EVENT_KEYS,
    _context,
    _delivery_call,
    _patch_pdf_export,
    _record,
    _run,
    _saved_event,
    _texts_in,
)

ACUTE = "́"
_STRESSED = f"Ста{ACUTE}рый за{ACUTE}мок стоял на холме."
_CONTEXT = _context("audiobook")
_UTC_SECONDS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX_HEAD = re.compile(r"^[0-9a-f]{7,}$")

# The keys spec 073 adds to ``ui_audiobook_artifact_saved`` (contracts/events.md): from the exports ...
_SPEC_073_EXPORT_EVENT_KEYS = {
    "narration_book_path",
    "narration_book_status",
    "narration_book_chapter_count",
    "narration_book_pause_counts",
}
# ... and from the run summary.
_SPEC_073_SUMMARY_KEYS = {
    "scene_break_count",
    "stress_mark_count",
    "stress_marks_per_1000_words",
    "latin_source_unit_count",
    "reading_glossary_status",
    "reading_glossary_candidate_count",
    "reading_glossary_sent_count",
    "reading_glossary_accepted_count",
    "reading_glossary_rerequested_count",
    "reading_glossary_unresolved_count",
    "reading_glossary_dropped_by_limit_count",
    "reading_glossary_rejected_by_reason",
    "reading_glossary_batch_count",
    "reading_glossary_call_count",
    "reading_glossary_retry_count",
    "reading_glossary_block_count",
    "reading_glossary_cost_usd",
    "reading_glossary_artifact_path",
}

# ---------------------------------------------------------------------------------------------------------------
# the SC-006 set: a chapter before the first Heading 1, a series 2 -> 1, a subheading, a scene separator between
# two body paragraphs that would otherwise be joined, U+0301, a newline inside a paragraph, a join of two records
# ---------------------------------------------------------------------------------------------------------------


def _sc006_records() -> list[NarrationParagraphRecord]:
    return [
        _record("b0", "Посвящается Квазибургу."),
        _record("s1", "Часть первая", role="heading", level=2),
        _record("s2", "Квазибург", role="heading", level=1),
        _record("b1", _STRESSED),
        _record("h3", "Подраздел первый", role="heading", level=2),
        # no closing dot, and the next one starts lowercase: joined, were it not for the separator between them
        _record("b2", "Первая строка\nвторая строка"),
        # (x1: the excluded ``***`` separator; x2: an excluded table of contents line)
        _record("b3", "утром пришли гости."),
        _record("b4", "Дорога вела вдоль реки и никто"),
        _record("b5", "не спрашивал, куда он идёт."),
    ]


# One word = a letter series of the text without combining marks: ``Ста́рый`` is ONE word. Counted by hand.
_SC006_WORD_COUNT = 2 + 2 + 1 + 5 + 2 + 4 + 3 + 6 + 5
_SC006_STRESS_MARKS = 2

# Written by hand from data-model §7: the groups and their pause kinds.
_SC006_GROUP_IDS = [["b0"], ["s1"], ["s2"], ["b1"], ["h3"], ["b2"], ["b3"], ["b4", "b5"]]
_SC006_PAUSE_KINDS = [None, None, "chapter", None, "heading", "scene_break", None, None]
_SC006_CHAPTERS = [
    {"ordinal": 1, "title": None, "segment_ordinals": [1]},
    {"ordinal": 2, "title": "Часть первая. Квазибург", "segment_ordinals": [2, 3, 4, 5, 6, 7, 8]},
]


def _sc006_state(
    records: Sequence[NarrationParagraphRecord] | None = None,
    *,
    glossary: ReadingGlossary | None = None,
    glossary_block_indexes: set[int] | None = None,
) -> ProcessingState:
    records = list(_sc006_records() if records is None else records)
    ids = [record.paragraph_id for record in records]
    kinds = [(pid, "narrated") for pid in ids]
    # the separator after b2 and a table of contents line after it: an excluded paragraph neither sets nor clears
    position = ids.index("b2") + 1
    kinds[position:position] = [("x1", "scene_break"), ("x2", "excluded")]
    state = ProcessingState(
        processed_chunks=["текст"],
        narration_paragraphs=records,
        narration_expected_paragraph_ids=ids,
        narration_paragraph_kinds=kinds,
        narration_exclusions=[
            {"paragraph_id": "x1", "block_index": 1, "reason": "fragment", "sample": "***"},
            {"paragraph_id": "x2", "block_index": 1, "reason": "toc", "sample": "Оглавление 7"},
        ],
    )
    state.audiobook_reading_glossary = glossary
    state.audiobook_reading_glossary_block_indexes = set(glossary_block_indexes or ())
    return state


def _glossary() -> ReadingGlossary:
    rejected = {reason: 0 for reason in READING_REJECTION_REASONS}
    rejected["latin_in_reading"] = 1
    return ReadingGlossary(
        status="built",
        candidates=(
            ReadingCandidate(abbreviation="QWZ", occurrences=4, first_block_index=1, context="…", sent=True),
            ReadingCandidate(abbreviation="ABC", occurrences=2, first_block_index=1, context="…", sent=True),
            ReadingCandidate(abbreviation="XyZ-QW", occurrences=1, first_block_index=2, context="…", sent=False),
        ),
        # the answer order, not the candidate order
        entries=(ReadingEntry("ABC", "а-бэ-цэ"), ReadingEntry("QWZ", "кувэзэ")),
        rejected_by_reason=rejected,
        rerequested=("QWZ",),
        unresolved=(),
        batch_count=2,
        call_count=3,
        retry_count=1,
        prompt_tokens=420,
        completion_tokens=37,
        cost_usd=0.00125,
        artifact_path="/tmp/run_glossaries/run-072_1.json",
    )


def _book(emitters: Any) -> dict[str, Any]:
    value = _delivery_call(emitters).get("latest_narration_exports")
    assert isinstance(value, Mapping), "latest_narration_exports is not in the state event that delivers the text"
    book_json = value.get("book_json")
    assert isinstance(book_json, str), value.keys()
    payload = json.loads(book_json)
    assert isinstance(payload, dict)
    return payload


def _segments_equal_tts(payload: Mapping[str, Any], tts_text: str) -> bool:
    """The contract invariant (SC-006, Anti-regression 10): the segments ARE the ``.tts.txt``, byte for byte."""

    return "\n\n".join(segment["text"] for segment in payload["segments"]) == tts_text


def _docx_texts(docx_bytes: bytes) -> list[str]:
    return [paragraph.text for paragraph in docx.Document(io.BytesIO(docx_bytes)).paragraphs]


def _no_git_head(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Callable[[], object]:
    """The late phase's git head, read in a directory that is no git checkout."""

    build_info = importlib.import_module("docxaicorrector.runtime.build_info")
    outside = tmp_path / "outside_git"
    outside.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    resolver = lambda: build_info.resolve_git_head(outside)  # noqa: E731
    monkeypatch.setattr(late_phases, "resolve_git_head", resolver)
    return resolver


def _fake_git_checkout(root: Path, object_id: str) -> Path:
    """A ``.git`` directory with ``HEAD`` -> a branch ref -> ``object_id`` (no objects: ``git`` itself cannot read it)."""

    git_dir = root / ".git"
    (git_dir / "refs" / "heads").mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (git_dir / "refs" / "heads" / "main").write_text(object_id + "\n", encoding="utf-8")
    return root


# ---------------------------------------------------------------------------------------------------------------
# T-H1 -- characterization (green before and after)
# ---------------------------------------------------------------------------------------------------------------

# The writer arguments and delivery state keys of a translate / edit run (072/integration snapshot, unchanged by 073).
_NON_AUDIOBOOK_WRITER_KEYS = {"source_name", "markdown_text", "docx_bytes", "assembly_mode", "result_manifest"}
_NON_AUDIOBOOK_DELIVERY_STATE_KEYS = {
    "final_generated_paragraph_registry",
    "latest_docx_bytes",
    "latest_markdown",
    "latest_narration_text",
    "latest_quality_warning",
    "latest_delivery_disposition",
    "latest_result_notice",
    "latest_result_notices",
    "last_error",
}


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_t_h1_translate_and_edit_hand_nobody_a_book_file(monkeypatch, tmp_path, operation):
    calls: list[str] = []

    def _forbidden(*args: object, **kwargs: object) -> object:
        calls.append("build_narration_book")
        raise AssertionError(f"build_narration_book must not run for {operation}")

    monkeypatch.setattr(narration_book, "build_narration_book", _forbidden)
    monkeypatch.setattr(narration_exports, "build_narration_book", _forbidden, raising=False)

    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation=operation, state=ProcessingState(processed_chunks=["текст"])
    )

    assert result == "succeeded"
    assert calls == []
    assert set(_delivery_call(emitters)) == _NON_AUDIOBOOK_DELIVERY_STATE_KEYS
    assert len(dependencies.writer_calls) == 1
    assert set(dependencies.writer_calls[0]) - {"model_accounting"} == _NON_AUDIOBOOK_WRITER_KEYS
    assert "narration_book_json" not in dependencies.writer_calls[0]
    written = sorted(path.name.split(".result", 1)[1] for path in (tmp_path / "ui_results").iterdir())
    assert written == [".docx", ".manifest.json", ".md", ".meta.json"]
    assert not [event for _level, event, _ctx in dependencies.events if event.startswith("audiobook_")]


def _groups_for_exports() -> tuple[NarrationGroup, ...]:
    return (
        NarrationGroup(paragraph_ids=("p1",), role="heading", heading_level=1, text="Квазибург"),
        NarrationGroup(paragraph_ids=("p2",), role="body", heading_level=None, text=_STRESSED),
        NarrationGroup(paragraph_ids=("p3", "p4"), role="body", heading_level=None, text="Утром пришли гости."),
    )


@pytest.mark.parametrize("pdf_ok", [True, False])
def test_t_h1_exports_without_book_inputs_build_and_log_what_spec_072_did(pdf_ok):
    groups = _groups_for_exports()
    events: list[tuple[int, str, dict[str, object]]] = []
    outcome = (
        NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail="")
        if pdf_ok
        else NarrationPdfOutcome(pdf_bytes=None, reason="soffice_not_found", seconds=0.0, detail="")
    )

    exports = narration_exports.build_narration_exports(
        groups=groups,
        source_name="kvazibu.docx",
        log_event=lambda level, event, message, **context: events.append((level, event, context)),
        export_pdf=lambda docx_bytes, **kwargs: outcome,
    )

    plan = build_narration_document_plan(groups)
    assert exports.plan == plan
    assert exports.docx_error is None
    assert exports.docx_bytes is not None
    assert _docx_texts(exports.docx_bytes) == _docx_texts(render_narration_docx(plan.paragraphs))
    assert exports.pdf == outcome
    assert [event for _level, event, _ctx in events] == ([] if pdf_ok else ["audiobook_narration_pdf_unavailable"])
    assert getattr(exports, "book", None) is None
    state_value = exports.state_value()
    assert {key: state_value[key] for key in ("docx_bytes", "pdf_bytes", "docx_unavailable_reason", "pdf_unavailable_reason")} == {
        "docx_bytes": exports.docx_bytes,
        "pdf_bytes": _FAKE_PDF if pdf_ok else None,
        "docx_unavailable_reason": None,
        "pdf_unavailable_reason": None if pdf_ok else "soffice_not_found",
    }


# ---------------------------------------------------------------------------------------------------------------
# T-H2 -- SC-006 / Anti-regression 10 on the late phase: the book file is the .tts.txt, byte for byte
# ---------------------------------------------------------------------------------------------------------------


def test_t_h2_book_file_segments_are_the_tts_text_and_reach_state_writer_and_disk(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    state = _sc006_state()

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    assert result == "succeeded"
    tts_text = _delivery_call(emitters)["latest_narration_text"]
    assert isinstance(tts_text, str)
    payload = _book(emitters)
    assert _segments_equal_tts(payload, tts_text)
    assert [segment["source_paragraph_ids"] for segment in payload["segments"]] == _SC006_GROUP_IDS
    assert [segment["after_scene_break"] for segment in payload["segments"]] == [
        False, False, False, False, False, False, True, False
    ]
    assert [
        None if segment["pause_after"] is None else segment["pause_after"]["kind"] for segment in payload["segments"]
    ] == _SC006_PAUSE_KINDS
    assert payload["chapters"] == _SC006_CHAPTERS
    assert payload["chapter_heading_level"] == 1

    # the writer got the SAME text, and the group member on disk is it, byte for byte (UTF-8, LF)
    book_json = _delivery_call(emitters)["latest_narration_exports"]["book_json"]  # type: ignore[index]
    writer_kwargs = dependencies.writer_calls[0]
    assert writer_kwargs["narration_book_json"] == book_json
    saved = _saved_event(dependencies)
    book_path = Path(str(saved["narration_book_path"]))
    assert book_path.name.endswith("_book_run-072.result.narration.json"), book_path.name
    assert book_path.name.removesuffix(".narration.json") == Path(str(saved["tts_text_path"])).name.removesuffix(".tts.txt")
    assert book_path.read_bytes() == str(book_json).encode("utf-8")
    assert Path(str(saved["tts_text_path"])).read_text(encoding="utf-8") == tts_text

    # negative controls through the SAME comparison: one extra space, one lost segment
    spaced = json.loads(str(book_json))
    spaced["segments"][3]["text"] += " "
    dropped = json.loads(str(book_json))
    del dropped["segments"][4]
    assert not _segments_equal_tts(spaced, tts_text)
    assert not _segments_equal_tts(dropped, tts_text)


# ---------------------------------------------------------------------------------------------------------------
# T-H3 -- FR-009: U+0301 byte for byte in the .tts.txt, the .tts.docx and the book file of one run
# ---------------------------------------------------------------------------------------------------------------


def test_t_h3_stress_mark_survives_in_the_three_narration_files(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))

    result, _emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=_sc006_state())

    assert result == "succeeded"
    saved = _saved_event(dependencies)
    tts_text = Path(str(saved["tts_text_path"])).read_text(encoding="utf-8")
    assert _STRESSED in tts_text.split("\n\n")
    docx_texts = _docx_texts(Path(str(saved["tts_docx_path"])).read_bytes())
    assert _STRESSED in docx_texts
    book_text = Path(str(saved["narration_book_path"])).read_text(encoding="utf-8")
    # the character itself, never its JSON escape (Anti-regression 5)
    assert ACUTE in book_text and "\\u0301" not in book_text
    assert _STRESSED in [segment["text"] for segment in json.loads(book_text)["segments"]]
    # the negative control of the same membership check: the text without the marks is not found
    unstressed = _STRESSED.replace(ACUTE, "")
    assert unstressed not in tts_text.split("\n\n") and unstressed not in docx_texts


# ---------------------------------------------------------------------------------------------------------------
# T-H4 -- the inputs of the book file: glossary, producer, book, stats, code version
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("with_glossary", [True, False])
def test_t_h4_book_inputs_come_from_the_run(monkeypatch, tmp_path, with_glossary):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    _no_git_head(monkeypatch, tmp_path)
    state = _sc006_state(glossary=_glossary() if with_glossary else None)
    before = datetime.now(UTC).replace(microsecond=0)

    result, emitters, _dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    after = datetime.now(UTC)
    assert result == "succeeded"
    payload = _book(emitters)
    assert payload["reading_glossary"] == (
        [{"abbreviation": "ABC", "reading": "а-бэ-цэ"}, {"abbreviation": "QWZ", "reading": "кувэзэ"}]
        if with_glossary
        else []
    )
    producer = payload["producer"]
    assert producer["name"] == "DocxAICorrector"
    assert producer["version"] is None  # no git checkout: never invented
    assert producer["run_id"] == _CONTEXT.run_id
    assert _UTC_SECONDS.match(producer["produced_at"]), producer["produced_at"]
    produced_at = datetime.strptime(producer["produced_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert before <= produced_at <= after
    assert payload["book"] == {"source_name": _CONTEXT.uploaded_filename, "source_token": _CONTEXT.source_token}
    summary = audiobook_narration_summary(state)
    assert payload["stats"]["excluded_count"] == summary["excluded_count"] == 2
    assert payload["stats"]["excluded_by_reason"] == summary["excluded_by_reason"] == {"fragment": 1, "toc": 1}
    assert payload["stats"]["reading_glossary_entry_count"] == (2 if with_glossary else 0)


def test_t_h4_producer_version_is_the_git_head_of_the_code(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    build_info = importlib.import_module("docxaicorrector.runtime.build_info")
    checkout = _fake_git_checkout(tmp_path / "checkout", "0123abc" + "d" * 33)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    monkeypatch.setattr(late_phases, "resolve_git_head", lambda: build_info.resolve_git_head(checkout))

    result, emitters, _dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=_sc006_state())

    assert result == "succeeded"
    version = _book(emitters)["producer"]["version"]
    assert version == "0123abc" and _HEX_HEAD.match(version)


def test_t_h4_resolve_git_head_is_none_outside_a_checkout_and_the_sha_inside(monkeypatch, tmp_path):
    build_info = importlib.import_module("docxaicorrector.runtime.build_info")
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    outside = tmp_path / "outside"
    outside.mkdir()
    checkout = _fake_git_checkout(tmp_path / "checkout", "fedcba9" + "0" * 33)

    assert build_info.resolve_git_head(outside) is None
    head = build_info.resolve_git_head(checkout)
    assert head == "fedcba9" and _HEX_HEAD.match(head)
    # a missing directory is no checkout either -- no exception
    assert build_info.resolve_git_head(tmp_path / "missing") is None


# ---------------------------------------------------------------------------------------------------------------
# T-H5 -- the book file is not built: WARNING, the other formats are delivered; and the reverse
# ---------------------------------------------------------------------------------------------------------------


def test_t_h5_book_failure_is_a_warning_and_txt_docx_pdf_are_delivered(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    message = "narration book: plan paragraph 3 does not match groups 3..4 of 8 " + "x" * 400

    def _raise(**kwargs: object) -> object:
        raise ValueError(message)

    monkeypatch.setattr(narration_exports, "build_narration_book", _raise)
    state = _sc006_state()

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    assert result == "succeeded"
    exports = _delivery_call(emitters)["latest_narration_exports"]
    assert isinstance(exports, Mapping)
    assert exports["book_json"] is None
    assert isinstance(exports["docx_bytes"], bytes) and exports["pdf_bytes"] == _FAKE_PDF
    warnings = dependencies.named("audiobook_narration_book_failed")
    assert len(warnings) == 1
    level, context = warnings[0]
    assert level == logging.WARNING
    assert context == {
        "filename": "book.docx",
        "error_class": "ValueError",
        "error_message": message[:300],
        "group_count": len(state.narration_groups),
    }
    writer_kwargs = dependencies.writer_calls[0]
    assert "narration_book_json" not in writer_kwargs
    assert writer_kwargs["narration_docx_bytes"] == exports["docx_bytes"]
    assert writer_kwargs["narration_pdf_bytes"] == _FAKE_PDF
    saved = _saved_event(dependencies)
    for key in ("tts_text_path", "tts_docx_path", "tts_pdf_path"):
        assert Path(str(saved[key])).is_file(), key
    assert not list((tmp_path / "ui_results").glob("*.narration.json"))
    assert saved["narration_book_path"] is None
    assert saved["narration_book_status"] == "failed"
    assert saved["narration_book_chapter_count"] == 0
    assert saved["narration_book_pause_counts"] == {"chapter": 0, "heading": 0, "scene_break": 0}


def test_t_h5_docx_renderer_failure_still_builds_the_book_file(monkeypatch, tmp_path):
    spy = _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    records = _sc006_records()
    # a vertical tab is not allowed in XML: the REAL renderer raises ValueError on it
    records[3] = _record("b1", "Старый замок\x0b стоял на холме.")

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=_sc006_state(records))

    assert result == "succeeded"
    assert spy.calls == []
    assert len(dependencies.named("audiobook_narration_docx_failed")) == 1
    assert not dependencies.named("audiobook_narration_book_failed")
    payload = _book(emitters)
    assert _segments_equal_tts(payload, str(_delivery_call(emitters)["latest_narration_text"]))
    assert "narration_book_json" in dependencies.writer_calls[0]
    saved = _saved_event(dependencies)
    assert saved["narration_docx_status"] == "failed"
    assert saved["narration_book_status"] == "built"
    assert Path(str(saved["narration_book_path"])).is_file()


# ---------------------------------------------------------------------------------------------------------------
# T-H6 -- FR-010: the fields of ui_audiobook_artifact_saved
# ---------------------------------------------------------------------------------------------------------------


def _with_latin(records: list[NarrationParagraphRecord], counts: Mapping[str, int]) -> list[NarrationParagraphRecord]:
    return [
        dataclasses.replace(record, source_latin_unit_count=counts[record.paragraph_id])
        if record.paragraph_id in counts
        else record
        for record in records
    ]


def test_t_h6_saved_event_carries_the_book_and_the_fr010_counters(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    records = _with_latin(_sc006_records(), {"b1": 2, "b3": 1})
    state = _sc006_state(records, glossary=_glossary(), glossary_block_indexes={1, 3})

    result, _emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    assert result == "succeeded"
    saved = _saved_event(dependencies)
    summary_keys = set(audiobook_narration_summary(state))
    assert _SPEC_073_SUMMARY_KEYS <= summary_keys
    # every 070 / 072 key is still there; the 073 keys are added, nothing else
    expected_keys = (
        _SPEC_070_SAVED_EVENT_KEYS
        | summary_keys
        | {"review_finding_count", "review_match_count", "review_rules"}
        | _SPEC_072_SAVED_EVENT_KEYS
        | _SPEC_073_EXPORT_EVENT_KEYS
    )
    assert set(saved) == expected_keys

    assert saved["narration_book_path"] == saved["artifact_paths"]["narration_book_path"]  # type: ignore[index]
    assert saved["narration_book_status"] == "built"
    assert saved["narration_book_chapter_count"] == 2
    assert saved["narration_book_pause_counts"] == {"chapter": 1, "heading": 1, "scene_break": 1}
    assert {key: saved[key] for key in sorted(_SPEC_073_SUMMARY_KEYS)} == {
        "latin_source_unit_count": 3,
        "reading_glossary_accepted_count": 2,
        "reading_glossary_artifact_path": "/tmp/run_glossaries/run-072_1.json",
        "reading_glossary_batch_count": 2,
        "reading_glossary_block_count": 2,
        "reading_glossary_call_count": 3,
        "reading_glossary_candidate_count": 3,
        "reading_glossary_cost_usd": 0.00125,
        "reading_glossary_dropped_by_limit_count": 1,
        "reading_glossary_rejected_by_reason": {
            "not_a_candidate": 0,
            "empty_reading": 0,
            "latin_in_reading": 1,
            "digit_in_reading": 0,
            "not_cyrillic_reading": 0,
            "duplicate": 0,
        },
        "reading_glossary_rerequested_count": 1,
        "reading_glossary_retry_count": 1,
        "reading_glossary_sent_count": 2,
        "reading_glossary_status": "built",
        "reading_glossary_unresolved_count": 0,
        "scene_break_count": 1,
        "stress_mark_count": _SC006_STRESS_MARKS,
        "stress_marks_per_1000_words": round(_SC006_STRESS_MARKS * 1000 / _SC006_WORD_COUNT, 3),
    }
    # no paragraph text in the new keys; no spelling and no reading of the glossary anywhere in the event
    texts = [record.text for record in records if len(record.text) >= 5]
    assert _texts_in({key: saved[key] for key in _SPEC_073_EXPORT_EVENT_KEYS | _SPEC_073_SUMMARY_KEYS}, texts) == []
    assert _texts_in(saved, ["а-бэ-цэ", "кувэзэ", "ABC", "QWZ", "XyZ-QW"]) == []


def test_t_h6_without_a_glossary_the_counters_say_not_applicable_and_zero(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    state = _sc006_state()

    result, _emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    assert result == "succeeded"
    saved = _saved_event(dependencies)
    assert {key: saved[key] for key in sorted(_SPEC_073_SUMMARY_KEYS) if key.startswith("reading_glossary_")} == {
        "reading_glossary_accepted_count": 0,
        "reading_glossary_artifact_path": None,
        "reading_glossary_batch_count": 0,
        "reading_glossary_block_count": 0,
        "reading_glossary_call_count": 0,
        "reading_glossary_candidate_count": 0,
        "reading_glossary_cost_usd": None,
        "reading_glossary_dropped_by_limit_count": 0,
        "reading_glossary_rejected_by_reason": {reason: 0 for reason in READING_REJECTION_REASONS},
        "reading_glossary_rerequested_count": 0,
        "reading_glossary_retry_count": 0,
        "reading_glossary_sent_count": 0,
        "reading_glossary_status": "not_applicable",
        "reading_glossary_unresolved_count": 0,
    }
    # no Latin in any source: zero is a statement, not an absent key
    assert saved["latin_source_unit_count"] == 0


def test_t_h6_latin_source_units_are_counted_per_record_by_the_finalizer():
    paragraphs = [
        # the source carries two Latin units, the narration has them transliterated
        AudiobookParagraphInput(
            paragraph_id="p1",
            role="body",
            source_text="Город Zentrix и отдел XyZ-QW открылись.",
            delivered_text="Город Зентрикс и отдел Иксиз-кувэ открылись.",
            status="accepted",
        ),
        # no Latin in the source (anti-vacuum: the count is per record, not per block)
        AudiobookParagraphInput(
            paragraph_id="p2",
            role="body",
            source_text="Квазибург стоял на холме.",
            delivered_text="Квазибург стоял на холме.",
            status="accepted",
        ),
        # an address is not Latin text (the class masks it): zero
        AudiobookParagraphInput(
            paragraph_id="p3",
            role="body",
            source_text="Адрес www.kvazi.example в тексте.",
            delivered_text="Адрес в тексте.",
            status="accepted",
        ),
    ]

    block = finalize_audiobook_block(block_index=1, paragraphs=paragraphs, repair=None)

    assert {record.paragraph_id: record.source_latin_unit_count for record in block.records} == {"p1": 2, "p2": 0, "p3": 0}
    state = ProcessingState(narration_paragraphs=list(block.records))
    assert audiobook_narration_summary(state)["latin_source_unit_count"] == 2
