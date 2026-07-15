from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import itertools
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from statistics import median
from typing import Any


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "corpus_registry.toml").exists() and (candidate / "src" / "docxaicorrector").exists():
            return candidate
    raise RuntimeError("Could not resolve repository root from benchmark project.")


REPO_ROOT = _resolve_repo_root()
SRC_ROOT = REPO_ROOT / "src"
BENCHMARK_ROOT = REPO_ROOT / "benchmark_projects" / "structure_recognition_benchmark"
ARTIFACT_ROOT = BENCHMARK_ROOT / "artifacts"
RUNS_ROOT = ARTIFACT_ROOT / "runs"
DEFAULT_CONFIG_PATH = BENCHMARK_ROOT / "benchmark_config.toml"


def _ensure_src_first_import_order(repo_root: Path, src_root: Path) -> None:
    repo_root_str = str(repo_root)
    src_root_str = str(src_root)
    sys.path[:] = [entry for entry in sys.path if entry not in {repo_root_str, src_root_str}]
    sys.path.insert(0, repo_root_str)
    sys.path.insert(0, src_root_str)


_ensure_src_first_import_order(REPO_ROOT, SRC_ROOT)

OpenAI = None
processing_runtime = None
load_project_dotenv = None
load_app_config = None
extract_document_content_with_normalization_reports = None
load_validation_registry = None
repair_pdf_derived_structure = None
validate_structure_quality = None
build_paragraph_descriptors = None
build_structure_map = None
apply_structure_map = None
detect_document_segments = None
collect_response_text_traversal = None
read_response_field = None
extract_unsupported_parameter_name = None
is_retryable_error = None
parse_json_object = None


def _ensure_project_imports() -> None:
    global OpenAI
    global processing_runtime
    global load_project_dotenv
    global load_app_config
    global extract_document_content_with_normalization_reports
    global load_validation_registry
    global repair_pdf_derived_structure
    global validate_structure_quality
    global build_paragraph_descriptors
    global build_structure_map
    global apply_structure_map
    global detect_document_segments
    global collect_response_text_traversal
    global read_response_field
    global extract_unsupported_parameter_name
    global is_retryable_error
    global parse_json_object

    if OpenAI is not None:
        return

    from openai import OpenAI as imported_openai

    import docxaicorrector.processing.processing_runtime as imported_processing_runtime
    from docxaicorrector.core.config import (
        load_app_config as imported_load_app_config,
        load_project_dotenv as imported_load_project_dotenv,
    )
    from docxaicorrector.document._document import (
        extract_document_content_with_normalization_reports as imported_extract_document_content_with_normalization_reports,
    )
    from docxaicorrector.document.segments import detect_document_segments as imported_detect_document_segments
    from docxaicorrector.document.structure_repair import repair_pdf_derived_structure as imported_repair_pdf_derived_structure
    from docxaicorrector.generation.openai_response_utils import (
        collect_response_text_traversal as imported_collect_response_text_traversal,
        read_response_field as imported_read_response_field,
    )
    from docxaicorrector.image.shared import (
        extract_unsupported_parameter_name as imported_extract_unsupported_parameter_name,
        is_retryable_error as imported_is_retryable_error,
        parse_json_object as imported_parse_json_object,
    )
    from docxaicorrector.structure.recognition import (
        apply_structure_map as imported_apply_structure_map,
        build_paragraph_descriptors as imported_build_paragraph_descriptors,
        build_structure_map as imported_build_structure_map,
    )
    from docxaicorrector.structure.validation import validate_structure_quality as imported_validate_structure_quality
    from docxaicorrector.validation.profiles import load_validation_registry as imported_load_validation_registry

    OpenAI = imported_openai
    processing_runtime = imported_processing_runtime
    load_project_dotenv = imported_load_project_dotenv
    load_app_config = imported_load_app_config
    extract_document_content_with_normalization_reports = imported_extract_document_content_with_normalization_reports
    load_validation_registry = imported_load_validation_registry
    repair_pdf_derived_structure = imported_repair_pdf_derived_structure
    validate_structure_quality = imported_validate_structure_quality
    build_paragraph_descriptors = imported_build_paragraph_descriptors
    build_structure_map = imported_build_structure_map
    apply_structure_map = imported_apply_structure_map
    detect_document_segments = imported_detect_document_segments
    collect_response_text_traversal = imported_collect_response_text_traversal
    read_response_field = imported_read_response_field
    extract_unsupported_parameter_name = imported_extract_unsupported_parameter_name
    is_retryable_error = imported_is_retryable_error
    parse_json_object = imported_parse_json_object


@dataclass(frozen=True)
class CandidateConfig:
    id: str
    label: str
    provider: str
    model: str


@dataclass(frozen=True)
class ResolvedBenchmarkConfig:
    config_path: Path
    output_root: Path
    judge_model: str
    openrouter_base_url: str
    openrouter_referer: str
    openrouter_title: str
    judge_prompt_file: str
    judge_prompt_path: Path
    judge_prompt_text: str
    profiles: tuple[str, ...]
    max_profiles: int
    max_paragraphs_per_profile: int
    review_max_windows_per_profile: int
    review_max_window_paragraphs: int
    review_overlap_paragraphs: int
    request_timeout_seconds: int
    max_retries: int
    judge_temperature: float
    min_confidence: str
    chunk_size: int
    run_deterministic_repair: bool
    run_deterministic_validation: bool
    run_segment_detection: bool
    run_judge: bool
    candidate_execution_mode: str
    candidate_inference_parameters: str
    production_windowing_mode: str
    candidates: tuple[CandidateConfig, ...]


@dataclass(frozen=True)
class ReviewWindow:
    id: str
    start_index: int
    end_index: int
    descriptors: tuple[object, ...]
    rationale: str
    expected_covered: bool = True


@dataclass(frozen=True)
class ProfilePreparation:
    profile_id: str
    source_path: Path
    source_sha256: str
    source_content_hash16: str
    paragraphs: tuple[object, ...]
    repaired_paragraphs: tuple[object, ...]
    repair_report: object | None
    validation_report: object | None
    baseline_segments: tuple[object, ...]
    baseline_segment_report: object | None
    baseline_structure_fingerprint: str
    descriptors: tuple[object, ...]
    review_windows: tuple[ReviewWindow, ...]
    baseline_metrics: dict[str, object]


@dataclass(frozen=True)
class CapturedResponseRecord:
    request_index: int
    requested_model: str
    response_model: str
    generation_id: str
    duration_seconds: float
    raw_text: str
    usage: dict[str, object]
    payload_summary: dict[str, object]
    error: str | None = None


