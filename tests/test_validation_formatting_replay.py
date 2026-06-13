from __future__ import annotations

import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from docx import Document

from docxaicorrector.validation.formatting_replay import replay_formatting_diagnostics_from_report


def _build_docx_bytes(paragraphs: list[str]) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_replay_formatting_diagnostics_from_report_recomputes_from_saved_final_docx(tmp_path: Path):
    target_docx_path = tmp_path / "target.docx"
    target_docx_path.write_bytes(_build_docx_bytes(["Heading translated", "Body translated"]))

    report_path = tmp_path / "report.json"
    report_payload = {
        "output_artifacts": {"docx_path": str(target_docx_path)},
        "formatting_diagnostics": [
            {
                "stage": "post_cleanup",
                "mapped_count": 0,
                "unmapped_source_ids": ["p0001", "p0002"],
                "unmapped_target_indexes": [0, 1],
                "source_registry": [
                    {
                        "paragraph_id": "p0001",
                        "source_index": 0,
                        "text_preview": "Heading translated",
                        "role": "heading",
                        "structural_role": "heading",
                        "heading_level": 1,
                    },
                    {
                        "paragraph_id": "p0002",
                        "source_index": 1,
                        "text_preview": "Body translated",
                        "role": "body",
                        "structural_role": "body",
                    },
                ],
            }
        ],
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    replayed = replay_formatting_diagnostics_from_report(report_path=report_path)

    assert replayed["source_reconstruction_basis"] == "saved_source_registry_preview"
    assert replayed["replay_scope"] == "restore_diagnostics_from_saved_final_docx"
    assert replayed["replay_mode"] == "no_llm_current_mapping_code"
    assert replayed["replay_fidelity"] == "matched_saved_source_count"
    assert replayed["saved_mapped_count"] == 0
    replayed_diagnostics = replayed["replayed_diagnostics"]
    assert replayed_diagnostics["mapped_count"] == 2
    assert replayed["replayed_summary"]["unmapped_source_count"] == 0
    role_aware_summary = replayed["replayed_summary"]["role_aware_summary"]
    assert role_aware_summary is None or role_aware_summary["effective_unmapped_source_count"] == 0


def test_classify_formatting_residuals_replay_mode_reports_replayed_restore_diagnostics(tmp_path: Path):
    target_docx_path = tmp_path / "target.docx"
    target_docx_path.write_bytes(_build_docx_bytes(["Heading translated", "Body translated"]))

    report_path = tmp_path / "report.json"
    report_payload = {
        "output_artifacts": {"docx_path": str(target_docx_path)},
        "formatting_diagnostics": [
            {
                "stage": "post_cleanup",
                "mapped_count": 0,
                "unmapped_source_ids": ["p0001", "p0002"],
                "unmapped_target_indexes": [0, 1],
                "source_registry": [
                    {
                        "paragraph_id": "p0001",
                        "source_index": 0,
                        "text_preview": "Heading translated",
                        "role": "heading",
                        "structural_role": "heading",
                        "heading_level": 1,
                    },
                    {
                        "paragraph_id": "p0002",
                        "source_index": 1,
                        "text_preview": "Body translated",
                        "role": "body",
                        "structural_role": "body",
                    },
                ],
            }
        ],
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/classify-formatting-residuals.py",
            str(report_path),
            "--replay",
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["classification_basis"] == "replayed_restore_diagnostics"
    assert payload["replay_scope"] == "restore_diagnostics_from_saved_final_docx"
    assert payload["replay_mode"] == "no_llm_current_mapping_code"
    assert payload["source_reconstruction_basis"] == "saved_source_registry_preview"
    assert payload["replay_fidelity"] == "matched_saved_source_count"
    assert payload["saved_mapped_count"] == 0
    assert payload["mapped_count"] == 2
    assert payload["unmapped_source_count"] == 0
