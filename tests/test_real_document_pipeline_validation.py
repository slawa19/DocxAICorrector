import base64
import importlib.util
import io
import json
import os
from io import BytesIO
from pathlib import Path
from contextlib import redirect_stdout

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


PNG_BYTES = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII=")


def _load_validation_module():
    project_root = Path(__file__).resolve().parents[1]
    module_path = project_root / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    spec = importlib.util.spec_from_file_location("run_lietaer_validation", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError("Unable to load run_lietaer_validation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _docx_bytes(document: Document) -> bytes:
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _append_numbering_level(level: str, fmt: str) -> OxmlElement:
    lvl = OxmlElement("w:lvl")
    lvl.set(qn("w:ilvl"), level)

    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    lvl.append(start)

    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), fmt)
    lvl.append(num_fmt)

    lvl_text = OxmlElement("w:lvlText")
    lvl_text.set(
        qn("w:val"),
        "%1." if fmt in {"decimal", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman"} else "•",
    )
    lvl.append(lvl_text)
    return lvl


def _append_multilevel_numbering_definition(document: Document, *, num_id: str, abstract_num_id: str) -> None:
    numbering_root = document.part.numbering_part.element

    abstract_num = OxmlElement("w:abstractNum")
    abstract_num.set(qn("w:abstractNumId"), abstract_num_id)
    abstract_num.append(_append_numbering_level("0", "bullet"))
    abstract_num.append(_append_numbering_level("1", "decimal"))
    numbering_root.append(abstract_num)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), num_id)
    abstract_num_ref = OxmlElement("w:abstractNumId")
    abstract_num_ref.set(qn("w:val"), abstract_num_id)
    num.append(abstract_num_ref)
    numbering_root.append(num)


def _attach_numbering(paragraph, *, num_id: str, ilvl: str) -> None:
    paragraph_properties = paragraph._element.get_or_add_pPr()
    num_pr = paragraph_properties.find(qn("w:numPr"))
    if num_pr is None:
        num_pr = OxmlElement("w:numPr")
        paragraph_properties.append(num_pr)

    ilvl_element = num_pr.find(qn("w:ilvl"))
    if ilvl_element is None:
        ilvl_element = OxmlElement("w:ilvl")
        num_pr.append(ilvl_element)
    ilvl_element.set(qn("w:val"), ilvl)

    num_id_element = num_pr.find(qn("w:numId"))
    if num_id_element is None:
        num_id_element = OxmlElement("w:numId")
        num_pr.append(num_id_element)
    num_id_element.set(qn("w:val"), num_id)


def test_evaluate_lietaer_acceptance_detects_caption_heading_regression(tmp_path):
    validation = _load_validation_module()
    image_path = tmp_path / "caption_image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    source_doc.add_paragraph("Рисунок 1. Подпись")

    output_doc = Document()
    output_doc.add_paragraph().add_run().add_picture(str(image_path))
    output_doc.add_paragraph("Рисунок 1. Подпись", style="Heading 1")

    report = {
        "result": "succeeded",
        "output_artifacts": {
            "output_docx_openable": True,
            "output_contains_placeholder_markup": False,
        },
        "formatting_diagnostics": [],
    }

    acceptance = validation.evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=_docx_bytes(source_doc),
        output_docx_bytes=_docx_bytes(output_doc),
    )

    assert acceptance["passed"] is False
    assert "captions_not_promoted_to_headings" in acceptance["failed_checks"]


def test_evaluate_lietaer_acceptance_detects_center_alignment_regression() -> None:
    validation = _load_validation_module()

    source_doc = Document()
    source_centered = source_doc.add_paragraph("ЭПИКТЕТ")
    source_centered.alignment = WD_ALIGN_PARAGRAPH.CENTER

    output_doc = Document()
    output_doc.add_paragraph("ЭПИКТЕТ")

    report = {
        "result": "succeeded",
        "output_artifacts": {
            "output_docx_openable": True,
            "output_contains_placeholder_markup": False,
        },
        "formatting_diagnostics": [],
    }

    acceptance = validation.evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=_docx_bytes(source_doc),
        output_docx_bytes=_docx_bytes(output_doc),
    )

    assert acceptance["passed"] is False
    assert "centered_short_paragraphs_preserved" in acceptance["failed_checks"]


