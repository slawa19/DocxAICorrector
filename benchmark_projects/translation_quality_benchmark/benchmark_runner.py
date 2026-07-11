from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any


def _resolve_repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in current.parents:
        if (candidate / "corpus_registry.toml").exists() and (candidate / "src" / "docxaicorrector" / "validation" / "profiles.py").exists():
            return candidate
    raise RuntimeError("Could not resolve repository root from benchmark project.")


REPO_ROOT = _resolve_repo_root()
SRC_ROOT = REPO_ROOT / "src"


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
build_document_text = None
build_semantic_blocks = None
extract_document_content_with_normalization_reports = None
collect_response_text_traversal = None
read_response_field = None
extract_unsupported_parameter_name = None
is_retryable_error = None
parse_json_object = None
load_validation_registry = None


def _ensure_project_imports() -> None:
    global OpenAI
    global processing_runtime
    global load_project_dotenv
    global build_document_text
    global build_semantic_blocks
    global extract_document_content_with_normalization_reports
    global collect_response_text_traversal
    global read_response_field
    global extract_unsupported_parameter_name
    global is_retryable_error
    global parse_json_object
    global load_validation_registry
    if OpenAI is not None:
        return

    from openai import OpenAI as imported_openai

    import docxaicorrector.processing.processing_runtime as imported_processing_runtime
    from docxaicorrector.core.config import load_project_dotenv as imported_load_project_dotenv
    from docxaicorrector.document._document import (
        build_document_text as imported_build_document_text,
        build_semantic_blocks as imported_build_semantic_blocks,
        extract_document_content_with_normalization_reports as imported_extract_document_content_with_normalization_reports,
    )
    from docxaicorrector.generation.openai_response_utils import (
        collect_response_text_traversal as imported_collect_response_text_traversal,
        read_response_field as imported_read_response_field,
    )
    from docxaicorrector.image.shared import (
        extract_unsupported_parameter_name as imported_extract_unsupported_parameter_name,
        is_retryable_error as imported_is_retryable_error,
        parse_json_object as imported_parse_json_object,
    )
    from docxaicorrector.validation.profiles import load_validation_registry as imported_load_validation_registry

    OpenAI = imported_openai
    processing_runtime = imported_processing_runtime
    load_project_dotenv = imported_load_project_dotenv
    build_document_text = imported_build_document_text
    build_semantic_blocks = imported_build_semantic_blocks
    extract_document_content_with_normalization_reports = imported_extract_document_content_with_normalization_reports
    collect_response_text_traversal = imported_collect_response_text_traversal
    read_response_field = imported_read_response_field
    extract_unsupported_parameter_name = imported_extract_unsupported_parameter_name
    is_retryable_error = imported_is_retryable_error
    parse_json_object = imported_parse_json_object
    load_validation_registry = imported_load_validation_registry


ARTIFACT_ROOT = REPO_ROOT / "benchmark_projects" / "translation_quality_benchmark" / "artifacts"
RUNS_ROOT = ARTIFACT_ROOT / "runs"
DEFAULT_CONFIG_PATH = REPO_ROOT / "benchmark_projects" / "translation_quality_benchmark" / "benchmark_config.toml"
DEFAULT_PROFILE_IDS = ("mazzucato-pdf-full-benchmark", "lietaer-pdf-full-benchmark")
TOC_STRUCTURAL_ROLES = {"toc_header", "toc_entry"}
FORBIDDEN_META_PATTERNS = (
    re.compile(r"^\s*(?:here(?:'s| is)\s+the\s+translation|translation\s*:)", re.IGNORECASE),
    re.compile(r"^\s*(?:sure[,!]?\s+)?(?:here(?:'s| is)|below is)\b", re.IGNORECASE),
    re.compile(r"^\s*(?:вот\s+перевод|перевод\s*:)", re.IGNORECASE),
)
ENGLISH_RESIDUE_WORD_PATTERN = re.compile(
    r"\b(?:the|and|with|from|into|this|that|these|those|because|however|therefore|market|value|state|capital|policy|system|economic|innovation)\b",
    re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"[A-Za-zА-Яа-яЁё0-9']+")
LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")
CYRILLIC_CHAR_PATTERN = re.compile(r"[А-Яа-яЁё]")
HEADING_PATTERN = re.compile(r"^#{1,6}\s+", re.MULTILINE)
LIST_PATTERN = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", re.MULTILINE)
ENGLISH_FUNCTION_WORDS = frozenset(
    {
        "the",
        "and",
        "of",
        "to",
        "in",
        "a",
        "is",
        "that",
        "for",
        "it",
        "as",
        "with",
        "was",
        "on",
        "be",
        "are",
        "by",
        "this",
        "from",
        "or",
        "an",
        "at",
        "we",
        "not",
        "have",
        "has",
        "but",
        "their",
        "they",
        "which",
        "can",
        "more",
        "than",
        "also",
        "into",
        "these",
        "those",
        "our",
        "who",
        "will",
    }
)
RUSSIAN_FUNCTION_WORDS = frozenset(
    {
        "и",
        "в",
        "на",
        "что",
        "это",
        "как",
        "не",
        "с",
        "по",
        "для",
        "из",
        "к",
        "мы",
        "они",
        "но",
        "или",
        "также",
        "при",
        "от",
        "у",
        "до",
        "если",
        "когда",
        "есть",
        "был",
        "были",
        "его",
        "ее",
        "их",
        "который",
        "которая",
        "которые",
        "чтобы",
        "же",
        "ли",
        "о",
        "об",
        "под",
        "над",
        "между",
    }
)
RUBRIC_WEIGHTS = {
    "russian_naturalness": 20,
    "semantic_accuracy": 18,
    "authorial_voice": 14,
    "anti_calque_quality": 12,
    "book_prose_rhythm": 10,
    "terminology_consistency": 10,
    "discourse_coherence": 6,
    "structure_preservation": 5,
    "post_editing_burden": 5,
}


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
    target_language: str
    target_language_name: str
    source_language: str
    judge_model: str
    openrouter_base_url: str
    openrouter_referer: str
    openrouter_title: str
    translation_prompt_file: str
    target_language_profile_file: str
    prompt_path: Path
    target_language_profile_path: Path
    prompt_template_text: str
    prompt_text: str
    target_language_profile_text: str
    target_language_profile: dict[str, object]
    profiles: tuple[str, ...]
    max_fragments: int
    preferred_min_chars: int
    preferred_max_chars: int
    fallback_min_chars: int
    fallback_max_chars: int
    request_timeout_seconds: int
    max_retries: int
    translation_temperature: float
    judge_temperature: float
    candidates: tuple[CandidateConfig, ...]


@dataclass
class ProfileExtraction:
    profile: object
    source_path: Path
    source_sha256: str
    paragraphs: list[object]
    relations: list[object]
    blocks: list[object]


@dataclass(frozen=True)
class FragmentCandidate:
    start_block_index: int
    end_block_index: int
    paragraph_count: int
    char_count: int
    word_count: int
    text: str
    region: str
    merged: bool
    feature_flags: tuple[str, ...]
    paragraph_indexes: tuple[int, ...]


@dataclass(frozen=True)
class FragmentRecord:
    fragment_id: str
    profile_id: str
    source_path: str
    source_text: str
    source_char_count: int
    source_word_count: int
    paragraph_count: int
    block_indexes: tuple[int, ...]
    paragraph_indexes: tuple[int, ...]
    region: str
    merged: bool
    feature_flags: tuple[str, ...]
    selection_reason: str
    metadata: dict[str, object]


@dataclass
class TranslationResult:
    fragment_id: str
    candidate_id: str
    candidate_label: str
    requested_model: str
    returned_model: str
    status: str
    output_text: str
    output_char_count: int
    usage: dict[str, object]
    automated_checks: dict[str, object]
    attempt_history: list[dict[str, object]]
    duration_seconds: float
    error_message: str | None
    artifact_paths: dict[str, str]


@dataclass
class JudgeArtifact:
    fragment_id: str
    rubric_scores: list[dict[str, object]] = field(default_factory=list)
    rubric_failures: list[dict[str, object]] = field(default_factory=list)
    pairwise_comparisons: list[dict[str, object]] = field(default_factory=list)
    pairwise_failures: list[dict[str, object]] = field(default_factory=list)
    judge_metadata: dict[str, object] = field(default_factory=dict)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the isolated translation quality benchmark.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--target-language", default="")
    parser.add_argument("--profiles", default="")
    parser.add_argument("--max-fragments", type=int, default=0)
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument("--candidates", default="")
    parser.add_argument("--output-root", default=str(RUNS_ROOT))
    return parser.parse_args(list(argv) if argv is not None else None)


def _make_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:8]}"


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _relative_artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _copy_latest_aliases(*, run_dir: Path, summary_json_path: Path, summary_md_path: Path, manifest_path: Path) -> None:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(summary_json_path, ARTIFACT_ROOT / "latest_summary.json")
    shutil.copy2(summary_md_path, ARTIFACT_ROOT / "latest_summary.md")
    shutil.copy2(manifest_path, ARTIFACT_ROOT / "latest_manifest.json")
    _write_json(
        ARTIFACT_ROOT / "latest_run.json",
        {
            "benchmark_run_id": run_dir.name,
            "run_dir": _relative_artifact_path(run_dir),
            "summary_json_path": _relative_artifact_path(summary_json_path),
            "summary_md_path": _relative_artifact_path(summary_md_path),
            "manifest_path": _relative_artifact_path(manifest_path),
        },
    )


