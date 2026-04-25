from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest


_SUPERSCRIPT_PATTERN = re.compile(r"[\u00B9\u00B2\u00B3\u2070-\u2079]")
_URL_PATTERN = re.compile(r"https?://|www\.", re.IGNORECASE)
_TAG_PATTERN = re.compile(r"\[(?:thoughtful|curious|serious|sad|excited|annoyed|sarcastic|whispers|short pause|long pause|sighs|laughs|chuckles|exhales)\]")
_SECTION_SPLIT_PATTERN = re.compile(r"\n\s*\n+")


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_paragraph_text_signature(docx_path: Path, *, limit: int = 80) -> list[str]:
    from docx import Document

    document = Document(str(docx_path))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return paragraphs[:limit]


def _run_validation(project_root: Path, *, run_profile_id: str) -> dict:
    latest_manifest_path = project_root / "tests" / "artifacts" / "real_document_pipeline" / "mazzucato_audiobook_validation_latest.json"
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["DOCXAI_REAL_DOCUMENT_PROFILE"] = "mazzucato-audiobook-core"
    env["DOCXAI_REAL_DOCUMENT_RUN_PROFILE"] = run_profile_id

    completed = subprocess.run(
        ["bash", "scripts/run-real-document-validation.sh"],
        cwd=project_root,
        env=env,
        check=False,
    )

    assert completed.returncode == 0
    assert latest_manifest_path.exists(), "latest Mazzucato manifest was not created"

    latest_manifest = _load_json(latest_manifest_path)
    report_path = project_root / str(latest_manifest["report_json"])
    report = _load_json(report_path)
    return {"manifest": latest_manifest, "report": report}


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("DOCXAI_RUN_REAL_DOCUMENT_AUDIOBOOK_SANITY") != "1",
    reason="real-document audiobook sanity runs only on explicit request",
)
def test_real_document_translate_plus_audiobook_postprocess_sanity() -> None:
    project_root = Path(__file__).resolve().parents[1]
    source_path = project_root / "tests" / "sources" / "The Value of Everything. Making and Taking in the Global Economy by Mariana Mazzucato (z-lib.org).docx"

    if not source_path.exists():
        pytest.skip(f"missing real-document source: {source_path}")

    baseline_run = _run_validation(project_root, run_profile_id="ui-parity-translate-baseline")
    audiobook_run = _run_validation(project_root, run_profile_id="ui-parity-translate-audiobook-postprocess")

    latest_manifest = audiobook_run["manifest"]
    report = audiobook_run["report"]
    baseline_report = baseline_run["report"]

    assert latest_manifest["document_profile_id"] == "mazzucato-audiobook-core"
    assert latest_manifest["run_profile_id"] == "ui-parity-translate-audiobook-postprocess"
    assert report["runtime_config"]["effective"]["processing_operation"] == "translate"
    assert report["runtime_config"]["effective"]["audiobook_postprocess_enabled"] is True
    assert latest_manifest["latest_tts_text"] == report["output_artifacts"]["latest_tts_text_path"]
    assert baseline_report["runtime_config"]["effective"]["processing_operation"] == "translate"
    assert baseline_report["runtime_config"]["effective"]["audiobook_postprocess_enabled"] is False

    output_artifacts = report["output_artifacts"]
    baseline_output_artifacts = baseline_report["output_artifacts"]
    assert output_artifacts["markdown_path"]
    assert output_artifacts["docx_path"]
    assert output_artifacts["tts_text_path"]
    assert baseline_output_artifacts["docx_path"]

    tts_path = project_root / str(output_artifacts["tts_text_path"])
    markdown_path = project_root / str(output_artifacts["markdown_path"])
    docx_path = project_root / str(output_artifacts["docx_path"])
    baseline_docx_path = project_root / str(baseline_output_artifacts["docx_path"])
    assert tts_path.exists(), f"tts artifact missing: {tts_path}"
    assert markdown_path.exists(), f"markdown artifact missing: {markdown_path}"
    assert docx_path.exists(), f"docx artifact missing: {docx_path}"
    assert baseline_docx_path.exists(), f"baseline docx artifact missing: {baseline_docx_path}"

    tts_text = tts_path.read_text(encoding="utf-8")
    markdown_text = markdown_path.read_text(encoding="utf-8")

    assert tts_text.strip()
    sections = [section for section in _SECTION_SPLIT_PATTERN.split(tts_text.strip()) if section.strip()]
    assert sections, "narration artifact has no logical sections"
    assert all(_TAG_PATTERN.search(section) for section in sections), "some narration sections have no ElevenLabs tags"
    assert not re.search(r"^\s*#", tts_text, re.MULTILINE)
    assert not _URL_PATTERN.search(tts_text)
    assert not _SUPERSCRIPT_PATTERN.search(tts_text)
    assert "toc_header" not in tts_text.lower()
    assert markdown_text.strip()

    assert _extract_paragraph_text_signature(docx_path) == _extract_paragraph_text_signature(baseline_docx_path)
