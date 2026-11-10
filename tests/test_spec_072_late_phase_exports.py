"""Spec 072 WP-H: the late phase builds the narration DOCX and PDF (FR-003 (в), FR-005, FR-006, FR-007, FR-008).

The chain under test is the product one: narration records -> ``_build_narration_text`` (real) -> the late phase
(``finalize_processing_success``, real) -> the narration exports -> ``emit_state`` / the result-group writer (the
REAL ``write_ui_result_artifacts`` into ``tmp_path``) / the log. Only the heavy collaborators that have nothing to do
with narration (quality report, reader cleanup, reassembly) are stubbed, and the PDF converter is replaced on
``pipeline.narration_exports`` (research R14: CI has no LibreOffice; the real converter is the system test).

* T-H1 is a characterization test: green before and after the change -- ``translate`` / ``edit`` hand neither a new
  state key nor narration bytes to anyone, and nothing of the export runs.
* T-H2...T-H6 fail without the change (``pipeline.narration_exports`` does not exist; the late phase publishes no
  narration DOCX / PDF, no new event fields, no Stop boundary before the export).

All texts are invented, of the same FORM as book text; no book of the corpus is quoted (Constitution VII).
"""

from __future__ import annotations

import functools
import importlib
import importlib.util
import io
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import docx
import pytest

import docxaicorrector.pipeline.late_phases as late_phases
from docxaicorrector.generation.narration_pdf import NarrationPdfOutcome
from docxaicorrector.pipeline.audiobook_pass import NarrationParagraphRecord, audiobook_narration_summary
from docxaicorrector.pipeline.contracts import ProcessingState
from docxaicorrector.runtime.artifacts import write_ui_result_artifacts
from docxaicorrector.text.narration_coverage import CoverageResult

_EXPORTS_MODULE = "docxaicorrector.pipeline.narration_exports"
_STOP_BEFORE_EXPORT_DETAIL = "Обработка остановлена перед сборкой DOCX и PDF озвучки."
_FAKE_PDF = b"%PDF-1.7\n% synthetic pdf for the late-phase test\n"

# ---------------------------------------------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------------------------------------------


def _exports_module() -> Any:
    """The module under construction; imported lazily so T-H1 runs before it exists."""

    return importlib.import_module(_EXPORTS_MODULE)


class _Emitters:
    def __init__(self) -> None:
        self.state_calls: list[dict[str, object]] = []
        self.finalize_calls: list[dict[str, object]] = []

    def emit_state(self, runtime: object, **values: object) -> None:
        self.state_calls.append(values)

    def emit_finalize(self, runtime: object, stage: str, detail: str, progress: float, terminal_kind: object = None) -> None:
        self.finalize_calls.append({"stage": stage, "detail": detail, "terminal_kind": terminal_kind})

    def emit_log(self, runtime: object, **payload: object) -> None:
        return None


class _Dependencies:
    def __init__(self, output_dir: Path) -> None:
        self.events: list[tuple[int, str, dict[str, object]]] = []
        self.writer_calls: list[dict[str, object]] = []
        self._writer = functools.partial(write_ui_result_artifacts, output_dir=output_dir, run_id="run-072")
        self.should_stop_processing: Callable[[object], bool] = lambda runtime: False

    def log_event(self, level: int, event: str, message: str, **context: object) -> None:
        self.events.append((level, event, context))

    def present_error(self, code: str, exc: BaseException, title: str, **kwargs: object) -> str:
        return f"{title}: {exc}"

    def write_ui_result_artifacts(self, **kwargs: Any) -> dict[str, str]:
        self.writer_calls.append(dict(kwargs))
        return self._writer(**kwargs)

    def write_segment_result_registry(self, *, records: object) -> dict[str, str]:
        return {}

    def named(self, name: str) -> list[tuple[int, dict[str, object]]]:
        return [(level, context) for level, event, context in self.events if event == name]


