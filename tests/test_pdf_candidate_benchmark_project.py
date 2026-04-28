from __future__ import annotations

from pathlib import Path

import benchmark_projects.pdf_candidate_benchmark.benchmark_runner as benchmark_runner


def _candidate(
    *,
    candidate_id: str,
    execution_class: str,
    visible_text_chars: int,
    isolated_marker_paragraph_count: int,
    toc_body_concat_detected: bool,
    first_block_risk: str,
    preparation_gate_outcome: str = "not_applicable",
    preparation_gate_basis: str = "benchmark_structural_proxy",
) -> benchmark_runner.CandidateResult:
    return benchmark_runner.CandidateResult(
        candidate_id=candidate_id,
        candidate_version="test",
        execution_class=execution_class,
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="canonical" if execution_class == "docx-normalizer" else "benchmark-only",
        metric_basis="existing_docx_diagnostics" if execution_class == "docx-normalizer" else "benchmark_block_projection",
        preparation_gate_basis=preparation_gate_basis,
        artifact_paths={},
        visible_text_chars=visible_text_chars,
        paragraph_count=100,
        isolated_marker_paragraph_count=isolated_marker_paragraph_count,
        heading_candidates_count=5,
        heading_like_block_count=5,
        list_item_candidates_count=4,
        toc_like_block_count=3,
        preparation_gate_outcome=preparation_gate_outcome,
        failed_checks=[],
        toc_body_concat_detected=toc_body_concat_detected,
        toc_body_concat_detector="existing_markdown_detector" if execution_class == "docx-normalizer" else "benchmark_block_detector",
        normalized_text_similarity_to_baseline=1.0,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk=first_block_risk,
        first_block_risk_reasons=[],
        first_block_preview="preview",
        notes=[],
    )


def test_recommendation_rejects_not_applicable_gate_without_other_improvement() -> None:
    baseline = _candidate(
        candidate_id="libreoffice",
        execution_class="docx-normalizer",
        visible_text_chars=1000,
        isolated_marker_paragraph_count=10,
        toc_body_concat_detected=True,
        first_block_risk="high",
        preparation_gate_outcome="blocked",
        preparation_gate_basis="production_docx_pipeline",
    )
    extractor = _candidate(
        candidate_id="docling",
        execution_class="structural-extractor",
        visible_text_chars=950,
        isolated_marker_paragraph_count=10,
        toc_body_concat_detected=True,
        first_block_risk="medium",
    )

    recommendation = benchmark_runner._recommendation([baseline, extractor], baseline)

    assert recommendation["promising_candidates"] == []
    assert recommendation["outcome"] == "keep_libreoffice_and_continue_structural_repair_work"


def test_recommendation_accepts_meaningful_isolated_marker_improvement() -> None:
    baseline = _candidate(
        candidate_id="libreoffice",
        execution_class="docx-normalizer",
        visible_text_chars=1000,
        isolated_marker_paragraph_count=10,
        toc_body_concat_detected=True,
        first_block_risk="high",
        preparation_gate_outcome="blocked",
        preparation_gate_basis="production_docx_pipeline",
    )
    candidate = _candidate(
        candidate_id="pymupdf",
        execution_class="structural-extractor",
        visible_text_chars=950,
        isolated_marker_paragraph_count=4,
        toc_body_concat_detected=False,
        first_block_risk="medium",
    )

    recommendation = benchmark_runner._recommendation([baseline, candidate], baseline)

    assert recommendation["promising_candidates"] == ["pymupdf"]
    assert recommendation["outcome"] == "write_integration_spec_for_alternative_structural_extraction_path"


def test_docx_profile_for_artifact_disables_pdf_conversion_requirement() -> None:
    repo_artifact = benchmark_runner.REPO_ROOT / "benchmark_projects" / "pdf_candidate_benchmark" / "artifacts" / "tmp" / "normalized.docx"
    repo_artifact.parent.mkdir(parents=True, exist_ok=True)
    repo_artifact.write_bytes(b"PK\x03\x04")
    try:
        profile = benchmark_runner._docx_profile_for_artifact("pdf2docx", repo_artifact)
    finally:
        repo_artifact.unlink(missing_ok=True)

    assert profile.require_pdf_conversion is False
    assert profile.require_translation_domain == "theology"
    assert profile.source_path.endswith("benchmark_projects/pdf_candidate_benchmark/artifacts/tmp/normalized.docx")