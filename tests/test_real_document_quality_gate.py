from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("DOCXAI_RUN_REAL_DOCUMENT_QUALITY") != "1",
        reason="real-document quality gate runs only on explicit exceptional request",
    ),
]


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_document_quality_gate_passes_and_updates_latest_manifest() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source_path = project_root / "tests" / "sources" / "Лиетар глава1.docx"
    latest_manifest_path = project_root / "tests" / "artifacts" / "real_document_pipeline" / "lietaer_validation_latest.json"

    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    completed = subprocess.run(
        ["bash", "scripts/run-real-document-validation.sh"],
        cwd=project_root,
        env=env,
        check=False,
    )

    assert latest_manifest_path.exists(), "latest manifest was not created"
    latest_manifest = _load_json(latest_manifest_path)

    report_path = project_root / str(latest_manifest["report_json"])
    summary_path = project_root / str(latest_manifest["summary_txt"])
    progress_path = project_root / str(latest_manifest["progress_json"])

    assert progress_path.exists(), "progress json was not created"
    assert report_path.exists(), f"report missing: {report_path}"
    assert summary_path.exists(), f"summary missing: {summary_path}"

    report = _load_json(report_path)
    progress = _load_json(progress_path)

    assert completed.returncode == 0, json.dumps(
        {
            "returncode": completed.returncode,
            "run_id": latest_manifest.get("run_id"),
            "status": latest_manifest.get("status"),
            "failure_classification": report.get("failure_classification"),
            "failed_checks": report.get("acceptance", {}).get("failed_checks"),
            "last_error": report.get("last_error"),
            "report_json": latest_manifest.get("report_json"),
            "summary_txt": latest_manifest.get("summary_txt"),
        },
        ensure_ascii=False,
        indent=2,
    )
    assert latest_manifest["status"] == "completed"
    assert progress["status"] == "completed"
    assert report["result"] == "succeeded"
    assert report["acceptance"]["passed"] is True
    assert latest_manifest["acceptance_passed"] is True
    assert latest_manifest["run_id"] == report["run"]["run_id"]
    assert report["output_artifacts"]["report_json"] == latest_manifest["report_json"]