def _install_stubs(monkeypatch: pytest.MonkeyPatch, *, markdown: str) -> None:
    assembly = SimpleNamespace(final_markdown=markdown, entries=(), diagnostics=None)
    monkeypatch.setattr(late_phases, "assemble_final_markdown", lambda **k: assembly)
    monkeypatch.setattr(
        late_phases, "_build_translation_quality_report", lambda **k: {"quality_status": "pass", "gate_reasons": []}
    )
    monkeypatch.setattr(late_phases, "build_report_acceptance_verdict", lambda *a, **k: {})
    monkeypatch.setattr(late_phases, "_write_quality_report_artifact", lambda **k: None)
    monkeypatch.setattr(
        late_phases,
        "_run_reader_cleanup_postprocess",
        lambda **k: late_phases.ReaderCleanupPostprocessResult(
            markdown=markdown,
            docx_bytes=b"PK\x03\x04 review docx bytes",
            report=None,
            raw_markdown=None,
            result_notice=None,
            final_generated_paragraph_registry=None,
        ),
    )
    monkeypatch.setattr(
        late_phases,
        "build_reassembly_plan",
        lambda **k: SimpleNamespace(assembly_mode="whole", selected_segment_count=None),
    )
    monkeypatch.setattr(late_phases, "build_segment_result_records", lambda **k: [])


def _context(operation: str) -> SimpleNamespace:
    return SimpleNamespace(
        app_config={},
        processing_operation=operation,
        uploaded_filename="book.docx",
        runtime={},
        output_mode="",
        jobs=[],
        source_paragraphs=[],
        model="",
        max_retries=0,
        run_id="run-072",
        source_token="source-072",
    )


def _docx_phase(markdown: str) -> dict[str, object]:
    return {
        "runtime_display_markdown": markdown,
        "latest_result_notice": None,
        "result_manifest": {"manifest": True},
        "base_docx_builder": None,
        "processed_image_assets": [],
        "pre_cleanup_formatting_baseline": None,
    }


def _record(pid: str, text: str, role: str = "body", reasons: tuple[str, ...] = (), level: int | None = None) -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=pid,
        block_index=1,
        role=role,
        text=text,
        needs_review_reasons=reasons,
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
        heading_level=level,
    )


def _audiobook_state(records: Sequence[NarrationParagraphRecord]) -> ProcessingState:
    return ProcessingState(
        processed_chunks=["текст"],
        narration_paragraphs=list(records),
        narration_expected_paragraph_ids=[record.paragraph_id for record in records],
    )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    operation: str,
    state: Any,
    stop: Callable[[object], bool] | None = None,
) -> tuple[str, _Emitters, _Dependencies]:
    markdown = "Итоговый текст для проверки."
    _install_stubs(monkeypatch, markdown=markdown)
    dependencies = _Dependencies(tmp_path / "ui_results")
    if stop is not None:
        dependencies.should_stop_processing = stop
    emitters = _Emitters()
    result = late_phases.finalize_processing_success(
        context=_context(operation),
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        docx_phase=_docx_phase(markdown),
        job_count=1,
        current_markdown_fn=lambda chunks: "",
    )
    return result, emitters, dependencies


class _PdfExportSpy:
    """Stands in for ``export_narration_pdf``: records the DOCX it was handed, returns a fixed outcome."""

    def __init__(self, outcome: NarrationPdfOutcome) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    def __call__(self, docx_bytes: bytes, **kwargs: object) -> NarrationPdfOutcome:
        self.calls.append({"docx_bytes": docx_bytes, **kwargs})
        return self.outcome


def _patch_pdf_export(monkeypatch: pytest.MonkeyPatch, outcome: NarrationPdfOutcome) -> _PdfExportSpy:
    spy = _PdfExportSpy(outcome)
    monkeypatch.setattr(_exports_module(), "export_narration_pdf", spy)
    return spy