def _parse_csv(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _coerce_str(value: object, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Expected non-empty string for {field_name}.")
    return value.strip()


def _coerce_int(value: object, *, field_name: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RuntimeError(f"Expected integer-compatible value for {field_name}.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Expected integer-compatible value for {field_name}.") from exc
    if minimum is not None and parsed < minimum:
        raise RuntimeError(f"Expected {field_name} >= {minimum}, got {parsed}.")
    return parsed


def _coerce_float(value: object, *, field_name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RuntimeError(f"Expected numeric value for {field_name}.")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Expected numeric value for {field_name}.") from exc
    if minimum is not None and parsed < minimum:
        raise RuntimeError(f"Expected {field_name} >= {minimum}, got {parsed}.")
    return parsed


def _normalize_model_output(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :].strip()
        else:
            cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


def _build_language_profile_summary(profile: Mapping[str, object]) -> str:
    lines: list[str] = []
    name = str(profile.get("name") or "").strip()
    quality_focus = str(profile.get("quality_focus") or "").strip()
    if name:
        lines.append(f"Language: {name}")
    if quality_focus:
        lines.append(f"Quality focus: {quality_focus}")
    avoid = profile.get("avoid")
    if isinstance(avoid, list) and avoid:
        lines.append("Avoid:")
        lines.extend(f"- {item}" for item in avoid)
    prefer = profile.get("prefer")
    if isinstance(prefer, list) and prefer:
        lines.append("Prefer:")
        lines.extend(f"- {item}" for item in prefer)
    return "\n".join(lines).strip()


def _load_config(args: argparse.Namespace) -> ResolvedBenchmarkConfig:
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (REPO_ROOT / config_path).resolve()
    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    benchmark = payload.get("benchmark")
    if not isinstance(benchmark, dict):
        raise RuntimeError("Benchmark config must define [benchmark].")

    configured_target_language = _coerce_str(benchmark.get("target_language"), field_name="benchmark.target_language")
    cli_target_language = str(args.target_language or "").strip()
    if cli_target_language and cli_target_language != configured_target_language:
        raise RuntimeError(
            f"This MVP ships only {configured_target_language!r} benchmark assets; refusing override to {cli_target_language!r}."
        )

    configured_profiles = benchmark.get("profiles")
    profile_ids: tuple[str, ...]
    if isinstance(configured_profiles, list) and configured_profiles:
        profile_ids = tuple(str(item).strip() for item in configured_profiles if str(item).strip())
    else:
        profile_ids = DEFAULT_PROFILE_IDS
    profile_ids = _parse_csv(args.profiles) or profile_ids
    if not profile_ids:
        raise RuntimeError("Benchmark config must provide at least one source profile.")

    candidate_tables = payload.get("candidates")
    if not isinstance(candidate_tables, list) or len(candidate_tables) < 2:
        raise RuntimeError("Benchmark config must define at least two [[candidates]].")
    selected_candidate_ids = set(_parse_csv(args.candidates))
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
            raise RuntimeError(f"Unsupported candidate provider for MVP: {candidate.provider}")
        if selected_candidate_ids and candidate.id not in selected_candidate_ids:
            continue
        candidates.append(candidate)
    if len(candidates) < 2:
        raise RuntimeError("At least two candidate models must remain after CLI filtering.")

    prompt_file = _coerce_str(benchmark.get("translation_prompt_file"), field_name="benchmark.translation_prompt_file")
    language_profile_file = _coerce_str(
        benchmark.get("target_language_profile_file"),
        field_name="benchmark.target_language_profile_file",
    )
    prompt_path = (REPO_ROOT / prompt_file).resolve()
    language_profile_path = (REPO_ROOT / language_profile_file).resolve()
    prompt_template_text = prompt_path.read_text(encoding="utf-8")
    target_language_profile_text = language_profile_path.read_text(encoding="utf-8")
    target_language_profile = tomllib.loads(target_language_profile_text)
    target_language_name = _coerce_str(benchmark.get("target_language_name"), field_name="benchmark.target_language_name")
    prompt_text = prompt_template_text.format(
        target_language=configured_target_language,
        target_language_name=target_language_name,
        language_profile_summary=_build_language_profile_summary(target_language_profile),
    )

    judge_model = str(os.getenv("TRANSLATION_BENCHMARK_JUDGE_MODEL", "")).strip() or _coerce_str(
        benchmark.get("judge_model"),
        field_name="benchmark.judge_model",
    )
    openrouter_referer = str(os.getenv("TRANSLATION_BENCHMARK_OPENROUTER_REFERER", "")).strip() or _coerce_str(
        benchmark.get("openrouter_referer"),
        field_name="benchmark.openrouter_referer",
    )
    openrouter_title = str(os.getenv("TRANSLATION_BENCHMARK_OPENROUTER_TITLE", "")).strip() or _coerce_str(
        benchmark.get("openrouter_title"),
        field_name="benchmark.openrouter_title",
    )
    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = (REPO_ROOT / output_root).resolve()

    return ResolvedBenchmarkConfig(
        config_path=config_path,
        output_root=output_root,
        target_language=configured_target_language,
        target_language_name=target_language_name,
        source_language=_coerce_str(benchmark.get("source_language"), field_name="benchmark.source_language"),
        judge_model=judge_model,
        openrouter_base_url=_coerce_str(benchmark.get("openrouter_base_url"), field_name="benchmark.openrouter_base_url"),
        openrouter_referer=openrouter_referer,
        openrouter_title=openrouter_title,
        translation_prompt_file=prompt_file,
        target_language_profile_file=language_profile_file,
        prompt_path=prompt_path,
        target_language_profile_path=language_profile_path,
        prompt_template_text=prompt_template_text,
        prompt_text=prompt_text,
        target_language_profile_text=target_language_profile_text,
        target_language_profile=target_language_profile,
        profiles=tuple(profile_ids),
        max_fragments=(
            int(args.max_fragments)
            if int(args.max_fragments or 0) > 0
            else _coerce_int(benchmark.get("max_fragments", 6), field_name="benchmark.max_fragments", minimum=1)
        ),
        preferred_min_chars=_coerce_int(
            benchmark.get("preferred_min_chars", 1500),
            field_name="benchmark.preferred_min_chars",
            minimum=1,
        ),
        preferred_max_chars=_coerce_int(
            benchmark.get("preferred_max_chars", 3500),
            field_name="benchmark.preferred_max_chars",
            minimum=1,
        ),
        fallback_min_chars=_coerce_int(
            benchmark.get("fallback_min_chars", 1000),
            field_name="benchmark.fallback_min_chars",
            minimum=1,
        ),
        fallback_max_chars=_coerce_int(
            benchmark.get("fallback_max_chars", 4500),
            field_name="benchmark.fallback_max_chars",
            minimum=1,
        ),
        request_timeout_seconds=_coerce_int(
            benchmark.get("request_timeout_seconds", 90),
            field_name="benchmark.request_timeout_seconds",
            minimum=1,
        ),
        max_retries=_coerce_int(benchmark.get("max_retries", 3), field_name="benchmark.max_retries", minimum=1),
        translation_temperature=_coerce_float(
            benchmark.get("translation_temperature", 0.2),
            field_name="benchmark.translation_temperature",
            minimum=0.0,
        ),
        judge_temperature=_coerce_float(
            benchmark.get("judge_temperature", 0.1),
            field_name="benchmark.judge_temperature",
            minimum=0.0,
        ),
        candidates=tuple(candidates),
    )


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
    lines.append(f"target_language = {_toml_scalar(config.target_language)}")
    lines.append(f"target_language_name = {_toml_scalar(config.target_language_name)}")
    lines.append(f"source_language = {_toml_scalar(config.source_language)}")
    lines.append(f"judge_model = {_toml_scalar(config.judge_model)}")
    lines.append(f"openrouter_base_url = {_toml_scalar(config.openrouter_base_url)}")
    lines.append(f"openrouter_referer = {_toml_scalar(config.openrouter_referer)}")
    lines.append(f"openrouter_title = {_toml_scalar(config.openrouter_title)}")
    lines.append(f"translation_prompt_file = {_toml_scalar(config.translation_prompt_file)}")
    lines.append(f"target_language_profile_file = {_toml_scalar(config.target_language_profile_file)}")
    lines.append(f"profiles = {_toml_array(config.profiles)}")
    lines.append(f"max_fragments = {_toml_scalar(config.max_fragments)}")
    lines.append(f"preferred_min_chars = {_toml_scalar(config.preferred_min_chars)}")
    lines.append(f"preferred_max_chars = {_toml_scalar(config.preferred_max_chars)}")
    lines.append(f"fallback_min_chars = {_toml_scalar(config.fallback_min_chars)}")
    lines.append(f"fallback_max_chars = {_toml_scalar(config.fallback_max_chars)}")
    lines.append(f"request_timeout_seconds = {_toml_scalar(config.request_timeout_seconds)}")
    lines.append(f"max_retries = {_toml_scalar(config.max_retries)}")
    lines.append(f"translation_temperature = {_toml_scalar(config.translation_temperature)}")
    lines.append(f"judge_temperature = {_toml_scalar(config.judge_temperature)}")
    for candidate in config.candidates:
        lines.append("")
        lines.append("[[candidates]]")
        lines.append(f"id = {_toml_scalar(candidate.id)}")
        lines.append(f"label = {_toml_scalar(candidate.label)}")
        lines.append(f"provider = {_toml_scalar(candidate.provider)}")
        lines.append(f"model = {_toml_scalar(candidate.model)}")
    return "\n".join(lines) + "\n"


def _git_commit_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _runtime_platform_details() -> dict[str, object]:
    uname_result = None
    try:
        completed = subprocess.run(
            ["uname", "-a"],
            check=True,
            capture_output=True,
            cwd=REPO_ROOT,
            text=True,
        )
        uname_result = completed.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError):
        uname_result = None
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "uname": uname_result,
    }


def _build_manifest(
    *,
    run_id: str,
    config: ResolvedBenchmarkConfig,
    args: argparse.Namespace,
    run_dir: Path,
    status: str,
    available_candidates: Sequence[CandidateConfig] | None,
    fragment_ids: Sequence[str],
    model_availability_path: Path,
    total_translation_cost: float = 0.0,
    total_judge_cost: float = 0.0,
    returned_judge_models: Sequence[str] | None = None,
    notes: Sequence[str] | None = None,
    source_language_verification: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "benchmark_run_id": run_id,
        "status": status,
        "created_at": _now_utc_iso(),
        "artifact_root": _relative_artifact_path(run_dir),
        "config_path": _relative_artifact_path(config.config_path),
        "repo_commit_sha": _git_commit_sha(),
        "candidate_list": [candidate.id for candidate in config.candidates],
        "available_candidates": [candidate.id for candidate in (available_candidates or ())],
        "source_language": config.source_language,
        "source_profiles": list(config.profiles),
        "fragment_ids": list(fragment_ids),
        "judge_model_requested": config.judge_model,
        "judge_models_returned": sorted(set(returned_judge_models or [])),
        "openrouter_base_url": config.openrouter_base_url,
        "environment_flags": {
            "skip_judge": bool(args.skip_judge),
            "source_language": config.source_language,
            "target_language": config.target_language,
            "openrouter_referer": config.openrouter_referer,
            "openrouter_title": config.openrouter_title,
            "max_fragments": config.max_fragments,
        },
        "python_version": platform.python_version(),
        "runtime_platform": _runtime_platform_details(),
        "model_availability_path": _relative_artifact_path(model_availability_path),
        "total_translation_cost": round(total_translation_cost, 6),
        "total_judge_cost": round(total_judge_cost, 6),
        "source_language_verification": dict(source_language_verification or {}),
        "notes": list(notes or ()),
    }


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
            "Accept": "application/json",
            "HTTP-Referer": config.openrouter_referer,
            "X-Title": config.openrouter_title,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else ""
        raise RuntimeError(f"OpenRouter model catalog request failed with HTTP {exc.code}: {body[:400]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenRouter model catalog request failed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise RuntimeError("OpenRouter model catalog returned unexpected payload.")
    return payload


def _run_model_availability_preflight(
    *,
    api_key: str,
    config: ResolvedBenchmarkConfig,
    run_dir: Path,
) -> tuple[list[CandidateConfig], dict[str, object]]:
    catalog = _fetch_model_catalog(api_key=api_key, config=config)
    catalog_items = [item for item in catalog.get("data", []) if isinstance(item, dict)]
    by_id: dict[str, dict[str, object]] = {}
    by_id_casefold: dict[str, dict[str, object]] = {}
    for item in catalog_items:
        item_id = str(item.get("id") or "").strip()
        if item_id:
            by_id[item_id] = item
            by_id_casefold[item_id.casefold()] = item
        canonical_slug = str(item.get("canonical_slug") or "").strip()
        if canonical_slug:
            by_id.setdefault(canonical_slug, item)
            by_id_casefold.setdefault(canonical_slug.casefold(), item)

    availability_entries: list[dict[str, object]] = []
    available_candidates: list[CandidateConfig] = []
    for candidate in config.candidates:
        exact_match = by_id.get(candidate.model)
        casefold_match = by_id_casefold.get(candidate.model.casefold())
        matched = exact_match or casefold_match
        status = "available"
        mismatch_reason = ""
        if exact_match is None and casefold_match is not None:
            status = "model_id_mismatch"
            mismatch_reason = "configured model id does not exactly match catalog id"
        if matched is None:
            status = "unavailable"
            mismatch_reason = "model id not found in catalog"
        matched_model_id = str((matched or {}).get("id") or "")
        entry = {
            "candidate_id": candidate.id,
            "label": candidate.label,
            "requested_model_id": candidate.model,
            "matched_catalog_id": matched_model_id,
            "availability_status": status,
            "mismatch_reason": mismatch_reason,
            "supported_parameters": list((matched or {}).get("supported_parameters") or []),
            "context_length": (matched or {}).get("context_length"),
            "pricing": (matched or {}).get("pricing"),
        }
        availability_entries.append(entry)
        if status == "available":
            available_candidates.append(candidate)

    payload = {
        "checked_at": _now_utc_iso(),
        "catalog_model_count": len(catalog_items),
        "candidates": availability_entries,
    }
    _write_json(run_dir / "model_availability.json", payload)
    return available_candidates, payload


def _unpack_extraction_result(
    extraction_result: Sequence[object],
) -> tuple[list[object], list[object], object, list[object], object, object, object | None]:
    paragraphs, image_assets, normalization_report, relations, relation_report, cleanup_report = extraction_result[:6]
    structure_repair_report = extraction_result[6] if len(extraction_result) > 6 else None
    return (
        list(paragraphs),
        list(image_assets),
        normalization_report,
        list(relations),
        relation_report,
        cleanup_report,
        structure_repair_report,
    )


def _load_profile_extraction(profile: object, config: ResolvedBenchmarkConfig) -> ProfileExtraction:
    _ensure_project_imports()
    source_path = profile.resolved_source_path(REPO_ROOT)
    source_bytes = source_path.read_bytes()
    normalized_source = processing_runtime.normalize_uploaded_document(filename=source_path.name, source_bytes=source_bytes)
    paragraphs, _image_assets, _normalization_report, relations, _relation_report, _cleanup_report, _structure_repair = _unpack_extraction_result(
        extract_document_content_with_normalization_reports(BytesIO(normalized_source.content_bytes))
    )
    blocks = list(build_semantic_blocks(paragraphs, max_chars=config.preferred_max_chars, relations=relations))
    return ProfileExtraction(
        profile=profile,
        source_path=source_path,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        paragraphs=paragraphs,
        relations=relations,
        blocks=blocks,
    )


def _word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def _verification_method_name() -> str:
    return "script_ratio_and_function_word_heuristic_v1"


def _function_word_signal(words: Sequence[str], vocabulary: frozenset[str]) -> tuple[int, list[str]]:
    counts: Counter[str] = Counter(word for word in words if word in vocabulary)
    return sum(counts.values()), [word for word, _count in counts.most_common(8)]


def _verify_source_language(text: str, expected_language: str) -> dict[str, object]:
    words = [word.casefold() for word in WORD_PATTERN.findall(text)]
    word_count = len(words)
    latin_chars = len(LATIN_CHAR_PATTERN.findall(text))
    cyrillic_chars = len(CYRILLIC_CHAR_PATTERN.findall(text))
    alpha_chars = latin_chars + cyrillic_chars
    english_hits, english_samples = _function_word_signal(words, ENGLISH_FUNCTION_WORDS)
    russian_hits, russian_samples = _function_word_signal(words, RUSSIAN_FUNCTION_WORDS)
    latin_ratio = round(latin_chars / max(1, alpha_chars), 4)
    cyrillic_ratio = round(cyrillic_chars / max(1, alpha_chars), 4)
    english_word_ratio = round(english_hits / max(1, word_count), 4)
    russian_word_ratio = round(russian_hits / max(1, word_count), 4)
    dominant_script = "latin" if latin_chars > cyrillic_chars else ("cyrillic" if cyrillic_chars > latin_chars else "mixed_or_unknown")
    minimum_signal_hits = max(6, word_count // 60)
    note = ""

    if expected_language == "en":
        verified = latin_ratio >= 0.55 and english_hits >= minimum_signal_hits and russian_hits <= max(3, english_hits // 3)
        failed = cyrillic_ratio >= 0.35 and russian_hits >= minimum_signal_hits and russian_hits > english_hits
    elif expected_language == "ru":
        verified = cyrillic_ratio >= 0.55 and russian_hits >= minimum_signal_hits and english_hits <= max(3, russian_hits // 3)
        failed = latin_ratio >= 0.35 and english_hits >= minimum_signal_hits and english_hits > russian_hits
    else:
        verified = False
        failed = False
        note = f"Source-language verification is implemented only for 'en' and 'ru'; expected={expected_language!r}."

    if verified:
        status = "verified"
        allow_translation = True
        note = note or f"Detected {expected_language} source text via dominant script and function-word signals."
    elif failed:
        status = "failed"
        allow_translation = False
        note = note or f"Source-language mismatch: expected {expected_language}, but fragment shows stronger alternate-language signals."
    else:
        status = "suspicious"
        allow_translation = False
        note = note or f"Source-language verification was inconclusive for expected={expected_language!r}; fragment withheld from translation."

    expected_signal = english_word_ratio if expected_language == "en" else russian_word_ratio if expected_language == "ru" else 0.0
    alternate_signal = russian_word_ratio if expected_language == "en" else english_word_ratio if expected_language == "ru" else max(english_word_ratio, russian_word_ratio)
    confidence = round(abs(expected_signal - alternate_signal) + abs((latin_ratio if expected_language == "en" else cyrillic_ratio) - (cyrillic_ratio if expected_language == "en" else latin_ratio)), 4)
    return {
        "expected_language": expected_language,
        "status": status,
        "allow_translation": allow_translation,
        "method": _verification_method_name(),
        "confidence": confidence,
        "dominant_script": dominant_script,
        "word_count": word_count,
        "script_ratios": {
            "latin": latin_ratio,
            "cyrillic": cyrillic_ratio,
        },
        "function_word_hits": {
            "english": english_hits,
            "russian": russian_hits,
        },
        "function_word_ratios": {
            "english": english_word_ratio,
            "russian": russian_word_ratio,
        },
        "signal_samples": {
            "english": english_samples,
            "russian": russian_samples,
        },
        "note": note,
    }


def _new_source_language_verification_summary(expected_language: str) -> dict[str, object]:
    return {
        "enabled": True,
        "expected_language": expected_language,
        "method": _verification_method_name(),
        "checked_candidate_count": 0,
        "selected_fragment_count": 0,
        "selected_fragment_ids": [],
        "rejected_candidate_count": 0,
        "rejected_candidate_count_by_profile": {},
        "status_counts": {
            "verified": 0,
            "suspicious": 0,
            "failed": 0,
        },
    }


def _record_source_language_check(summary: dict[str, object], verification: Mapping[str, object], *, profile_id: str) -> None:
    summary["checked_candidate_count"] = int(summary.get("checked_candidate_count") or 0) + 1
    status = str(verification.get("status") or "suspicious")
    status_counts = dict(summary.get("status_counts") or {})
    status_counts[status] = int(status_counts.get(status) or 0) + 1
    summary["status_counts"] = status_counts
    if not bool(verification.get("allow_translation")):
        summary["rejected_candidate_count"] = int(summary.get("rejected_candidate_count") or 0) + 1
        rejected_by_profile = dict(summary.get("rejected_candidate_count_by_profile") or {})
        rejected_by_profile[profile_id] = int(rejected_by_profile.get(profile_id) or 0) + 1
        summary["rejected_candidate_count_by_profile"] = rejected_by_profile


def _record_selected_verified_fragment(summary: dict[str, object], fragment_id: str) -> None:
    summary["selected_fragment_count"] = int(summary.get("selected_fragment_count") or 0) + 1
    selected_ids = list(summary.get("selected_fragment_ids") or [])
    selected_ids.append(fragment_id)
    summary["selected_fragment_ids"] = selected_ids


def _merge_source_language_verification_summary(target: dict[str, object], source: Mapping[str, object]) -> dict[str, object]:
    target["checked_candidate_count"] = int(target.get("checked_candidate_count") or 0) + int(source.get("checked_candidate_count") or 0)
    target["selected_fragment_count"] = int(target.get("selected_fragment_count") or 0) + int(source.get("selected_fragment_count") or 0)
    target["rejected_candidate_count"] = int(target.get("rejected_candidate_count") or 0) + int(source.get("rejected_candidate_count") or 0)
    target["selected_fragment_ids"] = list(target.get("selected_fragment_ids") or []) + list(source.get("selected_fragment_ids") or [])

    target_status_counts = dict(target.get("status_counts") or {})
    for status, count in dict(source.get("status_counts") or {}).items():
        target_status_counts[str(status)] = int(target_status_counts.get(str(status)) or 0) + int(count or 0)
    target["status_counts"] = target_status_counts

    rejected_by_profile = dict(target.get("rejected_candidate_count_by_profile") or {})
    for profile_id, count in dict(source.get("rejected_candidate_count_by_profile") or {}).items():
        rejected_by_profile[str(profile_id)] = int(rejected_by_profile.get(str(profile_id)) or 0) + int(count or 0)
    target["rejected_candidate_count_by_profile"] = rejected_by_profile
    return target


def _paragraph_indexes(paragraphs: Sequence[object]) -> tuple[int, ...]:
    indexes: list[int] = []
    for paragraph in paragraphs:
        source_index = getattr(paragraph, "source_index", -1)
        if isinstance(source_index, int) and source_index >= 0:
            indexes.append(source_index)
    return tuple(indexes)


def _block_region(index: int, total_blocks: int) -> str:
    if total_blocks <= 1:
        return "middle"
    fraction = index / max(1, total_blocks - 1)
    if fraction < 0.34:
        return "early"
    if fraction < 0.67:
        return "middle"
    return "late"


def _toc_dominant(paragraphs: Sequence[object]) -> bool:
    if not paragraphs:
        return False
    toc_count = sum(
        1
        for paragraph in paragraphs
        if str(getattr(paragraph, "structural_role", "") or "").strip().lower() in TOC_STRUCTURAL_ROLES
    )
    return toc_count == len(paragraphs) or (toc_count / len(paragraphs)) >= 0.7


def _exclude_block(block: object) -> bool:
    paragraphs = list(getattr(block, "paragraphs", ()) or ())
    if not paragraphs:
        return True
    if all(str(getattr(paragraph, "role", "") or "").strip().lower() in {"image", "table"} for paragraph in paragraphs):
        return True
    return _toc_dominant(paragraphs)


def _feature_flags(text: str, paragraphs: Sequence[object]) -> tuple[str, ...]:
    flags: list[str] = []
    if any(str(getattr(paragraph, "role", "") or "").strip().lower() in {"heading", "list"} for paragraph in paragraphs):
        flags.append("structural_non_trivial")
    if re.search(r"(?:\b[A-Z]{2,}\b|[%/:;()]|\d{2,})", text):
        flags.append("terminology_heavy")
    if re.search(r"[!?;:]", text) or any(token in text for token in ('"', "'", "--", " - ")):
        flags.append("stylistically_expressive")
    return tuple(sorted(set(flags)))


def _build_fragment_candidates(extraction: ProfileExtraction, config: ResolvedBenchmarkConfig) -> list[FragmentCandidate]:
    candidates: list[FragmentCandidate] = []
    blocks = extraction.blocks
    for start_index in range(len(blocks)):
        if _exclude_block(blocks[start_index]):
            continue
        collected_paragraphs: list[object] = []
        for end_index in range(start_index, min(len(blocks), start_index + 3)):
            current_block = blocks[end_index]
            if _exclude_block(current_block):
                break
            collected_paragraphs.extend(list(getattr(current_block, "paragraphs", ()) or ()))
            text = build_document_text(collected_paragraphs).strip()
            char_count = len(text)
            if char_count > config.fallback_max_chars:
                break
            if char_count < config.fallback_min_chars:
                continue
            midpoint = (start_index + end_index) // 2
            candidates.append(
                FragmentCandidate(
                    start_block_index=start_index,
                    end_block_index=end_index,
                    paragraph_count=len(collected_paragraphs),
                    char_count=char_count,
                    word_count=_word_count(text),
                    text=text,
                    region=_block_region(midpoint, len(blocks)),
                    merged=end_index > start_index,
                    feature_flags=_feature_flags(text, collected_paragraphs),
                    paragraph_indexes=_paragraph_indexes(collected_paragraphs),
                )
            )
    deduped: dict[tuple[int, int], FragmentCandidate] = {}
    for candidate in candidates:
        deduped[(candidate.start_block_index, candidate.end_block_index)] = candidate
    return list(deduped.values())


def _desired_regions(target_count: int) -> list[str]:
    if target_count <= 0:
        return []
    if target_count == 1:
        return ["middle"]
    if target_count == 2:
        return ["early", "late"]
    ordered = ["early", "middle", "late"]
    while len(ordered) < target_count:
        ordered.append(("middle", "early", "late")[(len(ordered) - 3) % 3])
    return ordered[:target_count]


def _candidate_score(candidate: FragmentCandidate, *, desired_region: str, config: ResolvedBenchmarkConfig) -> float:
    preferred_midpoint = (config.preferred_min_chars + config.preferred_max_chars) / 2
    score = 0.0
    if config.preferred_min_chars <= candidate.char_count <= config.preferred_max_chars:
        score += 1000.0
    score -= abs(candidate.char_count - preferred_midpoint) / 5.0
    if candidate.region == desired_region:
        score += 250.0
    score += 120.0 * len(candidate.feature_flags)
    if "structural_non_trivial" in candidate.feature_flags:
        score += 120.0
    if "terminology_heavy" in candidate.feature_flags:
        score += 90.0
    if "stylistically_expressive" in candidate.feature_flags:
        score += 70.0
    if candidate.merged:
        score -= 20.0
    score -= candidate.start_block_index * 0.01
    return score


def _distribute_targets(total_fragments: int, profile_ids: Sequence[str]) -> dict[str, int]:
    if not profile_ids:
        return {}
    base = total_fragments // len(profile_ids)
    remainder = total_fragments % len(profile_ids)
    distribution: dict[str, int] = {}
    for index, profile_id in enumerate(profile_ids):
        distribution[profile_id] = base + (1 if index < remainder else 0)
    return distribution


def _select_fragments_for_profile(
    extraction: ProfileExtraction,
    *,
    target_count: int,
    config: ResolvedBenchmarkConfig,
) -> tuple[list[FragmentRecord], list[str], dict[str, object]]:
    candidates = _build_fragment_candidates(extraction, config)
    selected: list[FragmentRecord] = []
    notes: list[str] = []
    occupied_indexes: set[int] = set()
    desired_regions = _desired_regions(target_count)
    profile_relative_source = _relative_artifact_path(extraction.source_path)
    verification_summary = _new_source_language_verification_summary(config.source_language)

    for desired_region in desired_regions:
        eligible = [
            candidate
            for candidate in candidates
            if not any(index in occupied_indexes for index in range(candidate.start_block_index, candidate.end_block_index + 1))
        ]
        if not eligible:
            break
        region_candidates = [candidate for candidate in eligible if candidate.region == desired_region] or eligible
        ranked_candidates = sorted(
            region_candidates,
            key=lambda candidate: (
                _candidate_score(candidate, desired_region=desired_region, config=config),
                -candidate.start_block_index,
                -candidate.end_block_index,
            ),
            reverse=True,
        )
        selected_candidate = None
        verification_payload: dict[str, object] | None = None
        rejected_for_slot = 0
        for candidate in ranked_candidates:
            candidate_verification = _verify_source_language(candidate.text, config.source_language)
            _record_source_language_check(verification_summary, candidate_verification, profile_id=extraction.profile.id)
            if bool(candidate_verification.get("allow_translation")):
                selected_candidate = candidate
                verification_payload = candidate_verification
                break
            rejected_for_slot += 1

        if selected_candidate is None or verification_payload is None:
            notes.append(
                f"Profile {extraction.profile.id} had no fragment candidate that verified as source_language={config.source_language!r} for region {desired_region}; rejected {rejected_for_slot} candidates."
            )
            continue

        occupied_indexes.update(range(selected_candidate.start_block_index, selected_candidate.end_block_index + 1))
        reason_parts = [f"region={desired_region}"]
        if config.preferred_min_chars <= selected_candidate.char_count <= config.preferred_max_chars:
            reason_parts.append("within_preferred_range")
        else:
            reason_parts.append("within_fallback_range")
        if selected_candidate.feature_flags:
            reason_parts.append("features=" + ",".join(selected_candidate.feature_flags))
        if rejected_for_slot > 0:
            notes.append(
                f"Profile {extraction.profile.id} skipped {rejected_for_slot} non-matching fragment candidates before selecting a verified source-language fragment for region {desired_region}."
            )
        fragment_id = f"{extraction.profile.id}-f{len(selected) + 1:02d}"
        _record_selected_verified_fragment(verification_summary, fragment_id)
        selected.append(
            FragmentRecord(
                fragment_id=fragment_id,
                profile_id=extraction.profile.id,
                source_path=profile_relative_source,
                source_text=selected_candidate.text,
                source_char_count=selected_candidate.char_count,
                source_word_count=selected_candidate.word_count,
                paragraph_count=selected_candidate.paragraph_count,
                block_indexes=tuple(range(selected_candidate.start_block_index, selected_candidate.end_block_index + 1)),
                paragraph_indexes=selected_candidate.paragraph_indexes,
                region=selected_candidate.region,
                merged=selected_candidate.merged,
                feature_flags=selected_candidate.feature_flags,
                selection_reason="; ".join(reason_parts),
                metadata={
                    "source_profile": extraction.profile.id,
                    "source_path": profile_relative_source,
                    "source_char_count": selected_candidate.char_count,
                    "source_word_count": selected_candidate.word_count,
                    "paragraph_count": selected_candidate.paragraph_count,
                    "block_indexes": list(range(selected_candidate.start_block_index, selected_candidate.end_block_index + 1)),
                    "paragraph_indexes": list(selected_candidate.paragraph_indexes),
                    "region": selected_candidate.region,
                    "selection_reason": "; ".join(reason_parts),
                    "selected_from": "merged_blocks" if selected_candidate.merged else "single_block",
                    "feature_flags": list(selected_candidate.feature_flags),
                    "source_language_verification": verification_payload,
                },
            )
        )

    if len(selected) < target_count:
        notes.append(
            f"Profile {extraction.profile.id} yielded {len(selected)} fragments after deterministic fallback selection; requested {target_count}."
        )
    return selected, notes, verification_summary


def _extract_fragments(config: ResolvedBenchmarkConfig, run_dir: Path) -> tuple[list[FragmentRecord], list[dict[str, object]], list[str], dict[str, object]]:
    _ensure_project_imports()
    registry = load_validation_registry()
    target_distribution = _distribute_targets(config.max_fragments, config.profiles)
    fragments: list[FragmentRecord] = []
    fragment_metadata_payloads: list[dict[str, object]] = []
    notes: list[str] = []
    source_language_verification = _new_source_language_verification_summary(config.source_language)

    for profile_id in config.profiles:
        profile = registry.get_document_profile(profile_id)
        extraction = _load_profile_extraction(profile, config)
        selected, profile_notes, profile_verification = _select_fragments_for_profile(
            extraction,
            target_count=target_distribution.get(profile_id, 0),
            config=config,
        )
        notes.extend(profile_notes)
        _merge_source_language_verification_summary(source_language_verification, profile_verification)
        for fragment in selected:
            fragments.append(fragment)
            metadata_payload = dict(fragment.metadata)
            metadata_payload["fragment_id"] = fragment.fragment_id
            metadata_payload["artifact_paths"] = {
                "source_markdown": _relative_artifact_path(run_dir / "fragments" / f"{fragment.fragment_id}.source.md"),
                "metadata": _relative_artifact_path(run_dir / "fragments" / f"{fragment.fragment_id}.metadata.json"),
            }
            fragment_metadata_payloads.append(metadata_payload)
            _write_text(run_dir / "fragments" / f"{fragment.fragment_id}.source.md", fragment.source_text + "\n")
            _write_json(run_dir / "fragments" / f"{fragment.fragment_id}.metadata.json", metadata_payload)
    if int(source_language_verification.get("rejected_candidate_count") or 0) > 0:
        notes.append(
            f"Source-language verification rejected {source_language_verification['rejected_candidate_count']} candidate fragments before translation dispatch; {len(fragments)} verified fragments remain."
        )
    if not fragments:
        notes.append(f"No selected fragments passed source-language verification for expected source_language={config.source_language!r}.")
    return fragments, fragment_metadata_payloads, notes, source_language_verification


def _estimate_max_output_tokens(text: str) -> int:
    estimated_output_tokens = max((len(text) // 3) * 4, 512)
    return min(estimated_output_tokens, 16384)


def _extract_response_text(response: object) -> str:
    _ensure_project_imports()
    response_status = read_response_field(response, "status")
    if response_status == "incomplete":
        raise RuntimeError("Model returned incomplete response.")
    if isinstance(response_status, str) and response_status and response_status != "completed":
        raise RuntimeError(f"Model returned unexpected response status: {response_status}.")
    traversal = collect_response_text_traversal(response, unsupported_message="Model returned unsupported response shape.")
    if traversal.collected_texts:
        return _normalize_model_output("\n".join(traversal.collected_texts))
    if traversal.raw_output_text is not None:
        cleaned = _normalize_model_output(traversal.raw_output_text)
        if cleaned:
            return cleaned
    raise RuntimeError("Model returned empty output.")


def _read_nested_field(value: object, *fields: str) -> object:
    _ensure_project_imports()
    current = value
    for field_name in fields:
        current = read_response_field(current, field_name)
        if current is None:
            return None
    return current


def _usage_payload(response: object, requested_model: str) -> dict[str, object]:
    usage = read_response_field(response, "usage")
    prompt_tokens = int(_read_nested_field(usage, "prompt_tokens") or _read_nested_field(usage, "input_tokens") or 0)
    completion_tokens = int(_read_nested_field(usage, "completion_tokens") or _read_nested_field(usage, "output_tokens") or 0)
    total_tokens = int(_read_nested_field(usage, "total_tokens") or prompt_tokens + completion_tokens)
    reasoning_tokens = int(
        _read_nested_field(usage, "reasoning_tokens")
        or _read_nested_field(usage, "output_tokens_details", "reasoning_tokens")
        or 0
    )
    cached_tokens = int(
        _read_nested_field(usage, "cached_tokens")
        or _read_nested_field(usage, "input_tokens_details", "cached_tokens")
        or 0
    )
    response_model = str(read_response_field(response, "model") or requested_model)
    generation_id = str(read_response_field(response, "id") or "")
    raw_cost = _read_nested_field(usage, "cost") or read_response_field(response, "cost") or 0.0
    try:
        cost = float(raw_cost)
    except (TypeError, ValueError):
        cost = 0.0
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "reasoning_tokens": reasoning_tokens,
        "cached_tokens": cached_tokens,
        "cost": round(cost, 6),
        "response_model": response_model,
        "generation_id": generation_id,
    }


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
            {
                "role": "system",
                "content": [{"type": "input_text", "text": system_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": user_prompt}],
            },
        ],
        "temperature": temperature,
        "max_output_tokens": _estimate_max_output_tokens(target_text),
        "timeout": timeout_seconds,
    }


def _empty_usage_payload() -> dict[str, object]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "reasoning_tokens": 0,
        "cached_tokens": 0,
        "cost": 0.0,
        "response_model": "",
        "generation_id": "",
    }


def _combine_usage_payloads(*payloads: Mapping[str, object]) -> dict[str, object]:
    combined = _empty_usage_payload()
    observed_models: list[str] = []
    generation_ids: list[str] = []
    for payload in payloads:
        combined["prompt_tokens"] = int(combined["prompt_tokens"]) + int(payload.get("prompt_tokens") or 0)
        combined["completion_tokens"] = int(combined["completion_tokens"]) + int(payload.get("completion_tokens") or 0)
        combined["total_tokens"] = int(combined["total_tokens"]) + int(payload.get("total_tokens") or 0)
        combined["reasoning_tokens"] = int(combined["reasoning_tokens"]) + int(payload.get("reasoning_tokens") or 0)
        combined["cached_tokens"] = int(combined["cached_tokens"]) + int(payload.get("cached_tokens") or 0)
        combined["cost"] = round(float(combined["cost"]) + float(payload.get("cost") or 0.0), 6)
        response_model = str(payload.get("response_model") or "").strip()
        generation_id = str(payload.get("generation_id") or "").strip()
        if response_model:
            observed_models.append(response_model)
        if generation_id:
            generation_ids.append(generation_id)
    combined["response_model"] = observed_models[-1] if observed_models else ""
    combined["generation_id"] = generation_ids[-1] if generation_ids else ""
    combined["observed_response_models"] = sorted(set(observed_models))
    combined["observed_generation_ids"] = generation_ids
    return combined


def _run_text_request(
    client: Any,
    *,
    requested_model: str,
    system_prompt: str,
    user_prompt: str,
    target_text: str,
    temperature: float,
    timeout_seconds: int,
    max_retries: int,
) -> dict[str, object]:
    _ensure_project_imports()
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
                    attempt_history.append(
                        {
                            "attempt": attempt,
                            "status": "retrying_without_optional_param",
                            "removed_param": unsupported_param,
                            "error": str(exc),
                        }
                    )
                    current_payload.pop(unsupported_param, None)
                    request_payload.pop(unsupported_param, None)
                    continue
                attempt_history.append({"attempt": attempt, "status": "failed", "error": str(exc)})
                return {
                    "ok": False,
                    "error": str(exc),
                    "attempt_history": attempt_history,
                    "duration_seconds": round(time.perf_counter() - started_at, 3),
                    "usage": _empty_usage_payload(),
                }
            except Exception as exc:  # noqa: BLE001
                unsupported_param = extract_unsupported_parameter_name(str(exc))
                if unsupported_param in removable_optional_params and unsupported_param in current_payload:
                    attempt_history.append(
                        {
                            "attempt": attempt,
                            "status": "retrying_without_optional_param",
                            "removed_param": unsupported_param,
                            "error": str(exc),
                        }
                    )
                    current_payload.pop(unsupported_param, None)
                    request_payload.pop(unsupported_param, None)
                    continue
                retryable = attempt < max_retries and is_retryable_error(exc)
                entry = {
                    "attempt": attempt,
                    "status": "retryable_error" if retryable else "failed",
                    "error": str(exc),
                }
                attempt_history.append(entry)
                if not retryable:
                    return {
                        "ok": False,
                        "error": str(exc),
                        "attempt_history": attempt_history,
                        "duration_seconds": round(time.perf_counter() - started_at, 3),
                        "usage": _empty_usage_payload(),
                    }
                sleep_seconds = min(2 ** (attempt - 1), 8)
                entry["sleep_seconds"] = sleep_seconds
                time.sleep(sleep_seconds)
                break
            else:
                try:
                    text = _extract_response_text(response)
                except Exception as exc:  # noqa: BLE001
                    attempt_history.append({"attempt": attempt, "status": "failed", "error": str(exc)})
                    return {
                        "ok": False,
                        "error": str(exc),
                        "attempt_history": attempt_history,
                        "duration_seconds": round(time.perf_counter() - started_at, 3),
                        "usage": _usage_payload(response, requested_model),
                    }
                usage = _usage_payload(response, requested_model)
                attempt_history.append(
                    {
                        "attempt": attempt,
                        "status": "succeeded",
                        "response_model": usage.get("response_model"),
                        "generation_id": usage.get("generation_id"),
                    }
                )
                return {
                    "ok": True,
                    "text": text,
                    "attempt_history": attempt_history,
                    "duration_seconds": round(time.perf_counter() - started_at, 3),
                    "usage": usage,
                }
    return {
        "ok": False,
        "error": "Responses retry loop exhausted unexpectedly.",
        "attempt_history": attempt_history,
        "duration_seconds": round(time.perf_counter() - started_at, 3),
        "usage": _empty_usage_payload(),
    }


def _split_paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text.strip()) if chunk.strip()]


def _english_residue_samples(text: str) -> list[str]:
    return sorted({match.group(0) for match in ENGLISH_RESIDUE_WORD_PATTERN.finditer(text)})[:8]


def _repeated_ngram_samples(text: str) -> list[str]:
    words = [word.lower() for word in WORD_PATTERN.findall(text)]
    counts: Counter[str] = Counter()
    for index in range(len(words) - 2):
        ngram = " ".join(words[index : index + 3])
        counts[ngram] += 1
    return sorted([ngram for ngram, count in counts.items() if count >= 3])[:5]


def _quote_balance(text: str, left: str, right: str | None = None) -> bool:
    if right is None:
        return text.count(left) % 2 == 0
    return text.count(left) == text.count(right)


def _build_automated_checks(fragment: FragmentRecord, output_text: str, error_message: str | None = None) -> dict[str, object]:
    source_text = fragment.source_text
    source_chars = max(1, fragment.source_char_count)
    output_chars = len(output_text.strip())
    paragraph_delta = abs(len(_split_paragraphs(source_text)) - len(_split_paragraphs(output_text)))
    heading_delta = abs(len(HEADING_PATTERN.findall(source_text)) - len(HEADING_PATTERN.findall(output_text)))
    list_delta = abs(len(LIST_PATTERN.findall(source_text)) - len(LIST_PATTERN.findall(output_text)))
    residue_samples = _english_residue_samples(output_text)
    repeated_ngrams = _repeated_ngram_samples(output_text)
    forbidden_meta = [pattern.pattern for pattern in FORBIDDEN_META_PATTERNS if pattern.search(output_text)]
    length_ratio = output_chars / source_chars
    hard_fail_reasons: list[str] = []
    risk_flags: list[str] = []

    if error_message:
        hard_fail_reasons.append("api_failure")
    if not output_text.strip():
        hard_fail_reasons.append("empty_output")
    if output_text.strip() and length_ratio < 0.60:
        hard_fail_reasons.append("too_short_vs_source")
    if output_text.strip() and length_ratio > 2.00:
        hard_fail_reasons.append("too_long_vs_source")
    if forbidden_meta:
        hard_fail_reasons.append("forbidden_meta_wrapper")
    if output_text.strip():
        if residue_samples:
            risk_flags.append("untranslated_english_residue")
        if repeated_ngrams:
            risk_flags.append("repeated_ngrams")
        if paragraph_delta > 1:
            risk_flags.append("paragraph_count_drift")
        if heading_delta > 0:
            risk_flags.append("heading_preservation_drift")
        if list_delta > 0:
            risk_flags.append("list_preservation_drift")
        if not _quote_balance(output_text, '"') or not _quote_balance(output_text, "(", ")") or not _quote_balance(output_text, "[", "]"):
            risk_flags.append("quote_or_bracket_imbalance")

    status = "failed" if hard_fail_reasons else ("ok_with_flags" if risk_flags else "ok")
    return {
        "status": status,
        "source_char_count": fragment.source_char_count,
        "output_char_count": output_chars,
        "length_ratio": round(length_ratio, 4),
        "paragraph_count_delta": paragraph_delta,
        "heading_count_delta": heading_delta,
        "list_count_delta": list_delta,
        "english_residue_samples": residue_samples,
        "repeated_ngram_samples": repeated_ngrams,
        "forbidden_meta_matches": forbidden_meta,
        "hard_fail_reasons": hard_fail_reasons,
        "risk_flags": risk_flags,
    }


def _build_translation_user_prompt(fragment: FragmentRecord, config: ResolvedBenchmarkConfig) -> str:
    return (
        f"Translate the following Markdown fragment from {config.source_language} to {config.target_language_name}.\n\n"
        "Return only the translated Markdown fragment.\n\n"
        "Source fragment:\n"
        f"```markdown\n{fragment.source_text}\n```"
    )


def _translate_fragment_candidate(
    *,
    client: Any,
    fragment: FragmentRecord,
    candidate: CandidateConfig,
    config: ResolvedBenchmarkConfig,
    run_dir: Path,
) -> TranslationResult:
    request_result = _run_text_request(
        client,
        requested_model=candidate.model,
        system_prompt=config.prompt_text,
        user_prompt=_build_translation_user_prompt(fragment, config),
        target_text=fragment.source_text,
        temperature=config.translation_temperature,
        timeout_seconds=config.request_timeout_seconds,
        max_retries=config.max_retries,
    )
    output_text = str(request_result.get("text") or "")
    error_message = None if bool(request_result.get("ok")) else str(request_result.get("error") or "Translation request failed.")
    automated_checks = _build_automated_checks(fragment, output_text, error_message)
    status = str(automated_checks.get("status") or "failed")
    usage = dict(request_result.get("usage") or _empty_usage_payload())
    returned_model = str(usage.get("response_model") or "").strip()
    model_mismatch = bool(returned_model and returned_model != candidate.model)
    candidate_dir = run_dir / "translations" / fragment.fragment_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = candidate_dir / f"{candidate.id}.metadata.json"
    usage_path = candidate_dir / f"{candidate.id}.usage.json"
    checks_path = candidate_dir / f"{candidate.id}.automated_checks.json"
    translation_path = candidate_dir / f"{candidate.id}.ru.md"
    if output_text.strip():
        _write_text(translation_path, output_text + "\n")
    translation_metadata = {
        "fragment_id": fragment.fragment_id,
        "candidate_id": candidate.id,
        "candidate_label": candidate.label,
        "provider": candidate.provider,
        "requested_model": candidate.model,
        "returned_model": returned_model,
        "model_mismatch": model_mismatch,
        "status": status,
        "duration_seconds": request_result.get("duration_seconds"),
        "attempt_history": list(request_result.get("attempt_history") or []),
        "error_message": error_message,
        "output_char_count": len(output_text),
    }
    _write_json(metadata_path, translation_metadata)
    _write_json(usage_path, usage)
    _write_json(checks_path, automated_checks)
    artifact_paths = {
        "metadata": _relative_artifact_path(metadata_path),
        "usage": _relative_artifact_path(usage_path),
        "automated_checks": _relative_artifact_path(checks_path),
    }
    if output_text.strip():
        artifact_paths["translation_markdown"] = _relative_artifact_path(translation_path)
    return TranslationResult(
        fragment_id=fragment.fragment_id,
        candidate_id=candidate.id,
        candidate_label=candidate.label,
        requested_model=candidate.model,
        returned_model=returned_model,
        status=status,
        output_text=output_text,
        output_char_count=len(output_text),
        usage=usage,
        automated_checks=automated_checks,
        attempt_history=list(request_result.get("attempt_history") or []),
        duration_seconds=float(request_result.get("duration_seconds") or 0.0),
        error_message=error_message,
        artifact_paths=artifact_paths,
    )


def _run_translations(
    *,
    client: Any,
    fragments: Sequence[FragmentRecord],
    candidates: Sequence[CandidateConfig],
    config: ResolvedBenchmarkConfig,
    run_dir: Path,
) -> list[TranslationResult]:
    results: list[TranslationResult] = []
    for fragment in fragments:
        for candidate in candidates:
            result = _translate_fragment_candidate(
                client=client,
                fragment=fragment,
                candidate=candidate,
                config=config,
                run_dir=run_dir,
            )
            results.append(result)
    return results


def _anonymized_candidate_map(results: Sequence[TranslationResult]) -> dict[str, str]:
    ordered_ids = sorted({result.candidate_id for result in results})
    return {candidate_id: f"candidate_{chr(ord('A') + index)}" for index, candidate_id in enumerate(ordered_ids)}


def _rubric_system_prompt(config: ResolvedBenchmarkConfig) -> str:
    weights_json = json.dumps(RUBRIC_WEIGHTS, ensure_ascii=False, indent=2)
    return (
        f"You are grading translations into {config.target_language_name}. "
        "Return strict JSON only. Do not include markdown fences or commentary.\n\n"
        f"Use this weighted rubric:\n{weights_json}\n\n"
        "Output schema:\n"
        "{\n"
        '  "candidate_id": "candidate_A",\n'
        '  "scores": {\n'
        '    "russian_naturalness": 0,\n'
        '    "semantic_accuracy": 0,\n'
        '    "authorial_voice": 0,\n'
        '    "anti_calque_quality": 0,\n'
        '    "book_prose_rhythm": 0,\n'
        '    "terminology_consistency": 0,\n'
        '    "discourse_coherence": 0,\n'
        '    "structure_preservation": 0,\n'
        '    "post_editing_burden": 0\n'
        "  },\n"
        '  "weighted_total": 0,\n'
        '  "verdict": "publishable_after_light_edit | usable_after_medium_edit | draft_only | unacceptable",\n'
        '  "major_errors": [],\n'
        '  "minor_errors": [],\n'
        '  "best_features": [],\n'
        '  "worst_features": [],\n'
        '  "examples": [\n'
        "    {\n"
        '      "source_excerpt": "...",\n'
        '      "translation_excerpt": "...",\n'
        '      "comment": "..."\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def _pairwise_system_prompt(config: ResolvedBenchmarkConfig) -> str:
    return (
        f"You are comparing translations into {config.target_language_name}. "
        "Return strict JSON only. Do not include markdown fences or commentary.\n\n"
        "Output schema:\n"
        "{\n"
        '  "fragment_id": "...",\n'
        '  "comparisons": [\n'
        "    {\n"
        '      "left": "candidate_A",\n'
        '      "right": "candidate_B",\n'
        '      "winner": "candidate_A | candidate_B | tie",\n'
        '      "margin": "slight | clear | decisive | tie",\n'
        '      "reason": "..."\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def _rubric_user_prompt(
    fragment: FragmentRecord,
    *,
    anonymized_id: str,
    translation_text: str,
    config: ResolvedBenchmarkConfig,
) -> str:
    return (
        f"Evaluate one anonymized translation into {config.target_language_name}.\n\n"
        f"Fragment ID: {fragment.fragment_id}\n"
        f"Candidate ID: {anonymized_id}\n\n"
        "Source:\n"
        f"```markdown\n{fragment.source_text}\n```\n\n"
        "Translation:\n"
        f"```markdown\n{translation_text}\n```"
    )


def _pairwise_user_prompt(
    fragment: FragmentRecord,
    *,
    anonymized_outputs: Mapping[str, str],
    config: ResolvedBenchmarkConfig,
) -> str:
    candidate_sections = []
    for anonymized_id, text in anonymized_outputs.items():
        candidate_sections.append(f"{anonymized_id}:\n```markdown\n{text}\n```")
    return (
        f"Compare anonymized translations into {config.target_language_name}.\n\n"
        f"Fragment ID: {fragment.fragment_id}\n\n"
        "Source:\n"
        f"```markdown\n{fragment.source_text}\n```\n\n"
        "Candidates:\n\n"
        + "\n\n".join(candidate_sections)
        + "\n\nCompare every unordered pair exactly once."
    )


def _parse_rubric_response(raw_text: str) -> dict[str, object]:
    _ensure_project_imports()
    payload = parse_json_object(
        raw_text,
        empty_message="Judge returned empty rubric response.",
        no_json_message="Judge did not return JSON rubric response.",
    )
    scores = payload.get("scores")
    if not isinstance(scores, dict):
        raise RuntimeError("Judge rubric response missing scores object.")
    normalized_scores: dict[str, int] = {}
    for key in RUBRIC_WEIGHTS:
        raw_value = scores.get(key)
        if isinstance(raw_value, bool):
            raise RuntimeError(f"Judge rubric score {key} must be numeric.")
        if not isinstance(raw_value, (int, float)):
            raise RuntimeError(f"Judge rubric score {key} missing.")
        numeric_value = int(round(float(raw_value)))
        if numeric_value < 0 or numeric_value > 100:
            raise RuntimeError(f"Judge rubric score {key} out of range: {numeric_value}")
        normalized_scores[key] = numeric_value
    payload["scores"] = normalized_scores
    weighted_total = payload.get("weighted_total")
    if not isinstance(weighted_total, (int, float)):
        raise RuntimeError("Judge rubric response missing weighted_total.")
    payload["weighted_total"] = round(float(weighted_total), 2)
    verdict = str(payload.get("verdict") or "").strip()
    if verdict not in {"publishable_after_light_edit", "usable_after_medium_edit", "draft_only", "unacceptable"}:
        raise RuntimeError(f"Judge rubric response has unsupported verdict: {verdict}")
    payload["verdict"] = verdict
    for key in ("major_errors", "minor_errors", "best_features", "worst_features", "examples"):
        value = payload.get(key)
        if not isinstance(value, list):
            raise RuntimeError(f"Judge rubric response missing list field: {key}")
    return payload


def _parse_pairwise_response(raw_text: str) -> dict[str, object]:
    _ensure_project_imports()
    payload = parse_json_object(
        raw_text,
        empty_message="Judge returned empty pairwise response.",
        no_json_message="Judge did not return JSON pairwise response.",
    )
    comparisons = payload.get("comparisons")
    if not isinstance(comparisons, list):
        raise RuntimeError("Judge pairwise response missing comparisons list.")
    normalized: list[dict[str, object]] = []
    for item in comparisons:
        if not isinstance(item, dict):
            raise RuntimeError("Judge pairwise comparison must be an object.")
        winner = str(item.get("winner") or "").strip()
        margin = str(item.get("margin") or "").strip()
        if winner not in {str(item.get("left") or "").strip(), str(item.get("right") or "").strip(), "tie"}:
            raise RuntimeError(f"Judge pairwise winner invalid: {winner}")
        if margin not in {"slight", "clear", "decisive", "tie"}:
            raise RuntimeError(f"Judge pairwise margin invalid: {margin}")
        normalized.append(
            {
                "left": str(item.get("left") or "").strip(),
                "right": str(item.get("right") or "").strip(),
                "winner": winner,
                "margin": margin,
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    payload["comparisons"] = normalized
    return payload


def _run_judge_json_request(
    client: Any,
    *,
    requested_model: str,
    system_prompt: str,
    user_prompt: str,
    target_text: str,
    temperature: float,
    timeout_seconds: int,
    max_retries: int,
    parser,
) -> dict[str, object]:
    request_result = _run_text_request(
        client,
        requested_model=requested_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        target_text=target_text,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )
    if not bool(request_result.get("ok")):
        return request_result
    raw_text = str(request_result.get("text") or "")
    try:
        parsed = parser(raw_text)
        request_result["parsed"] = parsed
        usage = dict(request_result.get("usage") or _empty_usage_payload())
        observed_models = [str(model).strip() for model in list(usage.get("observed_response_models") or []) if str(model).strip()]
        response_model = str(usage.get("response_model") or "").strip()
        if response_model:
            observed_models.append(response_model)
        request_result["observed_response_models"] = list(dict.fromkeys(observed_models))
        return request_result
    except Exception as first_exc:  # noqa: BLE001
        retry_result = _run_text_request(
            client,
            requested_model=requested_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt + "\n\nReturn strict JSON only. No commentary.",
            target_text=target_text,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
            max_retries=1,
        )
        retry_history = list(request_result.get("attempt_history") or []) + list(retry_result.get("attempt_history") or [])
        combined_usage = _combine_usage_payloads(
            dict(request_result.get("usage") or _empty_usage_payload()),
            dict(retry_result.get("usage") or _empty_usage_payload()),
        )
        if not bool(retry_result.get("ok")):
            return {
                "ok": False,
                "error": f"Judge JSON invalid on first attempt ({first_exc}); retry failed: {retry_result.get('error')}",
                "attempt_history": retry_history,
                "duration_seconds": round(
                    float(request_result.get("duration_seconds") or 0.0) + float(retry_result.get("duration_seconds") or 0.0),
                    3,
                ),
                "usage": combined_usage,
                "observed_response_models": list(combined_usage.get("observed_response_models") or []),
            }
        raw_retry_text = str(retry_result.get("text") or "")
        try:
            parsed = parser(raw_retry_text)
        except Exception as second_exc:  # noqa: BLE001
            return {
                "ok": False,
                "error": f"Judge JSON invalid after retry: {second_exc}",
                "attempt_history": retry_history,
                "duration_seconds": round(
                    float(request_result.get("duration_seconds") or 0.0) + float(retry_result.get("duration_seconds") or 0.0),
                    3,
                ),
                "usage": combined_usage,
                "observed_response_models": list(combined_usage.get("observed_response_models") or []),
            }
        return {
            "ok": True,
            "text": raw_retry_text,
            "parsed": parsed,
            "attempt_history": retry_history,
            "duration_seconds": round(
                float(request_result.get("duration_seconds") or 0.0) + float(retry_result.get("duration_seconds") or 0.0),
                3,
            ),
            "usage": combined_usage,
            "observed_response_models": list(combined_usage.get("observed_response_models") or []),
        }


def _run_judging(
    *,
    client: Any,
    fragments: Sequence[FragmentRecord],
    translation_results: Sequence[TranslationResult],
    config: ResolvedBenchmarkConfig,
    run_dir: Path,
) -> dict[str, JudgeArtifact]:
    results_by_fragment: dict[str, list[TranslationResult]] = defaultdict(list)
    for result in translation_results:
        results_by_fragment[result.fragment_id].append(result)

    judge_artifacts: dict[str, JudgeArtifact] = {}
    rubric_system_prompt = _rubric_system_prompt(config)
    pairwise_system_prompt = _pairwise_system_prompt(config)

    for fragment in fragments:
        eligible_results = [
            result
            for result in results_by_fragment.get(fragment.fragment_id, [])
            if result.status != "failed" and result.output_text.strip()
        ]
        artifact = JudgeArtifact(fragment_id=fragment.fragment_id)
        judge_artifacts[fragment.fragment_id] = artifact
        if len(eligible_results) < 2:
            artifact.judge_metadata = {
                "fragment_id": fragment.fragment_id,
                "status": "skipped",
                "reason": "fewer_than_two_judgeable_candidates",
                "eligible_candidate_ids": [result.candidate_id for result in eligible_results],
            }
            continue

        anonymized_map = _anonymized_candidate_map(eligible_results)
        observed_models: set[str] = set()
        total_cost = 0.0
        total_duration_seconds = 0.0
        rubric_payloads: list[dict[str, object]] = []
        pairwise_payload: dict[str, object] | None = None

        for result in eligible_results:
            rubric_result = _run_judge_json_request(
                client,
                requested_model=config.judge_model,
                system_prompt=rubric_system_prompt,
                user_prompt=_rubric_user_prompt(
                    fragment,
                    anonymized_id=anonymized_map[result.candidate_id],
                    translation_text=result.output_text,
                    config=config,
                ),
                target_text=result.output_text,
                temperature=config.judge_temperature,
                timeout_seconds=config.request_timeout_seconds,
                max_retries=config.max_retries,
                parser=_parse_rubric_response,
            )
            total_duration_seconds += float(rubric_result.get("duration_seconds") or 0.0)
            rubric_usage = dict(rubric_result.get("usage") or _empty_usage_payload())
            total_cost += float(rubric_usage.get("cost") or 0.0)
            for model_name in list(rubric_result.get("observed_response_models") or []) or [str(rubric_usage.get("response_model") or "")]:
                if model_name:
                    observed_models.add(str(model_name))
            if bool(rubric_result.get("ok")):
                parsed = dict(rubric_result.get("parsed") or {})
                parsed["candidate_id"] = anonymized_map[result.candidate_id]
                parsed["candidate_actual_id"] = result.candidate_id
                parsed["requested_judge_model"] = config.judge_model
                parsed["returned_judge_model"] = rubric_usage.get("response_model")
                parsed["judge_usage"] = rubric_usage
                parsed["judge_attempt_history"] = list(rubric_result.get("attempt_history") or [])
                artifact.rubric_scores.append(parsed)
                rubric_payloads.append(parsed)
            else:
                artifact.rubric_failures.append(
                    {
                        "candidate_id": anonymized_map[result.candidate_id],
                        "candidate_actual_id": result.candidate_id,
                        "error": str(rubric_result.get("error") or "judge_rubric_failed"),
                        "judge_usage": rubric_usage,
                        "judge_attempt_history": list(rubric_result.get("attempt_history") or []),
                    }
                )

        anonymized_outputs = {anonymized_map[result.candidate_id]: result.output_text for result in eligible_results}
        pairwise_result = _run_judge_json_request(
            client,
            requested_model=config.judge_model,
            system_prompt=pairwise_system_prompt,
            user_prompt=_pairwise_user_prompt(fragment, anonymized_outputs=anonymized_outputs, config=config),
            target_text="\n\n".join(anonymized_outputs.values()),
            temperature=config.judge_temperature,
            timeout_seconds=config.request_timeout_seconds,
            max_retries=config.max_retries,
            parser=_parse_pairwise_response,
        )
        total_duration_seconds += float(pairwise_result.get("duration_seconds") or 0.0)
        pairwise_usage = dict(pairwise_result.get("usage") or _empty_usage_payload())
        total_cost += float(pairwise_usage.get("cost") or 0.0)
        for model_name in list(pairwise_result.get("observed_response_models") or []) or [str(pairwise_usage.get("response_model") or "")]:
            if model_name:
                observed_models.add(str(model_name))
        if bool(pairwise_result.get("ok")):
            pairwise_payload = dict(pairwise_result.get("parsed") or {})
            normalized_comparisons: list[dict[str, object]] = []
            for comparison in list(pairwise_payload.get("comparisons") or []):
                left_alias = str(comparison.get("left") or "")
                right_alias = str(comparison.get("right") or "")
                winner_alias = str(comparison.get("winner") or "")
                normalized_comparisons.append(
                    {
                        "left": next((actual_id for actual_id, alias in anonymized_map.items() if alias == left_alias), left_alias),
                        "right": next((actual_id for actual_id, alias in anonymized_map.items() if alias == right_alias), right_alias),
                        "winner": (
                            "tie"
                            if winner_alias == "tie"
                            else next((actual_id for actual_id, alias in anonymized_map.items() if alias == winner_alias), winner_alias)
                        ),
                        "margin": str(comparison.get("margin") or ""),
                        "reason": str(comparison.get("reason") or ""),
                        "left_alias": left_alias,
                        "right_alias": right_alias,
                        "winner_alias": winner_alias,
                    }
                )
            artifact.pairwise_comparisons = normalized_comparisons
        else:
            artifact.pairwise_failures.append(
                {
                    "fragment_id": fragment.fragment_id,
                    "error": str(pairwise_result.get("error") or "judge_pairwise_failed"),
                    "judge_usage": pairwise_usage,
                    "judge_attempt_history": list(pairwise_result.get("attempt_history") or []),
                }
            )

        artifact.judge_metadata = {
            "fragment_id": fragment.fragment_id,
            "status": "completed",
            "requested_judge_model": config.judge_model,
            "returned_judge_models": sorted(observed_models),
            "total_judge_cost": round(total_cost, 6),
            "duration_seconds": round(total_duration_seconds, 3),
            "eligible_candidate_ids": [result.candidate_id for result in eligible_results],
            "anonymized_mapping": {value: key for key, value in anonymized_map.items()},
            "rubric_score_count": len(artifact.rubric_scores),
            "rubric_failure_count": len(artifact.rubric_failures),
            "pairwise_comparison_count": len(artifact.pairwise_comparisons),
            "pairwise_failure_count": len(artifact.pairwise_failures),
        }

        _write_json(
            run_dir / "judging" / f"{fragment.fragment_id}.rubric_scores.json",
            {
                "fragment_id": fragment.fragment_id,
                "scores": artifact.rubric_scores,
                "failures": artifact.rubric_failures,
            },
        )
        _write_json(
            run_dir / "judging" / f"{fragment.fragment_id}.pairwise.json",
            {
                "fragment_id": fragment.fragment_id,
                "comparisons": artifact.pairwise_comparisons,
                "failures": artifact.pairwise_failures,
                "raw": pairwise_payload or {},
            },
        )
        _write_json(run_dir / "judging" / f"{fragment.fragment_id}.judge_metadata.json", artifact.judge_metadata)

    return judge_artifacts


def _safe_divide(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _pairwise_metrics_by_candidate(judge_artifacts: Mapping[str, JudgeArtifact]) -> tuple[dict[str, float], dict[str, int], dict[str, int]]:
    win_credit: defaultdict[str, float] = defaultdict(float)
    total_comparisons: defaultdict[str, int] = defaultdict(int)
    decisive_wins: defaultdict[str, int] = defaultdict(int)
    for artifact in judge_artifacts.values():
        for comparison in artifact.pairwise_comparisons:
            left = str(comparison.get("left") or "")
            right = str(comparison.get("right") or "")
            winner = str(comparison.get("winner") or "")
            margin = str(comparison.get("margin") or "")
            if not left or not right:
                continue
            total_comparisons[left] += 1
            total_comparisons[right] += 1
            if winner == "tie":
                win_credit[left] += 0.5
                win_credit[right] += 0.5
                continue
            win_credit[winner] += 1.0
            if margin == "decisive":
                decisive_wins[winner] += 1
    return dict(win_credit), dict(total_comparisons), dict(decisive_wins)


def _verdict_rank(value: str) -> int:
    order = {
        "publishable_after_light_edit": 0,
        "usable_after_medium_edit": 1,
        "draft_only": 2,
        "unacceptable": 3,
    }
    return order.get(value, 99)


def _estimate_book_cost(total_source_chars: int, total_source_words: int, total_cost: float) -> float | None:
    if total_source_chars <= 0 or total_source_words <= 0:
        return None
    avg_chars_per_word = total_source_chars / total_source_words
    estimated_source_chars = avg_chars_per_word * 300000
    observed_cost_per_source_char = total_cost / total_source_chars
    return observed_cost_per_source_char * estimated_source_chars


def _candidate_summary_payload(
    *,
    candidate: CandidateConfig,
    candidate_results: Sequence[TranslationResult],
    judge_artifacts: Mapping[str, JudgeArtifact],
    fragment_lookup: Mapping[str, FragmentRecord],
    anonymized_mapping_cache: Mapping[str, Mapping[str, str]],
    win_credit_by_candidate: Mapping[str, float],
    total_pairwise_by_candidate: Mapping[str, int],
    decisive_wins_by_candidate: Mapping[str, int],
) -> dict[str, object]:
    total_translation_cost = sum(float(result.usage.get("cost") or 0.0) for result in candidate_results)
    completed_results = [result for result in candidate_results if result.status != "failed"]
    failed_results = [result for result in candidate_results if result.status == "failed"]
    total_source_chars = sum(fragment_lookup[result.fragment_id].source_char_count for result in completed_results)
    total_output_chars = sum(result.output_char_count for result in completed_results)
    total_source_words = sum(fragment_lookup[result.fragment_id].source_word_count for result in completed_results)
    risk_counter: Counter[str] = Counter()
    serious_errors: list[str] = []
    returned_models: set[str] = set()
    per_fragment_scores: list[float] = []
    verdicts: list[str] = []
    pairwise_failures = 0

    for result in candidate_results:
        returned_models.add(result.returned_model)
        for flag in result.automated_checks.get("risk_flags", []):
            risk_counter[str(flag)] += 1
        for reason in result.automated_checks.get("hard_fail_reasons", []):
            serious_errors.append(str(reason))

    for fragment_id, artifact in judge_artifacts.items():
        mapping = anonymized_mapping_cache.get(fragment_id, {})
        target_alias = ""
        for anonymized_id, actual_id in mapping.items():
            if actual_id == candidate.id:
                target_alias = anonymized_id
                break
        if not target_alias:
            continue
        matched_score = next((item for item in artifact.rubric_scores if str(item.get("candidate_id") or "") == target_alias), None)
        if matched_score is not None:
            per_fragment_scores.append(float(matched_score.get("weighted_total") or 0.0))
            verdicts.append(str(matched_score.get("verdict") or ""))
        else:
            pairwise_failures += 1

    avg_weighted_score = _safe_divide(sum(per_fragment_scores), len(per_fragment_scores))
    avg_cost_per_fragment = _safe_divide(total_translation_cost, len(candidate_results))
    pairwise_win_rate = _safe_divide(win_credit_by_candidate.get(candidate.id, 0.0), total_pairwise_by_candidate.get(candidate.id, 0))
    cost_per_quality_point = _safe_divide(total_translation_cost, sum(per_fragment_scores))
    estimated_book_cost = _estimate_book_cost(total_source_chars, total_source_words, total_translation_cost)
    worst_verdict = max(verdicts, key=_verdict_rank) if verdicts else "unrated"
    editorial_risk_summary = []
    if failed_results:
        editorial_risk_summary.append(f"{len(failed_results)} hard fragment failures")
    if risk_counter:
        editorial_risk_summary.append(
            ", ".join(f"{flag}={count}" for flag, count in sorted(risk_counter.items(), key=lambda item: (-item[1], item[0]))[:5])
        )
    if not editorial_risk_summary:
        editorial_risk_summary.append("low deterministic risk observed in MVP checks")

    return {
        "candidate_id": candidate.id,
        "label": candidate.label,
        "provider": candidate.provider,
        "requested_model": candidate.model,
        "returned_models": sorted(model for model in returned_models if model),
        "fragment_count": len(candidate_results),
        "completed_fragment_count": len(completed_results),
        "failed_fragment_count": len(failed_results),
        "average_weighted_score": _round_or_none(avg_weighted_score, 2),
        "pairwise_win_rate": _round_or_none(pairwise_win_rate, 4),
        "decisive_win_count": int(decisive_wins_by_candidate.get(candidate.id, 0)),
        "total_translation_cost": round(total_translation_cost, 6),
        "avg_cost_per_fragment": _round_or_none(avg_cost_per_fragment, 6),
        "cost_per_1k_source_chars": _round_or_none(_safe_divide(total_translation_cost * 1000.0, total_source_chars), 6),
        "cost_per_1k_output_chars": _round_or_none(_safe_divide(total_translation_cost * 1000.0, total_output_chars), 6),
        "cost_per_quality_point": _round_or_none(cost_per_quality_point, 6),
        "estimated_cost_per_300k_word_book": _round_or_none(estimated_book_cost, 2),
        "editorial_risk_summary": "; ".join(editorial_risk_summary),
        "risk_flag_counts": dict(sorted(risk_counter.items())),
        "serious_errors": sorted(set(serious_errors)),
        "worst_verdict": worst_verdict,
        "artifact_paths": {
            result.fragment_id: result.artifact_paths for result in candidate_results
        },
    }


def _recommendation_categories(candidate_summaries: list[dict[str, object]]) -> dict[str, str]:
    categories = {str(item["candidate_id"]): "not_recommended" for item in candidate_summaries}
    if not candidate_summaries:
        return categories
    ranked = sorted(
        candidate_summaries,
        key=lambda item: (
            -float(item.get("average_weighted_score") or -1e9),
            -(float(item.get("pairwise_win_rate") or 0.0)),
            float(item.get("avg_cost_per_fragment") or 1e9),
        ),
    )
    best_quality = ranked[0]
    best_quality_id = str(best_quality["candidate_id"])
    if int(best_quality.get("failed_fragment_count") or 0) == 0:
        categories[best_quality_id] = "best_quality"

    best_quality_score = float(best_quality.get("average_weighted_score") or 0.0)
    best_quality_pairwise = float(best_quality.get("pairwise_win_rate") or 0.0)
    for candidate in ranked[1:]:
        candidate_id = str(candidate["candidate_id"])
        if int(candidate.get("failed_fragment_count") or 0) > 0:
            categories[candidate_id] = "not_recommended"
            continue
        if candidate.get("worst_verdict") in {"draft_only", "unacceptable"}:
            categories[candidate_id] = "not_recommended"
            continue
        score_gap = best_quality_score - float(candidate.get("average_weighted_score") or 0.0)
        cost = float(candidate.get("avg_cost_per_fragment") or 0.0)
        best_cost = float(best_quality.get("avg_cost_per_fragment") or 0.0)
        cheaper_enough = best_cost > 0 and cost <= best_cost * 0.70
        if score_gap <= 3.0 and cheaper_enough:
            categories[candidate_id] = "best_price_quality"
        elif float(candidate.get("pairwise_win_rate") or 0.0) >= max(0.0, best_quality_pairwise - 0.1):
            categories[candidate_id] = "budget_acceptable"
        else:
            categories[candidate_id] = "not_recommended"
    return categories


def _summary_markdown(
    *,
    run_id: str,
    config: ResolvedBenchmarkConfig,
    candidate_summaries: Sequence[dict[str, object]],
    total_translation_cost: float,
    total_judge_cost: float,
    notes: Sequence[str],
    source_language_verification: Mapping[str, object],
) -> str:
    lines = [
        f"# Translation Benchmark Summary: {run_id}",
        "",
        "## Run",
        f"- Source language: {config.source_language}",
        f"- Target language: {config.target_language_name} ({config.target_language})",
        f"- Profiles: {', '.join(config.profiles)}",
        f"- Candidate count: {len(candidate_summaries)}",
        f"- Total translation cost: {total_translation_cost:.6f}",
        f"- Total judge cost: {total_judge_cost:.6f}",
        "- Source-language verification: "
        f"checked={int(source_language_verification.get('checked_candidate_count') or 0)}, "
        f"selected={int(source_language_verification.get('selected_fragment_count') or 0)}, "
        f"rejected={int(source_language_verification.get('rejected_candidate_count') or 0)}",
        "",
        "## Candidates",
    ]
    for item in candidate_summaries:
        lines.append(
            "- "
            f"{item['candidate_id']}: recommendation={item.get('recommendation_category')}, "
            f"avg_score={item.get('average_weighted_score')}, "
            f"pairwise_win_rate={item.get('pairwise_win_rate')}, "
            f"avg_cost_per_fragment={item.get('avg_cost_per_fragment')}, "
            f"risk={item.get('editorial_risk_summary')}"
        )
    if notes:
        lines.extend(["", "## Notes"])
        lines.extend(f"- {note}" for note in notes)
    return "\n".join(lines) + "\n"


def _human_review_pack(
    *,
    run_dir: Path,
    candidate_summaries: Sequence[dict[str, object]],
    fragment_lookup: Mapping[str, FragmentRecord],
    translation_results: Sequence[TranslationResult],
    judge_artifacts: Mapping[str, JudgeArtifact],
) -> None:
    review_dir = run_dir / "human_review_pack"
    review_dir.mkdir(parents=True, exist_ok=True)
    summary_lines = ["# Human Review Pack", "", "## Ranked Models"]
    for item in candidate_summaries:
        summary_lines.append(
            f"- {item['candidate_id']} ({item['label']}): recommendation={item.get('recommendation_category')}, avg_score={item.get('average_weighted_score')}, pairwise_win_rate={item.get('pairwise_win_rate')}"
        )
    _write_text(review_dir / "summary.md", "\n".join(summary_lines) + "\n")

    blinded_lines = ["# Blinded Model Ranking", ""]
    model_mapping: dict[str, str] = {}
    blind_index = 1
    for item in candidate_summaries:
        blind_id = f"model_{blind_index:02d}"
        model_mapping[blind_id] = str(item["candidate_id"])
        blinded_lines.append(
            f"- {blind_id}: avg_score={item.get('average_weighted_score')}, pairwise_win_rate={item.get('pairwise_win_rate')}, recommendation={item.get('recommendation_category')}"
        )
        blind_index += 1
    _write_text(review_dir / "model_ranking_blinded.md", "\n".join(blinded_lines) + "\n")
    _write_json(review_dir / "model_mapping.json", model_mapping)

    by_fragment_candidate = {(result.fragment_id, result.candidate_id): result for result in translation_results}
    top_examples: list[tuple[float, str, str, str]] = []
    serious_examples: list[tuple[str, str, str]] = []
    questionable_examples: list[tuple[float, str, str, str]] = []
    for fragment_id, artifact in judge_artifacts.items():
        comparisons = artifact.pairwise_comparisons
        if not comparisons:
            continue
        decisive = [item for item in comparisons if str(item.get('margin') or '') == 'decisive' and str(item.get('winner') or '') != 'tie']
        ties = [item for item in comparisons if str(item.get('winner') or '') == 'tie']
        if decisive:
            top_examples.append((len(decisive), fragment_id, decisive[0].get('winner', ''), str(decisive[0].get('reason') or '')))
        if ties:
            questionable_examples.append((len(ties), fragment_id, 'tie', str(ties[0].get('reason') or '')))
    for result in translation_results:
        if result.status == "failed":
            serious_examples.append((result.fragment_id, result.candidate_id, str(result.error_message or result.automated_checks.get("hard_fail_reasons") or "failed")))

    lines = ["# Top Examples", "", "## Clearly Better"]
    for _, fragment_id, winner, reason in sorted(top_examples, reverse=True)[:3]:
        lines.append(f"- {fragment_id}: winner={winner}; reason={reason}")
        lines.append(f"  Source preview: {fragment_lookup[fragment_id].source_text[:300].replace(chr(10), ' ')}")
    lines.extend(["", "## Questionable Winners"])
    for _, fragment_id, winner, reason in sorted(questionable_examples, reverse=True)[:3]:
        lines.append(f"- {fragment_id}: winner={winner}; reason={reason}")
        lines.append(f"  Source preview: {fragment_lookup[fragment_id].source_text[:300].replace(chr(10), ' ')}")
    lines.extend(["", "## Serious Errors"])
    for fragment_id, candidate_id, reason in serious_examples[:3]:
        lines.append(f"- {fragment_id}/{candidate_id}: {reason}")
    _write_text(review_dir / "top_examples.md", "\n".join(lines) + "\n")


def _write_findings_for_project_backlog(*, run_dir: Path, candidate_summaries: Sequence[dict[str, object]]) -> None:
    findings: list[str] = ["# Findings For Project Backlog", ""]
    for item in candidate_summaries:
        failed = int(item.get("failed_fragment_count") or 0)
        if failed <= 0 and not item.get("risk_flag_counts"):
            continue
        findings.extend(
            [
                f"## Finding: Translation reliability signals for {item['candidate_id']}",
                "",
                "Severity: major" if failed else "Severity: minor",
                "",
                "Evidence:",
                f"Artifacts under translations/*/{item['candidate_id']}.* and summary.json metrics for {item['candidate_id']}.",
                "",
                "Impact:",
                f"Observed failed_fragment_count={failed} and risk_flag_counts={json.dumps(item.get('risk_flag_counts') or {}, ensure_ascii=False)}.",
                "",
                "Suggested follow-up:",
                "Specify prompt/glossary/output-validation improvements separately before changing production pipeline behavior.",
                "",
                "Requires approval before implementation: yes",
                "",
            ]
        )
    if len(findings) == 2:
        findings.extend(
            [
                "## Finding: No benchmark-specific backlog items identified in this run",
                "",
                "Severity: cosmetic",
                "",
                "Evidence:",
                "Benchmark artifacts did not surface project-level issues beyond candidate ranking.",
                "",
                "Impact:",
                "No separate production follow-up is implied by this run.",
                "",
                "Suggested follow-up:",
                "Review benchmark results before proposing production changes.",
                "",
                "Requires approval before implementation: yes",
                "",
            ]
        )
    _write_text(run_dir / "findings_for_project_backlog.md", "\n".join(findings))


def _aggregate_summary(
    *,
    run_id: str,
    config: ResolvedBenchmarkConfig,
    fragments: Sequence[FragmentRecord],
    translation_results: Sequence[TranslationResult],
    judge_artifacts: Mapping[str, JudgeArtifact],
    available_candidates: Sequence[CandidateConfig],
    run_dir: Path,
    notes: Sequence[str],
    source_language_verification: Mapping[str, object],
) -> tuple[dict[str, object], str]:
    fragment_lookup = {fragment.fragment_id: fragment for fragment in fragments}
    anonymized_mapping_cache = {
        fragment_id: dict(artifact.judge_metadata.get("anonymized_mapping") or {})
        for fragment_id, artifact in judge_artifacts.items()
    }
    candidate_results_by_id: defaultdict[str, list[TranslationResult]] = defaultdict(list)
    for result in translation_results:
        candidate_results_by_id[result.candidate_id].append(result)

    win_credit_by_candidate, total_pairwise_by_candidate, decisive_wins_by_candidate = _pairwise_metrics_by_candidate(judge_artifacts)
    candidate_summaries = [
        _candidate_summary_payload(
            candidate=candidate,
            candidate_results=candidate_results_by_id.get(candidate.id, []),
            judge_artifacts=judge_artifacts,
            fragment_lookup=fragment_lookup,
            anonymized_mapping_cache=anonymized_mapping_cache,
            win_credit_by_candidate=win_credit_by_candidate,
            total_pairwise_by_candidate=total_pairwise_by_candidate,
            decisive_wins_by_candidate=decisive_wins_by_candidate,
        )
        for candidate in available_candidates
    ]
    recommendation_categories = _recommendation_categories(candidate_summaries)
    for item in candidate_summaries:
        item["recommendation_category"] = recommendation_categories.get(str(item["candidate_id"]), "not_recommended")

    total_translation_cost = sum(float(result.usage.get("cost") or 0.0) for result in translation_results)
    total_judge_cost = sum(float(artifact.judge_metadata.get("total_judge_cost") or 0.0) for artifact in judge_artifacts.values())
    observed_judge_models = sorted(
        {
            model
            for artifact in judge_artifacts.values()
            for model in artifact.judge_metadata.get("returned_judge_models", [])
            if model
        }
    )
    summary_payload = {
        "benchmark_run_id": run_id,
        "source_language": {
            "id": config.source_language,
        },
        "target_language": {
            "id": config.target_language,
            "name": config.target_language_name,
        },
        "source_profiles": list(config.profiles),
        "fragment_ids": [fragment.fragment_id for fragment in fragments],
        "requested_judge_model": config.judge_model,
        "returned_judge_models": observed_judge_models,
        "total_translation_cost": round(total_translation_cost, 6),
        "total_judge_cost": round(total_judge_cost, 6),
        "source_language_verification": dict(source_language_verification),
        "candidates": candidate_summaries,
        "fragment_count": len(fragments),
        "translation_call_count": len(translation_results),
        "judge_fragment_count": sum(1 for artifact in judge_artifacts.values() if artifact.judge_metadata.get("status") == "completed"),
        "notes": list(notes),
    }
    summary_markdown = _summary_markdown(
        run_id=run_id,
        config=config,
        candidate_summaries=candidate_summaries,
        total_translation_cost=total_translation_cost,
        total_judge_cost=total_judge_cost,
        notes=notes,
        source_language_verification=source_language_verification,
    )
    _write_json(run_dir / "summary.json", summary_payload)
    _write_text(run_dir / "summary.md", summary_markdown)
    _human_review_pack(
        run_dir=run_dir,
        candidate_summaries=candidate_summaries,
        fragment_lookup=fragment_lookup,
        translation_results=translation_results,
        judge_artifacts=judge_artifacts,
    )
    _write_findings_for_project_backlog(run_dir=run_dir, candidate_summaries=candidate_summaries)
    return summary_payload, summary_markdown


def _write_run_snapshots(run_dir: Path, config: ResolvedBenchmarkConfig) -> None:
    _write_text(run_dir / "benchmark_config.snapshot.toml", _render_config_snapshot(config))
    _write_text(run_dir / "translation_prompt.snapshot.txt", config.prompt_text + "\n")
    _write_text(run_dir / "target_language_profile.snapshot.toml", config.target_language_profile_text)


def _projected_call_counts(fragment_count: int, candidate_count: int, *, skip_judge: bool) -> dict[str, int]:
    translation_calls = fragment_count * candidate_count
    judge_rubric_calls = 0 if skip_judge else translation_calls
    pair_count = candidate_count * (candidate_count - 1) // 2
    judge_pairwise_calls = 0 if skip_judge else fragment_count * pair_count
    return {
        "translation_calls": translation_calls,
        "judge_rubric_calls": judge_rubric_calls,
        "judge_pairwise_calls": judge_pairwise_calls,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    config = _load_config(args)
    run_id = _make_run_id()
    run_dir = config.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_run_snapshots(run_dir, config)

    api_key = _ensure_openrouter_env()
    available_candidates, _availability_payload = _run_model_availability_preflight(api_key=api_key, config=config, run_dir=run_dir)
    if len(available_candidates) < 2:
        manifest = _build_manifest(
            run_id=run_id,
            config=config,
            args=args,
            run_dir=run_dir,
            status="aborted_preflight",
            available_candidates=available_candidates,
            fragment_ids=[],
            model_availability_path=run_dir / "model_availability.json",
            notes=["Fewer than two candidate models remained available after model catalog preflight."],
            source_language_verification=_new_source_language_verification_summary(config.source_language),
        )
        _write_json(run_dir / "manifest.json", manifest)
        _write_json(
            run_dir / "summary.json",
            {
                "benchmark_run_id": run_id,
                "status": "aborted_preflight",
                "reason": "fewer_than_two_available_candidates",
                "available_candidates": [candidate.id for candidate in available_candidates],
            },
        )
        _write_text(run_dir / "summary.md", "# Translation Benchmark Summary\n\nRun aborted: fewer than two candidate models remained after model availability preflight.\n")
        _copy_latest_aliases(
            run_dir=run_dir,
            summary_json_path=run_dir / "summary.json",
            summary_md_path=run_dir / "summary.md",
            manifest_path=run_dir / "manifest.json",
        )
        print(json.dumps({"benchmark_run_id": run_id, "status": "aborted_preflight"}, ensure_ascii=False, indent=2))
        return 2

    fragments, _fragment_metadata, extraction_notes, source_language_verification = _extract_fragments(config, run_dir)
    if not fragments:
        summary_payload = {
            "benchmark_run_id": run_id,
            "status": "aborted_source_language_verification",
            "reason": "no_verified_source_language_fragments",
            "source_language": {
                "id": config.source_language,
            },
            "source_profiles": list(config.profiles),
            "fragment_count": 0,
            "source_language_verification": dict(source_language_verification),
            "notes": list(extraction_notes),
        }
        summary_md = (
            "# Translation Benchmark Summary\n\n"
            f"Run aborted: no selected fragments passed source-language verification for expected source_language={config.source_language!r}.\n"
        )
        manifest = _build_manifest(
            run_id=run_id,
            config=config,
            args=args,
            run_dir=run_dir,
            status="aborted_source_language_verification",
            available_candidates=available_candidates,
            fragment_ids=[],
            model_availability_path=run_dir / "model_availability.json",
            notes=extraction_notes,
            source_language_verification=source_language_verification,
        )
        _write_json(run_dir / "summary.json", summary_payload)
        _write_text(run_dir / "summary.md", summary_md)
        _write_json(run_dir / "manifest.json", manifest)
        _copy_latest_aliases(
            run_dir=run_dir,
            summary_json_path=run_dir / "summary.json",
            summary_md_path=run_dir / "summary.md",
            manifest_path=run_dir / "manifest.json",
        )
        print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
        return 3
    call_projection = _projected_call_counts(len(fragments), len(available_candidates), skip_judge=bool(args.skip_judge))
    projection_note = (
        f"Projected calls: translation={call_projection['translation_calls']}, "
        f"judge_rubric={call_projection['judge_rubric_calls']}, judge_pairwise={call_projection['judge_pairwise_calls']}"
    )
    notes = [projection_note, *extraction_notes]

    client = _build_openrouter_client(api_key, config)
    translation_results = _run_translations(
        client=client,
        fragments=fragments,
        candidates=available_candidates,
        config=config,
        run_dir=run_dir,
    )
    judge_artifacts: dict[str, JudgeArtifact]
    if args.skip_judge:
        judge_artifacts = {
            fragment.fragment_id: JudgeArtifact(
                fragment_id=fragment.fragment_id,
                judge_metadata={
                    "fragment_id": fragment.fragment_id,
                    "status": "skipped_by_flag",
                    "reason": "--skip-judge",
                },
            )
            for fragment in fragments
        }
    else:
        judge_artifacts = _run_judging(
            client=client,
            fragments=fragments,
            translation_results=translation_results,
            config=config,
            run_dir=run_dir,
        )

    summary_payload, _summary_markdown_text = _aggregate_summary(
        run_id=run_id,
        config=config,
        fragments=fragments,
        translation_results=translation_results,
        judge_artifacts=judge_artifacts,
        available_candidates=available_candidates,
        run_dir=run_dir,
        notes=notes,
        source_language_verification=source_language_verification,
    )
    manifest = _build_manifest(
        run_id=run_id,
        config=config,
        args=args,
        run_dir=run_dir,
        status="completed_skip_judge" if args.skip_judge else "completed",
        available_candidates=available_candidates,
        fragment_ids=[fragment.fragment_id for fragment in fragments],
        model_availability_path=run_dir / "model_availability.json",
        total_translation_cost=float(summary_payload.get("total_translation_cost") or 0.0),
        total_judge_cost=float(summary_payload.get("total_judge_cost") or 0.0),
        returned_judge_models=list(summary_payload.get("returned_judge_models") or []),
        notes=notes,
        source_language_verification=source_language_verification,
    )
    _write_json(run_dir / "manifest.json", manifest)
    _copy_latest_aliases(
        run_dir=run_dir,
        summary_json_path=run_dir / "summary.json",
        summary_md_path=run_dir / "summary.md",
        manifest_path=run_dir / "manifest.json",
    )
    print(json.dumps(summary_payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
