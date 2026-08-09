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

import pytest

import docxaicorrector.pipeline._pipeline as document_pipeline
import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.pipeline.quality_gate as quality_gate
import docxaicorrector.ui._ui as ui
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
    assert quality_gate.build_source_text_delivery_notice(facts) is None


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

    notice = quality_gate.build_source_text_delivery_notice(facts)
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

    notice = quality_gate.build_source_text_delivery_notice(facts)
    assert notice is not None
    assert notice["message_key"] == "result.source_text_delivered_with_unanchored"


def test_source_text_delivery_ignores_a_block_without_a_per_paragraph_record() -> None:
    """A passthrough block is a plain ``str``: no record, no claim (Constitution VII)."""
    facts = quality_gate.build_source_text_delivery_facts(["Обычный блок без записи."])

    assert facts["paragraph_count"] == 0
    assert quality_gate.build_source_text_delivery_notice(facts) is None


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

    assert quality_gate.build_source_text_delivery_notice(facts) is None


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
    assert quality_gate.build_source_text_delivery_notice(facts) is not None


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
    assert delivered[0]["message_key"] == "result.source_text_delivered"
    assert dict(delivered[0]["params"])["count"] == 1  # type: ignore[arg-type]
    assert list(delivered[0]["anchors"]) == ["Once upon a time in a small village."]  # type: ignore[arg-type]
    assert [
        event for event in events if event["event_id"] == "source_text_delivered_to_document"
    ]


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