def _delivery_call(emitters: _Emitters) -> dict[str, object]:
    calls = [call for call in emitters.state_calls if "latest_narration_text" in call and call.get("last_error") == ""]
    assert len(calls) == 1, emitters.state_calls
    return calls[0]


def _exports_state_value(emitters: _Emitters) -> Mapping[str, object]:
    value = _delivery_call(emitters).get("latest_narration_exports")
    assert isinstance(value, Mapping), "latest_narration_exports is not in the state event that delivers the text"
    return value


def _docx_paragraphs(docx_bytes: bytes) -> list[tuple[str, str]]:
    document = docx.Document(io.BytesIO(docx_bytes))
    return [(str(paragraph.style.name if paragraph.style is not None else ""), paragraph.text) for paragraph in document.paragraphs]


def _saved_event(dependencies: _Dependencies) -> dict[str, object]:
    events = dependencies.named("ui_audiobook_artifact_saved")
    assert len(events) == 1, dependencies.events
    return events[0][1]


# ---------------------------------------------------------------------------------------------------------------
# the SC-001 set: the WP-A golden shapes plus the heading series of FR-003
# ---------------------------------------------------------------------------------------------------------------


def _sc001_records() -> list[NarrationParagraphRecord]:
    return [
        # series 2 -> 1 (a part number, then the chapter title): ONE Heading 1
        _record("s1", "Часть первая", role="heading", level=2),
        _record("s2", "Дорога", role="heading", level=1),
        _record("p2", "Он пришёл в посёлок поздним вечером."),
        # a torn sentence: joined by the assembly into one group with two ids
        _record("p3", "Дорога вела вдоль реки и никто"),
        _record("p4", "не спрашивал, куда он идёт."),
        # a single newline inside one paragraph
        _record("p5", "Первая строка\nвторая строка."),
        # a body paragraph that begins with a hash -- stays a body paragraph
        _record("p6", "# не заголовок, а тело."),
        # a combining acute accent and a capital vowel
        _record("p7", "за́мок и замОк стоят рядом."),
        # needs_review records are narrated like any other
        _record("p8", "Этот абзац вернулся из источника.", reasons=("source_restored",)),
        _record("p9", "Этот абзац целиком взят из источника.", reasons=("source_fallback",)),
        # series 1 -> 2: a Heading 1, then the subsection as a Normal paragraph (not merged)
        _record("s3", "Глава вторая", role="heading", level=1),
        _record("s4", "Подраздел первый", role="heading", level=2),
        _record("s5", "Текст подраздела."),
        # series 3 -> 3 below the chapter level: ONE Normal paragraph; the first part already ends with a dot
        _record("s6", "Пункт А.", role="heading", level=3),
        _record("s7", "Пункт Б", role="heading", level=3),
        _record("s8", "Текст пунктов."),
        # a heading without a level (FR-003 (г)): Normal, never part of a series
        _record("p10", "Подраздел", role="heading"),
        _record("p11", "Последний абзац книги."),
        # a heading at the end of the book stays
        _record("s9", "Послесловие", role="heading", level=1),
    ]


# Written by hand from FR-003 (а)-(г); every row is checked against the product below.
_SC001_EXPECTED_DOCX = [
    ("Heading 1", "Часть первая. Дорога"),
    ("Normal", "Он пришёл в посёлок поздним вечером."),
    ("Normal", "Дорога вела вдоль реки и никто не спрашивал, куда он идёт."),
    ("Normal", "Первая строка\nвторая строка."),
    ("Normal", "# не заголовок, а тело."),
    ("Normal", "за́мок и замОк стоят рядом."),
    ("Normal", "Этот абзац вернулся из источника."),
    ("Normal", "Этот абзац целиком взят из источника."),
    ("Heading 1", "Глава вторая"),
    ("Normal", "Подраздел первый"),
    ("Normal", "Текст подраздела."),
    ("Normal", "Пункт А. Пункт Б"),
    ("Normal", "Текст пунктов."),
    ("Normal", "Подраздел"),
    ("Normal", "Последний абзац книги."),
    ("Heading 1", "Послесловие"),
]


