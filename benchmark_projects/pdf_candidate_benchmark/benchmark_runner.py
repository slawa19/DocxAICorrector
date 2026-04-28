from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import sys
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "corpus_registry.toml").exists() and (candidate / "real_document_validation_profiles.py").exists():
            return candidate
    raise RuntimeError("Could not resolve repository root from benchmark project.")


REPO_ROOT = _resolve_repo_root()
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import processing_runtime  # noqa: E402
from document import build_document_text, build_semantic_blocks, extract_document_content_with_normalization_reports  # noqa: E402
from real_document_validation_profiles import DocumentProfile, load_validation_registry  # noqa: E402
from real_document_validation_structural import build_preparation_diagnostic_snapshot  # noqa: E402


MEANINGFUL_RELATIVE_IMPROVEMENT = 0.20
MIN_VISIBLE_TEXT_CHAR_RATIO_VS_BASELINE = 0.90
ARTIFACT_ROOT = REPO_ROOT / "benchmark_projects" / "pdf_candidate_benchmark" / "artifacts"
RUNS_ROOT = ARTIFACT_ROOT / "runs"
DEFAULT_SOURCE_PROFILE_ID = "end-times-pdf-core"
_TOC_ENTRY_PATTERN = re.compile(
    r"(?:\.{2,}|[\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7]{2,}|\s{2,})\s*[0-9ivxlcdmIVXLCDM]+(?:\s|$)"
)
_LIST_ITEM_PATTERN = re.compile(r"^(?:[-*•●]|\d+[.)])\s+")
_ISOLATED_MARKER_PATTERN = re.compile(r"^(?:[-*•●]|\d+[.)])$")
_TOC_HEADER_PATTERN = re.compile(r"^(?:contents|table of contents|содержание)$", re.IGNORECASE)


@dataclass(frozen=True)
class BenchmarkContext:
    benchmark_run_id: str
    source_profile_id: str
    run_profile_id: str
    source_pdf_path: Path
    source_pdf_bytes: bytes
    source_pdf_sha256: str
    run_dir: Path
    baseline_dir: Path
    thresholds: dict[str, float]


@dataclass
class CandidateResult:
    candidate_id: str
    candidate_version: str
    execution_class: str
    status: str
    dependency_status: str
    runtime_platform: str
    duration_seconds: float
    diagnostic_mode: str
    metric_basis: str
    preparation_gate_basis: str
    artifact_paths: dict[str, str]
    visible_text_chars: int
    paragraph_count: int
    isolated_marker_paragraph_count: int
    heading_candidates_count: int
    heading_like_block_count: int
    list_item_candidates_count: int
    toc_like_block_count: int
    preparation_gate_outcome: str
    failed_checks: list[str]
    toc_body_concat_detected: bool
    toc_body_concat_detector: str
    normalized_text_similarity_to_baseline: float | None
    first_20_blocks_have_nonempty_text: bool | None
    first_block_risk: str
    first_block_risk_reasons: list[str]
    first_block_preview: str
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["duration_seconds"] = round(self.duration_seconds, 3)
        if self.normalized_text_similarity_to_baseline is not None:
            payload["normalized_text_similarity_to_baseline"] = round(self.normalized_text_similarity_to_baseline, 4)
        return payload


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated PDF candidate benchmark.")
    parser.add_argument("--source-profile-id", default=DEFAULT_SOURCE_PROFILE_ID)
    parser.add_argument("--run-profile-id", default="")
    parser.add_argument("--output-root", default=str(RUNS_ROOT))
    return parser.parse_args(list(argv) if argv is not None else None)


def _package_version(distribution_name: str, fallback: str) -> str:
    try:
        return importlib.metadata.version(distribution_name)
    except importlib.metadata.PackageNotFoundError:
        return fallback


def _make_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:8]}"


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _sequence_similarity(left: str, right: str) -> float:
    if not left and not right:
        return 1.0
    return SequenceMatcher(None, _normalize_text(left), _normalize_text(right)).ratio()


def _visible_text_chars(text: str) -> int:
    return sum(1 for char in text if not char.isspace())


def _paragraphs_from_projection(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if chunk.strip()]


