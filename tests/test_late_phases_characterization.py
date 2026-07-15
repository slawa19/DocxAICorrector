"""Characterization safety net for ``pipeline/late_phases.py`` (spec 031, Step 0).

Snapshots the behaviour of the late-phase quality-gate / acceptance / delivery
functions and the Cluster E quality-report retention I/O to canonical sorted-JSON
goldens under ``tests/fixtures/late_phases_characterization/``. These goldens MUST
stay byte-identical across every behaviour-preserving decomposition step of spec 031
(Cluster E extraction and beyond).

Inputs are built fully offline: ``_build_translation_quality_report`` is a pure
function over ``context`` / ``final_markdown`` / ``assembly_result``; the retention
functions touch only a monkeypatched temp directory; and the monkeypatch-contract
test drives ``run_docx_build_phase`` with fake ``dependencies``/``emitters``/``state``.

To regenerate the goldens after an intentional, reviewed behaviour change, run::

    UPDATE_LATE_PHASES_GOLDEN=1 <run this test>
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import docxaicorrector.pipeline.late_phases as late_phases
import docxaicorrector.pipeline.output_validation as output_validation
import docxaicorrector.pipeline.quality_report_retention as quality_report_retention

# spec 031 Step 1: the retention constant/functions now live in
# ``pipeline.quality_report_retention``. Because ``_write_quality_report_artifact``
# reads ``QUALITY_REPORTS_DIR`` from its OWN module (situation 2), the retention tests
# below patch the module that owns the reader — the new module, not the
# ``late_phases`` re-export (which would not propagate to the moved function).
_RETENTION_MODULE = quality_report_retention

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "late_phases_characterization"
_UPDATE = os.environ.get("UPDATE_LATE_PHASES_GOLDEN") == "1"


def _canonical(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)


def _assert_golden(name: str, obj: object) -> None:
    path = _FIXTURE_DIR / f"{name}.json"
    serialized = _canonical(obj)
    if _UPDATE:
        _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
        return
    assert path.exists(), f"missing golden fixture: {path} (run UPDATE_LATE_PHASES_GOLDEN=1)"
    expected = path.read_text(encoding="utf-8")
    assert serialized == expected, f"golden diff for {name}"


def _ctx(**over: object) -> SimpleNamespace:
    base: dict[str, object] = dict(
        app_config={"translation_output_quality_gate_policy": "strict"},
        processing_operation="translate",
        uploaded_filename="report.docx",
        translation_domain="general",
    )
    base.update(over)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# _build_translation_quality_report matrix
# --------------------------------------------------------------------------- #


def test_quality_report_clean_pass_golden():
    report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown="Переведённый абзац текста для итоговой проверки качества.",
        formatting_diagnostics_artifacts=[],
    )
    assert report["quality_status"] == "pass"
    _assert_golden("clean_pass", report)


def test_quality_report_hygiene_bullet_marker_heading_golden():
    report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown="## ●\n\nПереведённый абзац",
        formatting_diagnostics_artifacts=[],
    )
    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["bullet_marker_headings_review_required"]
    _assert_golden("hygiene_bullet_marker_heading", report)


def test_quality_report_manual_review_untranslated_structural_golden():
    assembly_result = output_validation.FinalMarkdownAssemblyResult(
        final_markdown="## The Competitive Society\n\n## Terra\n\nПереведённый текст.",
        entries=(
            output_validation.FinalAssemblyEntry(
                text="## The Competitive Society",
                block_index=1, paragraph_id="p1", source_index=0,
                role="heading", structural_role="heading", heading_level=2, from_registry=True,
            ),
            output_validation.FinalAssemblyEntry(
                text="## Terra",
                block_index=1, paragraph_id="p2", source_index=1,
                role="heading", structural_role="heading", heading_level=2, from_registry=True,
            ),
            output_validation.FinalAssemblyEntry(
                text="Переведённый текст.",
                block_index=1, paragraph_id="p3", source_index=2,
                role="body", structural_role="body", from_registry=True,
            ),
        ),
        diagnostics=output_validation.FinalAssemblyDiagnostics(),
    )
    report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown=assembly_result.final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )
    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["untranslated_structural_text_review_required"]
    _assert_golden("manual_review_untranslated_structural", report)


def test_quality_report_untranslated_body_fail_golden():
    untranslated_body = (
        "This framework has been tested using years of quantitative data collected about how biomass "
        "flows through natural ecosystems. Natural ecosystems are large complex flow networks that "
        "show how resilience and efficiency interact across many scales. "
    ) * 12
    assembly_result = output_validation.FinalMarkdownAssemblyResult(
        final_markdown=untranslated_body,
        entries=(
            output_validation.FinalAssemblyEntry(
                text=untranslated_body,
                block_index=1, paragraph_id="p1", source_index=0,
                role="body", structural_role="body", from_registry=True,
            ),
        ),
        diagnostics=output_validation.FinalAssemblyDiagnostics(),
    )
    report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown=assembly_result.final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly_result,
    )
    assert report["quality_status"] == "fail"
    assert report["gate_reasons"] == ["untranslated_body_text_above_threshold"]
    _assert_golden("untranslated_body_fail", report)


def test_quality_report_toc_body_concat_golden():
    report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown="Заключение ........ 29 Введение",
        formatting_diagnostics_artifacts=[],
    )
    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == ["toc_body_concatenation_review_required"]
    _assert_golden("toc_body_concat", report)


def test_quality_report_controlled_fallback_combo_golden():
    report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown="## ●\n\nЗаключение ........ 29 Введение",
        formatting_diagnostics_artifacts=[],
    )
    assert report["quality_status"] == "warn"
    assert report["gate_reasons"] == [
        "bullet_marker_headings_review_required",
        "toc_body_concatenation_review_required",
    ]
    _assert_golden("controlled_fallback_combo", report)


# --------------------------------------------------------------------------- #
# build_report_acceptance_verdict + _resolve_document_delivery_verdict
# --------------------------------------------------------------------------- #


def test_acceptance_verdict_clean_golden():
    clean_report = late_phases._build_translation_quality_report(
        context=_ctx(),
        final_markdown="Переведённый абзац текста для итоговой проверки качества.",
        formatting_diagnostics_artifacts=[],
    )
    acceptance_context = {
        "result": "succeeded",
        "runtime_config": {"effective": {"processing_operation": "translate"}},
        "translation_quality_report": dict(clean_report),
        "formatting_diagnostics": [],
        "output_artifacts": {},
        "runtime": {},
        "reader_cleanup_evidence": {},
        "preparation_diagnostic_snapshot": {},
    }
    verdict = late_phases.build_report_acceptance_verdict(acceptance_context)
    _assert_golden("acceptance_verdict_clean", verdict)


def test_resolve_document_delivery_verdict_transitions_golden():
    review_grade_reasons = [
        "role_loss_above_manual_review_threshold",
        "heading_demotion_above_manual_review_threshold",
        "false_fragment_headings_present",
        "list_fragment_regressions_present",
        "unmapped_source_paragraphs_present",
        "toc_body_concatenation_detected",
        "mixed_script_terms_present",
    ]
    transitions: dict[str, str] = {}
    for reason in review_grade_reasons:
        transitions[f"fail::{reason}"] = late_phases._resolve_document_delivery_verdict(
            quality_status="fail", gate_reasons=[reason]
        )
    transitions["fail::untranslated_body_text_above_threshold"] = (
        late_phases._resolve_document_delivery_verdict(
            quality_status="fail", gate_reasons=["untranslated_body_text_above_threshold"]
        )
    )
    transitions["fail::mixed_fatal"] = late_phases._resolve_document_delivery_verdict(
        quality_status="fail",
        gate_reasons=[
            "role_loss_above_manual_review_threshold",
            "untranslated_body_text_above_threshold",
        ],
    )
    transitions["pass::empty"] = late_phases._resolve_document_delivery_verdict(
        quality_status="pass", gate_reasons=[]
    )
    transitions["warn::empty"] = late_phases._resolve_document_delivery_verdict(
        quality_status="warn", gate_reasons=[]
    )
    _assert_golden("delivery_verdict_transitions", transitions)


# --------------------------------------------------------------------------- #
# Cluster E retention: _prune_quality_reports + _write_quality_report_artifact
# --------------------------------------------------------------------------- #


def _touch_report(target_dir: Path, name: str, *, age_seconds: float = 0.0) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / name
    path.write_text("{}", encoding="utf-8")
    if age_seconds:
        past = time.time() - age_seconds
        os.utime(path, (past, past))
    return path


def test_prune_quality_reports_removes_reports_older_than_max_age(tmp_path):
    target_dir = tmp_path / "quality_reports"
    fresh = _touch_report(target_dir, "fresh.json")
    stale = _touch_report(
        target_dir, "stale.json",
        age_seconds=late_phases.QUALITY_REPORTS_MAX_AGE_SECONDS + 3600,
    )
    late_phases._prune_quality_reports(target_dir=target_dir)
    assert fresh.exists()
    assert not stale.exists()


def test_prune_quality_reports_caps_count_evicting_oldest(tmp_path, monkeypatch):
    target_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(_RETENTION_MODULE, "QUALITY_REPORTS_MAX_COUNT", 3)
    # Create 5 reports with strictly increasing mtimes so eviction order is deterministic.
    created: list[Path] = []
    for index in range(5):
        path = _touch_report(target_dir, f"report_{index}.json")
        past = time.time() - (100 - index)  # older -> newer
        os.utime(path, (past, past))
        created.append(path)
    late_phases._prune_quality_reports(target_dir=target_dir)
    survivors = sorted(p.name for p in target_dir.glob("*.json"))
    # Only the 3 newest (highest index) survive; the 2 oldest are evicted.
    assert survivors == ["report_2.json", "report_3.json", "report_4.json"]


def test_prune_quality_reports_noop_on_missing_dir(tmp_path):
    # Must not raise when the directory does not exist.
    late_phases._prune_quality_reports(target_dir=tmp_path / "does_not_exist")


def test_write_quality_report_artifact_writes_json_and_returns_path(tmp_path, monkeypatch):
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(_RETENTION_MODULE, "QUALITY_REPORTS_DIR", quality_dir)
    payload = {"quality_status": "pass", "gate_reasons": [], "value": "Переведено"}
    result_path = late_phases._write_quality_report_artifact(
        source_name="my report!.docx", payload=payload
    )
    assert result_path is not None
    written = Path(result_path)
    assert written.exists()
    assert written.parent == quality_dir
    # Filename is sanitized (no spaces / punctuation runs, no bang).
    assert " " not in written.name and "!" not in written.name
    assert json.loads(written.read_text(encoding="utf-8")) == payload


def test_write_quality_report_artifact_prunes_after_write(tmp_path, monkeypatch):
    quality_dir = tmp_path / "quality_reports"
    monkeypatch.setattr(_RETENTION_MODULE, "QUALITY_REPORTS_DIR", quality_dir)
    # Seed a stale artifact that the post-write prune must remove.
    stale = _touch_report(
        quality_dir, "old_document_1.json",
        age_seconds=late_phases.QUALITY_REPORTS_MAX_AGE_SECONDS + 3600,
    )
    result_path = late_phases._write_quality_report_artifact(
        source_name="document", payload={"quality_status": "pass"}
    )
    assert result_path is not None
    assert not stale.exists()
    assert Path(result_path).exists()


# --------------------------------------------------------------------------- #
# Monkeypatch-contract regression (pins the Cluster D re-export requirement)
# --------------------------------------------------------------------------- #


def test_run_docx_build_phase_observes_patched_collect_recent(tmp_path, monkeypatch):
    """``run_docx_build_phase`` reads ``collect_recent_formatting_diagnostics_artifacts``
    as a ``late_phases`` module global. Patching that global via monkeypatch MUST be
    observed by the function — this pins the re-export contract for later decomposition
    steps (Cluster D), where the function moves out but is re-exported back."""
    observed: list[dict[str, object]] = []

    def _fake_collect(*, since_epoch_seconds, diagnostics_dir):
        observed.append(
            {"since_epoch_seconds": since_epoch_seconds, "diagnostics_dir": str(diagnostics_dir)}
        )
        return []

    monkeypatch.setattr(
        late_phases, "collect_recent_formatting_diagnostics_artifacts", _fake_collect
    )

    diagnostics_dir = tmp_path / "formatting_diagnostics"

    context = SimpleNamespace(
        # processing_operation != "translate" keeps reader-cleanup OFF, so the base
        # DOCX is built inline and ``collect_recent_...`` is reached.
        processing_operation="correct",
        app_config={},
        output_mode="",
        jobs=[{"target_text": "block", "context_before": "", "context_after": "", "target_chars": 5, "context_chars": 0}],
        source_paragraphs=[],
        uploaded_filename="report.docx",
        source_token="",
        run_id="",
        runtime={},
        on_progress=lambda **kwargs: None,
    )
    dependencies = SimpleNamespace(
        convert_markdown_to_docx_bytes=lambda markdown_text: b"docx-bytes",
        preserve_source_paragraph_properties=lambda docx_bytes, paragraphs, generated_paragraph_registry=None: docx_bytes,
        reinsert_inline_images=lambda docx_bytes, image_assets: docx_bytes,
        present_error=lambda code, exc, title, **kwargs: f"{title}: {exc}",
        log_event=lambda *args, **kwargs: None,
    )
    emitters = SimpleNamespace(
        emit_status=lambda *args, **kwargs: None,
        emit_activity=lambda *args, **kwargs: None,
        emit_state=lambda *args, **kwargs: None,
        emit_log=lambda *args, **kwargs: None,
    )
    state = SimpleNamespace(
        processed_chunks=["Обработанный блок"],
        generated_paragraph_registry=[],
    )

    result = late_phases.run_docx_build_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        image_phase={"processed_image_assets": []},
        job_count=1,
        diagnostics_dir=diagnostics_dir,
        current_markdown_fn=lambda chunks: "",
        call_docx_restorer_with_optional_registry_fn=lambda fn, docx_bytes, paragraphs, registry: docx_bytes,
    )

    assert result is not None
    assert len(observed) == 1, "patched collect_recent_... was not observed"
    assert observed[0]["diagnostics_dir"] == str(diagnostics_dir)