def _docx_equals_tts_with_merges(
    docx_paragraphs: Sequence[tuple[str, str]],
    *,
    tts_text: str,
    groups: Sequence[Any],
    merges: Sequence[Mapping[str, object]],
) -> bool:
    """The ``.tts.docx`` paragraphs are the ``.tts.txt`` paragraphs with exactly the listed merges (SC-001).

    An independent oracle: it reads the ``.tts.txt`` and the merges the event published (by id), and decides the
    style from the role and level of the groups -- a body group is never ``Heading 1``.
    """

    tts_paragraphs = tts_text.split("\n\n")
    if tts_paragraphs != [group.text for group in groups]:
        return False
    levels = [group.heading_level for group in groups if group.role == "heading" and group.heading_level is not None]
    chapter_level = min(levels) if levels else None
    merge_by_first_id = {str(list(m["paragraph_ids"])[0]): m for m in merges}  # type: ignore[call-overload]
    expected: list[tuple[str, str]] = []
    index = 0
    while index < len(groups):
        group = groups[index]
        merge = merge_by_first_id.get(group.paragraph_ids[0]) if group.role == "heading" else None
        if merge is not None:
            member_ids = list(merge["paragraph_ids"])  # type: ignore[call-overload]
            parts: list[str] = []
            while index < len(groups) and groups[index].paragraph_ids[0] in member_ids:
                if groups[index].role != "heading":
                    return False
                parts.append(tts_paragraphs[index])
                index += 1
            text = ""
            for part in parts:
                text = part if not text else (f"{text} {part}" if text.endswith(".") else f"{text}. {part}")
            merge_levels = list(merge["levels"])  # type: ignore[call-overload]
            style = "Heading 1" if min(merge_levels) == chapter_level else "Normal"
            if merge.get("style") != style:
                return False
            expected.append((style, text))
            continue
        is_chapter = group.role == "heading" and group.heading_level is not None and group.heading_level == chapter_level
        expected.append(("Heading 1" if is_chapter else "Normal", tts_paragraphs[index]))
        index += 1
    return list(docx_paragraphs) == expected


# ---------------------------------------------------------------------------------------------------------------
# T-H1 -- characterization: translate / edit are untouched (green before and after)
# ---------------------------------------------------------------------------------------------------------------

# The delivery ``emit_state`` keys and the writer arguments of a translate / edit run, taken on 072/integration
# @ 9b02435 before WP-H. ``model_accounting`` depends on the process-wide accounting of earlier tests and is left out.
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
_NON_AUDIOBOOK_WRITER_KEYS = {"source_name", "markdown_text", "docx_bytes", "assembly_mode", "result_manifest"}


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_t_h1_translate_and_edit_publish_no_narration_exports(monkeypatch, tmp_path, operation):
    calls: list[str] = []

    def _forbidden(name: str) -> Callable[..., object]:
        def _call(*args: object, **kwargs: object) -> object:
            calls.append(name)
            raise AssertionError(f"{name} must not run for {operation}")

        return _call

    import docxaicorrector.generation.narration_docx as narration_docx
    import docxaicorrector.generation.narration_pdf as narration_pdf

    monkeypatch.setattr(narration_pdf, "export_narration_pdf", _forbidden("export_narration_pdf"))
    monkeypatch.setattr(narration_docx, "render_narration_docx", _forbidden("render_narration_docx"))
    if importlib.util.find_spec(_EXPORTS_MODULE) is not None:
        module = _exports_module()
        monkeypatch.setattr(module, "export_narration_pdf", _forbidden("export_narration_pdf"))
        monkeypatch.setattr(module, "render_narration_docx", _forbidden("render_narration_docx"))

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation=operation, state=ProcessingState(processed_chunks=["текст"]))

    assert result == "succeeded"
    assert calls == []
    delivery = _delivery_call(emitters)
    assert set(delivery) == _NON_AUDIOBOOK_DELIVERY_STATE_KEYS
    assert delivery["latest_narration_text"] is None
    assert all("latest_narration_exports" not in call for call in emitters.state_calls)
    assert len(dependencies.writer_calls) == 1
    assert set(dependencies.writer_calls[0]) - {"model_accounting"} == _NON_AUDIOBOOK_WRITER_KEYS
    written = sorted(path.name.split(".result", 1)[1] for path in (tmp_path / "ui_results").iterdir())
    assert written == [".docx", ".manifest.json", ".md", ".meta.json"]
    assert not [event for _level, event, _ctx in dependencies.events if event.startswith("audiobook_")]
    assert not dependencies.named("ui_audiobook_artifact_saved")