def _is_heading_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    word_count = len(stripped.split())
    if word_count == 0 or word_count > 12:
        return False
    alpha_only = re.sub(r"[^A-Za-zА-Яа-яЁё]", "", stripped)
    if alpha_only and alpha_only.upper() == alpha_only and len(alpha_only) >= 3:
        return True
    return not stripped.endswith((".", ":", ";", "?", "!")) and stripped[:1].isupper()


def _is_toc_like(text: str) -> bool:
    stripped = text.strip()
    return bool(_TOC_HEADER_PATTERN.match(stripped) or _TOC_ENTRY_PATTERN.search(stripped))


def _detect_toc_body_concat_projection(text: str) -> bool:
    paragraphs = _paragraphs_from_projection(text)
    for paragraph in paragraphs:
        if _TOC_ENTRY_PATTERN.search(paragraph) and re.search(r"\s+[A-Za-zА-Яа-яЁё]{3,}", paragraph.split()[-1] if paragraph.split() else ""):
            if re.search(r"(?:\.{2,}|[\u2024\u2025\u2026\u2027\u2219\u22c5\u00b7]{2,}|\s{2,})\s*[0-9ivxlcdmIVXLCDM]+\s+[A-Za-zА-Яа-яЁё]", paragraph):
                return True
    return False


def _derive_first_block_risk(first_block: str) -> tuple[str, list[str]]:
    if not first_block.strip():
        return "unknown", ["first_block_empty"]
    reasons: list[str] = []
    lines = [line.strip() for line in first_block.splitlines() if line.strip()]
    joined = "\n".join(lines)
    if any(_is_toc_like(line) for line in lines):
        reasons.append("first_block_has_toc")
    if any(line.startswith(('"', "'", "“", "”", "«")) for line in lines):
        reasons.append("first_block_has_epigraph")
    if any(_is_heading_like(line) and not _is_toc_like(line) for line in lines):
        reasons.append("first_block_has_body_start")
    if any(_ISOLATED_MARKER_PATTERN.match(line) for line in lines):
        reasons.append("first_block_has_isolated_marker")
    if len(joined) > 3000:
        reasons.append("first_block_target_chars_large")
    if not reasons:
        return "low", []
    if any(reason in {"first_block_has_toc", "first_block_has_isolated_marker", "first_block_target_chars_large"} for reason in reasons):
        return "high", reasons
    return "medium", reasons


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _copy_latest_aliases(run_dir: Path, summary_path: Path, manifest_path: Path, report_path: Path) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(summary_path, ARTIFACT_ROOT / "latest_summary.json")
    shutil.copy2(manifest_path, ARTIFACT_ROOT / "latest_manifest.json")
    shutil.copy2(report_path, ARTIFACT_ROOT / "latest_report.txt")
    _write_json(
        ARTIFACT_ROOT / "latest_run.json",
        {
            "benchmark_run_id": run_dir.name,
            "run_dir": _relative_artifact_path(run_dir),
            "summary_path": _relative_artifact_path(summary_path),
            "manifest_path": _relative_artifact_path(manifest_path),
            "report_path": _relative_artifact_path(report_path),
        },
    )


def _relative_artifact_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _load_context(source_profile_id: str, run_profile_id: str, output_root: Path) -> BenchmarkContext:
    registry = load_validation_registry()
    document_profile = registry.get_document_profile(source_profile_id)
    selected_run_profile_id = run_profile_id.strip() or str(document_profile.structural_run_profile or document_profile.default_run_profile or "")
    if not selected_run_profile_id:
        raise RuntimeError(f"Document profile {source_profile_id} does not declare a structural/default run profile.")
    source_pdf_path = document_profile.resolved_source_path(REPO_ROOT)
    source_pdf_bytes = source_pdf_path.read_bytes()
    benchmark_run_id = _make_run_id()
    run_dir = output_root / benchmark_run_id
    return BenchmarkContext(
        benchmark_run_id=benchmark_run_id,
        source_profile_id=source_profile_id,
        run_profile_id=selected_run_profile_id,
        source_pdf_path=source_pdf_path,
        source_pdf_bytes=source_pdf_bytes,
        source_pdf_sha256=hashlib.sha256(source_pdf_bytes).hexdigest(),
        run_dir=run_dir,
        baseline_dir=run_dir / "baseline",
        thresholds={
            "meaningful_relative_improvement": MEANINGFUL_RELATIVE_IMPROVEMENT,
            "min_visible_text_char_ratio_vs_baseline": MIN_VISIBLE_TEXT_CHAR_RATIO_VS_BASELINE,
        },
    )


