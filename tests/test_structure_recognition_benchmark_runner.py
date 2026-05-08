from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import SimpleNamespace


def _load_runner_module():
    module_path = Path(__file__).resolve().parents[1] / "benchmark_projects" / "structure_recognition_benchmark" / "benchmark_runner.py"
    spec = spec_from_file_location("structure_recognition_benchmark_runner", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_config(module, *, run_judge: bool = True):
    return module.ResolvedBenchmarkConfig(
        config_path=Path("benchmark_projects/structure_recognition_benchmark/benchmark_config.toml"),
        output_root=Path("benchmark_projects/structure_recognition_benchmark/artifacts"),
        judge_model="openai/gpt-5.5",
        openrouter_base_url="https://openrouter.ai/api/v1",
        openrouter_referer="DocxAICorrectorStructureBenchmark",
        openrouter_title="DocxAICorrector Structure Benchmark",
        judge_prompt_file="benchmark_projects/structure_recognition_benchmark/prompts/structure_judge_rubric.txt",
        judge_prompt_path=Path("benchmark_projects/structure_recognition_benchmark/prompts/structure_judge_rubric.txt"),
        judge_prompt_text="judge prompt",
        profiles=("sample-profile",),
        max_profiles=1,
        max_paragraphs_per_profile=120,
        review_max_windows_per_profile=3,
        review_max_window_paragraphs=50,
        review_overlap_paragraphs=10,
        request_timeout_seconds=90,
        max_retries=3,
        judge_temperature=0.1,
        min_confidence="medium",
        chunk_size=6000,
        run_deterministic_repair=True,
        run_deterministic_validation=True,
        run_segment_detection=True,
        run_judge=run_judge,
        candidate_execution_mode="production_pipeline",
        candidate_inference_parameters="inherit_production_defaults",
        production_windowing_mode="inherit_production_defaults",
        candidates=(
            module.CandidateConfig(
                id="candidate-a",
                label="Candidate A",
                provider="openrouter",
                model="provider/candidate-a",
            ),
        ),
    )


def _build_preparation(module):
    return module.ProfilePreparation(
        profile_id="sample-profile",
        source_path=Path("tests/sources/sample.docx"),
        source_sha256="abc123",
        source_content_hash16="abc123def4567890",
        paragraphs=(),
        repaired_paragraphs=(),
        repair_report=None,
        validation_report=None,
        baseline_segments=(),
        baseline_segment_report=None,
        baseline_structure_fingerprint="fingerprint",
        descriptors=(),
        review_windows=(),
        baseline_metrics={
            "paragraph_count": 10,
            "nonempty_paragraph_count": 10,
            "heading_count_after_apply": 2,
            "toc_header_count_after_apply": 1,
            "toc_entry_count_after_apply": 3,
            "list_evidence_count": 1,
            "segment_count": 4,
            "fallback_segment_count": 0,
            "toc_matched_count": 3,
            "readiness_status": "ready",
            "quality_gate_status": "pass",
            "structure_fingerprint": "fingerprint",
        },
    )


def test_build_summary_for_baseline_only_run_has_no_fabricated_rankings():
    module = _load_runner_module()
    config = _build_config(module)
    preparation = _build_preparation(module)

    summary_payload, summary_markdown = module._build_summary(
        run_id="run-001",
        config=config,
        preparation_by_profile={"sample-profile": preparation},
        candidate_results=[],
        judging_summary={"judge_models_returned": [], "total_judge_cost": 0.0},
    )

    assert summary_payload["candidate_count"] == 0
    assert summary_payload["rankings"] == []
    assert "No paid candidate executions were run" in summary_markdown
    assert "baseline-only run" in summary_markdown


def test_json_from_response_text_accepts_plain_json_object():
    module = _load_runner_module()

    payload = module._json_from_response_text('{"candidate_scores": {"candidate-a": {"weighted_score": 91}}}')

    assert payload == {"candidate_scores": {"candidate-a": {"weighted_score": 91}}}


def test_build_summary_with_executed_candidate_includes_ranking(monkeypatch):
    module = _load_runner_module()
    config = _build_config(module, run_judge=False)
    preparation = _build_preparation(module)

    monkeypatch.setattr(module, "load_validation_registry", lambda: SimpleNamespace(get_document_profile=lambda _profile_id: SimpleNamespace(structural_expected_result="warning")))

    candidate_result = module.CandidateProfileResult(
        candidate=config.candidates[0],
        profile_id="sample-profile",
        ok=True,
        error=None,
        structure_map_payload={},
        applied_summary={},
        metrics={
            "schema_violation_count": 0,
            "classified_count": 4,
            "average_latency_seconds": 1.25,
            "readiness_status": "ready",
            "deterministic_pipeline_score": 100.0,
        },
        flags=[],
        severe_flags=[],
        validation_payload={},
        segment_payload={},
        usage={"cost": 0.01, "cost_known": True},
        records=[],
        returned_models=["provider/candidate-a-2026-05-08"],
    )
    candidate_result.judge_weighted_score = 82.0
    candidate_result.pairwise_wins = 1.0
    candidate_result.pairwise_total = 1.0

    summary_payload, summary_markdown = module._build_summary(
        run_id="run-002",
        config=config,
        preparation_by_profile={"sample-profile": preparation},
        candidate_results=[candidate_result],
        judging_summary={"judge_models_returned": ["openai/gpt-5.5"], "total_judge_cost": 0.0},
    )

    assert summary_payload["candidate_count"] == 1
    assert summary_payload["rankings"][0]["candidate_id"] == "candidate-a"
    assert "Candidate A" in summary_markdown
    assert "No paid candidate executions were run" not in summary_markdown