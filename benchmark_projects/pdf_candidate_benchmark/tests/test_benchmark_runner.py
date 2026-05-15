from __future__ import annotations

from pathlib import Path

import benchmark_projects.pdf_candidate_benchmark.benchmark_runner as benchmark_runner


def test_recommendation_ignores_heuristic_toc_improvement_without_other_improvement() -> None:
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
        preparation_gate_basis="benchmark_projection_heuristic",
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
        toc_body_concat_detected=False,
        toc_body_concat_detector="benchmark_block_detector:heuristic_benchmark_only",
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
    assert any("evidence provenance is not comparable" in note for note in recommendation["notes"])


def test_recommendation_allows_snapshot_backed_toc_improvement() -> None:
    baseline = benchmark_runner.CandidateResult(
        candidate_id="libreoffice",
        candidate_version="baseline",
        execution_class="docx-normalizer",
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="debug-only",
        metric_basis="benchmark_block_projection",
        preparation_gate_basis="benchmark_structural_proxy",
        artifact_paths={},
        visible_text_chars=1000,
        paragraph_count=100,
        isolated_marker_paragraph_count=10,
        heading_candidates_count=5,
        heading_like_block_count=5,
        list_item_candidates_count=4,
        toc_like_block_count=3,
        preparation_gate_outcome="blocked",
        failed_checks=["toc_body_concat_risk"],
        toc_body_concat_detected=True,
        toc_body_concat_detector="preparation_snapshot:legacy_markdown",
        normalized_text_similarity_to_baseline=1.0,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk="medium",
        first_block_risk_reasons=["first_block_has_toc"],
        first_block_preview="Contents",
        notes=[],
    )
    candidate = benchmark_runner.CandidateResult(
        candidate_id="pdf2docx",
        candidate_version="test",
        execution_class="docx-normalizer",
        status="ok",
        dependency_status="available",
        runtime_platform="linux",
        duration_seconds=1.0,
        diagnostic_mode="debug-only",
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
        preparation_gate_outcome="pass",
        failed_checks=[],
        toc_body_concat_detected=False,
        toc_body_concat_detector="preparation_snapshot:topology_projection",
        normalized_text_similarity_to_baseline=0.99,
        first_20_blocks_have_nonempty_text=True,
        first_block_risk="medium",
        first_block_risk_reasons=["first_block_has_body_start"],
        first_block_preview="Introduction",
        notes=[],
    )

    recommendation = benchmark_runner._recommendation([baseline, candidate], baseline)

    assert recommendation["promising_candidates"] == ["pdf2docx"]
    assert recommendation["outcome"] == "investigate_converter_swap_candidate"


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


def test_docx_structural_proxy_prefers_snapshot_toc_gate_fields_over_preview_detector(monkeypatch) -> None:
    monkeypatch.setattr(
        benchmark_runner,
        "build_preparation_diagnostic_snapshot",
        lambda **kwargs: {
            "toc_entry_count": 1,
            "bounded_toc_region_count": 1,
            "remaining_isolated_marker_count": 0,
            "first_block_has_toc": False,
            "first_block_has_body_start": False,
            "toc_body_concat_detected": False,
            "toc_body_concat_markdown_detected": True,
            "toc_body_concat_structure_detected": False,
            "toc_body_concat_gate_source": "topology_projection",
        },
    )

    result = benchmark_runner._build_docx_structural_proxy(
        paragraphs=[],
        relations=[],
        structure_repair_report=None,
        preview_paragraphs=["Contents........ 1 Introduction"],
    )

    metrics = result["metrics"]
    assert metrics["toc_body_concat_detected"] is False
    assert metrics["toc_body_concat_markdown_detected"] is True
    assert metrics["toc_body_concat_structure_detected"] is False
    assert metrics["toc_body_concat_gate_source"] == "topology_projection"


def test_structural_projection_result_marks_toc_gate_as_heuristic_benchmark_only() -> None:
    projection_text = "Contents........ 1 Introduction"
    candidate_dir = (
        benchmark_runner.REPO_ROOT
        / "benchmark_projects"
        / "pdf_candidate_benchmark"
        / "artifacts"
        / "tmp"
        / "test_structural_projection_result_marks_toc_gate_as_heuristic_benchmark_only"
    )
    candidate_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = benchmark_runner._build_structural_projection_result(
            candidate_id="docling",
            candidate_version="test",
            candidate_dir=candidate_dir,
            projection_text=projection_text,
            blocks=[projection_text],
            duration_seconds=1.0,
        )
    finally:
        for artifact_name in ("projection_preview.txt", "blocks.json"):
            (candidate_dir / artifact_name).unlink(missing_ok=True)
        candidate_dir.rmdir()

    assert result.preparation_gate_basis == "benchmark_projection_heuristic"
    assert result.toc_body_concat_detected is benchmark_runner._detect_toc_body_concat_projection(projection_text)
    assert result.toc_body_concat_detector == "benchmark_block_detector:heuristic_benchmark_only"
    assert any("benchmark-only block heuristic" in note for note in result.notes)