@dataclass
class CandidateProfileResult:
    candidate: CandidateConfig
    profile_id: str
    ok: bool
    error: str | None
    structure_map_payload: dict[str, object]
    applied_summary: dict[str, object]
    metrics: dict[str, object]
    flags: list[str]
    severe_flags: list[str]
    validation_payload: dict[str, object]
    segment_payload: dict[str, object]
    usage: dict[str, object]
    records: list[CapturedResponseRecord]
    returned_models: list[str]
    review_classifications: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    judge_weighted_score: float | None = None
    pairwise_wins: float = 0.0
    pairwise_total: float = 0.0


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{uuid.uuid4().hex[:8]}"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _write_text(path: Path, content: str) -> None:
    _ensure_parent(path)
    path.write_text(content, encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    _write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _coerce_str(value: object, *, field_name: str) -> str:
    resolved = str(value or "").strip()
    if not resolved:
        raise RuntimeError(f"Missing required string field: {field_name}")
    return resolved


def _coerce_int(value: object, *, field_name: str, minimum: int = 0) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid integer for {field_name}: {value!r}") from exc
    if resolved < minimum:
        raise RuntimeError(f"Expected {field_name} >= {minimum}, got {resolved}")
    return resolved


def _coerce_float(value: object, *, field_name: str, minimum: float = 0.0) -> float:
    try:
        resolved = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid float for {field_name}: {value!r}") from exc
    if resolved < minimum:
        raise RuntimeError(f"Expected {field_name} >= {minimum}, got {resolved}")
    return resolved


def _coerce_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise RuntimeError(f"Invalid boolean for {field_name}: {value!r}")


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return json.dumps(value)
    return json.dumps(str(value), ensure_ascii=False)


def _toml_array(values: Sequence[object]) -> str:
    return "[" + ", ".join(_toml_scalar(value) for value in values) + "]"


def _render_config_snapshot(config: ResolvedBenchmarkConfig) -> str:
    lines = ["[benchmark]"]
    lines.append(f"judge_model = {_toml_scalar(config.judge_model)}")
    lines.append(f"openrouter_base_url = {_toml_scalar(config.openrouter_base_url)}")
    lines.append(f"openrouter_referer = {_toml_scalar(config.openrouter_referer)}")
    lines.append(f"openrouter_title = {_toml_scalar(config.openrouter_title)}")
    lines.append(f"judge_prompt_file = {_toml_scalar(config.judge_prompt_file)}")
    lines.append(f"profiles = {_toml_array(config.profiles)}")
    lines.append(f"max_profiles = {_toml_scalar(config.max_profiles)}")
    lines.append(f"max_paragraphs_per_profile = {_toml_scalar(config.max_paragraphs_per_profile)}")
    lines.append(f"review_max_windows_per_profile = {_toml_scalar(config.review_max_windows_per_profile)}")
    lines.append(f"review_max_window_paragraphs = {_toml_scalar(config.review_max_window_paragraphs)}")
    lines.append(f"review_overlap_paragraphs = {_toml_scalar(config.review_overlap_paragraphs)}")
    lines.append(f"request_timeout_seconds = {_toml_scalar(config.request_timeout_seconds)}")
    lines.append(f"max_retries = {_toml_scalar(config.max_retries)}")
    lines.append(f"judge_temperature = {_toml_scalar(config.judge_temperature)}")
    lines.append(f"min_confidence = {_toml_scalar(config.min_confidence)}")
    lines.append(f"chunk_size = {_toml_scalar(config.chunk_size)}")
    lines.append(f"run_deterministic_repair = {_toml_scalar(config.run_deterministic_repair)}")
    lines.append(f"run_deterministic_validation = {_toml_scalar(config.run_deterministic_validation)}")
    lines.append(f"run_segment_detection = {_toml_scalar(config.run_segment_detection)}")
    lines.append(f"run_judge = {_toml_scalar(config.run_judge)}")
    lines.append(f"candidate_execution_mode = {_toml_scalar(config.candidate_execution_mode)}")
    lines.append(f"candidate_inference_parameters = {_toml_scalar(config.candidate_inference_parameters)}")
    lines.append(f"production_windowing_mode = {_toml_scalar(config.production_windowing_mode)}")
    for candidate in config.candidates:
        lines.append("")
        lines.append("[[candidates]]")
        lines.append(f"id = {_toml_scalar(candidate.id)}")
        lines.append(f"label = {_toml_scalar(candidate.label)}")
        lines.append(f"provider = {_toml_scalar(candidate.provider)}")
        lines.append(f"model = {_toml_scalar(candidate.model)}")
    return "\n".join(lines) + "\n"


def _load_config(args: argparse.Namespace) -> ResolvedBenchmarkConfig:
    config_path = Path(args.config or DEFAULT_CONFIG_PATH)
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    benchmark = payload.get("benchmark")
    if not isinstance(benchmark, dict):
        raise RuntimeError("Config must define [benchmark].")

    candidate_tables = payload.get("candidates")
    if not isinstance(candidate_tables, list) or not candidate_tables:
        raise RuntimeError("Config must define at least one [[candidates]] entry.")

    selected_ids = set(_parse_csv(args.candidates))
    candidates: list[CandidateConfig] = []
    for item in candidate_tables:
        if not isinstance(item, dict):
            raise RuntimeError("Each [[candidates]] entry must be a table.")
        candidate = CandidateConfig(
            id=_coerce_str(item.get("id"), field_name="candidates.id"),
            label=_coerce_str(item.get("label"), field_name="candidates.label"),
            provider=_coerce_str(item.get("provider"), field_name="candidates.provider"),
            model=_coerce_str(item.get("model"), field_name="candidates.model"),
        )
        if candidate.provider != "openrouter":
            raise RuntimeError(f"Unsupported provider for MVP: {candidate.provider}")
        if selected_ids and candidate.id not in selected_ids:
            continue
        candidates.append(candidate)

    if not candidates and not args.baseline_only:
        raise RuntimeError("No candidate models remain after filtering.")

    configured_profiles = benchmark.get("profiles")
    if not isinstance(configured_profiles, list) or not configured_profiles:
        raise RuntimeError("benchmark.profiles must be a non-empty list.")
    profiles = tuple(str(item).strip() for item in configured_profiles if str(item).strip())
    cli_profiles = _parse_csv(args.profiles)
    if cli_profiles:
        profiles = cli_profiles

    max_profiles = _coerce_int(benchmark.get("max_profiles", len(profiles)), field_name="benchmark.max_profiles", minimum=1)
    if args.max_profiles is not None:
        max_profiles = max(1, int(args.max_profiles))
    profiles = profiles[:max_profiles]

    output_root = Path(args.output_root or ARTIFACT_ROOT)
    if not output_root.is_absolute():
        output_root = (REPO_ROOT / output_root).resolve()

    judge_prompt_file = _coerce_str(benchmark.get("judge_prompt_file"), field_name="benchmark.judge_prompt_file")
    judge_prompt_path = (REPO_ROOT / judge_prompt_file).resolve()
    judge_prompt_text = judge_prompt_path.read_text(encoding="utf-8").strip()

    return ResolvedBenchmarkConfig(
        config_path=config_path,
        output_root=output_root,
        judge_model=_coerce_str(benchmark.get("judge_model"), field_name="benchmark.judge_model"),
        openrouter_base_url=_coerce_str(benchmark.get("openrouter_base_url"), field_name="benchmark.openrouter_base_url"),
        openrouter_referer=_coerce_str(benchmark.get("openrouter_referer"), field_name="benchmark.openrouter_referer"),
        openrouter_title=_coerce_str(benchmark.get("openrouter_title"), field_name="benchmark.openrouter_title"),
        judge_prompt_file=judge_prompt_file,
        judge_prompt_path=judge_prompt_path,
        judge_prompt_text=judge_prompt_text,
        profiles=profiles,
        max_profiles=max_profiles,
        max_paragraphs_per_profile=(
            int(args.max_paragraphs_per_profile)
            if args.max_paragraphs_per_profile is not None
            else _coerce_int(benchmark.get("max_paragraphs_per_profile", 450), field_name="benchmark.max_paragraphs_per_profile", minimum=1)
        ),
        review_max_windows_per_profile=_coerce_int(
            benchmark.get("review_max_windows_per_profile", 4),
            field_name="benchmark.review_max_windows_per_profile",
            minimum=1,
        ),
        review_max_window_paragraphs=_coerce_int(
            benchmark.get("review_max_window_paragraphs", 180),
            field_name="benchmark.review_max_window_paragraphs",
            minimum=1,
        ),
        review_overlap_paragraphs=_coerce_int(
            benchmark.get("review_overlap_paragraphs", 20),
            field_name="benchmark.review_overlap_paragraphs",
            minimum=0,
        ),
        request_timeout_seconds=_coerce_int(
            benchmark.get("request_timeout_seconds", 90),
            field_name="benchmark.request_timeout_seconds",
            minimum=1,
        ),
        max_retries=_coerce_int(benchmark.get("max_retries", 3), field_name="benchmark.max_retries", minimum=1),
        judge_temperature=_coerce_float(benchmark.get("judge_temperature", 0.1), field_name="benchmark.judge_temperature", minimum=0.0),
        min_confidence=_coerce_str(benchmark.get("min_confidence", "medium"), field_name="benchmark.min_confidence"),
        chunk_size=_coerce_int(benchmark.get("chunk_size", 6000), field_name="benchmark.chunk_size", minimum=1),
        run_deterministic_repair=_coerce_bool(benchmark.get("run_deterministic_repair", True), field_name="benchmark.run_deterministic_repair"),
        run_deterministic_validation=_coerce_bool(benchmark.get("run_deterministic_validation", True), field_name="benchmark.run_deterministic_validation"),
        run_segment_detection=_coerce_bool(benchmark.get("run_segment_detection", True), field_name="benchmark.run_segment_detection"),
        run_judge=(False if args.skip_judge else _coerce_bool(benchmark.get("run_judge", True), field_name="benchmark.run_judge")),
        candidate_execution_mode=_coerce_str(benchmark.get("candidate_execution_mode", "production_pipeline"), field_name="benchmark.candidate_execution_mode"),
        candidate_inference_parameters=_coerce_str(benchmark.get("candidate_inference_parameters", "inherit_production_defaults"), field_name="benchmark.candidate_inference_parameters"),
        production_windowing_mode=_coerce_str(benchmark.get("production_windowing_mode", "inherit_production_defaults"), field_name="benchmark.production_windowing_mode"),
        candidates=tuple(candidates),
    )


def _git_commit_sha() -> str | None:
    try:
        completed = subprocess.run(["git", "rev-parse", "HEAD"], check=True, capture_output=True, cwd=REPO_ROOT, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _git_dirty_worktree() -> bool:
    try:
        completed = subprocess.run(["git", "status", "--porcelain"], check=True, capture_output=True, cwd=REPO_ROOT, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False
    return bool(completed.stdout.strip())


def _ensure_openrouter_env() -> str:
    _ensure_project_imports()
    load_project_dotenv()
    api_key = str(os.getenv("OPENROUTER_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("Missing required environment variable OPENROUTER_API_KEY.")
    return api_key


def _build_openrouter_client(api_key: str, config: ResolvedBenchmarkConfig):
    _ensure_project_imports()
    return OpenAI(
        api_key=api_key,
        base_url=config.openrouter_base_url,
        default_headers={
            "HTTP-Referer": config.openrouter_referer,
            "X-Title": config.openrouter_title,
        },
    )


def _fetch_model_catalog(*, api_key: str, config: ResolvedBenchmarkConfig) -> dict[str, object]:
    request = urllib.request.Request(
        url=config.openrouter_base_url.rstrip("/") + "/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": config.openrouter_referer,
            "X-Title": config.openrouter_title,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("OpenRouter model catalog returned unexpected payload.")
    return payload


def _availability_for_candidates(
    *,
    config: ResolvedBenchmarkConfig,
    candidates: Sequence[CandidateConfig],
    run_dir: Path,
    api_key: str,
) -> tuple[list[CandidateConfig], dict[str, object]]:
    catalog_payload = _fetch_model_catalog(api_key=api_key, config=config)
    catalog_items = list(catalog_payload.get("data") or ())
    catalog_by_id = {str(item.get("id") or "").strip(): item for item in catalog_items if isinstance(item, dict)}

    availability_entries: list[dict[str, object]] = []
    available: list[CandidateConfig] = []
    for candidate in candidates:
        matched = catalog_by_id.get(candidate.model)
        status = "available" if matched is not None else "missing"
        entry = {
            "id": candidate.id,
            "label": candidate.label,
            "requested_model_id": candidate.model,
            "availability_status": status,
            "context_length": (matched or {}).get("context_length"),
            "pricing": (matched or {}).get("pricing"),
        }
        availability_entries.append(entry)
        if status == "available":
            available.append(candidate)

    payload = {
        "checked_at": _now_utc_iso(),
        "catalog_model_count": len(catalog_items),
        "candidates": availability_entries,
    }
    _write_json(run_dir / "model_availability.json", payload)
    return available, payload


def _read_nested_field(value: object, *fields: str) -> object:
    _ensure_project_imports()
    current = value
    for field_name in fields:
        current = read_response_field(current, field_name)
        if current is None:
            return None
    return current


def _empty_usage_payload() -> dict[str, object]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "cost": 0.0,
        "cost_known": False,
        "response_model": "",
        "generation_id": "",
    }


def _combine_usage_payloads(*payloads: Mapping[str, object]) -> dict[str, object]:
    combined = _empty_usage_payload()
    observed_models: list[str] = []
    generation_ids: list[str] = []
    cost_known = True
    for payload in payloads:
        combined["prompt_tokens"] = int(combined["prompt_tokens"]) + int(payload.get("prompt_tokens") or 0)
        combined["completion_tokens"] = int(combined["completion_tokens"]) + int(payload.get("completion_tokens") or 0)
        combined["total_tokens"] = int(combined["total_tokens"]) + int(payload.get("total_tokens") or 0)
        combined["reasoning_tokens"] = int(combined["reasoning_tokens"]) + int(payload.get("reasoning_tokens") or 0)
        combined["cached_tokens"] = int(combined["cached_tokens"]) + int(payload.get("cached_tokens") or 0)
        combined["cost"] = round(float(combined["cost"]) + float(payload.get("cost") or 0.0), 6)
        cost_known = cost_known and bool(payload.get("cost_known"))
        response_model = str(payload.get("response_model") or "").strip()
        generation_id = str(payload.get("generation_id") or "").strip()
        if response_model:
            observed_models.append(response_model)
        if generation_id:
            generation_ids.append(generation_id)
    combined["cost_known"] = cost_known
    combined["response_model"] = observed_models[-1] if observed_models else ""
    combined["generation_id"] = generation_ids[-1] if generation_ids else ""
    combined["observed_response_models"] = sorted(set(observed_models))
    combined["observed_generation_ids"] = generation_ids
    return combined


def _extract_response_text(response: object) -> str:
    _ensure_project_imports()
    traversal = collect_response_text_traversal(response, unsupported_message="Model returned unsupported response shape.")
    if traversal.collected_texts:
        return "\n".join(str(text).strip() for text in traversal.collected_texts if str(text).strip())
    if traversal.raw_output_text is not None:
        return str(traversal.raw_output_text).strip()
    return ""


def _usage_payload(response: object, requested_model: str) -> dict[str, object]:
    usage = read_response_field(response, "usage")
    prompt_tokens = int(_read_nested_field(usage, "prompt_tokens") or _read_nested_field(usage, "input_tokens") or 0)
    completion_tokens = int(_read_nested_field(usage, "completion_tokens") or _read_nested_field(usage, "output_tokens") or 0)
    total_tokens = int(_read_nested_field(usage, "total_tokens") or prompt_tokens + completion_tokens)
    reasoning_tokens = int(_read_nested_field(usage, "reasoning_tokens") or _read_nested_field(usage, "output_tokens_details", "reasoning_tokens") or 0)
    cached_tokens = int(_read_nested_field(usage, "cached_tokens") or _read_nested_field(usage, "input_tokens_details", "cached_tokens") or 0)
    response_model = str(read_response_field(response, "model") or requested_model)
    generation_id = str(read_response_field(response, "id") or "")
    raw_cost = _read_nested_field(usage, "cost")
    if raw_cost is None:
        raw_cost = read_response_field(response, "cost")
    cost_known = raw_cost is not None
    try:
        cost = float(raw_cost) if raw_cost is not None else 0.0
    except (TypeError, ValueError):
        cost = 0.0
        cost_known = False
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
        "cost": round(cost, 6),
        "cost_known": cost_known,
        "response_model": response_model,
        "generation_id": generation_id,
    }


class _CapturingResponses:
    def __init__(self, underlying: object, records: list[CapturedResponseRecord]):
        self._underlying = underlying
        self._records = records

    def create(self, **payload: object) -> object:
        requested_model = str(payload.get("model") or "")
        started_at = time.perf_counter()
        request_index = len(self._records) + 1
        payload_summary = {
            "model": requested_model,
            "timeout": payload.get("timeout"),
            "temperature": payload.get("temperature"),
            "max_output_tokens": payload.get("max_output_tokens"),
            "input_message_count": len(payload.get("input") or []) if isinstance(payload.get("input"), list) else None,
        }
        try:
            response = self._underlying.create(**payload)
        except Exception as exc:  # noqa: BLE001
            self._records.append(
                CapturedResponseRecord(
                    request_index=request_index,
                    requested_model=requested_model,
                    response_model="",
                    generation_id="",
                    duration_seconds=round(time.perf_counter() - started_at, 3),
                    raw_text="",
                    usage=_empty_usage_payload(),
                    payload_summary=payload_summary,
                    error=str(exc),
                )
            )
            raise

        raw_text = _extract_response_text(response)
        usage = _usage_payload(response, requested_model)
        self._records.append(
            CapturedResponseRecord(
                request_index=request_index,
                requested_model=requested_model,
                response_model=str(usage.get("response_model") or ""),
                generation_id=str(usage.get("generation_id") or ""),
                duration_seconds=round(time.perf_counter() - started_at, 3),
                raw_text=raw_text,
                usage=usage,
                payload_summary=payload_summary,
                error=None,
            )
        )
        return response


class _CapturingClient:
    def __init__(self, underlying: object, *, records: list[CapturedResponseRecord] | None = None):
        self._underlying = underlying
        self._records = records if records is not None else []
        self.responses = _CapturingResponses(getattr(underlying, "responses"), self._records)

    @property
    def records(self) -> list[CapturedResponseRecord]:
        return self._records

    def with_options(self, **kwargs: object) -> "_CapturingClient":
        with_options = getattr(self._underlying, "with_options", None)
        if not callable(with_options):
            return self
        return _CapturingClient(with_options(**kwargs), records=self._records)


def _extract_requested_candidate_ids(config: ResolvedBenchmarkConfig) -> list[str]:
    return [candidate.id for candidate in config.candidates]


def _unpack_extraction_result(extraction_result: Sequence[object]) -> tuple[list[object], object | None]:
    paragraphs = list(extraction_result[0] if len(extraction_result) > 0 else [])
    structure_repair_report = extraction_result[6] if len(extraction_result) > 6 else None
    return paragraphs, structure_repair_report


def _slice_paragraphs(paragraphs: Sequence[object], max_paragraphs: int) -> list[object]:
    if max_paragraphs <= 0 or len(paragraphs) <= max_paragraphs:
        return list(paragraphs)
    return list(paragraphs[:max_paragraphs])


def _count_heading_paragraphs(paragraphs: Sequence[object]) -> int:
    return sum(1 for paragraph in paragraphs if str(getattr(paragraph, "role", "") or "").strip().lower() == "heading")


def _count_structural_role(paragraphs: Sequence[object], role: str) -> int:
    return sum(1 for paragraph in paragraphs if str(getattr(paragraph, "structural_role", "") or "").strip().lower() == role)


def _count_list_evidence(paragraphs: Sequence[object]) -> int:
    count = 0
    for paragraph in paragraphs:
        if getattr(paragraph, "list_kind", None) is not None:
            count += 1
            continue
        text = str(getattr(paragraph, "text", "") or "").strip()
        if text.startswith(("- ", "* ", "• ")):
            count += 1
        elif text[:2].isdigit() and len(text) > 2 and text[2] in {".", ")"}:
            count += 1
    return count


def _resolve_quality_gate_status(validation_report: object | None) -> str:
    readiness_status = str(getattr(validation_report, "readiness_status", "") or "")
    if readiness_status == "ready":
        return "pass"
    if readiness_status == "ready_with_warnings":
        return "warning"
    return "fail"


def _descriptor_has_heading_signal(descriptor: object) -> bool:
    style_name = str(getattr(descriptor, "style_name", "") or "").strip().lower()
    return bool(getattr(descriptor, "explicit_heading_level", None) is not None or "heading" in style_name)


def _build_review_windows(descriptors: Sequence[object], config: ResolvedBenchmarkConfig) -> tuple[ReviewWindow, ...]:
    descriptor_list = list(descriptors)
    if not descriptor_list:
        return ()
    window_size = max(1, config.review_max_window_paragraphs)
    total = len(descriptor_list)

    anchors: list[tuple[str, int, str]] = []
    anchors.append(("front_matter", 0, "document_start"))

    first_heading_index = None
    for index, descriptor in enumerate(descriptor_list):
        if _descriptor_has_heading_signal(descriptor) and index > 0:
            first_heading_index = index
            break
    if first_heading_index is not None:
        anchors.append(("first_heading_context", max(0, first_heading_index - window_size // 4), "first_heading_signal"))

    anchors.append(("middle_body", max(0, total // 2 - window_size // 2), "middle_body"))
    anchors.append(("tail_body", max(0, total - window_size), "document_tail"))

    windows: list[ReviewWindow] = []
    seen: set[tuple[int, int]] = set()
    for window_id, start_index, rationale in anchors:
        end_index = min(total - 1, start_index + window_size - 1)
        key = (start_index, end_index)
        if key in seen:
            continue
        seen.add(key)
        windows.append(
            ReviewWindow(
                id=window_id,
                start_index=start_index,
                end_index=end_index,
                descriptors=tuple(descriptor_list[start_index : end_index + 1]),
                rationale=rationale,
                expected_covered=True,
            )
        )
        if len(windows) >= config.review_max_windows_per_profile:
            break
    return tuple(windows)


def _descriptor_to_json(descriptor: object) -> dict[str, object]:
    return {
        "index": int(getattr(descriptor, "index", -1) or -1),
        "text_preview": str(getattr(descriptor, "text_preview", "") or ""),
        "text_length": int(getattr(descriptor, "text_length", 0) or 0),
        "style_name": str(getattr(descriptor, "style_name", "") or ""),
        "is_bold": bool(getattr(descriptor, "is_bold", False)),
        "is_centered": bool(getattr(descriptor, "is_centered", False)),
        "is_all_caps": bool(getattr(descriptor, "is_all_caps", False)),
        "font_size_pt": getattr(descriptor, "font_size_pt", None),
        "has_numbering": bool(getattr(descriptor, "has_numbering", False)),
        "explicit_heading_level": getattr(descriptor, "explicit_heading_level", None),
        "context_before_preview": str(getattr(descriptor, "context_before_preview", "") or ""),
        "context_after_preview": str(getattr(descriptor, "context_after_preview", "") or ""),
        "isolated_marker": bool(getattr(descriptor, "isolated_marker", False)),
        "toc_candidate": bool(getattr(descriptor, "toc_candidate", False)),
        "scripture_reference_candidate": bool(getattr(descriptor, "scripture_reference_candidate", False)),
    }


def _render_outline_markdown(window: ReviewWindow) -> str:
    lines = [f"# {window.id}", "", f"Rationale: {window.rationale}", ""]
    for descriptor in window.descriptors:
        flags: list[str] = []
        if getattr(descriptor, "explicit_heading_level", None) is not None:
            flags.append(f"hl={getattr(descriptor, 'explicit_heading_level')}")
        if bool(getattr(descriptor, "toc_candidate", False)):
            flags.append("toc")
        if bool(getattr(descriptor, "has_numbering", False)):
            flags.append("num")
        if bool(getattr(descriptor, "isolated_marker", False)):
            flags.append("isolated_marker")
        flag_text = ", ".join(flags) if flags else "-"
        lines.append(
            f"{int(getattr(descriptor, 'index', -1) or -1):03d} | len={int(getattr(descriptor, 'text_length', 0) or 0)} | style={str(getattr(descriptor, 'style_name', '') or '-') } | flags={flag_text} | text={json.dumps(str(getattr(descriptor, 'text_preview', '') or ''), ensure_ascii=False)}"
        )
    lines.append("")
    return "\n".join(lines)


def _validation_payload(report: object | None) -> dict[str, object]:
    if report is None:
        return {}
    return {
        "paragraph_count": int(getattr(report, "paragraph_count", 0) or 0),
        "nonempty_paragraph_count": int(getattr(report, "nonempty_paragraph_count", 0) or 0),
        "explicit_heading_count": int(getattr(report, "explicit_heading_count", 0) or 0),
        "heuristic_heading_count": int(getattr(report, "heuristic_heading_count", 0) or 0),
        "toc_like_sequence_count": int(getattr(report, "toc_like_sequence_count", 0) or 0),
        "isolated_marker_paragraph_count": int(getattr(report, "isolated_marker_paragraph_count", 0) or 0),
        "structure_quality_risk_level": str(getattr(report, "structure_quality_risk_level", "") or ""),
        "readiness_status": str(getattr(report, "readiness_status", "") or ""),
        "readiness_reasons": list(getattr(report, "readiness_reasons", ()) or ()),
    }


def _segment_payload(report: object | None, structure_fingerprint: str, segments: Sequence[object]) -> dict[str, object]:
    if report is None:
        return {
            "segment_count": 0,
            "high_confidence_count": 0,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "fallback_segment_count": 0,
            "toc_matched_count": 0,
            "warnings": [],
            "structure_fingerprint": structure_fingerprint,
        }
    return {
        "segment_count": int(getattr(report, "segment_count", len(segments)) or len(segments)),
        "high_confidence_count": int(getattr(report, "high_confidence_count", 0) or 0),
        "medium_confidence_count": int(getattr(report, "medium_confidence_count", 0) or 0),
        "low_confidence_count": int(getattr(report, "low_confidence_count", 0) or 0),
        "fallback_segment_count": int(getattr(report, "fallback_segment_count", 0) or 0),
        "toc_matched_count": int(getattr(report, "toc_matched_count", 0) or 0),
        "warnings": list(getattr(report, "warnings", ()) or ()),
        "structure_fingerprint": structure_fingerprint,
    }


def _baseline_metrics(
    *,
    paragraphs: Sequence[object],
    validation_report: object | None,
    segment_payload: Mapping[str, object],
    structure_fingerprint: str,
) -> dict[str, object]:
    return {
        "paragraph_count": len(paragraphs),
        "nonempty_paragraph_count": int(getattr(validation_report, "nonempty_paragraph_count", 0) or 0),
        "heading_count_after_apply": _count_heading_paragraphs(paragraphs),
        "toc_header_count_after_apply": _count_structural_role(paragraphs, "toc_header"),
        "toc_entry_count_after_apply": _count_structural_role(paragraphs, "toc_entry"),
        "list_evidence_count": _count_list_evidence(paragraphs),
        "segment_count": int(segment_payload.get("segment_count") or 0),
        "fallback_segment_count": int(segment_payload.get("fallback_segment_count") or 0),
        "toc_matched_count": int(segment_payload.get("toc_matched_count") or 0),
        "readiness_status": str(getattr(validation_report, "readiness_status", "") or ""),
        "quality_gate_status": _resolve_quality_gate_status(validation_report),
        "structure_fingerprint": structure_fingerprint,
    }


def _load_profile_preparation(profile_id: str, config: ResolvedBenchmarkConfig, app_config: object) -> ProfilePreparation:
    _ensure_project_imports()
    registry = load_validation_registry()
    profile = registry.get_document_profile(profile_id)
    source_path = profile.resolved_source_path(REPO_ROOT)
    source_bytes = source_path.read_bytes()
    normalized_source = processing_runtime.normalize_uploaded_document(filename=source_path.name, source_bytes=source_bytes)
    extraction_result = extract_document_content_with_normalization_reports(BytesIO(normalized_source.content_bytes), app_config=app_config)
    paragraphs, extracted_structure_repair = _unpack_extraction_result(extraction_result)
    paragraphs = _slice_paragraphs(paragraphs, config.max_paragraphs_per_profile)

    repair_report = extracted_structure_repair
    repaired_paragraphs = list(paragraphs)
    if config.run_deterministic_repair:
        repaired_paragraphs, repair_report = repair_pdf_derived_structure(paragraphs, app_config=app_config)

    validation_report = None
    if config.run_deterministic_validation:
        validation_report = validate_structure_quality(
            paragraphs=repaired_paragraphs,
            app_config=app_config,
            structure_repair_report=repair_report,
        )

    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    source_content_hash16 = source_sha256[:16]
    baseline_segments: list[object] = []
    baseline_segment_report = None
    structure_fingerprint = ""
    if config.run_segment_detection:
        baseline_segments, baseline_segment_report, structure_fingerprint = detect_document_segments(
            repaired_paragraphs,
            source_content_hash16=source_content_hash16,
            chunk_size=config.chunk_size,
        )

    descriptors = list(build_paragraph_descriptors(repaired_paragraphs))
    review_windows = _build_review_windows(descriptors, config)
    baseline_segment_payload = _segment_payload(baseline_segment_report, structure_fingerprint, baseline_segments)
    baseline_metrics = _baseline_metrics(
        paragraphs=repaired_paragraphs,
        validation_report=validation_report,
        segment_payload=baseline_segment_payload,
        structure_fingerprint=structure_fingerprint,
    )
    return ProfilePreparation(
        profile_id=profile_id,
        source_path=source_path,
        source_sha256=source_sha256,
        source_content_hash16=source_content_hash16,
        paragraphs=tuple(paragraphs),
        repaired_paragraphs=tuple(repaired_paragraphs),
        repair_report=repair_report,
        validation_report=validation_report,
        baseline_segments=tuple(baseline_segments),
        baseline_segment_report=baseline_segment_report,
        baseline_structure_fingerprint=structure_fingerprint,
        descriptors=tuple(descriptors),
        review_windows=review_windows,
        baseline_metrics=baseline_metrics,
    )


def _profile_inputs_artifacts(run_dir: Path, preparation: ProfilePreparation) -> None:
    base_dir = run_dir / "inputs" / preparation.profile_id
    for window in preparation.review_windows:
        _write_json(base_dir / f"{window.id}.descriptors.json", [_descriptor_to_json(item) for item in window.descriptors])
        _write_text(base_dir / f"{window.id}.source_outline.md", _render_outline_markdown(window))
        _write_json(
            base_dir / f"{window.id}.metadata.json",
            {
                "id": window.id,
                "start_index": window.start_index,
                "end_index": window.end_index,
                "descriptor_count": len(window.descriptors),
                "rationale": window.rationale,
                "expected_covered": window.expected_covered,
            },
        )


def _baseline_artifacts(run_dir: Path, preparation: ProfilePreparation) -> None:
    base_dir = run_dir / "baselines" / preparation.profile_id / "deterministic_repair_only"
    repair_payload = asdict(preparation.repair_report) if preparation.repair_report is not None else {}
    _write_json(base_dir / "repair_report.json", repair_payload)
    _write_json(base_dir / "validation_report.json", _validation_payload(preparation.validation_report))
    _write_json(
        base_dir / "segment_diagnostics.json",
        _segment_payload(preparation.baseline_segment_report, preparation.baseline_structure_fingerprint, preparation.baseline_segments),
    )
    _write_json(base_dir / "metrics.json", preparation.baseline_metrics)


def _classification_to_json(classification: object) -> dict[str, object]:
    return {
        "index": int(getattr(classification, "index", -1) or -1),
        "role": str(getattr(classification, "role", "") or ""),
        "heading_level": getattr(classification, "heading_level", None),
        "confidence": str(getattr(classification, "confidence", "") or ""),
        "rationale": getattr(classification, "rationale", None),
    }


def _structure_map_payload(structure_map: object) -> dict[str, object]:
    classifications = getattr(structure_map, "classifications", {}) or {}
    items = [
        _classification_to_json(classification)
        for _, classification in sorted(classifications.items(), key=lambda pair: int(pair[0]))
    ]
    return {
        "model_used": str(getattr(structure_map, "model_used", "") or ""),
        "total_tokens_used": int(getattr(structure_map, "total_tokens_used", 0) or 0),
        "processing_time_seconds": round(float(getattr(structure_map, "processing_time_seconds", 0.0) or 0.0), 3),
        "window_count": int(getattr(structure_map, "window_count", 0) or 0),
        "classified_count": len(items),
        "heading_count": sum(1 for item in items if item["role"] == "heading"),
        "classifications": items,
    }


def _review_classifications(windows: Sequence[ReviewWindow], structure_map_payload: Mapping[str, object]) -> dict[str, list[dict[str, object]]]:
    by_index = {int(item.get("index") or -1): item for item in list(structure_map_payload.get("classifications") or []) if isinstance(item, dict)}
    payload: dict[str, list[dict[str, object]]] = {}
    for window in windows:
        items: list[dict[str, object]] = []
        for descriptor in window.descriptors:
            descriptor_index = int(getattr(descriptor, "index", -1) or -1)
            classification = by_index.get(descriptor_index)
            items.append(
                {
                    "index": descriptor_index,
                    "text_preview": str(getattr(descriptor, "text_preview", "") or ""),
                    "classification": classification,
                }
            )
        payload[window.id] = items
    return payload


def _quality_gate_status(validation_report: object | None) -> str:
    return _resolve_quality_gate_status(validation_report)


def _candidate_metrics(
    *,
    preparation: ProfilePreparation,
    paragraphs_after_apply: Sequence[object],
    structure_map_payload: Mapping[str, object],
    validation_report: object | None,
    segment_payload: Mapping[str, object],
    usage: Mapping[str, object],
) -> dict[str, object]:
    role_counts: dict[str, int] = {}
    for item in list(structure_map_payload.get("classifications") or []):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        role_counts[role] = int(role_counts.get(role) or 0) + 1
    review_indexes = {
        int(getattr(descriptor, "index", -1) or -1)
        for window in preparation.review_windows
        for descriptor in window.descriptors
        if int(getattr(descriptor, "index", -1) or -1) >= 0
    }
    classified_indexes = {int(item.get("index") or -1) for item in list(structure_map_payload.get("classifications") or []) if isinstance(item, dict)}
    missing_classifications = sorted(index for index in review_indexes if index not in classified_indexes)
    return {
        "paragraph_count": len(paragraphs_after_apply),
        "nonempty_paragraph_count": int(getattr(validation_report, "nonempty_paragraph_count", 0) or 0),
        "input_window_count": int(structure_map_payload.get("window_count") or 0),
        "review_window_count": len(preparation.review_windows),
        "classified_count": int(structure_map_payload.get("classified_count") or 0),
        "missing_classification_count": len(missing_classifications),
        "schema_violation_count": 0,
        "ai_heading_count": int(role_counts.get("heading") or 0),
        "ai_toc_header_count": int(role_counts.get("toc_header") or 0),
        "ai_toc_entry_count": int(role_counts.get("toc_entry") or 0),
        "ai_list_count": int(role_counts.get("list") or 0),
        "ai_epigraph_count": int(role_counts.get("epigraph") or 0),
        "ai_attribution_count": int(role_counts.get("attribution") or 0),
        "heading_count_after_apply": _count_heading_paragraphs(paragraphs_after_apply),
        "toc_header_count_after_apply": _count_structural_role(paragraphs_after_apply, "toc_header"),
        "toc_entry_count_after_apply": _count_structural_role(paragraphs_after_apply, "toc_entry"),
        "segment_count": int(segment_payload.get("segment_count") or 0),
        "high_confidence_segment_count": int(segment_payload.get("high_confidence_count") or 0),
        "medium_confidence_segment_count": int(segment_payload.get("medium_confidence_count") or 0),
        "low_confidence_segment_count": int(segment_payload.get("low_confidence_count") or 0),
        "fallback_segment_count": int(segment_payload.get("fallback_segment_count") or 0),
        "toc_matched_count": int(segment_payload.get("toc_matched_count") or 0),
        "readiness_status": str(getattr(validation_report, "readiness_status", "") or ""),
        "quality_gate_status": _quality_gate_status(validation_report),
        "cost_known": bool(usage.get("cost_known")),
        "total_cost": float(usage.get("cost") or 0.0),
        "average_latency_seconds": round(float(structure_map_payload.get("processing_time_seconds") or 0.0), 3),
        "structure_fingerprint": str(segment_payload.get("structure_fingerprint") or ""),
        "missing_classification_indexes": missing_classifications,
    }


def _looks_like_isolated_marker(text: str) -> bool:
    stripped = text.strip()
    if stripped in {"●", "•", "-", "*"}:
        return True
    if len(stripped) >= 2 and stripped[:-1].isdigit() and stripped[-1] in {".", ")"}:
        return True
    return False


def _count_bullet_heading_violations(paragraphs: Sequence[object]) -> int:
    violations = 0
    for paragraph in paragraphs:
        if str(getattr(paragraph, "role", "") or "").strip().lower() != "heading":
            continue
        if _looks_like_isolated_marker(str(getattr(paragraph, "text", "") or "")):
            violations += 1
    return violations


def _candidate_flags(
    *,
    preparation: ProfilePreparation,
    candidate_result: CandidateProfileResult,
    paragraphs_after_apply: Sequence[object],
    profile: object,
) -> tuple[list[str], list[str]]:
    metrics = candidate_result.metrics
    baseline_metrics = preparation.baseline_metrics
    flags: list[str] = []
    severe_flags: list[str] = []

    if not candidate_result.ok:
        flags.append("candidate_call_failure")
        severe_flags.append("candidate_call_failure")
        return flags, severe_flags

    if int(metrics.get("classified_count") or 0) == 0:
        flags.append("invalid_json_output")

    if int(metrics.get("missing_classification_count") or 0) > 0:
        flags.append("missing_classifications")

    nonempty_paragraph_count = max(int(metrics.get("nonempty_paragraph_count") or 0), 1)
    baseline_heading_count = max(int(baseline_metrics.get("heading_count_after_apply") or 0), 1)
    heading_count_after_apply = int(metrics.get("heading_count_after_apply") or 0)
    heading_ratio = heading_count_after_apply / nonempty_paragraph_count
    baseline_heading_ratio = baseline_heading_count / max(int(baseline_metrics.get("nonempty_paragraph_count") or 0), 1)
    if heading_ratio >= 0.20 and heading_ratio >= baseline_heading_ratio * 2.5:
        flags.append("heading_only_collapse")
    if heading_ratio >= 0.30 or heading_count_after_apply >= baseline_heading_count * 3:
        severe_flags.append("severe_heading_only_collapse")

    bullet_heading_violations = _count_bullet_heading_violations(paragraphs_after_apply)
    if bullet_heading_violations > 0:
        flags.append("bullet_heading_violation")
    if bullet_heading_violations >= 3:
        severe_flags.append("bullet_heading_violation")

    if bool(getattr(profile, "require_toc_detected", False)) and (int(metrics.get("toc_header_count_after_apply") or 0) + int(metrics.get("toc_entry_count_after_apply") or 0) == 0):
        flags.append("toc_not_detected")

    if bool(getattr(profile, "require_no_toc_body_concat", False)) and int(getattr(preparation.repair_report, "toc_body_boundary_repairs", 0) or 0) > 0 and int(metrics.get("toc_entry_count_after_apply") or 0) < 2:
        flags.append("toc_body_concat_risk")

    baseline_list_evidence = int(baseline_metrics.get("list_evidence_count") or 0)
    if bool(getattr(profile, "require_numbered_lists_preserved", False)) and baseline_list_evidence > 0:
        retained = _count_list_evidence(paragraphs_after_apply)
        if retained < baseline_list_evidence * 0.8:
            flags.append("list_loss_risk")

    segment_count = max(int(metrics.get("segment_count") or 0), 1)
    fallback_ratio = int(metrics.get("fallback_segment_count") or 0) / segment_count
    if fallback_ratio > 0.34:
        flags.append("segment_fallback_overuse")
    if fallback_ratio > 0.50:
        severe_flags.append("segment_fallback_overuse")

    min_headings = int(getattr(profile, "min_headings", 0) or 0)
    if min_headings >= 3 and int(metrics.get("segment_count") or 0) < max(2, min_headings // 2):
        flags.append("segment_under_split")
    baseline_segment_count = int(baseline_metrics.get("segment_count") or 0)
    if baseline_segment_count > 0 and int(metrics.get("segment_count") or 0) > max(baseline_segment_count * 2, baseline_segment_count + 8):
        flags.append("segment_over_split")

    baseline_readiness = str(baseline_metrics.get("readiness_status") or "")
    current_readiness = str(metrics.get("readiness_status") or "")
    if baseline_readiness in {"ready", "ready_with_warnings"} and current_readiness not in {"ready", "ready_with_warnings"}:
        flags.append("readiness_regression")

    return sorted(set(flags + severe_flags)), sorted(set(severe_flags))


def _write_candidate_records(base_dir: Path, records: Sequence[CapturedResponseRecord]) -> None:
    for record in records:
        request_id = f"request_{record.request_index:03d}"
        _write_text(base_dir / "raw" / f"{request_id}.txt", record.raw_text)
        _write_json(base_dir / "usage" / f"{request_id}.json", record.usage)
        _write_json(
            base_dir / "metadata" / f"{request_id}.json",
            {
                "request_index": record.request_index,
                "requested_model": record.requested_model,
                "response_model": record.response_model,
                "generation_id": record.generation_id,
                "duration_seconds": record.duration_seconds,
                "payload_summary": record.payload_summary,
                "error": record.error,
            },
        )


def _run_candidate_for_profile(
    *,
    candidate: CandidateConfig,
    preparation: ProfilePreparation,
    config: ResolvedBenchmarkConfig,
    app_config: object,
    base_client: object,
) -> CandidateProfileResult:
    wrapped_client = _CapturingClient(base_client)
    candidate_paragraphs = deepcopy(list(preparation.repaired_paragraphs))
    try:
        structure_map = build_structure_map(
            candidate_paragraphs,
            client=wrapped_client,
            model=candidate.model,
            max_window_paragraphs=int(getattr(app_config, "structure_recognition_max_window_paragraphs", 1800) or 1800),
            overlap_paragraphs=int(getattr(app_config, "structure_recognition_overlap_paragraphs", 50) or 50),
            timeout=float(config.request_timeout_seconds),
        )
        structure_map_payload = _structure_map_payload(structure_map)
        applied_summary = apply_structure_map(candidate_paragraphs, structure_map, min_confidence=config.min_confidence)
        validation_report = validate_structure_quality(
            paragraphs=candidate_paragraphs,
            app_config=app_config,
            structure_repair_report=preparation.repair_report,
        )
        segments: list[object] = []
        segment_report = None
        structure_fingerprint = ""
        if config.run_segment_detection:
            segments, segment_report, structure_fingerprint = detect_document_segments(
                candidate_paragraphs,
                source_content_hash16=preparation.source_content_hash16,
                chunk_size=config.chunk_size,
            )
        segment_payload = _segment_payload(segment_report, structure_fingerprint, segments)
        usage = _combine_usage_payloads(*(record.usage for record in wrapped_client.records if record.error is None))
        metrics = _candidate_metrics(
            preparation=preparation,
            paragraphs_after_apply=candidate_paragraphs,
            structure_map_payload=structure_map_payload,
            validation_report=validation_report,
            segment_payload=segment_payload,
            usage=usage,
        )
        result = CandidateProfileResult(
            candidate=candidate,
            profile_id=preparation.profile_id,
            ok=True,
            error=None,
            structure_map_payload=structure_map_payload,
            applied_summary=dict(applied_summary),
            metrics=metrics,
            flags=[],
            severe_flags=[],
            validation_payload=_validation_payload(validation_report),
            segment_payload=segment_payload,
            usage=usage,
            records=list(wrapped_client.records),
            returned_models=sorted({record.response_model for record in wrapped_client.records if record.response_model}),
            review_classifications=_review_classifications(preparation.review_windows, structure_map_payload),
        )
        registry = load_validation_registry()
        profile = registry.get_document_profile(preparation.profile_id)
        flags, severe_flags = _candidate_flags(
            preparation=preparation,
            candidate_result=result,
            paragraphs_after_apply=candidate_paragraphs,
            profile=profile,
        )
        result.flags = flags
        result.severe_flags = severe_flags
        return result
    except Exception as exc:  # noqa: BLE001
        usage = _combine_usage_payloads(*(record.usage for record in wrapped_client.records if record.error is None)) if wrapped_client.records else _empty_usage_payload()
        return CandidateProfileResult(
            candidate=candidate,
            profile_id=preparation.profile_id,
            ok=False,
            error=str(exc),
            structure_map_payload={},
            applied_summary={},
            metrics={
                "paragraph_count": len(preparation.repaired_paragraphs),
                "nonempty_paragraph_count": int(getattr(preparation.validation_report, "nonempty_paragraph_count", 0) or 0),
                "classified_count": 0,
                "missing_classification_count": len({int(getattr(descriptor, 'index', -1) or -1) for window in preparation.review_windows for descriptor in window.descriptors if int(getattr(descriptor, 'index', -1) or -1) >= 0}),
                "schema_violation_count": 0,
                "heading_count_after_apply": _count_heading_paragraphs(preparation.repaired_paragraphs),
                "segment_count": int(preparation.baseline_metrics.get("segment_count") or 0),
                "fallback_segment_count": int(preparation.baseline_metrics.get("fallback_segment_count") or 0),
                "readiness_status": str(preparation.baseline_metrics.get("readiness_status") or ""),
                "quality_gate_status": str(preparation.baseline_metrics.get("quality_gate_status") or ""),
                "cost_known": bool(usage.get("cost_known")),
                "total_cost": float(usage.get("cost") or 0.0),
                "average_latency_seconds": round(sum(record.duration_seconds for record in wrapped_client.records) / max(len(wrapped_client.records), 1), 3) if wrapped_client.records else 0.0,
                "structure_fingerprint": str(preparation.baseline_metrics.get("structure_fingerprint") or ""),
            },
            flags=["candidate_call_failure"],
            severe_flags=["candidate_call_failure"],
            validation_payload={},
            segment_payload={},
            usage=usage,
            records=list(wrapped_client.records),
            returned_models=sorted({record.response_model for record in wrapped_client.records if record.response_model}),
        )


def _write_candidate_artifacts(run_dir: Path, result: CandidateProfileResult) -> None:
    base_dir = run_dir / "candidates" / result.profile_id / result.candidate.id
    _write_candidate_records(base_dir, result.records)
    _write_json(base_dir / "structure_map.json", result.structure_map_payload)
    _write_json(base_dir / "applied_summary.json", result.applied_summary)
    _write_json(base_dir / "segment_diagnostics.json", result.segment_payload)
    _write_json(base_dir / "pipeline_checks.json", {
        "flags": result.flags,
        "severe_flags": result.severe_flags,
        "metrics": result.metrics,
        "error": result.error,
    })
    _write_json(base_dir / "validation_report.json", result.validation_payload)
    _write_json(base_dir / "usage_summary.json", result.usage)
    _write_json(base_dir / "review_classifications.json", result.review_classifications)


def _deterministic_pipeline_score(result: CandidateProfileResult) -> float:
    flags = set(result.flags)
    severe_flags = set(result.severe_flags)
    score = 100.0
    if "severe_heading_only_collapse" in severe_flags:
        score -= 25
    if "toc_not_detected" in flags:
        score -= 20
    if "bullet_heading_violation" in flags:
        score -= 18
    if "toc_body_concat_risk" in flags:
        score -= 18
    if "readiness_regression" in flags:
        score -= 15
    if "segment_under_split" in flags or "segment_over_split" in flags:
        score -= 12
    if "segment_fallback_overuse" in flags:
        score -= 10
    if "list_loss_risk" in flags:
        score -= 8
    if "missing_classifications" in flags or "invalid_json_output" in flags:
        score -= 5
    return max(0.0, min(100.0, score))


def _estimate_max_output_tokens(text: str) -> int:
    estimated_output_tokens = max((len(text) // 3) * 4, 512)
    return min(estimated_output_tokens, 16384)


def _build_request_payload(
    *,
    model: str,
    system_prompt: str,
    user_prompt: str,
    target_text: str,
    temperature: float,
    timeout_seconds: int,
) -> dict[str, object]:
    return {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
        "temperature": temperature,
        "max_output_tokens": _estimate_max_output_tokens(target_text),
        "timeout": timeout_seconds,
    }


def _run_text_request(
    client: object,
    *,
    requested_model: str,
    system_prompt: str,
    user_prompt: str,
    target_text: str,
    temperature: float,
    timeout_seconds: int,
    max_retries: int,
) -> dict[str, object]:
    request_payload = _build_request_payload(
        model=requested_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        target_text=target_text,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
    )
    started_at = time.perf_counter()
    attempt_history: list[dict[str, object]] = []
    removable_optional_params = {"timeout", "temperature", "max_output_tokens"}

    for attempt in range(1, max_retries + 1):
        current_payload = dict(request_payload)
        while True:
            try:
                response = client.responses.create(**current_payload)
            except TypeError as exc:
                unsupported_param = extract_unsupported_parameter_name(str(exc))
                if unsupported_param in removable_optional_params and unsupported_param in current_payload:
                    current_payload.pop(unsupported_param, None)
                    request_payload.pop(unsupported_param, None)
                    attempt_history.append({"attempt": attempt, "status": "retrying_without_optional_param", "removed_param": unsupported_param, "error": str(exc)})
                    continue
                attempt_history.append({"attempt": attempt, "status": "failed", "error": str(exc)})
                return {"ok": False, "error": str(exc), "attempt_history": attempt_history, "duration_seconds": round(time.perf_counter() - started_at, 3), "usage": _empty_usage_payload()}
            except Exception as exc:  # noqa: BLE001
                unsupported_param = extract_unsupported_parameter_name(str(exc))
                if unsupported_param in removable_optional_params and unsupported_param in current_payload:
                    current_payload.pop(unsupported_param, None)
                    request_payload.pop(unsupported_param, None)
                    attempt_history.append({"attempt": attempt, "status": "retrying_without_optional_param", "removed_param": unsupported_param, "error": str(exc)})
                    continue
                retryable = attempt < max_retries and is_retryable_error(exc)
                attempt_history.append({"attempt": attempt, "status": "retryable_error" if retryable else "failed", "error": str(exc)})
                if retryable:
                    continue
                return {"ok": False, "error": str(exc), "attempt_history": attempt_history, "duration_seconds": round(time.perf_counter() - started_at, 3), "usage": _empty_usage_payload()}
            break

        try:
            response_text = _extract_response_text(response)
        except Exception as exc:  # noqa: BLE001
            attempt_history.append({"attempt": attempt, "status": "failed", "error": str(exc)})
            return {"ok": False, "error": str(exc), "attempt_history": attempt_history, "duration_seconds": round(time.perf_counter() - started_at, 3), "usage": _usage_payload(response, requested_model)}

        usage = _usage_payload(response, requested_model)
        attempt_history.append({"attempt": attempt, "status": "succeeded"})
        return {
            "ok": True,
            "response_text": response_text,
            "usage": usage,
            "duration_seconds": round(time.perf_counter() - started_at, 3),
            "attempt_history": attempt_history,
        }
    return {"ok": False, "error": "request_exhausted", "attempt_history": attempt_history, "duration_seconds": round(time.perf_counter() - started_at, 3), "usage": _empty_usage_payload()}


def _json_from_response_text(text: str) -> dict[str, object] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except Exception:  # noqa: BLE001
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    try:
        parsed = parse_json_object(stripped)
    except Exception:  # noqa: BLE001
        return None
    return parsed if isinstance(parsed, dict) else None


def _render_candidate_window_lines(window_payload: Sequence[Mapping[str, object]]) -> list[str]:
    lines: list[str] = []
    for item in window_payload:
        classification = item.get("classification") if isinstance(item, Mapping) else None
        if not isinstance(classification, Mapping):
            lines.append(f"{int(item.get('index') or -1):03d} | missing")
            continue
        lines.append(
            f"{int(item.get('index') or -1):03d} | {classification.get('role')} | level={classification.get('heading_level')} | confidence={classification.get('confidence')}"
        )
    return lines


def _build_profile_review_pack(profile_id: str, preparation: ProfilePreparation, results: Sequence[CandidateProfileResult]) -> str:
    lines = [f"PROFILE: {profile_id}", ""]
    for window in preparation.review_windows:
        lines.append(f"WINDOW: {window.id}")
        lines.append("")
        lines.append("SOURCE PARAGRAPH OUTLINE:")
        for descriptor in window.descriptors:
            lines.append(
                f"{int(getattr(descriptor, 'index', -1) or -1):03d} | len={int(getattr(descriptor, 'text_length', 0) or 0)} | style={str(getattr(descriptor, 'style_name', '') or '-')} | text={json.dumps(str(getattr(descriptor, 'text_preview', '') or ''), ensure_ascii=False)}"
            )
        lines.append("")
        for result in results:
            lines.append(f"{result.candidate.id.upper()} CLASSIFICATIONS:")
            lines.extend(_render_candidate_window_lines(result.review_classifications.get(window.id, [])))
            lines.append("")
        lines.append("PIPELINE OUTCOME:")
        for result in results:
            lines.append(
                f"- {result.candidate.id}: headings_after_apply={result.metrics.get('heading_count_after_apply')} toc_entries_after_apply={result.metrics.get('toc_entry_count_after_apply')} segment_count={result.metrics.get('segment_count')} fallback_segment_count={result.metrics.get('fallback_segment_count')} readiness_status={result.metrics.get('readiness_status')} automated_flags={sorted(set(result.flags))}"
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _build_rubric_prompt(review_pack: str, results: Sequence[CandidateProfileResult]) -> str:
    candidate_ids = [result.candidate.id for result in results]
    return (
        "TASK_MODE=rubric\n"
        "Evaluate all candidates in the review pack.\n"
        "Return strict JSON with top-level key candidate_scores.\n"
        f"Candidates: {', '.join(candidate_ids)}\n\n"
        f"{review_pack}"
    )


def _build_pairwise_prompt(review_pack: str, results: Sequence[CandidateProfileResult]) -> str:
    candidate_ids = [result.candidate.id for result in results]
    return (
        "TASK_MODE=pairwise\n"
        "Compare all candidate pairs in the review pack.\n"
        "Return strict JSON with top-level key comparisons.\n"
        f"Candidates: {', '.join(candidate_ids)}\n\n"
        f"{review_pack}"
    )


def _apply_judging(
    *,
    config: ResolvedBenchmarkConfig,
    base_client: object,
    run_dir: Path,
    preparation_by_profile: Mapping[str, ProfilePreparation],
    candidate_results: list[CandidateProfileResult],
) -> dict[str, object]:
    if not config.run_judge:
        return {"skipped": True, "reason": "skip_judge", "total_judge_cost": 0.0, "judge_models_returned": []}

    grouped: dict[str, list[CandidateProfileResult]] = {}
    for result in candidate_results:
        grouped.setdefault(result.profile_id, []).append(result)

    total_judge_cost = 0.0
    returned_models: list[str] = []
    judging_summary: dict[str, object] = {"profiles": {}, "total_judge_cost": 0.0, "judge_models_returned": []}

    for profile_id, results in grouped.items():
        successful_results = [result for result in results if result.ok]
        if len(successful_results) < 2:
            continue
        review_pack = _build_profile_review_pack(profile_id, preparation_by_profile[profile_id], successful_results)
        _write_text(run_dir / "judging" / profile_id / "review_pack.txt", review_pack)

        rubric_response = _run_text_request(
            base_client,
            requested_model=config.judge_model,
            system_prompt=config.judge_prompt_text,
            user_prompt=_build_rubric_prompt(review_pack, successful_results),
            target_text=review_pack,
            temperature=config.judge_temperature,
            timeout_seconds=config.request_timeout_seconds,
            max_retries=config.max_retries,
        )
        pairwise_response = _run_text_request(
            base_client,
            requested_model=config.judge_model,
            system_prompt=config.judge_prompt_text,
            user_prompt=_build_pairwise_prompt(review_pack, successful_results),
            target_text=review_pack,
            temperature=config.judge_temperature,
            timeout_seconds=config.request_timeout_seconds,
            max_retries=config.max_retries,
        )

        total_judge_cost += float(rubric_response.get("usage", {}).get("cost") or 0.0)
        total_judge_cost += float(pairwise_response.get("usage", {}).get("cost") or 0.0)
        returned_models.extend(
            model
            for model in [
                str(rubric_response.get("usage", {}).get("response_model") or "").strip(),
                str(pairwise_response.get("usage", {}).get("response_model") or "").strip(),
            ]
            if model
        )

        rubric_payload = _json_from_response_text(str(rubric_response.get("response_text") or "")) if rubric_response.get("ok") else None
        pairwise_payload = _json_from_response_text(str(pairwise_response.get("response_text") or "")) if pairwise_response.get("ok") else None
        _write_json(run_dir / "judging" / profile_id / "rubric_response.json", rubric_response)
        _write_json(run_dir / "judging" / profile_id / "pairwise_response.json", pairwise_response)
        _write_json(run_dir / "judging" / profile_id / "rubric_payload.json", rubric_payload or {})
        _write_json(run_dir / "judging" / profile_id / "pairwise_payload.json", pairwise_payload or {})

        if rubric_payload is not None:
            candidate_scores = rubric_payload.get("candidate_scores")
            if isinstance(candidate_scores, dict):
                for result in successful_results:
                    payload = candidate_scores.get(result.candidate.id)
                    if isinstance(payload, dict):
                        try:
                            result.judge_weighted_score = float(payload.get("weighted_score") or 0.0)
                        except (TypeError, ValueError):
                            result.judge_weighted_score = 0.0

        if pairwise_payload is not None:
            comparisons = pairwise_payload.get("comparisons")
            if isinstance(comparisons, list):
                for comparison in comparisons:
                    if not isinstance(comparison, dict):
                        continue
                    left = str(comparison.get("left") or "")
                    right = str(comparison.get("right") or "")
                    winner = str(comparison.get("winner") or "")
                    if not left or not right:
                        continue
                    left_result = next((item for item in successful_results if item.candidate.id == left), None)
                    right_result = next((item for item in successful_results if item.candidate.id == right), None)
                    if left_result is None or right_result is None:
                        continue
                    if winner == "tie":
                        left_result.pairwise_wins += 0.5
                        right_result.pairwise_wins += 0.5
                    elif winner == left:
                        left_result.pairwise_wins += 1.0
                    elif winner == right:
                        right_result.pairwise_wins += 1.0
                    left_result.pairwise_total += 1.0
                    right_result.pairwise_total += 1.0

        judging_summary["profiles"][profile_id] = {
            "rubric_ok": bool(rubric_response.get("ok")),
            "pairwise_ok": bool(pairwise_response.get("ok")),
            "rubric_cost": float(rubric_response.get("usage", {}).get("cost") or 0.0),
            "pairwise_cost": float(pairwise_response.get("usage", {}).get("cost") or 0.0),
        }

    judging_summary["total_judge_cost"] = round(total_judge_cost, 6)
    judging_summary["judge_models_returned"] = sorted(set(returned_models))
    return judging_summary


def _cost_latency_scores(results: Sequence[dict[str, object]]) -> dict[str, float]:
    candidate_rows = [row for row in results if row.get("candidate_id")]
    if not candidate_rows:
        return {}
    cost_known_rows = [row for row in candidate_rows if bool(row.get("cost_known", False))]
    cost_rank_order = sorted(cost_known_rows, key=lambda row: (float(row.get("total_cost") or 0.0), float(row.get("average_latency_seconds") or 0.0)))
    latency_rank_order = sorted(candidate_rows, key=lambda row: float(row.get("average_latency_seconds") or 0.0))
    scores: dict[str, float] = {}
    for row in candidate_rows:
        candidate_id = str(row.get("candidate_id") or "")
        latency_rank = latency_rank_order.index(row) + 1
        latency_component = 100.0 * (len(latency_rank_order) - latency_rank + 1) / max(len(latency_rank_order), 1)
        if row in cost_rank_order:
            cost_rank = cost_rank_order.index(row) + 1
            cost_component = 100.0 * (len(cost_rank_order) - cost_rank + 1) / max(len(cost_rank_order), 1)
            score = (latency_component + cost_component) / 2.0
        else:
            score = latency_component
        scores[candidate_id] = round(score, 2)
    return scores


def _recommendation_for_row(row: Mapping[str, object], top_score: float) -> str:
    severe_flag_count = int(row.get("severe_flag_count") or 0)
    final_score = float(row.get("final_score") or 0.0)
    pairwise_win_rate = float(row.get("pairwise_win_rate") or 0.0)
    if int(row.get("hard_failure_count") or 0) >= int(row.get("selected_profile_count") or 1):
        return "not_recommended"
    if severe_flag_count > 0:
        return "not_recommended"
    if float(row.get("judge_coverage_ratio") or 0.0) < 0.5:
        return "needs_more_validation"
    if final_score >= top_score and pairwise_win_rate >= 0.60:
        return "best_structure_quality"
    if final_score >= top_score - 5 and bool(row.get("cheaper_or_faster_than_leader", False)) and not bool(row.get("worse_than_deterministic_on_pass_profile", False)):
        return "best_price_quality"
    if final_score >= max(60.0, top_score - 10):
        return "promising_with_risks"
    return "needs_more_validation"


def _build_summary(
    *,
    run_id: str,
    config: ResolvedBenchmarkConfig,
    preparation_by_profile: Mapping[str, ProfilePreparation],
    candidate_results: Sequence[CandidateProfileResult],
    judging_summary: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    per_candidate_results: dict[str, list[CandidateProfileResult]] = {}
    for result in candidate_results:
        per_candidate_results.setdefault(result.candidate.id, []).append(result)

    candidate_rows: list[dict[str, object]] = []
    for candidate in config.candidates:
        rows = per_candidate_results.get(candidate.id, [])
        if not rows:
            continue
        completed_rows = [row for row in rows if row.ok]
        hard_failure_count = sum(1 for row in rows if not row.ok)
        judge_scores = [float(row.judge_weighted_score) for row in completed_rows if row.judge_weighted_score is not None]
        pairwise_wins = sum(row.pairwise_wins for row in completed_rows)
        pairwise_total = sum(row.pairwise_total for row in completed_rows)
        deterministic_scores = [_deterministic_pipeline_score(row) for row in completed_rows]
        schema_violation_count = sum(int(row.metrics.get("schema_violation_count") or 0) for row in rows)
        total_classified = sum(max(int(row.metrics.get("classified_count") or 0), 1) for row in rows)
        hard_failure_rate = hard_failure_count / max(len(config.profiles), 1)
        schema_violation_rate = schema_violation_count / max(total_classified, 1)
        normalized_schema_violation_penalty = min(25.0, schema_violation_rate * 100.0)
        reliability_score = max(0.0, 100.0 - hard_failure_rate * 100.0 - normalized_schema_violation_penalty)
        judge_coverage_ratio = len(judge_scores) / max(len(config.profiles), 1)
        total_cost = round(sum(float(row.usage.get("cost") or 0.0) for row in rows), 6)
        cost_known = all(bool(row.usage.get("cost_known")) for row in rows if row.ok) if rows else False
        average_latency_seconds = round(sum(float(row.metrics.get("average_latency_seconds") or 0.0) for row in completed_rows) / max(len(completed_rows), 1), 3) if completed_rows else 0.0
        row = {
            "candidate_id": candidate.id,
            "label": candidate.label,
            "average_judge_weighted_score": round(sum(judge_scores) / max(len(judge_scores), 1), 2) if judge_scores else 0.0,
            "pairwise_win_rate": round(pairwise_wins / max(pairwise_total, 1.0), 4) if pairwise_total else 0.0,
            "deterministic_pipeline_score": round(sum(deterministic_scores) / max(len(deterministic_scores), 1), 2) if deterministic_scores else 0.0,
            "reliability_score": round(reliability_score, 2),
            "cost_latency_score": 0.0,
            "completed_profiles": len(completed_rows),
            "failed_profiles": hard_failure_count,
            "hard_failure_count": hard_failure_count,
            "schema_violation_count": schema_violation_count,
            "severe_flag_counts": {
                flag: sum(1 for item in rows if flag in item.severe_flags)
                for flag in sorted({flag for item in rows for flag in item.severe_flags})
            },
            "severe_flag_count": sum(1 for item in rows if item.severe_flags),
            "total_cost": total_cost,
            "cost_known": cost_known,
            "average_latency_seconds": average_latency_seconds,
            "returned_models": sorted({model for item in rows for model in item.returned_models}),
            "artifact_paths": [
                f"benchmark_projects/structure_recognition_benchmark/artifacts/runs/{run_id}/candidates/{item.profile_id}/{candidate.id}"
                for item in rows
            ],
            "judge_coverage_ratio": round(judge_coverage_ratio, 4),
            "selected_profile_count": len(config.profiles),
            "worse_than_deterministic_on_pass_profile": any(
                _deterministic_pipeline_score(item) < 100.0 and str(getattr(load_validation_registry().get_document_profile(item.profile_id), "structural_expected_result", "pass")) == "pass"
                for item in completed_rows
            ),
        }
        candidate_rows.append(row)

    cost_latency_scores = _cost_latency_scores(candidate_rows)
    for row in candidate_rows:
        row["cost_latency_score"] = cost_latency_scores.get(str(row.get("candidate_id") or ""), 0.0)

    for row in candidate_rows:
        row["final_score"] = round(
            0.55 * float(row.get("average_judge_weighted_score") or 0.0)
            + 0.20 * (float(row.get("pairwise_win_rate") or 0.0) * 100.0)
            + 0.15 * float(row.get("deterministic_pipeline_score") or 0.0)
            + 0.05 * float(row.get("reliability_score") or 0.0)
            + 0.05 * float(row.get("cost_latency_score") or 0.0),
            2,
        )

    sorted_rows = sorted(candidate_rows, key=lambda row: (float(row.get("final_score") or 0.0), float(row.get("deterministic_pipeline_score") or 0.0)), reverse=True)
    top_score = float(sorted_rows[0].get("final_score") or 0.0) if sorted_rows else 0.0
    leader = sorted_rows[0] if sorted_rows else None
    for row in sorted_rows:
        row["cheaper_or_faster_than_leader"] = False if leader is None else (
            float(row.get("total_cost") or 0.0) < float(leader.get("total_cost") or 0.0)
            or float(row.get("average_latency_seconds") or 0.0) < float(leader.get("average_latency_seconds") or 0.0)
        )
        row["recommendation"] = _recommendation_for_row(row, top_score)

    per_profile: dict[str, object] = {}
    for profile_id, preparation in preparation_by_profile.items():
        results = [result for result in candidate_results if result.profile_id == profile_id]
        winners = sorted((result for result in results if result.ok), key=lambda result: (_deterministic_pipeline_score(result), float(result.judge_weighted_score or 0.0)), reverse=True)
        per_profile[profile_id] = {
            "baseline": preparation.baseline_metrics,
            "winner": winners[0].candidate.id if winners else None,
            "major_failures": [
                {"candidate_id": result.candidate.id, "error": result.error, "flags": result.flags}
                for result in results
                if not result.ok or result.severe_flags
            ],
        }

    summary_payload = {
        "run_id": run_id,
        "profiles": list(config.profiles),
        "judge_model_requested": config.judge_model,
        "judge_model_returned": list(judging_summary.get("judge_models_returned") or []),
        "candidate_count": len(sorted_rows),
        "profile_count": len(config.profiles),
        "window_count": sum(len(preparation.review_windows) for preparation in preparation_by_profile.values()),
        "total_candidate_cost": round(sum(float(row.get("total_cost") or 0.0) for row in sorted_rows), 6),
        "total_judge_cost": round(float(judging_summary.get("total_judge_cost") or 0.0), 6),
        "rankings": [{"candidate_id": row["candidate_id"], "final_score": row["final_score"], "recommendation": row["recommendation"]} for row in sorted_rows],
        "per_candidate": {row["candidate_id"]: row for row in sorted_rows},
        "per_profile": per_profile,
        "baseline_comparison": {profile_id: preparation.baseline_metrics for profile_id, preparation in preparation_by_profile.items()},
        "notes": [],
    }

    lines = [f"# Structure Recognition Benchmark {run_id}", "", f"Profiles: {', '.join(config.profiles)}", ""]
    lines.append("## Ranking")
    lines.append("")
    if sorted_rows:
        lines.append("| Candidate | Final Score | Judge | Pairwise | Deterministic | Cost | Latency | Recommendation |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|---|")
        for row in sorted_rows:
            lines.append(
                f"| {row['label']} | {row['final_score']:.2f} | {float(row['average_judge_weighted_score']):.2f} | {float(row['pairwise_win_rate']):.4f} | {float(row['deterministic_pipeline_score']):.2f} | {float(row['total_cost']):.6f} | {float(row['average_latency_seconds']):.3f}s | {row['recommendation']} |"
            )
    else:
        lines.append("- No paid candidate executions were run in this benchmark invocation.")
    lines.append("")
    lines.append("## Baseline")
    lines.append("")
    for profile_id, preparation in preparation_by_profile.items():
        lines.append(f"- {profile_id}: readiness={preparation.baseline_metrics['readiness_status']} segments={preparation.baseline_metrics['segment_count']} headings={preparation.baseline_metrics['heading_count_after_apply']}")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    if not config.run_judge:
        lines.append("- Judge was skipped; ranking is deterministic-only and provisional.")
    elif not sorted_rows:
        lines.append("- This was a baseline-only run; candidate ranking was intentionally skipped.")
    elif not judging_summary.get("judge_models_returned"):
        lines.append("- Judge artifacts were requested, but no judge model response was recorded.")
    else:
        lines.append(f"- Judge models returned: {', '.join(judging_summary.get('judge_models_returned') or [])}")
    markdown = "\n".join(lines).strip() + "\n"
    return summary_payload, markdown


def _write_latest_aliases(config: ResolvedBenchmarkConfig, run_id: str, run_dir: Path) -> None:
    latest_run_payload = {
        "run_id": run_id,
        "artifact_root": _relative_path(run_dir),
        "created_at": _now_utc_iso(),
    }
    _write_json(config.output_root / "latest_run.json", latest_run_payload)
    summary_path = run_dir / "summary.json"
    summary_md_path = run_dir / "summary.md"
    manifest_path = run_dir / "manifest.json"
    shutil.copyfile(summary_path, config.output_root / "latest_summary.json")
    shutil.copyfile(summary_md_path, config.output_root / "latest_summary.md")
    shutil.copyfile(manifest_path, config.output_root / "latest_manifest.json")


def _build_manifest(
    *,
    run_id: str,
    config: ResolvedBenchmarkConfig,
    run_dir: Path,
    status: str,
    available_candidates: Sequence[CandidateConfig],
    preparation_by_profile: Mapping[str, ProfilePreparation],
    candidate_results: Sequence[CandidateProfileResult],
    judging_summary: Mapping[str, object],
    notes: Sequence[str],
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "created_at": _now_utc_iso(),
        "status": status,
        "artifact_root": _relative_path(run_dir),
        "config_path": _relative_path(config.config_path),
        "repo_commit_sha": _git_commit_sha(),
        "dirty_worktree": _git_dirty_worktree(),
        "selected_profile_ids": list(config.profiles),
        "source_documents": [
            {
                "profile_id": preparation.profile_id,
                "source_path": _relative_path(preparation.source_path),
                "source_sha256": preparation.source_sha256,
            }
            for preparation in preparation_by_profile.values()
        ],
        "candidate_list": _extract_requested_candidate_ids(config),
        "available_candidate_list": [candidate.id for candidate in available_candidates],
        "requested_models": {result.candidate.id: result.candidate.model for result in candidate_results},
        "returned_models": {result.candidate.id: result.returned_models for result in candidate_results},
        "judge_model_requested": config.judge_model,
        "judge_models_returned": list(judging_summary.get("judge_models_returned") or []),
        "provider_contract": {
            "openrouter_base_url": config.openrouter_base_url,
            "openrouter_referer": config.openrouter_referer,
            "openrouter_title": config.openrouter_title,
        },
        "prompt_snapshot_paths": {
            "production_structure_prompt": "benchmark_projects/structure_recognition_benchmark/artifacts/runs/" + run_id + "/resolved_production_structure_prompt.snapshot.txt",
            "judge_prompt": "benchmark_projects/structure_recognition_benchmark/artifacts/runs/" + run_id + "/judge_prompt.snapshot.txt",
        },
        "candidate_execution_entrypoint": "production_equivalent_helper_chain",
        "total_candidate_cost": round(sum(float(result.usage.get("cost") or 0.0) for result in candidate_results), 6),
        "total_judge_cost": round(float(judging_summary.get("total_judge_cost") or 0.0), 6),
        "total_candidate_duration_seconds": round(sum(float(result.metrics.get("average_latency_seconds") or 0.0) for result in candidate_results), 3),
        "hard_failure_count": sum(1 for result in candidate_results if not result.ok),
        "notes": list(notes),
        "runtime_platform": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
        },
    }


def _arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run structure recognition benchmark.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--profiles", default="")
    parser.add_argument("--candidates", default="")
    parser.add_argument("--max-profiles", type=int, default=None)
    parser.add_argument("--max-paragraphs-per-profile", type=int, default=None)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--output-root", default=str(ARTIFACT_ROOT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _arg_parser().parse_args(argv)
    _ensure_project_imports()

    config = _load_config(args)
    run_id = _new_run_id()
    run_dir = config.output_root / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_text(run_dir / "judge_prompt.snapshot.txt", config.judge_prompt_text + "\n")
    production_prompt_path = REPO_ROOT / "src" / "docxaicorrector" / "resources" / "prompts" / "structure_recognition_system.txt"
    _write_text(run_dir / "resolved_production_structure_prompt.snapshot.txt", production_prompt_path.read_text(encoding="utf-8"))
    _write_text(run_dir / "benchmark_config.snapshot.toml", _render_config_snapshot(config))

    app_config = load_app_config()
    preparation_by_profile: dict[str, ProfilePreparation] = {}
    notes: list[str] = []
    for profile_id in config.profiles:
        preparation = _load_profile_preparation(profile_id, config, app_config)
        preparation_by_profile[profile_id] = preparation
        _profile_inputs_artifacts(run_dir, preparation)
        _baseline_artifacts(run_dir, preparation)

    available_candidates: list[CandidateConfig] = []
    model_availability_payload: dict[str, object] = {"skipped": True}
    api_key = None
    base_client = None
    if not args.baseline_only:
        api_key = _ensure_openrouter_env()
        available_candidates, model_availability_payload = _availability_for_candidates(
            config=config,
            candidates=config.candidates,
            run_dir=run_dir,
            api_key=api_key,
        )
        if len(available_candidates) < 2:
            raise RuntimeError("Fewer than two candidate models remain after OpenRouter availability preflight.")
        base_client = _build_openrouter_client(api_key, config)
    else:
        _write_json(run_dir / "model_availability.json", model_availability_payload)

    candidate_results: list[CandidateProfileResult] = []
    if not args.baseline_only and base_client is not None:
        for profile_id in config.profiles:
            preparation = preparation_by_profile[profile_id]
            for candidate in available_candidates:
                result = _run_candidate_for_profile(
                    candidate=candidate,
                    preparation=preparation,
                    config=config,
                    app_config=app_config,
                    base_client=base_client,
                )
                candidate_results.append(result)
                _write_candidate_artifacts(run_dir, result)

    judging_summary = {"skipped": True, "reason": "baseline_only" if args.baseline_only else "not_run", "total_judge_cost": 0.0, "judge_models_returned": []}
    if not args.baseline_only and base_client is not None:
        judging_summary = _apply_judging(
            config=config,
            base_client=base_client,
            run_dir=run_dir,
            preparation_by_profile=preparation_by_profile,
            candidate_results=candidate_results,
        )

    summary_payload, summary_markdown = _build_summary(
        run_id=run_id,
        config=config,
        preparation_by_profile=preparation_by_profile,
        candidate_results=candidate_results,
        judging_summary=judging_summary,
    )
    _write_json(run_dir / "summary.json", summary_payload)
    _write_text(run_dir / "summary.md", summary_markdown)
    _write_text(run_dir / "findings_for_project_backlog.md", "# Findings Backlog\n\n")
    _write_text(run_dir / "human_review_pack" / "summary.md", summary_markdown)
    _write_text(run_dir / "human_review_pack" / "top_disagreements.md", "# Top Disagreements\n\n")
    _write_text(run_dir / "human_review_pack" / "model_ranking_blinded.md", "# Blinded Ranking\n\n")
    _write_json(
        run_dir / "human_review_pack" / "model_mapping.json",
        {candidate.id: candidate.label for candidate in config.candidates},
    )

    manifest_payload = _build_manifest(
        run_id=run_id,
        config=config,
        run_dir=run_dir,
        status="completed",
        available_candidates=available_candidates,
        preparation_by_profile=preparation_by_profile,
        candidate_results=candidate_results,
        judging_summary=judging_summary,
        notes=notes,
    )
    _write_json(run_dir / "manifest.json", manifest_payload)
    _write_latest_aliases(config, run_id, run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())