# ---------------------------------------------------------------------------------------------------------------
# T-H2 -- SC-001: the .tts.docx is the .tts.txt with exactly the listed merges
# ---------------------------------------------------------------------------------------------------------------


def test_t_h2_tts_docx_is_the_tts_text_with_exactly_the_listed_merges(monkeypatch, tmp_path):
    spy = _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.5, detail=""))
    state = _audiobook_state(_sc001_records())

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    assert result == "succeeded"
    delivery = _delivery_call(emitters)
    tts_text = delivery["latest_narration_text"]
    assert isinstance(tts_text, str)
    exports = _exports_state_value(emitters)
    docx_bytes = exports["docx_bytes"]
    assert isinstance(docx_bytes, bytes) and docx_bytes.startswith(b"PK")
    paragraphs = _docx_paragraphs(docx_bytes)

    saved = _saved_event(dependencies)
    merges = saved["heading_merges"]
    assert merges == [
        {"paragraph_ids": ["s1", "s2"], "levels": [2, 1], "style": "Heading 1"},
        {"paragraph_ids": ["s6", "s7"], "levels": [3, 3], "style": "Normal"},
    ]
    groups = list(state.narration_groups)

    # the product equals the hand-written expectation AND the independent oracle over the .tts.txt
    assert paragraphs == _SC001_EXPECTED_DOCX
    assert _docx_equals_tts_with_merges(paragraphs, tts_text=tts_text, groups=groups, merges=merges)  # type: ignore[arg-type]
    # the exporter got exactly the DOCX that was published
    assert [call["docx_bytes"] for call in spy.calls] == [docx_bytes]

    # negative controls through the SAME comparison function
    dropped = paragraphs[:3] + paragraphs[4:]
    duplicated = paragraphs + [paragraphs[2]]
    body_as_heading = list(paragraphs)
    body_as_heading[1] = ("Heading 1", body_as_heading[1][1])
    for broken in (dropped, duplicated, body_as_heading):
        assert not _docx_equals_tts_with_merges(broken, tts_text=tts_text, groups=groups, merges=merges)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------------------------------------------
# T-H3 -- SC-005: no LibreOffice / a timeout -> the run succeeds with TXT and DOCX, the reason is published
# ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", ["soffice_not_found", "timeout"])
def test_t_h3_pdf_unavailable_is_published_and_the_run_succeeds(monkeypatch, tmp_path, reason):
    seconds = 0.0 if reason == "soffice_not_found" else 60.2
    detail = "" if reason == "soffice_not_found" else "Превышено время ожидания конвертации."
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=None, reason=reason, seconds=seconds, detail=detail))

    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="audiobook", state=_audiobook_state(_sc001_records())
    )

    assert result == "succeeded"
    exports = _exports_state_value(emitters)
    assert isinstance(exports["docx_bytes"], bytes) and exports["docx_bytes"]
    assert exports["pdf_bytes"] is None
    assert exports["docx_unavailable_reason"] is None
    assert exports["pdf_unavailable_reason"] == reason

    writer_kwargs = dependencies.writer_calls[0]
    assert writer_kwargs["narration_docx_bytes"] == exports["docx_bytes"]
    assert writer_kwargs.get("narration_pdf_bytes") is None
    assert isinstance(writer_kwargs["narration_text"], str)

    warnings = dependencies.named("audiobook_narration_pdf_unavailable")
    assert len(warnings) == 1
    level, context = warnings[0]
    assert level == logging.WARNING
    assert context["reason"] == reason
    assert context["filename"] == "book.docx"
    assert context["seconds"] == seconds
    assert context["detail"] == detail
    assert context["timeout_seconds"] == 60
    assert not dependencies.named("audiobook_narration_docx_failed")

    saved = _saved_event(dependencies)
    assert saved["narration_docx_status"] == "built"
    assert saved["narration_pdf_status"] == "unavailable"
    assert saved["narration_pdf_unavailable_reason"] == reason
    assert saved["tts_pdf_path"] is None
    assert isinstance(saved["tts_docx_path"], str) and Path(saved["tts_docx_path"]).read_bytes() == exports["docx_bytes"]
    assert Path(str(saved["tts_text_path"])).is_file()
    assert "processing_completed" in [event for _level, event, _ctx in dependencies.events]