def test_evaluate_lietaer_acceptance_passes_for_clean_structural_output(tmp_path):
    validation = _load_validation_module()
    image_path = tmp_path / "clean_image.png"
    image_path.write_bytes(PNG_BYTES)

    source_doc = Document()
    centered_title = source_doc.add_paragraph("Глава 1", style="Heading 1")
    centered_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    source_doc.add_paragraph("Первый пункт", style="List Number")
    source_doc.add_paragraph("Второй пункт", style="List Number")
    source_doc.add_paragraph().add_run().add_picture(str(image_path))
    source_caption = source_doc.add_paragraph("Рисунок 1. Корректная подпись")
    source_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    output_doc = Document()
    centered_output_title = output_doc.add_paragraph("Глава 1", style="Heading 1")
    centered_output_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    output_doc.add_paragraph("Первый пункт", style="List Number")
    output_doc.add_paragraph("Второй пункт", style="List Number")
    output_doc.add_paragraph().add_run().add_picture(str(image_path))
    output_caption = output_doc.add_paragraph("Рисунок 1. Корректная подпись")
    output_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    report = {
        "result": "succeeded",
        "output_artifacts": {
            "output_docx_openable": True,
            "output_contains_placeholder_markup": False,
        },
        "formatting_diagnostics": [],
    }

    acceptance = validation.evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=_docx_bytes(source_doc),
        output_docx_bytes=_docx_bytes(output_doc),
    )

    assert acceptance["passed"] is True
    assert acceptance["failed_checks"] == []


def test_evaluate_lietaer_acceptance_allows_centered_text_edits_when_alignment_is_preserved() -> None:
    validation = _load_validation_module()

    source_doc = Document()
    source_quote = source_doc.add_paragraph(
        "Богатство заключается не в том, чтобы иметь много имущества, а в том, чтобы иметь мало желаний."
    )
    source_quote.alignment = WD_ALIGN_PARAGRAPH.CENTER
    source_caption = source_doc.add_paragraph("Рисунок 1.2. Взаимосвязь между потребностями, активами и капиталом")
    source_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    output_doc = Document()
    output_quote = output_doc.add_paragraph("Богатство — не в обилии имущества, а в умении довольствоваться малым.")
    output_quote.alignment = WD_ALIGN_PARAGRAPH.CENTER
    output_caption = output_doc.add_paragraph("Рисунок 1.2. Взаимосвязь потребностей, активов и капитала")
    output_caption.alignment = WD_ALIGN_PARAGRAPH.CENTER

    report = {
        "result": "succeeded",
        "output_artifacts": {
            "output_docx_openable": True,
            "output_contains_placeholder_markup": False,
        },
        "formatting_diagnostics": [],
    }

    acceptance = validation.evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=_docx_bytes(source_doc),
        output_docx_bytes=_docx_bytes(output_doc),
    )

    centered_check = next(check for check in acceptance["checks"] if check["name"] == "centered_short_paragraphs_preserved")
    assert centered_check["passed"] is True
    assert len(centered_check["matches"]) == 2


def test_count_ordered_word_numbered_paragraphs_handles_multilevel_numbering() -> None:
    validation = _load_validation_module()

    document = Document()
    _append_multilevel_numbering_definition(document, num_id="9001", abstract_num_id="9000")

    bullet_paragraph = document.add_paragraph("Маркер")
    first_ordered_paragraph = document.add_paragraph("Первый пункт")
    second_ordered_paragraph = document.add_paragraph("Второй пункт")

    _attach_numbering(bullet_paragraph, num_id="9001", ilvl="0")
    _attach_numbering(first_ordered_paragraph, num_id="9001", ilvl="1")
    _attach_numbering(second_ordered_paragraph, num_id="9001", ilvl="1")

    assert validation._count_ordered_word_numbered_paragraphs(document) == 2