def _docx_profile_for_artifact(candidate_id: str, artifact_path: Path) -> DocumentProfile:
    relative_source_path = str(artifact_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return DocumentProfile(
        id=f"benchmark-{candidate_id}",
        source_path=relative_source_path,
        artifact_prefix=f"benchmark_{candidate_id}",
        output_basename=artifact_path.stem,
        structural_mode="strict",
        min_paragraphs=1,
        require_nonempty_output=True,
        forbid_heading_only_collapse=True,
        require_toc_detected=False,
        require_pdf_conversion=False,
        require_no_bullet_headings=False,
        require_no_toc_body_concat=False,
        require_translation_domain="theology",
        structural_run_profile=None,
        default_run_profile=None,
        tags=("benchmark", candidate_id),
        provenance="Isolated PDF candidate benchmark temporary DOCX artifact.",
    )


def _extract_docx_projection(docx_bytes: bytes) -> tuple[str, list[str], dict[str, int], list[object], list[object], object | None]:
    paragraphs, _image_assets, _normalization_report, relations, _relation_report, _cleanup_report, structure_repair_report = extract_document_content_with_normalization_reports(BytesIO(docx_bytes))
    text = build_document_text(paragraphs)
    blocks = build_semantic_blocks(paragraphs, max_chars=6000, relations=relations)
    preview_paragraphs = [str(getattr(paragraph, "text", "") or "") for paragraph in paragraphs]
    metrics = {
        "paragraph_count": len(preview_paragraphs),
        "heading_candidates_count": sum(1 for paragraph in paragraphs if str(getattr(paragraph, "role", "") or "") == "heading"),
        "list_item_candidates_count": sum(1 for paragraph in paragraphs if str(getattr(paragraph, "role", "") or "") == "list"),
        "toc_like_block_count": sum(1 for paragraph in paragraphs if str(getattr(paragraph, "structural_role", "") or "") in {"toc_header", "toc_entry"}),
        "isolated_marker_paragraph_count": sum(1 for item in preview_paragraphs if _ISOLATED_MARKER_PATTERN.match(item.strip())),
        "semantic_block_count": len(blocks),
    }
    return text, preview_paragraphs, metrics, list(paragraphs), list(relations), structure_repair_report


def _build_docx_structural_proxy(
    *,
    paragraphs: Sequence[object],
    relations: Sequence[object],
    structure_repair_report: object | None,
    preview_paragraphs: Sequence[str],
) -> dict[str, object]:
    snapshot = build_preparation_diagnostic_snapshot(
        paragraphs=paragraphs,
        relations=relations,
        structure_repair_report=structure_repair_report,
        chunk_size=6000,
        event_log=[],
    )
    preview_text = "\n\n".join(preview_paragraphs)
    failed_checks: list[str] = []
    if int(snapshot.get("toc_entry_count") or 0) > 0 and int(snapshot.get("bounded_toc_region_count") or 0) == 0:
        failed_checks.append("unbounded_toc_region")
    if int(snapshot.get("remaining_isolated_marker_count") or 0) > 0:
        failed_checks.append("isolated_marker_fragments")
    if bool(snapshot.get("first_block_has_toc")) and bool(snapshot.get("first_block_has_body_start")):
        failed_checks.append("toc_body_concat_risk")
    if not preview_text.strip():
        failed_checks.append("empty_output_projection")

    preparation_gate_outcome = "blocked" if failed_checks else "pass"
    readiness_status = "blocked_unsafe_best_effort_only" if failed_checks else "ready"
    return {
        "validation_tier": "structural",
        "validation_execution_mode": "proxy",
        "metric_basis": "benchmark_block_projection",
        "preparation_gate_basis": "benchmark_structural_proxy",
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "metrics": {
            "quality_gate_status": preparation_gate_outcome,
            "readiness_status": readiness_status,
            "toc_body_concat_detected": _detect_toc_body_concat_projection(preview_text),
        },
        "preparation_diagnostic_snapshot": {
            **snapshot,
            "quality_gate_status": preparation_gate_outcome,
            "readiness_status": readiness_status,
        },
    }


def _build_docx_candidate_result(
    *,
    context: BenchmarkContext,
    candidate_id: str,
    candidate_version: str,
    candidate_dir: Path,
    docx_bytes: bytes,
    notes: list[str] | None = None,
) -> CandidateResult:
    start = time.perf_counter()
    candidate_dir.mkdir(parents=True, exist_ok=True)
    normalized_docx_path = candidate_dir / "normalized.docx"
    normalized_docx_path.write_bytes(docx_bytes)
    projection_text, preview_paragraphs, projection_metrics, paragraphs, relations, structure_repair_report = _extract_docx_projection(docx_bytes)
    (candidate_dir / "recovered_preview.txt").write_text("\n\n".join(preview_paragraphs[:20]), encoding="utf-8")
    structural_result = _build_docx_structural_proxy(
        paragraphs=paragraphs,
        relations=relations,
        structure_repair_report=structure_repair_report,
        preview_paragraphs=preview_paragraphs,
    )
    structural_result_path = candidate_dir / "structural_diagnostic.json"
    _write_json(structural_result_path, structural_result)
    snapshot = dict(structural_result.get("preparation_diagnostic_snapshot") or {})
    quality_gate_status = str(snapshot.get("quality_gate_status") or "")
    first_block_preview = "\n\n".join(preview_paragraphs[:5])
    first_block_risk, first_block_risk_reasons = _derive_first_block_risk(first_block_preview)
    if snapshot.get("first_block_has_toc"):
        first_block_risk_reasons = sorted(set([*first_block_risk_reasons, "first_block_has_toc"]))
    if snapshot.get("first_block_has_epigraph"):
        first_block_risk_reasons = sorted(set([*first_block_risk_reasons, "first_block_has_epigraph"]))
    if snapshot.get("first_block_has_body_start"):
        first_block_risk_reasons = sorted(set([*first_block_risk_reasons, "first_block_has_body_start"]))
    if snapshot.get("first_block_has_isolated_marker"):
        first_block_risk_reasons = sorted(set([*first_block_risk_reasons, "first_block_has_isolated_marker"]))
    return CandidateResult(
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        execution_class="docx-normalizer",
        status="ok",
        dependency_status="available",
        runtime_platform=sys.platform,
        duration_seconds=time.perf_counter() - start,
        diagnostic_mode="debug-only",
        metric_basis=str(structural_result.get("metric_basis") or "benchmark_block_projection"),
        preparation_gate_basis=str(structural_result.get("preparation_gate_basis") or "benchmark_structural_proxy"),
        artifact_paths={
            "normalized_docx": _relative_artifact_path(normalized_docx_path),
            "structural_diagnostic": _relative_artifact_path(structural_result_path),
            "recovered_preview": _relative_artifact_path(candidate_dir / "recovered_preview.txt"),
        },
        visible_text_chars=_visible_text_chars(projection_text),
        paragraph_count=projection_metrics["paragraph_count"],
        isolated_marker_paragraph_count=int(snapshot.get("remaining_isolated_marker_count") or projection_metrics["isolated_marker_paragraph_count"]),
        heading_candidates_count=projection_metrics["heading_candidates_count"],
        heading_like_block_count=int(snapshot.get("heading_count") or projection_metrics["heading_candidates_count"]),
        list_item_candidates_count=projection_metrics["list_item_candidates_count"],
        toc_like_block_count=int(snapshot.get("toc_header_count") or 0) + int(snapshot.get("toc_entry_count") or 0) or projection_metrics["toc_like_block_count"],
        preparation_gate_outcome=("blocked" if quality_gate_status == "blocked" else ("pass" if quality_gate_status == "pass" else "error")),
        failed_checks=[str(item) for item in structural_result.get("failed_checks") or []],
        toc_body_concat_detected=bool((structural_result.get("metrics") or {}).get("toc_body_concat_detected")),
        toc_body_concat_detector="benchmark_block_detector",
        normalized_text_similarity_to_baseline=None,
        first_20_blocks_have_nonempty_text=all(bool(paragraph.strip()) for paragraph in preview_paragraphs[:20]),
        first_block_risk=first_block_risk,
        first_block_risk_reasons=first_block_risk_reasons,
        first_block_preview=first_block_preview[:1200],
        notes=[*(notes or []), "DOCX candidate used deterministic preparation-snapshot proxy instead of the full structural passthrough runner."],
    )


def _build_structural_projection_result(
    *,
    candidate_id: str,
    candidate_version: str,
    candidate_dir: Path,
    projection_text: str,
    blocks: list[str],
    duration_seconds: float,
    notes: list[str] | None = None,
) -> CandidateResult:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    preview_path = candidate_dir / "projection_preview.txt"
    blocks_path = candidate_dir / "blocks.json"
    preview_path.write_text("\n\n".join(blocks[:20]), encoding="utf-8")
    _write_json(blocks_path, {"blocks": blocks})
    first_block_preview = blocks[0] if blocks else ""
    first_block_risk, first_block_risk_reasons = _derive_first_block_risk(first_block_preview)
    return CandidateResult(
        candidate_id=candidate_id,
        candidate_version=candidate_version,
        execution_class="structural-extractor",
        status="ok",
        dependency_status="available",
        runtime_platform=sys.platform,
        duration_seconds=duration_seconds,
        diagnostic_mode="benchmark-only",
        metric_basis="benchmark_block_projection",
        preparation_gate_basis="benchmark_structural_proxy",
        artifact_paths={
            "blocks_json": _relative_artifact_path(blocks_path),
            "projection_preview": _relative_artifact_path(preview_path),
        },
        visible_text_chars=_visible_text_chars(projection_text),
        paragraph_count=len(blocks),
        isolated_marker_paragraph_count=sum(1 for block in blocks if _ISOLATED_MARKER_PATTERN.match(block.strip())),
        heading_candidates_count=sum(1 for block in blocks if _is_heading_like(block)),
        heading_like_block_count=sum(1 for block in blocks if _is_heading_like(block)),
        list_item_candidates_count=sum(1 for block in blocks if _LIST_ITEM_PATTERN.match(block.strip())),
        toc_like_block_count=sum(1 for block in blocks if _is_toc_like(block)),
        preparation_gate_outcome="not_applicable",
        failed_checks=[],
        toc_body_concat_detected=_detect_toc_body_concat_projection(projection_text),
        toc_body_concat_detector="benchmark_block_detector",
        normalized_text_similarity_to_baseline=None,
        first_20_blocks_have_nonempty_text=all(bool(block.strip()) for block in blocks[:20]),
        first_block_risk=first_block_risk,
        first_block_risk_reasons=first_block_risk_reasons,
        first_block_preview=first_block_preview[:1200],
        notes=list(notes or []),
    )


def _unsupported_candidate(candidate_id: str, execution_class: str, note: str) -> CandidateResult:
    return CandidateResult(
        candidate_id=candidate_id,
        candidate_version="unavailable",
        execution_class=execution_class,
        status="unsupported",
        dependency_status="missing_optional_dependency",
        runtime_platform=sys.platform,
        duration_seconds=0.0,
        diagnostic_mode="benchmark-only",
        metric_basis="benchmark_block_projection" if execution_class == "structural-extractor" else "existing_docx_diagnostics",
        preparation_gate_basis="unavailable",
        artifact_paths={},
        visible_text_chars=0,
        paragraph_count=0,
        isolated_marker_paragraph_count=0,
        heading_candidates_count=0,
        heading_like_block_count=0,
        list_item_candidates_count=0,
        toc_like_block_count=0,
        preparation_gate_outcome="not_applicable",
        failed_checks=[],
        toc_body_concat_detected=False,
        toc_body_concat_detector="unavailable",
        normalized_text_similarity_to_baseline=None,
        first_20_blocks_have_nonempty_text=None,
        first_block_risk="unknown",
        first_block_risk_reasons=[],
        first_block_preview="",
        notes=[note],
    )


def _error_candidate(candidate_id: str, execution_class: str, candidate_version: str, exc: Exception) -> CandidateResult:
    result = _unsupported_candidate(candidate_id, execution_class, f"{type(exc).__name__}: {exc}")
    result.status = "error"
    result.dependency_status = "available"
    result.candidate_version = candidate_version
    return result


def _run_baseline(context: BenchmarkContext) -> CandidateResult:
    normalized_source = processing_runtime.normalize_uploaded_document(
        filename=context.source_pdf_path.name,
        source_bytes=context.source_pdf_bytes,
    )
    provider = str(getattr(normalized_source, "provider", "libreoffice"))
    return _build_docx_candidate_result(
        context=context,
        candidate_id="libreoffice",
        candidate_version=provider,
        candidate_dir=context.baseline_dir,
        docx_bytes=bytes(normalized_source.content_bytes),
        notes=["Baseline uses repository PDF normalization path."],
    )


def _run_pdf2docx(context: BenchmarkContext) -> CandidateResult:
    start = time.perf_counter()
    try:
        from pdf2docx import Converter  # type: ignore
    except ImportError:
        return _unsupported_candidate("pdf2docx", "docx-normalizer", "Optional dependency pdf2docx is not installed.")
    candidate_dir = context.run_dir / "pdf2docx"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    source_path = candidate_dir / context.source_pdf_path.name
    source_path.write_bytes(context.source_pdf_bytes)
    docx_path = candidate_dir / "normalized.docx"
    converter = Converter(str(source_path))
    try:
        converter.convert(str(docx_path))
    finally:
        converter.close()
    result = _build_docx_candidate_result(
        context=context,
        candidate_id="pdf2docx",
        candidate_version=_package_version("pdf2docx", "unknown"),
        candidate_dir=candidate_dir,
        docx_bytes=docx_path.read_bytes(),
        notes=["DOCX candidate evaluated through repository structural passthrough validation."],
    )
    result.duration_seconds = time.perf_counter() - start
    return result


def _run_docling(context: BenchmarkContext) -> CandidateResult:
    start = time.perf_counter()
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except ImportError:
        return _unsupported_candidate("docling", "structural-extractor", "Optional dependency docling is not installed.")
    candidate_dir = context.run_dir / "docling"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    source_path = candidate_dir / context.source_pdf_path.name
    source_path.write_bytes(context.source_pdf_bytes)
    converter = DocumentConverter()
    result = converter.convert(str(source_path))
    document = getattr(result, "document", None)
    if document is None:
        raise RuntimeError("Docling did not return a document object.")
    if hasattr(document, "export_to_markdown"):
        projection_text = str(document.export_to_markdown() or "")
    elif hasattr(document, "markdown"):
        projection_text = str(getattr(document, "markdown") or "")
    else:
        projection_text = str(document)
    blocks = _paragraphs_from_projection(projection_text)
    benchmark_result = _build_structural_projection_result(
        candidate_id="docling",
        candidate_version=_package_version("docling", "unknown"),
        candidate_dir=candidate_dir,
        projection_text=projection_text,
        blocks=blocks,
        duration_seconds=time.perf_counter() - start,
        notes=["Benchmark-only structural extractor result."],
    )
    return benchmark_result


def _run_pymupdf(context: BenchmarkContext) -> CandidateResult:
    start = time.perf_counter()
    try:
        import fitz  # type: ignore
    except ImportError:
        return _unsupported_candidate("pymupdf", "structural-extractor", "Optional dependency PyMuPDF is not installed.")
    candidate_dir = context.run_dir / "pymupdf"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    source_path = candidate_dir / context.source_pdf_path.name
    source_path.write_bytes(context.source_pdf_bytes)
    blocks: list[str] = []
    document = fitz.open(str(source_path))
    try:
        for page in document:
            page_blocks = page.get_text("blocks")
            sorted_blocks = sorted(page_blocks, key=lambda item: (round(item[1], 3), round(item[0], 3)))
            for block in sorted_blocks:
                text = str(block[4] or "").strip()
                if text:
                    blocks.append(text)
    finally:
        document.close()
    projection_text = "\n\n".join(blocks)
    benchmark_result = _build_structural_projection_result(
        candidate_id="pymupdf",
        candidate_version=_package_version("PyMuPDF", "unknown"),
        candidate_dir=candidate_dir,
        projection_text=projection_text,
        blocks=blocks,
        duration_seconds=time.perf_counter() - start,
        notes=["Minimal block extraction only; no semantic hierarchy beyond benchmark heuristics."],
    )
    return benchmark_result


def _recommendation(candidates: Sequence[CandidateResult], baseline: CandidateResult) -> dict[str, object]:
    baseline_visible = max(baseline.visible_text_chars, 1)
    promising: list[str] = []
    notes: list[str] = []
    for candidate in candidates:
        if candidate.candidate_id == baseline.candidate_id or candidate.status != "ok":
            continue
        char_ratio = candidate.visible_text_chars / baseline_visible
        gate_improved = (
            candidate.execution_class == "docx-normalizer"
            and baseline.preparation_gate_basis == "production_docx_pipeline"
            and candidate.preparation_gate_basis == "production_docx_pipeline"
            and baseline.preparation_gate_outcome == "blocked"
            and candidate.preparation_gate_outcome == "pass"
        )
        toc_improved = baseline.toc_body_concat_detected and not candidate.toc_body_concat_detected
        isolated_baseline = max(baseline.isolated_marker_paragraph_count, 1)
        isolated_improved = (
            candidate.isolated_marker_paragraph_count < baseline.isolated_marker_paragraph_count
            and (baseline.isolated_marker_paragraph_count - candidate.isolated_marker_paragraph_count) / isolated_baseline >= MEANINGFUL_RELATIVE_IMPROVEMENT
        )
        if char_ratio < MIN_VISIBLE_TEXT_CHAR_RATIO_VS_BASELINE:
            notes.append(f"{candidate.candidate_id}: rejected as promising due to visible-text char ratio {char_ratio:.3f}.")
            continue
        if candidate.first_block_risk == "high":
            notes.append(f"{candidate.candidate_id}: not promising because first block risk remained high.")
            continue
        if gate_improved or toc_improved or isolated_improved:
            promising.append(candidate.candidate_id)
    if not promising:
        return {
            "outcome": "keep_libreoffice_and_continue_structural_repair_work",
            "promising_candidates": [],
            "notes": notes or ["No candidate cleared the promising threshold on this run."],
        }
    if any(candidate_id == "pdf2docx" for candidate_id in promising):
        outcome = "investigate_converter_swap_candidate"
    else:
        outcome = "write_integration_spec_for_alternative_structural_extraction_path"
    return {
        "outcome": outcome,
        "promising_candidates": promising,
        "notes": notes,
    }


def _apply_baseline_similarity(candidates: Sequence[CandidateResult], baseline_text: str, text_by_candidate: Mapping[str, str]) -> None:
    for candidate in candidates:
        candidate_text = text_by_candidate.get(candidate.candidate_id, "")
        if candidate.status == "ok":
            candidate.normalized_text_similarity_to_baseline = _sequence_similarity(baseline_text, candidate_text)


def _human_report(context: BenchmarkContext, candidates: Sequence[CandidateResult], recommendation: Mapping[str, object]) -> str:
    lines = [
        f"benchmark_run_id={context.benchmark_run_id}",
        f"source_profile_id={context.source_profile_id}",
        f"run_profile_id={context.run_profile_id}",
        f"source_pdf_path={_relative_artifact_path(context.source_pdf_path)}",
        f"source_pdf_sha256={context.source_pdf_sha256}",
        "",
        "candidate_results:",
    ]
    for candidate in candidates:
        lines.append(
            " | ".join(
                [
                    candidate.candidate_id,
                    f"status={candidate.status}",
                    f"class={candidate.execution_class}",
                    f"gate={candidate.preparation_gate_outcome}/{candidate.preparation_gate_basis}",
                    f"toc_body_concat={candidate.toc_body_concat_detected}",
                    f"visible_text_chars={candidate.visible_text_chars}",
                    f"similarity_to_baseline={candidate.normalized_text_similarity_to_baseline}",
                    f"first_block_risk={candidate.first_block_risk}",
                ]
            )
        )
        if candidate.notes:
            lines.append(f"  notes={'; '.join(candidate.notes)}")
    lines.extend(
        [
            "",
            f"recommendation_outcome={recommendation.get('outcome')}",
            f"promising_candidates={','.join(recommendation.get('promising_candidates') or [])}",
            f"recommendation_notes={json.dumps(list(recommendation.get('notes') or []), ensure_ascii=False)}",
        ]
    )
    return "\n".join(lines) + "\n"


def run_benchmark(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = _parse_args(argv)
    output_root = Path(args.output_root)
    context = _load_context(args.source_profile_id, args.run_profile_id, output_root)
    context.run_dir.mkdir(parents=True, exist_ok=True)

    runners: list[tuple[str, Callable[[BenchmarkContext], CandidateResult]]] = [
        ("libreoffice", _run_baseline),
        ("pdf2docx", _run_pdf2docx),
        ("docling", _run_docling),
        ("pymupdf", _run_pymupdf),
    ]
    text_by_candidate: dict[str, str] = {}
    candidate_results: list[CandidateResult] = []
    baseline_text = ""
    for candidate_id, runner in runners:
        try:
            candidate = runner(context)
        except Exception as exc:
            execution_class = "docx-normalizer" if candidate_id in {"libreoffice", "pdf2docx"} else "structural-extractor"
            candidate = _error_candidate(candidate_id, execution_class, "unknown", exc)
        candidate_results.append(candidate)
        preview_path = candidate.artifact_paths.get("recovered_preview") or candidate.artifact_paths.get("projection_preview")
        if preview_path:
            text_by_candidate[candidate.candidate_id] = (REPO_ROOT / preview_path).read_text(encoding="utf-8")
        else:
            text_by_candidate[candidate.candidate_id] = candidate.first_block_preview
        if candidate.candidate_id == "libreoffice" and candidate.status == "ok":
            baseline_text = text_by_candidate[candidate.candidate_id]

    baseline = next((candidate for candidate in candidate_results if candidate.candidate_id == "libreoffice"), None)
    if baseline is None or baseline.status != "ok":
        raise RuntimeError("Benchmark is invalid without a successful LibreOffice baseline result.")

    _apply_baseline_similarity(candidate_results, baseline_text, text_by_candidate)
    recommendation = _recommendation(candidate_results, baseline)

    manifest = {
        "benchmark_run_id": context.benchmark_run_id,
        "source_pdf_path": _relative_artifact_path(context.source_pdf_path),
        "source_pdf_sha256": context.source_pdf_sha256,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "candidates_requested": [candidate_id for candidate_id, _runner in runners],
        "candidates_completed": [candidate.candidate_id for candidate in candidate_results if candidate.status == "ok"],
        "candidates_unsupported": [candidate.candidate_id for candidate in candidate_results if candidate.status == "unsupported"],
        "thresholds": context.thresholds,
        "artifact_root": _relative_artifact_path(context.run_dir),
    }
    summary = {
        "benchmark_run_id": context.benchmark_run_id,
        "source": {
            "document_profile_id": context.source_profile_id,
            "path": _relative_artifact_path(context.source_pdf_path),
            "sha256": context.source_pdf_sha256,
        },
        "thresholds": context.thresholds,
        "candidates": [candidate.to_dict() for candidate in candidate_results],
        "recommendation": recommendation,
    }

    manifest_path = context.run_dir / "manifest.json"
    summary_path = context.run_dir / "summary.json"
    report_path = context.run_dir / "report.txt"
    _write_json(manifest_path, manifest)
    _write_json(summary_path, summary)
    report_path.write_text(_human_report(context, candidate_results, recommendation), encoding="utf-8")
    _copy_latest_aliases(context.run_dir, summary_path, manifest_path, report_path)
    return {
        "manifest": manifest,
        "summary": summary,
        "manifest_path": str(manifest_path),
        "summary_path": str(summary_path),
        "report_path": str(report_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    payload = run_benchmark(argv)
    print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())