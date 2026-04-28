from __future__ import annotations

from pathlib import Path

import benchmark_projects.pdf_candidate_benchmark.benchmark_runner as benchmark_runner


def test_recommendation_rejects_not_applicable_gate_without_other_improvement() -> None:
    baseline = benchmark_runner.CandidateResult(
        candidate_id="libreoffice",
        candidate_version="baseline",
        execution_class="docx-normalizer",
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="canonical",
        metric_basis="existing_docx_diagnostics",
        preparation_gate_basis="production_docx_pipeline",
        artifact_paths={},
        visible_text_chars=1000,
        paragraph_count=100,
        isolated_marker_paragraph_count=10,
        heading_candidates_count=5,
        heading_like_block_count=5,
        list_item_candidates_count=4,
        toc_like_block_count=3,
        preparation_gate_outcome="blocked",
        failed_checks=["preparation_quality_gate_blocked"],
        toc_body_concat_detected=True,
        toc_body_concat_detector="existing_markdown_detector",
        normalized_text_similarity_to_baseline=1.0,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk="high",
        first_block_risk_reasons=["first_block_has_toc"],
        first_block_preview="Contents",
        notes=[],
    )
    extractor = benchmark_runner.CandidateResult(
        candidate_id="docling",
        candidate_version="test",
        execution_class="structural-extractor",
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="benchmark-only",
        metric_basis="benchmark_block_projection",
        preparation_gate_basis="benchmark_structural_proxy",
        artifact_paths={},
        visible_text_chars=950,
        paragraph_count=100,
        isolated_marker_paragraph_count=10,
        heading_candidates_count=5,
        heading_like_block_count=5,
        list_item_candidates_count=4,
        toc_like_block_count=3,
        preparation_gate_outcome="not_applicable",
        failed_checks=[],
        toc_body_concat_detected=True,
        toc_body_concat_detector="benchmark_block_detector",
        normalized_text_similarity_to_baseline=0.99,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk="medium",
        first_block_risk_reasons=["first_block_has_body_start"],
        first_block_preview="Introduction",
        notes=[],
    )

    recommendation = benchmark_runner._recommendation([baseline, extractor], baseline)

    assert recommendation["promising_candidates"] == []
    assert recommendation["outcome"] == "keep_libreoffice_and_continue_structural_repair_work"


def test_recommendation_accepts_meaningful_isolated_marker_improvement() -> None:
    baseline = benchmark_runner.CandidateResult(
        candidate_id="libreoffice",
        candidate_version="baseline",
        execution_class="docx-normalizer",
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="canonical",
        metric_basis="existing_docx_diagnostics",
        preparation_gate_basis="production_docx_pipeline",
        artifact_paths={},
        visible_text_chars=1000,
        paragraph_count=100,
        isolated_marker_paragraph_count=10,
        heading_candidates_count=5,
        heading_like_block_count=5,
        list_item_candidates_count=4,
        toc_like_block_count=3,
        preparation_gate_outcome="blocked",
        failed_checks=["preparation_quality_gate_blocked"],
        toc_body_concat_detected=True,
        toc_body_concat_detector="existing_markdown_detector",
        normalized_text_similarity_to_baseline=1.0,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk="high",
        first_block_risk_reasons=["first_block_has_toc"],
        first_block_preview="Contents",
        notes=[],
    )
    candidate = benchmark_runner.CandidateResult(
        candidate_id="pymupdf",
        candidate_version="test",
        execution_class="structural-extractor",
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="benchmark-only",
        metric_basis="benchmark_block_projection",
        preparation_gate_basis="benchmark_structural_proxy",
        artifact_paths={},
        visible_text_chars=950,
        paragraph_count=100,
        isolated_marker_paragraph_count=4,
        heading_candidates_count=8,
        heading_like_block_count=8,
        list_item_candidates_count=4,
        toc_like_block_count=3,
        preparation_gate_outcome="not_applicable",
        failed_checks=[],
        toc_body_concat_detected=False,
        toc_body_concat_detector="benchmark_block_detector",
        normalized_text_similarity_to_baseline=0.99,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk="medium",
        first_block_risk_reasons=["first_block_has_body_start"],
        first_block_preview="Introduction",
        notes=[],
    )

    recommendation = benchmark_runner._recommendation([baseline, candidate], baseline)

    assert recommendation["promising_candidates"] == ["pymupdf"]
    assert recommendation["outcome"] == "write_integration_spec_for_alternative_structural_extraction_path"


def test_docx_profile_for_artifact_disables_pdf_conversion_requirement(tmp_path: Path) -> None:
    artifact = tmp_path / "candidate" / "normalized.docx"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"PK\x03\x04")

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