def test_summarize_repeat_runs_detects_intermittent_failures() -> None:
    validation = _load_validation_module()

    summary, acceptance, failure_classification = validation._summarize_repeat_runs(
        [
            {
                "repeat_index": 1,
                "run_id": "run-1",
                "result": "succeeded",
                "acceptance_passed": True,
                "failure_classification": None,
                "signals": {"heading_only_output_detected": False},
            },
            {
                "repeat_index": 2,
                "run_id": "run-2",
                "result": "failed",
                "acceptance_passed": False,
                "failure_classification": "heading_only_output",
                "signals": {"heading_only_output_detected": True},
            },
            {
                "repeat_index": 3,
                "run_id": "run-3",
                "result": "succeeded",
                "acceptance_passed": True,
                "failure_classification": None,
                "signals": {"heading_only_output_detected": False},
            },
        ]
    )

    assert summary["repeat_count"] == 3
    assert summary["pipeline_succeeded_count"] == 2
    assert summary["acceptance_passed_count"] == 2
    assert summary["intermittent_failure_detected"] is True
    assert summary["heading_only_output_detected_count"] == 1
    assert summary["failed_repeat_indexes"] == [2]
    assert acceptance["passed"] is False
    assert acceptance["failed_checks"] == ["all_repeat_runs_succeeded", "all_repeat_runs_acceptance_passed"]
    assert failure_classification == "intermittent_failure"


def test_apply_repeat_count_override_ignores_invalid_value() -> None:
    validation = _load_validation_module()
    run_profile = validation.load_validation_registry().get_run_profile("ui-parity-default")
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        updated = validation._apply_repeat_count_override(run_profile, "abc")

    assert updated.repeat_count == run_profile.repeat_count
    assert "invalid DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE" in buffer.getvalue()


def test_select_repeat_artifact_references_exposes_failing_and_successful_runs() -> None:
    validation = _load_validation_module()

    references = validation._select_repeat_artifact_references(
        [
            {
                "run_id": "run-1",
                "acceptance_passed": False,
                "report_path": "runs/run-1/report.json",
                "summary_path": "runs/run-1/summary.txt",
                "output_artifacts": {
                    "markdown_path": "runs/run-1/output.md",
                    "docx_path": "runs/run-1/output.docx",
                },
            },
            {
                "run_id": "run-2",
                "acceptance_passed": True,
                "report_path": "runs/run-2/report.json",
                "summary_path": "runs/run-2/summary.txt",
                "output_artifacts": {
                    "markdown_path": "runs/run-2/output.md",
                    "docx_path": "runs/run-2/output.docx",
                },
            },
        ]
    )

    assert references["first_failing_run_id"] == "run-1"
    assert references["first_failing_docx_path"] == "runs/run-1/output.docx"
    assert references["representative_success_run_id"] == "run-2"
    assert references["representative_success_markdown_path"] == "runs/run-2/output.md"


def test_write_latest_alias_artifacts_preserves_stable_manifest_schema(tmp_path) -> None:
    validation = _load_validation_module()

    report_path = tmp_path / "run_report.json"
    summary_path = tmp_path / "run_summary.txt"
    progress_path = tmp_path / "run_progress.json"
    markdown_path = tmp_path / "run_output.md"
    docx_path = tmp_path / "run_output.docx"
    latest_report_path = tmp_path / "latest_report.json"
    latest_summary_path = tmp_path / "latest_summary.txt"
    latest_markdown_path = tmp_path / "latest_output.md"
    latest_docx_path = tmp_path / "latest_output.docx"
    latest_manifest_path = tmp_path / "latest.json"

    report_path.write_text("{}", encoding="utf-8")
    summary_path.write_text("summary", encoding="utf-8")
    progress_path.write_text("{}", encoding="utf-8")
    markdown_path.write_text("markdown", encoding="utf-8")
    docx_path.write_bytes(b"PK")

    manifest_payload = {
        "run_id": "run-123",
        "document_profile_id": "lietaer-core",
        "run_profile_id": "ui-parity-default",
        "validation_tier": "full",
        "status": "completed",
        "report_json": validation._path_for_report(report_path),
        "summary_txt": validation._path_for_report(summary_path),
        "progress_json": validation._path_for_report(progress_path),
        "latest_progress_json": validation._path_for_report(progress_path),
        "acceptance_passed": True,
    }

    validation._write_latest_alias_artifacts(
        report_path=report_path,
        summary_path=summary_path,
        markdown_artifact=markdown_path,
        docx_artifact=docx_path,
        latest_report_path=latest_report_path,
        latest_summary_path=latest_summary_path,
        latest_markdown_path=latest_markdown_path,
        latest_docx_path=latest_docx_path,
        latest_manifest_path=latest_manifest_path,
        run_id="run-123",
        run_dir=tmp_path,
        manifest_payload=manifest_payload,
    )

    latest_manifest = json.loads(latest_manifest_path.read_text(encoding="utf-8"))

    assert latest_manifest["status"] == "completed"
    assert latest_manifest["report_json"] == manifest_payload["report_json"]
    assert latest_manifest["summary_txt"] == manifest_payload["summary_txt"]
    assert latest_manifest["progress_json"] == manifest_payload["progress_json"]
    assert latest_manifest["latest_report"] == validation._path_for_report(latest_report_path)
    assert latest_manifest["latest_summary"] == validation._path_for_report(latest_summary_path)