def test_t_h3_a_built_pdf_reaches_state_writer_disk_and_event(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=1.25, detail=""))

    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="audiobook", state=_audiobook_state(_sc001_records())
    )

    assert result == "succeeded"
    exports = _exports_state_value(emitters)
    assert exports["pdf_bytes"] == _FAKE_PDF
    assert exports["pdf_unavailable_reason"] is None
    assert dependencies.writer_calls[0]["narration_pdf_bytes"] == _FAKE_PDF
    assert not dependencies.named("audiobook_narration_pdf_unavailable")
    saved = _saved_event(dependencies)
    assert saved["narration_pdf_status"] == "built"
    assert saved["narration_pdf_unavailable_reason"] is None
    assert saved["narration_pdf_seconds"] == 1.25
    assert Path(str(saved["tts_pdf_path"])).read_bytes() == _FAKE_PDF
    artifact_paths = saved["artifact_paths"]
    assert isinstance(artifact_paths, Mapping)
    assert artifact_paths["tts_docx_path"] == saved["tts_docx_path"]
    assert artifact_paths["tts_pdf_path"] == saved["tts_pdf_path"]


# ---------------------------------------------------------------------------------------------------------------
# T-H4 -- the renderer raises: ERROR, no DOCX, no PDF attempt, the book is still delivered
# ---------------------------------------------------------------------------------------------------------------


def test_t_h4_renderer_failure_is_an_error_and_the_book_is_still_delivered(monkeypatch, tmp_path):
    spy = _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=1.0, detail=""))
    records = _sc001_records()
    # a vertical tab is not allowed in XML: the REAL renderer raises ValueError on it (WP-C, T-C5)
    records[2] = _record("p2", "Он пришёл в посёлок\x0b поздним вечером.")

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=_audiobook_state(records))

    assert result == "succeeded"
    assert spy.calls == []
    exports = _exports_state_value(emitters)
    assert exports == {
        "docx_bytes": None,
        "pdf_bytes": None,
        "docx_unavailable_reason": "render_failed",
        "pdf_unavailable_reason": "docx_not_built",
    }
    errors = dependencies.named("audiobook_narration_docx_failed")
    assert len(errors) == 1
    level, context = errors[0]
    assert level == logging.ERROR
    assert context["error_class"] == "ValueError"
    assert context["filename"] == "book.docx"
    assert context["group_count"] == len(_SC001_EXPECTED_DOCX) + 2  # two members merged away
    assert isinstance(context["error_message"], str) and len(context["error_message"]) <= 300
    pdf_warnings = dependencies.named("audiobook_narration_pdf_unavailable")
    assert [ctx["reason"] for _level, ctx in pdf_warnings] == ["docx_not_built"]

    # Anti-regression 3: the .tts.txt and the DOCX for review are delivered
    writer_kwargs = dependencies.writer_calls[0]
    assert isinstance(writer_kwargs["narration_text"], str) and writer_kwargs["narration_text"]
    assert writer_kwargs.get("narration_docx_bytes") is None
    assert writer_kwargs.get("narration_pdf_bytes") is None
    saved = _saved_event(dependencies)
    assert Path(str(saved["tts_text_path"])).is_file()
    assert Path(str(saved["artifact_paths"]["docx_path"])).is_file()  # type: ignore[index]
    assert saved["tts_docx_path"] is None and saved["tts_pdf_path"] is None
    assert saved["narration_docx_status"] == "failed"
    assert saved["narration_pdf_status"] == "unavailable"
    assert saved["narration_pdf_unavailable_reason"] == "docx_not_built"
    assert saved["narration_docx_paragraph_count"] == 0
    assert _delivery_call(emitters)["latest_narration_text"] == writer_kwargs["narration_text"]


