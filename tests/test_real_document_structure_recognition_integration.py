from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from config import load_project_dotenv


pytestmark = [pytest.mark.integration]


AI_RUN_PROFILE_ID = "ui-parity-ai-default"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_lietaer_real_validation_uses_canonical_ai_profile() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source_path = project_root / "tests" / "sources" / "Лиетар глава1.docx"
    latest_manifest_path = project_root / "tests" / "artifacts" / "real_document_pipeline" / "lietaer_validation_latest.json"

    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")
    load_project_dotenv()
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        pytest.skip("OPENAI_API_KEY is required for real AI structure-recognition smoke")

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["DOCXAI_REAL_DOCUMENT_PROFILE"] = "lietaer-core"
    env["DOCXAI_REAL_DOCUMENT_RUN_PROFILE"] = AI_RUN_PROFILE_ID

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

    assert report_path.exists(), f"report missing: {report_path}"
    assert summary_path.exists(), f"summary missing: {summary_path}"

    report = _load_json(report_path)
    summary_text = summary_path.read_text(encoding="utf-8")

    assert completed.returncode == 0, json.dumps(
        {
            "returncode": completed.returncode,
            "run_id": latest_manifest.get("run_id"),
            "status": latest_manifest.get("status"),
            "run_profile_id": latest_manifest.get("run_profile_id"),
            "failure_classification": report.get("failure_classification"),
            "failed_checks": report.get("acceptance", {}).get("failed_checks"),
            "report_json": latest_manifest.get("report_json"),
            "summary_txt": latest_manifest.get("summary_txt"),
        },
        ensure_ascii=False,
        indent=2,
    )
    assert latest_manifest["status"] == "completed"
    assert latest_manifest["run_profile_id"] == AI_RUN_PROFILE_ID
    assert report["result"] == "succeeded"
    assert report["run_profile_id"] == AI_RUN_PROFILE_ID
    assert report["acceptance"]["passed"] is True
    assert report["runtime_config"]["effective"]["structure_recognition_enabled"] is True
    assert report["runtime_config"]["overrides"]["structure_recognition_enabled"] is True
    assert report["preparation"]["ai_classified_count"] > 0
    assert report["preparation"]["ai_heading_count"] > 0
    assert report["preparation"]["ai_role_change_count"] >= 0
    assert report["preparation"]["ai_heading_promotion_count"] >= 0
    assert report["preparation"]["ai_heading_demotion_count"] >= 0
    assert report["preparation"]["ai_structural_role_change_count"] >= 0
    assert "run_profile_id=ui-parity-ai-default" in summary_text
    assert 'runtime_overrides={"enable_paragraph_markers": true, "structure_recognition_enabled": true}' in summary_text
    assert "ai_classified_count=" in summary_text
    assert "ai_heading_count=" in summary_text
    assert "ai_role_change_count=" in summary_text
    assert "ai_heading_promotion_count=" in summary_text
    assert "ai_heading_demotion_count=" in summary_text
    assert "ai_structural_role_change_count=" in summary_text