def test_full_tier_runtime_contract_is_nested_only() -> None:
    validation = _load_validation_module()

    runtime_config = validation._build_report_runtime_config(None)

    assert set(runtime_config.keys()) == {"effective", "ui_defaults", "overrides"}


def test_classify_failure_detects_heading_only_output_from_block_rejection_event() -> None:
    validation = _load_validation_module()

    failure_classification = validation.classify_failure(
        {
            "result": "failed",
            "last_error": "",
            "event_log": [
                {
                    "event_id": "block_rejected",
                    "context": {
                        "output_classification": "heading_only_output",
                        "message": "Модель вернула только заголовок при наличии основного текста во входном блоке.",
                    },
                }
            ],
        }
    )

    assert failure_classification == "heading_only_output"


def test_extract_run_formatting_diagnostics_paths_prefers_current_run_artifacts() -> None:
    validation = _load_validation_module()

    event_log = [
        {
            "event_id": "formatting_diagnostics_artifacts_detected",
            "context": {"artifact_paths": [".run\\formatting_diagnostics\\older.json"]},
        },
        {
            "event_id": "formatting_diagnostics_artifacts_detected",
            "context": {
                "artifact_paths": [
                    ".run\\formatting_diagnostics\\normalize_current.json",
                    ".run\\formatting_diagnostics\\preserve_current.json",
                ]
            },
        },
    ]

    assert validation._extract_run_formatting_diagnostics_paths(event_log) == [
        ".run\\formatting_diagnostics\\normalize_current.json",
        ".run\\formatting_diagnostics\\preserve_current.json",
    ]


def test_collect_new_formatting_diagnostics_paths_returns_only_new_files_sorted(tmp_path) -> None:
    validation = _load_validation_module()

    old_path = tmp_path / "old.json"
    new_first = tmp_path / "new_first.json"
    new_second = tmp_path / "new_second.json"
    old_path.write_text("{}", encoding="utf-8")
    new_first.write_text("{}", encoding="utf-8")
    new_second.write_text("{}", encoding="utf-8")

    before = {str(old_path.resolve())}
    after = {str(old_path.resolve()), str(new_second.resolve()), str(new_first.resolve())}

    assert validation._collect_new_formatting_diagnostics_paths(before, after) == [
        str(new_first),
        str(new_second),
    ]


def test_build_environment_snapshot_reports_workspace_runtime(monkeypatch) -> None:
    validation = _load_validation_module()
    monkeypatch.setenv("PYTHONPATH", ".")
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/docxai/.venv")

    snapshot = validation._build_environment_snapshot()

    assert snapshot["project_root"] == "."
    assert isinstance(snapshot["python_executable"], str)
    assert snapshot["python_version"]
    assert snapshot["pythonpath"] == "."
    assert snapshot["virtual_env"] == "/tmp/docxai/.venv"
    assert "is_wsl" in snapshot


def test_format_terminal_progress_line_includes_phase_progress_and_metrics() -> None:
    validation = _load_validation_module()

    line = validation._format_terminal_progress_line(
        event_type="status",
        phase="process",
        stage="Ожидание ответа OpenAI",
        detail="Блок отправлен в модель.",
        progress=0.5,
        elapsed_seconds=12.34,
        metrics={"current_block": 3, "block_count": 6, "output_ratio": 0.91},
    )

    assert "[status]" in line
    assert "[process]" in line
    assert "50.0%" in line
    assert "current_block=3" in line
    assert "block_count=6" in line
    assert "output_ratio=0.91" in line