# ---------------------------------------------------------------------------------------------------------------
# T-H5 -- Stop before the export ends the run as stopped (plan deviation О-3)
# ---------------------------------------------------------------------------------------------------------------


def test_t_h5_stop_before_the_export_stops_the_run_and_publishes_nothing(monkeypatch, tmp_path):
    spy = _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=1.0, detail=""))
    rendered: list[object] = []
    module = _exports_module()
    real_render = module.render_narration_docx
    monkeypatch.setattr(module, "render_narration_docx", lambda *a, **k: rendered.append(a) or real_render(*a, **k))
    state = _audiobook_state(_sc001_records())

    # Stop is pressed once the narration text exists: the first boundary after it is the one before the export.
    result, emitters, dependencies = _run(
        monkeypatch, tmp_path, operation="audiobook", state=state, stop=lambda runtime: bool(state.narration_groups)
    )

    assert result == "stopped"
    assert state.narration_groups, "the narration text was built before Stop"
    assert [call["detail"] for call in emitters.finalize_calls] == [_STOP_BEFORE_EXPORT_DETAIL]
    assert emitters.finalize_calls[0]["terminal_kind"] == "stopped"
    assert spy.calls == [] and rendered == []
    assert all("latest_narration_exports" not in call for call in emitters.state_calls)
    assert dependencies.writer_calls == []


# ---------------------------------------------------------------------------------------------------------------
# T-H6 -- the fields of ui_audiobook_artifact_saved; the Studio limits event and notice
# ---------------------------------------------------------------------------------------------------------------

_NEW_SAVED_EVENT_KEYS = {
    "tts_docx_path",
    "tts_pdf_path",
    "narration_docx_status",
    "narration_pdf_status",
    "narration_pdf_unavailable_reason",
    "narration_pdf_seconds",
    "chapter_heading_level",
    "heading_levels_present",
    "heading1_count",
    "demoted_heading_count",
    "heading_merge_count",
    "heading_merges",
    "studio_max_chapter_paragraph_count",
    "studio_max_paragraph_chars",
    "studio_limits_exceeded",
    "narration_docx_paragraph_count",
}
_SPEC_070_SAVED_EVENT_KEYS = {"filename", "source_name", "artifact_paths", "tts_text_path", "char_count"}


def _texts_in(payload: object, texts: Sequence[str]) -> list[str]:
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    return [text for text in texts if text in serialized]


def test_t_h6_saved_event_carries_every_new_key_and_keeps_the_spec_070_ones(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=_FAKE_PDF, reason=None, seconds=0.75, detail=""))
    records = _sc001_records()
    state = _audiobook_state(records)

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=state)

    assert result == "succeeded"
    saved = _saved_event(dependencies)
    # Anti-regression 6: every spec 070 key is still there, unchanged in meaning
    spec_070_keys = _SPEC_070_SAVED_EVENT_KEYS | set(audiobook_narration_summary(state)) | {
        "review_finding_count",
        "review_match_count",
        "review_rules",
    }
    assert spec_070_keys <= set(saved)
    assert saved["char_count"] == len(str(_delivery_call(emitters)["latest_narration_text"]))
    assert saved["deterministic_join_pairs"] == [["p3", "p4"]]
    assert _NEW_SAVED_EVENT_KEYS <= set(saved)
    assert set(saved) == spec_070_keys | _NEW_SAVED_EVENT_KEYS

    assert {key: saved[key] for key in sorted(_NEW_SAVED_EVENT_KEYS - {"tts_docx_path", "tts_pdf_path", "heading_merges"})} == {
        "chapter_heading_level": 1,
        "demoted_heading_count": 2,
        "heading1_count": 3,
        "heading_levels_present": [1, 2, 3],
        "heading_merge_count": 2,
        "narration_docx_paragraph_count": len(_SC001_EXPECTED_DOCX),
        "narration_docx_status": "built",
        "narration_pdf_seconds": 0.75,
        "narration_pdf_status": "built",
        "narration_pdf_unavailable_reason": None,
        "studio_limits_exceeded": [],
        "studio_max_chapter_paragraph_count": 7,
        "studio_max_paragraph_chars": max(len(text) for _style, text in _SC001_EXPECTED_DOCX),
    }
    # within the limits: no event, no notice
    assert not dependencies.named("audiobook_studio_limits_exceeded")
    notices = _delivery_call(emitters)["latest_result_notices"]
    assert isinstance(notices, list)
    assert not [n for n in notices if n.get("message_key") == "result.audiobook_studio_limits_exceeded"]
    # no paragraph text in the new keys (LOGGING §1.5: ids, numbers and codes only)
    texts = [record.text for record in records if len(record.text) >= 5]
    assert _texts_in({key: saved[key] for key in _NEW_SAVED_EVENT_KEYS}, texts) == []


def test_t_h6_a_chapter_of_401_paragraphs_raises_the_studio_limits_event_and_notice(monkeypatch, tmp_path):
    _patch_pdf_export(monkeypatch, NarrationPdfOutcome(pdf_bytes=None, reason="soffice_not_found", seconds=0.0, detail=""))
    records = [_record("h1", "Глава единственная", role="heading", level=1)]
    records += [_record(f"b{n}", f"Абзац номер {n} заканчивается точкой.") for n in range(1, 402)]

    result, emitters, dependencies = _run(monkeypatch, tmp_path, operation="audiobook", state=_audiobook_state(records))

    assert result == "succeeded"
    limits_events = dependencies.named("audiobook_studio_limits_exceeded")
    assert len(limits_events) == 1
    level, context = limits_events[0]
    assert level == logging.WARNING
    assert context == {
        "filename": "book.docx",
        "review_data": True,
        "advisory": True,
        "exceeded": ["chapter_paragraphs"],
        "heading1_count": 1,
        "max_chapter_paragraph_count": 401,
        "max_paragraph_chars": len("Абзац номер 401 заканчивается точкой."),
        "limits": {"chapters": 500, "chapter_paragraphs": 400, "paragraph_chars": 5000},
    }
    saved = _saved_event(dependencies)
    assert saved["studio_limits_exceeded"] == ["chapter_paragraphs"]
    assert saved["studio_max_chapter_paragraph_count"] == 401
    notices = _delivery_call(emitters)["latest_result_notices"]
    assert isinstance(notices, list)
    limit_notices = [n for n in notices if n.get("message_key") == "result.audiobook_studio_limits_exceeded"]
    assert limit_notices == [
        {
            "kind": "narration",
            "level": "warning",
            "message_key": "result.audiobook_studio_limits_exceeded",
            "params": {"limits": "chapter_paragraphs: 401 > 400"},
        }
    ]
    # the new events carry no paragraph text
    texts = [record.text for record in records]
    for name in ("audiobook_studio_limits_exceeded", "audiobook_narration_pdf_unavailable"):
        assert _texts_in([ctx for _level, ctx in dependencies.named(name)], texts) == []