def test_normalize_terminal_detail_removes_nested_heartbeat_prefixes() -> None:
    validation = _load_validation_module()

    assert validation._normalize_terminal_detail("Heartbeat: Heartbeat: Блок 4 отправлен") == "Блок 4 отправлен"


def test_print_terminal_completion_summary_is_concise() -> None:
    validation = _load_validation_module()
    buffer = io.StringIO()

    with redirect_stdout(buffer):
        validation._print_terminal_completion_summary(
            final_status="failed",
            report={
                "result": "succeeded",
                "progress_path": "tests/artifacts/real_document_pipeline/runs/run-1/lietaer_validation_progress.json",
                "run": {"run_id": "run-1"},
                "output_artifacts": {
                    "report_json": "tests/artifacts/real_document_pipeline/runs/run-1/lietaer_validation_report.json",
                    "summary_txt": "tests/artifacts/real_document_pipeline/runs/run-1/lietaer_validation_summary.txt",
                },
                "acceptance": {
                    "passed": False,
                    "failed_checks": ["centered_short_paragraphs_preserved"],
                },
            },
        )

    output = buffer.getvalue()

    assert "[summary]" in output
    assert "[artifacts]" in output
    assert "[acceptance] failed_checks=centered_short_paragraphs_preserved" in output
    assert "latest_docx_bytes" not in output
    assert "processed_block_markdowns" not in output


def test_validation_progress_tracker_writes_progress_and_manifest(tmp_path) -> None:
    validation = _load_validation_module()

    run_dir = tmp_path / "runs" / "run-1"
    artifact_root = tmp_path
    progress_path = run_dir / "lietaer_validation_progress.json"
    latest_progress_path = artifact_root / "lietaer_validation_progress.json"
    latest_manifest_path = artifact_root / "lietaer_validation_latest.json"
    report_path = run_dir / "lietaer_validation_report.json"
    summary_path = run_dir / "lietaer_validation_summary.txt"
    markdown_path = run_dir / "validated.md"
    docx_path = run_dir / "validated.docx"
    latest_report_path = artifact_root / "lietaer_validation_report.json"
    latest_summary_path = artifact_root / "lietaer_validation_summary.txt"
    latest_markdown_path = artifact_root / "validated.md"
    latest_docx_path = artifact_root / "validated.docx"

    tracker = validation.ValidationProgressTracker(
        run_id="run-1",
        source_path=tmp_path / "source.docx",
        run_dir=run_dir,
        artifact_root=artifact_root,
        progress_path=progress_path,
        latest_progress_path=latest_progress_path,
        latest_manifest_path=latest_manifest_path,
        report_path=report_path,
        summary_path=summary_path,
        markdown_path=markdown_path,
        docx_path=docx_path,
        latest_report_path=latest_report_path,
        latest_summary_path=latest_summary_path,
        latest_markdown_path=latest_markdown_path,
        latest_docx_path=latest_docx_path,
        started_at_utc=validation.datetime.now(validation.UTC),
    )

    tracker.emit(
        event_type="prepare",
        phase="prepare",
        stage="Разбор документа",
        detail="Построено 12 paragraph units.",
        progress=0.2,
        metrics={"job_count": 4},
        print_line=False,
    )
    tracker.finalize(
        status="completed",
        result="succeeded",
        acceptance_passed=True,
        failure_classification=None,
        last_error="",
        detail="Acceptance=passed",
    )

    progress_payload = json.loads(progress_path.read_text(encoding="utf-8"))
    latest_manifest = json.loads(latest_manifest_path.read_text(encoding="utf-8"))

    assert progress_payload["status"] == "completed"
    assert progress_payload["phase"] == "completed"
    assert progress_payload["acceptance_passed"] is True
    assert progress_payload["metrics"] == {"job_count": 4}
    assert latest_manifest["run_id"] == "run-1"
    assert latest_manifest["status"] == "completed"
    assert latest_manifest["progress_json"] == str(progress_path).replace("\\", "/")