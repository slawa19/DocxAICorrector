from __future__ import annotations

import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import traceback
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from difflib import SequenceMatcher
import json
from io import BytesIO
from pathlib import Path
import platform
import re
import time
from typing import Any, cast

SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn

import app_runtime
import application_flow
import document_pipeline
import logger as app_logger
import processing_runtime
import processing_service
from config import get_client, load_app_config, load_system_prompt
from document import (
    ORDERED_LIST_FORMATS,
    extract_document_content_from_docx,
    inspect_placeholder_integrity,
)
from formatting_transfer import (
    normalize_semantic_output_docx,
    preserve_source_paragraph_properties,
)
from image_reinsertion import reinsert_inline_images
from generation import (
    convert_markdown_to_docx_bytes,
    ensure_pandoc_available,
    generate_markdown_block,
)
from logger import present_error
from real_document_validation_profiles import (
    apply_runtime_resolution_to_app_config,
    load_validation_registry,
    resolve_runtime_resolution,
)
from runtime_events import (
    AppendImageLogEvent,
    AppendLogEvent,
    FinalizeProcessingStatusEvent,
    PushActivityEvent,
    ResetImageStateEvent,
    SetProcessingStatusEvent,
    SetStateEvent,
)


service = processing_service.get_processing_service()
REAL_DOCUMENT_ARTIFACT_ROOT = PROJECT_ROOT / "tests" / "artifacts" / "real_document_pipeline"
FORMATTING_DIAGNOSTICS_DIR = PROJECT_ROOT / ".run" / "formatting_diagnostics"
HEARTBEAT_INTERVAL_SECONDS = 15.0


class UploadedFileStub:
    def __init__(self, name: str, content: bytes):
        self.name = name
        self._content = content
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = self._content[self._position :]
            self._position = len(self._content)
            return data
        start = self._position
        end = min(len(self._content), start + size)
        self._position = end
        return self._content[start:end]

    def getvalue(self) -> bytes:
        return self._content

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._position = max(0, offset)
        elif whence == 1:
            self._position = max(0, self._position + offset)
        elif whence == 2:
            self._position = max(0, len(self._content) + offset)
        else:
            raise ValueError(f"Unsupported whence: {whence}")
        return self._position


def _path_for_report(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _build_run_id(source_path: Path) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    sanitized_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", source_path.stem).strip("_") or "real_doc"
    return f"{timestamp}_{os.getpid()}_{sanitized_stem}"


def _snapshot_formatting_diagnostics_paths() -> set[str]:
    if not FORMATTING_DIAGNOSTICS_DIR.exists():
        return set()
    return {str(path.resolve()) for path in FORMATTING_DIAGNOSTICS_DIR.glob("*.json") if path.is_file()}


def _collect_new_formatting_diagnostics_paths(before: set[str], after: set[str]) -> list[str]:
    new_paths = [Path(path) for path in after - before]
    return [
        str(path)
        for path in sorted(new_paths, key=lambda candidate: (candidate.stat().st_mtime, str(candidate)))
    ]


def _safe_git_head() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            check=True,
            text=True,
        )
    except Exception:
        return None
    return result.stdout.strip() or None


def _detect_wsl_runtime() -> bool:
    release = platform.release().lower()
    return "microsoft" in release or bool(os.environ.get("WSL_DISTRO_NAME"))


def _build_environment_snapshot() -> dict[str, object]:
    return {
        "script_path": _path_for_report(SCRIPT_PATH),
        "project_root": _path_for_report(PROJECT_ROOT),
        "cwd": _path_for_report(Path.cwd()),
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "pythonpath": os.environ.get("PYTHONPATH"),
        "virtual_env": os.environ.get("VIRTUAL_ENV"),
        "workspace_venv_exists": (PROJECT_ROOT / ".venv" / "bin" / "activate").exists(),
        "workspace_venv_win_exists": (PROJECT_ROOT / ".venv-win" / "Scripts" / "python.exe").exists(),
        "platform": platform.platform(),
        "release": platform.release(),
        "hostname": socket.gethostname(),
        "is_wsl": _detect_wsl_runtime(),
        "git_head": _safe_git_head(),
    }


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _format_terminal_progress_line(
    *,
    event_type: str,
    phase: str,
    stage: str,
    detail: str,
    progress: float | None,
    elapsed_seconds: float,
    metrics: Mapping[str, object] | None,
) -> str:
    progress_text = "-"
    if isinstance(progress, (int, float)):
        progress_text = f"{max(0.0, min(1.0, float(progress))) * 100:.1f}%"
    metrics_parts: list[str] = []
    if metrics:
        for key in ("current_block", "block_count", "job_count", "output_ratio", "target_chars", "context_chars"):
            value = metrics.get(key)
            if value is not None:
                metrics_parts.append(f"{key}={value}")
    suffix = f" | {' '.join(metrics_parts)}" if metrics_parts else ""
    return f"[{event_type}] +{elapsed_seconds:.1f}s [{phase}] {stage} | {progress_text} | {detail}{suffix}"


def _normalize_terminal_detail(detail: str) -> str:
    normalized = detail.strip()
    while normalized.startswith("Heartbeat: "):
        normalized = normalized.removeprefix("Heartbeat: ").strip()
    return normalized


def _as_string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(item) for item in value]


def _as_object_list(value: object) -> list[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return list(value)


def _as_float_or_none(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _print_terminal_completion_summary(*, report: Mapping[str, object], final_status: str) -> None:
    output_artifacts = cast(Mapping[str, object], report.get("output_artifacts") or {})
    acceptance = cast(Mapping[str, object], report.get("acceptance") or {})
    failed_checks = _as_string_list(acceptance.get("failed_checks"))
    print(
        "[summary] "
        f"status={final_status} "
        f"result={report.get('result')} "
        f"acceptance_passed={acceptance.get('passed')} "
        f"run_id={cast(Mapping[str, object], report.get('run') or {}).get('run_id')}",
        flush=True,
    )
    print(
        "[artifacts] "
        f"report={output_artifacts.get('report_json')} "
        f"summary={output_artifacts.get('summary_txt')} "
        f"progress={report.get('progress_path')}",
        flush=True,
    )
    if failed_checks:
        print(f"[acceptance] failed_checks={','.join(str(item) for item in failed_checks)}", flush=True)


class ValidationProgressTracker:
    def __init__(
        self,
        *,
        run_id: str,
        document_profile_id: str | None = None,
        run_profile_id: str | None = None,
        validation_tier: str | None = None,
        source_path: Path,
        run_dir: Path,
        artifact_root: Path,
        progress_path: Path,
        latest_progress_path: Path,
        latest_manifest_path: Path,
        report_path: Path,
        summary_path: Path,
        markdown_path: Path,
        docx_path: Path,
        latest_report_path: Path,
        latest_summary_path: Path,
        latest_markdown_path: Path,
        latest_docx_path: Path,
        started_at_utc: datetime,
    ) -> None:
        self.run_id = run_id
        self.progress_path = progress_path
        self.latest_progress_path = latest_progress_path
        self.latest_manifest_path = latest_manifest_path
        self.started_at_monotonic = time.perf_counter()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.heartbeat_thread: threading.Thread | None = None
        self.state: dict[str, object] = {
            "run_id": run_id,
            "document_profile_id": document_profile_id,
            "run_profile_id": run_profile_id,
            "validation_tier": validation_tier,
            "status": "in_progress",
            "source_file": _path_for_report(source_path),
            "run_dir": _path_for_report(run_dir),
            "artifact_root": _path_for_report(artifact_root),
            "progress_json": _path_for_report(progress_path),
            "latest_progress_json": _path_for_report(latest_progress_path),
            "report_json": _path_for_report(report_path),
            "summary_txt": _path_for_report(summary_path),
            "markdown_path": _path_for_report(markdown_path),
            "docx_path": _path_for_report(docx_path),
            "latest_report_json": _path_for_report(latest_report_path),
            "latest_summary_txt": _path_for_report(latest_summary_path),
            "latest_markdown_path": _path_for_report(latest_markdown_path),
            "latest_docx_path": _path_for_report(latest_docx_path),
            "started_at_utc": started_at_utc.isoformat(),
            "finished_at_utc": None,
            "last_update_at_utc": started_at_utc.isoformat(),
            "phase": "startup",
            "stage": "Инициализация",
            "detail": "Создаю run-scoped артефакты и latest manifest.",
            "progress": 0.0,
            "last_error": "",
            "result": "not_started",
            "acceptance_passed": None,
            "failure_classification": None,
            "runtime_config": None,
            "runtime_overrides": {},
            "metrics": {},
            "recent_events": [],
        }
        self._write_locked()

    def set_manifest_context(self, **values: object) -> None:
        with self.lock:
            self.state.update(cast(dict[str, object], sanitize_for_json(values)))
            self._write_locked()

    def start(self) -> None:
        if self.heartbeat_thread is not None:
            return
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="lietaer-validation-heartbeat", daemon=True)
        self.heartbeat_thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.heartbeat_thread is not None:
            self.heartbeat_thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS + 2.0)

    def emit(
        self,
        *,
        event_type: str,
        phase: str,
        stage: str,
        detail: str,
        progress: float | None = None,
        metrics: Mapping[str, object] | None = None,
        print_line: bool = True,
    ) -> None:
        line = ""
        with self.lock:
            now = datetime.now(UTC)
            elapsed_seconds = max(0.0, time.perf_counter() - self.started_at_monotonic)
            if progress is not None:
                self.state["progress"] = max(0.0, min(1.0, float(progress)))
            self.state["phase"] = phase
            self.state["stage"] = stage
            self.state["detail"] = detail
            self.state["last_update_at_utc"] = now.isoformat()
            self.state["elapsed_seconds"] = round(elapsed_seconds, 3)
            if metrics:
                self.state["metrics"] = sanitize_for_json(dict(metrics))
            recent_events = _as_object_list(self.state.get("recent_events"))
            recent_events.append(
                {
                    "timestamp_utc": now.isoformat(),
                    "event_type": event_type,
                    "phase": phase,
                    "stage": stage,
                    "detail": detail,
                    "progress": self.state.get("progress"),
                    "metrics": sanitize_for_json(dict(metrics or {})),
                }
            )
            self.state["recent_events"] = recent_events[-25:]
            self._write_locked()
            if print_line:
                line = _format_terminal_progress_line(
                    event_type=event_type,
                    phase=phase,
                    stage=stage,
                    detail=detail,
                    progress=_as_float_or_none(self.state.get("progress")) or 0.0,
                    elapsed_seconds=elapsed_seconds,
                    metrics=metrics,
                )
        if line:
            print(line, flush=True)

    def finalize(
        self,
        *,
        status: str,
        result: str,
        acceptance_passed: bool,
        failure_classification: str | None,
        last_error: str,
        detail: str,
    ) -> None:
        line = ""
        with self.lock:
            finished_at_utc = datetime.now(UTC)
            elapsed_seconds = max(0.0, time.perf_counter() - self.started_at_monotonic)
            self.state["status"] = status
            self.state["result"] = result
            self.state["acceptance_passed"] = acceptance_passed
            self.state["failure_classification"] = failure_classification
            self.state["last_error"] = last_error
            self.state["phase"] = "completed" if status == "completed" else "failed"
            self.state["stage"] = "Завершено" if status == "completed" else "Завершено с ошибкой"
            self.state["detail"] = detail
            self.state["progress"] = 1.0
            self.state["finished_at_utc"] = finished_at_utc.isoformat()
            self.state["last_update_at_utc"] = finished_at_utc.isoformat()
            self.state["elapsed_seconds"] = round(elapsed_seconds, 3)
            self._write_locked()
            line = _format_terminal_progress_line(
                event_type=status,
                phase=str(self.state["phase"]),
                stage=str(self.state["stage"]),
                detail=detail,
                progress=1.0,
                elapsed_seconds=elapsed_seconds,
                metrics={"result": result, "acceptance_passed": acceptance_passed},
            )
        print(line, flush=True)

    def _build_manifest_payload_locked(self) -> dict[str, object]:
        return {
            "run_id": self.state.get("run_id"),
            "document_profile_id": self.state.get("document_profile_id"),
            "run_profile_id": self.state.get("run_profile_id"),
            "validation_tier": self.state.get("validation_tier"),
            "status": self.state.get("status"),
            "source_file": self.state.get("source_file"),
            "run_dir": self.state.get("run_dir"),
            "progress_json": self.state.get("progress_json"),
            "latest_progress_json": self.state.get("latest_progress_json"),
            "report_json": self.state.get("report_json"),
            "summary_txt": self.state.get("summary_txt"),
            "markdown_path": self.state.get("markdown_path"),
            "docx_path": self.state.get("docx_path"),
            "latest_report_json": self.state.get("latest_report_json"),
            "latest_summary_txt": self.state.get("latest_summary_txt"),
            "latest_markdown_path": self.state.get("latest_markdown_path"),
            "latest_docx_path": self.state.get("latest_docx_path"),
            "started_at_utc": self.state.get("started_at_utc"),
            "finished_at_utc": self.state.get("finished_at_utc"),
            "last_update_at_utc": self.state.get("last_update_at_utc"),
            "phase": self.state.get("phase"),
            "stage": self.state.get("stage"),
            "detail": self.state.get("detail"),
            "progress": self.state.get("progress"),
            "result": self.state.get("result"),
            "acceptance_passed": self.state.get("acceptance_passed"),
            "failure_classification": self.state.get("failure_classification"),
            "last_error": self.state.get("last_error"),
            "runtime_config": self.state.get("runtime_config"),
            "runtime_overrides": self.state.get("runtime_overrides"),
            "latest_report": self.state.get("latest_report_json"),
            "latest_summary": self.state.get("latest_summary_txt"),
            "latest_markdown": self.state.get("latest_markdown_path"),
            "latest_docx": self.state.get("latest_docx_path"),
        }

    def _write_locked(self) -> None:
        progress_payload = cast(Mapping[str, object], sanitize_for_json(dict(self.state)))
        _write_json_atomic(self.progress_path, progress_payload)
        _write_json_atomic(self.latest_progress_path, progress_payload)
        _write_json_atomic(self.latest_manifest_path, self._build_manifest_payload_locked())

    def _heartbeat_loop(self) -> None:
        while not self.stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            with self.lock:
                if str(self.state.get("status") or "") != "in_progress":
                    return
                phase = str(self.state.get("phase") or "processing")
                stage = str(self.state.get("stage") or "Ожидание")
                detail = str(self.state.get("detail") or "Процесс продолжается.")
                progress_value = self.state.get("progress")
                metrics = cast(Mapping[str, object], self.state.get("metrics") or {})
            self.emit(
                event_type="heartbeat",
                phase=phase,
                stage=stage,
                detail=f"Heartbeat: {_normalize_terminal_detail(detail)}",
                progress=float(progress_value) if isinstance(progress_value, (int, float)) else None,
                metrics=metrics,
            )


def _write_latest_alias_artifacts(
    *,
    report_path: Path,
    summary_path: Path,
    markdown_artifact: Path | None,
    docx_artifact: Path | None,
    latest_report_path: Path,
    latest_summary_path: Path,
    latest_markdown_path: Path | None,
    latest_docx_path: Path | None,
    latest_manifest_path: Path,
    run_id: str,
    run_dir: Path,
    manifest_payload: Mapping[str, object],
) -> None:
    latest_report_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(report_path, latest_report_path)
    shutil.copy2(summary_path, latest_summary_path)
    if markdown_artifact is not None and latest_markdown_path is not None:
        shutil.copy2(markdown_artifact, latest_markdown_path)
    if docx_artifact is not None and latest_docx_path is not None:
        shutil.copy2(docx_artifact, latest_docx_path)

    latest_manifest = dict(manifest_payload)
    latest_manifest.update(
        {
            "run_id": run_id,
            "run_dir": _path_for_report(run_dir),
            "latest_report": _path_for_report(latest_report_path),
            "latest_summary": _path_for_report(latest_summary_path),
            "latest_markdown": _path_for_report(latest_markdown_path) if latest_markdown_path is not None else None,
            "latest_docx": _path_for_report(latest_docx_path) if latest_docx_path is not None else None,
        }
    )
    _write_json_atomic(latest_manifest_path, latest_manifest)


def _load_json_file(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _build_repeat_run_id(parent_run_id: str, repeat_index: int, repeat_count: int) -> str:
    width = max(2, len(str(max(1, repeat_count))))
    return f"{parent_run_id}_r{repeat_index:0{width}d}of{repeat_count:0{width}d}"


def _summarize_repeat_runs(repeat_runs: Sequence[Mapping[str, object]]) -> tuple[dict[str, object], dict[str, object], str | None]:
    total_runs = len(repeat_runs)
    pipeline_succeeded_count = 0
    acceptance_passed_count = 0
    heading_only_output_detected_count = 0
    result_counts: dict[str, int] = {}
    failure_classification_counts: dict[str, int] = {}
    failed_repeat_indexes: list[int] = []
    failed_repeat_run_ids: list[str] = []

    for repeat_run in repeat_runs:
        result = str(repeat_run.get("result") or "unknown")
        result_counts[result] = result_counts.get(result, 0) + 1
        if result == "succeeded":
            pipeline_succeeded_count += 1

        acceptance_passed = bool(repeat_run.get("acceptance_passed"))
        if acceptance_passed:
            acceptance_passed_count += 1
        else:
            repeat_index = repeat_run.get("repeat_index")
            if isinstance(repeat_index, int):
                failed_repeat_indexes.append(repeat_index)
            repeat_run_id = str(repeat_run.get("run_id") or "")
            if repeat_run_id:
                failed_repeat_run_ids.append(repeat_run_id)

        failure_classification = str(repeat_run.get("failure_classification") or "").strip()
        if failure_classification:
            failure_classification_counts[failure_classification] = (
                failure_classification_counts.get(failure_classification, 0) + 1
            )

        signals = cast(Mapping[str, object], repeat_run.get("signals") or {})
        if bool(signals.get("heading_only_output_detected")):
            heading_only_output_detected_count += 1

    all_pipeline_succeeded = total_runs > 0 and pipeline_succeeded_count == total_runs
    all_acceptance_passed = total_runs > 0 and acceptance_passed_count == total_runs
    intermittent_failure_detected = 0 < acceptance_passed_count < total_runs

    checks = [
        {
            "name": "all_repeat_runs_succeeded",
            "passed": all_pipeline_succeeded,
            "actual": pipeline_succeeded_count,
            "expected": total_runs,
        },
        {
            "name": "all_repeat_runs_acceptance_passed",
            "passed": all_acceptance_passed,
            "actual": acceptance_passed_count,
            "expected": total_runs,
        },
    ]
    failed_checks = [check["name"] for check in checks if not bool(check["passed"])]

    acceptance = {
        "passed": all_pipeline_succeeded and all_acceptance_passed,
        "failed_checks": failed_checks,
        "checks": checks,
    }

    failure_classification: str | None = None
    if not acceptance["passed"]:
        if intermittent_failure_detected:
            failure_classification = "intermittent_failure"
        elif len(failure_classification_counts) == 1:
            failure_classification = next(iter(failure_classification_counts))
        else:
            failure_classification = "repeat_failures"

    summary = {
        "repeat_count": total_runs,
        "pipeline_succeeded_count": pipeline_succeeded_count,
        "acceptance_passed_count": acceptance_passed_count,
        "failed_repeat_indexes": failed_repeat_indexes,
        "failed_repeat_run_ids": failed_repeat_run_ids,
        "intermittent_failure_detected": intermittent_failure_detected,
        "heading_only_output_detected_count": heading_only_output_detected_count,
        "result_counts": result_counts,
        "failure_classification_counts": failure_classification_counts,
    }
    return summary, acceptance, failure_classification


def _select_repeat_artifact_references(repeat_runs: Sequence[Mapping[str, object]]) -> dict[str, object | None]:
    first_failing_run = next((run for run in repeat_runs if not bool(run.get("acceptance_passed"))), None)
    representative_success_run = next((run for run in reversed(list(repeat_runs)) if bool(run.get("acceptance_passed"))), None)

    def extract_paths(run: Mapping[str, object] | None, prefix: str) -> dict[str, object | None]:
        if run is None:
            return {
                f"{prefix}_run_id": None,
                f"{prefix}_report_json": None,
                f"{prefix}_summary_txt": None,
                f"{prefix}_markdown_path": None,
                f"{prefix}_docx_path": None,
            }
        output_artifacts = cast(Mapping[str, object], run.get("output_artifacts") or {})
        return {
            f"{prefix}_run_id": run.get("run_id"),
            f"{prefix}_report_json": run.get("report_path"),
            f"{prefix}_summary_txt": run.get("summary_path"),
            f"{prefix}_markdown_path": output_artifacts.get("markdown_path"),
            f"{prefix}_docx_path": output_artifacts.get("docx_path"),
        }

    artifact_references = {}
    artifact_references.update(extract_paths(first_failing_run, "first_failing"))
    artifact_references.update(extract_paths(representative_success_run, "representative_success"))
    return artifact_references


def _run_repeat_validation(
    *,
    document_profile,
    run_profile,
    source_path: Path,
    artifact_root: Path,
    requested_run_profile_id: str | None,
) -> None:
    artifact_root.mkdir(parents=True, exist_ok=True)
    parent_run_id = _build_run_id(source_path)
    artifact_dir = artifact_root / "runs" / parent_run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    artifact_prefix = document_profile.artifact_prefix
    output_basename = document_profile.output_basename or f"{source_path.stem}_validated"
    report_path = artifact_dir / f"{artifact_prefix}_report.json"
    summary_path = artifact_dir / f"{artifact_prefix}_summary.txt"
    progress_path = artifact_dir / f"{artifact_prefix}_progress.json"
    markdown_artifact = artifact_dir / f"{output_basename}.md"
    docx_artifact = artifact_dir / f"{output_basename}.docx"
    latest_report_path = artifact_root / f"{artifact_prefix}_report.json"
    latest_summary_path = artifact_root / f"{artifact_prefix}_summary.txt"
    latest_progress_path = artifact_root / f"{artifact_prefix}_progress.json"
    latest_markdown_path = artifact_root / f"{output_basename}.md"
    latest_docx_path = artifact_root / f"{output_basename}.docx"
    latest_manifest_path = artifact_root / f"{artifact_prefix}_latest.json"

    run_started_at_utc = datetime.now(UTC)
    run_started_at_epoch_seconds = time.time()
    tracker = ValidationProgressTracker(
        run_id=parent_run_id,
        document_profile_id=document_profile.id,
        run_profile_id=run_profile.id,
        validation_tier=run_profile.tier,
        source_path=source_path,
        run_dir=artifact_dir,
        artifact_root=artifact_root,
        progress_path=progress_path,
        latest_progress_path=latest_progress_path,
        latest_manifest_path=latest_manifest_path,
        report_path=report_path,
        summary_path=summary_path,
        markdown_path=markdown_artifact,
        docx_path=docx_artifact,
        latest_report_path=latest_report_path,
        latest_summary_path=latest_summary_path,
        latest_markdown_path=latest_markdown_path,
        latest_docx_path=latest_docx_path,
        started_at_utc=run_started_at_utc,
    )
    tracker.start()
    tracker.emit(
        event_type="start",
        phase="startup",
        stage="Repeat orchestration",
        detail=f"Запуск repeat/soak профиля {run_profile.id} на {run_profile.repeat_count} повторов.",
        progress=0.0,
        metrics={"repeat_count": run_profile.repeat_count},
    )

    app_config = load_app_config()
    runtime_resolution = resolve_runtime_resolution(app_config, run_profile)
    tracker.set_manifest_context(
        runtime_config=runtime_resolution.effective.to_dict(),
        runtime_overrides=runtime_resolution.overrides,
    )

    repeat_runs: list[dict[str, object]] = []
    last_markdown_artifact: Path | None = None
    last_docx_artifact: Path | None = None

    try:
        for repeat_index in range(1, run_profile.repeat_count + 1):
            repeat_run_id = _build_repeat_run_id(parent_run_id, repeat_index, run_profile.repeat_count)
            tracker.emit(
                event_type="repeat_start",
                phase="repeat",
                stage=f"Repeat {repeat_index}/{run_profile.repeat_count}",
                detail=f"Запускаю повтор {repeat_index} из {run_profile.repeat_count}.",
                progress=(repeat_index - 1) / run_profile.repeat_count,
                metrics={"current_repeat": repeat_index, "repeat_count": run_profile.repeat_count},
            )

            child_env = os.environ.copy()
            child_env["DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE"] = "1"
            child_env["DOCXAI_REAL_DOCUMENT_FORCED_RUN_ID"] = repeat_run_id
            child_env["DOCXAI_REAL_DOCUMENT_PARENT_RUN_ID"] = parent_run_id
            child_env["DOCXAI_REAL_DOCUMENT_REPEAT_INDEX"] = str(repeat_index)
            child_env["DOCXAI_REAL_DOCUMENT_REPEAT_TOTAL"] = str(run_profile.repeat_count)
            child_env["DOCXAI_REAL_DOCUMENT_PROFILE"] = document_profile.id
            if requested_run_profile_id:
                child_env["DOCXAI_REAL_DOCUMENT_RUN_PROFILE"] = requested_run_profile_id

            completed = subprocess.run(
                [sys.executable, str(SCRIPT_PATH)],
                cwd=PROJECT_ROOT,
                env=child_env,
                check=False,
            )

            repeat_dir = artifact_root / "runs" / repeat_run_id
            repeat_report_path = repeat_dir / f"{artifact_prefix}_report.json"
            repeat_summary_path = repeat_dir / f"{artifact_prefix}_summary.txt"
            repeat_progress_path = repeat_dir / f"{artifact_prefix}_progress.json"

            repeat_report = _load_json_file(repeat_report_path) if repeat_report_path.exists() else {}
            repeat_output_artifacts = cast(Mapping[str, object], repeat_report.get("output_artifacts") or {})
            repeat_markdown_path = repeat_output_artifacts.get("markdown_path")
            repeat_docx_path = repeat_output_artifacts.get("docx_path")
            if isinstance(repeat_markdown_path, str) and repeat_markdown_path:
                candidate = PROJECT_ROOT / repeat_markdown_path
                if candidate.exists():
                    last_markdown_artifact = candidate
            if isinstance(repeat_docx_path, str) and repeat_docx_path:
                candidate = PROJECT_ROOT / repeat_docx_path
                if candidate.exists():
                    last_docx_artifact = candidate

            repeat_run_payload = {
                "repeat_index": repeat_index,
                "repeat_count": run_profile.repeat_count,
                "run_id": repeat_run_id,
                "returncode": completed.returncode,
                "status": "completed" if completed.returncode == 0 else "failed",
                "result": repeat_report.get("result") if repeat_report else "failed",
                "acceptance_passed": bool(cast(Mapping[str, object], repeat_report.get("acceptance") or {}).get("passed")),
                "failed_checks": _as_string_list(cast(Mapping[str, object], repeat_report.get("acceptance") or {}).get("failed_checks")),
                "failure_classification": repeat_report.get("failure_classification"),
                "duration_seconds": cast(Mapping[str, object], repeat_report.get("run") or {}).get("duration_seconds"),
                "report_path": _path_for_report(repeat_report_path) if repeat_report_path.exists() else None,
                "summary_path": _path_for_report(repeat_summary_path) if repeat_summary_path.exists() else None,
                "progress_path": _path_for_report(repeat_progress_path) if repeat_progress_path.exists() else None,
                "signals": repeat_report.get("signals") or {},
                "output_artifacts": repeat_output_artifacts,
            }
            repeat_runs.append(repeat_run_payload)

            tracker.emit(
                event_type="repeat_complete",
                phase="repeat",
                stage=f"Repeat {repeat_index}/{run_profile.repeat_count}",
                detail=(
                    f"Повтор {repeat_index} завершён: result={repeat_run_payload['result']} "
                    f"acceptance={repeat_run_payload['acceptance_passed']}."
                ),
                progress=repeat_index / run_profile.repeat_count,
                metrics={
                    "current_repeat": repeat_index,
                    "repeat_count": run_profile.repeat_count,
                    "returncode": completed.returncode,
                },
            )

        repeat_summary, acceptance, failure_classification = _summarize_repeat_runs(repeat_runs)
        run_finished_at_epoch_seconds = time.time()
        run_finished_at_utc = datetime.now(UTC)
        run_duration_seconds = round(run_finished_at_epoch_seconds - run_started_at_epoch_seconds, 3)
        result = "succeeded" if acceptance["passed"] else "failed"

        repeat_artifact_references = _select_repeat_artifact_references(repeat_runs)

        report = {
            "run": {
                "run_id": parent_run_id,
                "started_at_utc": run_started_at_utc.isoformat(),
                "finished_at_utc": run_finished_at_utc.isoformat(),
                "duration_seconds": run_duration_seconds,
                "document_profile_id": document_profile.id,
                "run_profile_id": run_profile.id,
                "validation_tier": run_profile.tier,
                "repeat_count": run_profile.repeat_count,
                "artifact_root": _path_for_report(artifact_root),
                "artifact_dir": _path_for_report(artifact_dir),
                "environment": _build_environment_snapshot(),
            },
            "document_profile_id": document_profile.id,
            "run_profile_id": run_profile.id,
            "validation_tier": run_profile.tier,
            "source_document_path": _path_for_report(source_path),
            "source_file": _path_for_report(source_path),
            "artifact_dir": _path_for_report(artifact_dir),
            "progress_path": _path_for_report(progress_path),
            "result": result,
            "runtime_config": {
                "effective": runtime_resolution.effective.to_dict(),
                "ui_defaults": runtime_resolution.ui_defaults.to_dict(),
                "overrides": runtime_resolution.overrides,
            },
            "failure_classification": failure_classification,
            "signals": {
                "intermittent_failure_detected": repeat_summary["intermittent_failure_detected"],
                "heading_only_output_detected_count": repeat_summary["heading_only_output_detected_count"],
            },
            "preparation": None,
            "formatting_diagnostics": [],
            "repeat_summary": repeat_summary,
            "repeat_runs": repeat_runs,
            "acceptance": acceptance,
            "output_artifacts": {
                "markdown_path": _path_for_report(last_markdown_artifact),
                "docx_path": _path_for_report(last_docx_artifact),
                "report_json": _path_for_report(report_path),
                "summary_txt": _path_for_report(summary_path),
                "latest_report_json": _path_for_report(latest_report_path),
                "latest_summary_txt": _path_for_report(latest_summary_path),
                "latest_markdown_path": _path_for_report(latest_markdown_path) if last_markdown_artifact is not None else None,
                "latest_docx_path": _path_for_report(latest_docx_path) if last_docx_artifact is not None else None,
                "latest_manifest_json": _path_for_report(latest_manifest_path),
                **repeat_artifact_references,
            },
        }
        sanitized_report = sanitize_for_json(report)
        final_status = "completed" if acceptance["passed"] else "failed"

        summary_lines = [
            f"run_id={parent_run_id}",
            f"document_profile_id={document_profile.id}",
            f"run_profile_id={run_profile.id}",
            f"validation_tier={run_profile.tier}",
            f"status={final_status}",
            f"run_started_at_utc={run_started_at_utc.isoformat()}",
            f"run_finished_at_utc={run_finished_at_utc.isoformat()}",
            f"run_duration_seconds={run_duration_seconds}",
            f"source={_path_for_report(source_path)}",
            f"artifact_dir={_path_for_report(artifact_dir)}",
            f"artifact_root={_path_for_report(artifact_root)}",
            f"progress_json={_path_for_report(progress_path)}",
            f"result={result}",
            f"failure_classification={failure_classification}",
            f"repeat_count={run_profile.repeat_count}",
            f"runtime_overrides={json.dumps(cast(Mapping[str, object], report['runtime_config']).get('overrides') or {}, ensure_ascii=False, sort_keys=True)}",
            f"pipeline_succeeded_count={repeat_summary['pipeline_succeeded_count']}",
            f"acceptance_passed_count={repeat_summary['acceptance_passed_count']}",
            f"intermittent_failure_detected={repeat_summary['intermittent_failure_detected']}",
            f"failed_repeat_indexes={','.join(str(index) for index in _as_object_list(repeat_summary['failed_repeat_indexes']))}",
            f"failed_repeat_run_ids={','.join(str(item) for item in _as_object_list(repeat_summary['failed_repeat_run_ids']))}",
            f"result_counts={json.dumps(repeat_summary['result_counts'], ensure_ascii=False, sort_keys=True)}",
            f"failure_classification_counts={json.dumps(repeat_summary['failure_classification_counts'], ensure_ascii=False, sort_keys=True)}",
            f"acceptance_passed={acceptance['passed']}",
            f"acceptance_failed_checks={','.join(_as_string_list(acceptance['failed_checks']))}",
            f"markdown_path={report['output_artifacts']['markdown_path']}",
            f"docx_path={report['output_artifacts']['docx_path']}",
            f"latest_manifest_json={report['output_artifacts']['latest_manifest_json']}",
        ]

        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        report_path.write_text(json.dumps(sanitized_report, ensure_ascii=False, indent=2), encoding="utf-8")
        _write_latest_alias_artifacts(
            report_path=report_path,
            summary_path=summary_path,
            markdown_artifact=last_markdown_artifact,
            docx_artifact=last_docx_artifact,
            latest_report_path=latest_report_path,
            latest_summary_path=latest_summary_path,
            latest_markdown_path=latest_markdown_path if last_markdown_artifact is not None else None,
            latest_docx_path=latest_docx_path if last_docx_artifact is not None else None,
            latest_manifest_path=latest_manifest_path,
            run_id=parent_run_id,
            run_dir=artifact_dir,
            manifest_payload=cast(Mapping[str, object], tracker._build_manifest_payload_locked()),
        )
        tracker.finalize(
            status=final_status,
            result=result,
            acceptance_passed=bool(acceptance["passed"]),
            failure_classification=failure_classification,
            last_error="",
            detail=(
                f"Acceptance={'passed' if acceptance['passed'] else 'failed'}; report={_path_for_report(report_path)}"
            ),
        )
        _print_terminal_completion_summary(report=cast(Mapping[str, object], report), final_status=final_status)
        if not bool(acceptance["passed"]):
            raise SystemExit(1)
    finally:
        tracker.stop()


def present_error_adapter(code: str, exc: Exception, title: str, **context: object) -> str:
    return present_error(code, exc, title, **context)


def emit_state_adapter(runtime: object, **values: object) -> None:
    app_runtime.emit_state(cast(Any, runtime), **values)


def emit_finalize_adapter(runtime: object, stage: str, detail: str, progress: float) -> None:
    app_runtime.emit_finalize(cast(Any, runtime), stage, detail, progress)


def emit_activity_adapter(runtime: object, message: str) -> None:
    app_runtime.emit_activity(cast(Any, runtime), message)


def emit_log_adapter(runtime: object, **payload: object) -> None:
    app_runtime.emit_log(cast(Any, runtime), **payload)


def emit_status_adapter(runtime: object, **payload: object) -> None:
    app_runtime.emit_status(cast(Any, runtime), **payload)


def should_stop_processing_adapter(runtime: object) -> bool:
    return processing_runtime.should_stop_processing(cast(Any, runtime))


def generate_markdown_block_adapter(
    *,
    client: object,
    model: str,
    system_prompt: str,
    target_text: str,
    context_before: str,
    context_after: str,
    max_retries: int,
    expected_paragraph_ids=None,
    marker_mode: bool = False,
) -> str:
    return generate_markdown_block(
        client=cast(Any, client),
        model=model,
        system_prompt=system_prompt,
        target_text=target_text,
        context_before=context_before,
        context_after=context_after,
        max_retries=max_retries,
        expected_paragraph_ids=expected_paragraph_ids,
        marker_mode=marker_mode,
    )


def process_document_images_adapter(
    *,
    image_assets: Sequence[object],
    image_mode: str,
    config: Mapping[str, object],
    on_progress,
    runtime: object,
    client: object,
):
    return service.process_document_images(
        image_assets=cast(Any, image_assets),
        image_mode=image_mode,
        config=dict(config),
        on_progress=on_progress,
        runtime=cast(Any, runtime),
        client=cast(Any, client),
    )


def inspect_placeholder_integrity_adapter(markdown_text: str, image_assets: Sequence[object]) -> Mapping[str, str]:
    return inspect_placeholder_integrity(markdown_text, cast(Any, list(image_assets)))


def preserve_source_paragraph_properties_adapter(
    docx_bytes: bytes,
    paragraphs: Sequence[object],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    return preserve_source_paragraph_properties(
        docx_bytes,
        cast(Any, list(paragraphs)),
        generated_paragraph_registry=generated_paragraph_registry,
    )


def normalize_semantic_output_docx_adapter(
    docx_bytes: bytes,
    paragraphs: Sequence[object],
    generated_paragraph_registry: Sequence[Mapping[str, object]] | None = None,
) -> bytes:
    return normalize_semantic_output_docx(
        docx_bytes,
        cast(Any, list(paragraphs)),
        generated_paragraph_registry=generated_paragraph_registry,
    )


def reinsert_inline_images_adapter(docx_bytes: bytes, image_assets: Sequence[object]) -> bytes:
    return reinsert_inline_images(docx_bytes, cast(Any, list(image_assets)))


def _apply_runtime_event(event: object, runtime_snapshot: dict) -> None:
    if isinstance(event, SetStateEvent):
        runtime_snapshot.setdefault("state", {}).update(event.values)
    elif isinstance(event, ResetImageStateEvent):
        runtime_snapshot["image_reset_count"] = int(
            runtime_snapshot.get("image_reset_count", 0)
        ) + 1
    elif isinstance(event, SetProcessingStatusEvent):
        runtime_snapshot.setdefault("status", []).append(event.payload)
    elif isinstance(event, FinalizeProcessingStatusEvent):
        runtime_snapshot.setdefault("finalize", []).append(
            {
                "stage": event.stage,
                "detail": event.detail,
                "progress": event.progress,
            }
        )
    elif isinstance(event, PushActivityEvent):
        runtime_snapshot.setdefault("activity", []).append(event.message)
    elif isinstance(event, AppendLogEvent):
        runtime_snapshot.setdefault("log", []).append(event.payload)
    elif isinstance(event, AppendImageLogEvent):
        runtime_snapshot.setdefault("image_log", []).append(event.payload)


def drain_runtime_events(event_queue: queue.Queue, runtime_snapshot: dict, on_event=None) -> None:
    while True:
        try:
            event = event_queue.get_nowait()
        except queue.Empty:
            break
        _apply_runtime_event(event, runtime_snapshot)
        if on_event is not None:
            on_event(event)


def sanitize_for_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): sanitize_for_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_for_json(item) for item in value]
    return app_logger.sanitize_log_context(value)


def classify_failure(report: dict) -> str | None:
    candidates = []
    last_error = str(report.get("last_error") or "")
    candidates.append(last_error)
    exc = report.get("exception") or {}
    if isinstance(exc, dict):
        candidates.append(str(exc.get("message") or ""))
        candidates.append(str(exc.get("traceback") or ""))
    for event in report.get("event_log", []):
        if isinstance(event, dict):
            candidates.append(str(event.get("event_id") or ""))
            candidates.append(json.dumps(event, ensure_ascii=False))
    joined = "\n".join(text for text in candidates if text)
    for marker in (
        "heading_only_output",
        "empty_processed_block",
        "empty_response",
        "collapsed_output",
        "unsupported_response_shape",
        "image_placeholder_integrity_failed",
        "docx_build_failed",
        "image_processing_failed",
        "processing_init_failed",
    ):
        if marker in joined:
            return marker
    if report.get("result") == "failed":
        return "failed_unclassified"
    if report.get("result") == "stopped":
        return "stopped"
    return None


def is_heading_only_markdown(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(line.startswith("#") and len(line.split()) >= 2 for line in lines)


def _normalize_structural_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    normalized = re.sub(r"^#{1,6}\s+", "", normalized)
    return normalized


def _find_child_by_local_name(element, local_name: str):
    if element is None:
        return None
    for child in element:
        if child.tag == qn(f"w:{local_name}"):
            return child
    return None


def _paragraph_has_word_numbering(paragraph) -> bool:
    paragraph_properties = getattr(paragraph._element, "pPr", None)
    num_pr = _find_child_by_local_name(paragraph_properties, "numPr")
    if num_pr is not None:
        return True

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = _find_child_by_local_name(getattr(style, "_element", None), "pPr")
        num_pr = _find_child_by_local_name(style_properties, "numPr")
        if num_pr is not None:
            return True
        style = getattr(style, "base_style", None)
    return False


def _count_word_numbered_paragraphs(document: DocxDocument) -> int:
    return sum(1 for paragraph in document.paragraphs if _paragraph_has_word_numbering(paragraph))


def _resolve_paragraph_num_id(paragraph) -> str | None:
    paragraph_properties = getattr(paragraph._element, "pPr", None)
    num_pr = _find_child_by_local_name(paragraph_properties, "numPr")
    if num_pr is not None:
        num_id_element = _find_child_by_local_name(num_pr, "numId")
        if num_id_element is not None:
            return num_id_element.get(qn("w:val"))

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = _find_child_by_local_name(getattr(style, "_element", None), "pPr")
        num_pr = _find_child_by_local_name(style_properties, "numPr")
        if num_pr is not None:
            num_id_element = _find_child_by_local_name(num_pr, "numId")
            if num_id_element is not None:
                return num_id_element.get(qn("w:val"))
        style = getattr(style, "base_style", None)
    return None


def _resolve_paragraph_ilvl(paragraph) -> str | None:
    paragraph_properties = getattr(paragraph._element, "pPr", None)
    num_pr = _find_child_by_local_name(paragraph_properties, "numPr")
    if num_pr is not None:
        ilvl_element = _find_child_by_local_name(num_pr, "ilvl")
        if ilvl_element is not None:
            return ilvl_element.get(qn("w:val"))

    style = getattr(paragraph, "style", None)
    while style is not None:
        style_properties = _find_child_by_local_name(getattr(style, "_element", None), "pPr")
        num_pr = _find_child_by_local_name(style_properties, "numPr")
        if num_pr is not None:
            ilvl_element = _find_child_by_local_name(num_pr, "ilvl")
            if ilvl_element is not None:
                return ilvl_element.get(qn("w:val"))
        style = getattr(style, "base_style", None)
    return None


def _resolve_numbering_format_by_num_id(document: DocxDocument) -> dict[tuple[str, str], str]:
    numbering_part = getattr(document.part, "numbering_part", None)
    numbering_root = getattr(numbering_part, "element", None)
    if numbering_root is None:
        return {}

    abstract_num_formats: dict[str, dict[str, str]] = {}
    for child in numbering_root:
        if child.tag != qn("w:abstractNum"):
            continue
        abstract_num_id = child.get(qn("w:abstractNumId"))
        if not abstract_num_id:
            continue
        level_formats: dict[str, str] = {}
        for candidate in child:
            if candidate.tag != qn("w:lvl"):
                continue
            ilvl = candidate.get(qn("w:ilvl")) or "0"
            num_fmt = _find_child_by_local_name(candidate, "numFmt")
            format_value = None if num_fmt is None else num_fmt.get(qn("w:val"))
            if format_value:
                level_formats[ilvl] = format_value
        if level_formats:
            abstract_num_formats[abstract_num_id] = level_formats

    formats_by_num_id: dict[tuple[str, str], str] = {}
    for child in numbering_root:
        if child.tag != qn("w:num"):
            continue
        num_id = child.get(qn("w:numId"))
        if not num_id:
            continue
        abstract_num_id_element = _find_child_by_local_name(child, "abstractNumId")
        abstract_num_id = None if abstract_num_id_element is None else abstract_num_id_element.get(qn("w:val"))
        if not abstract_num_id or abstract_num_id not in abstract_num_formats:
            continue
        for ilvl, format_value in abstract_num_formats[abstract_num_id].items():
            formats_by_num_id[(num_id, ilvl)] = format_value
    return formats_by_num_id


def _count_ordered_word_numbered_paragraphs(document: DocxDocument) -> int:
    formats_by_num_id = _resolve_numbering_format_by_num_id(document)
    count = 0
    for paragraph in document.paragraphs:
        num_id = _resolve_paragraph_num_id(paragraph)
        ilvl = _resolve_paragraph_ilvl(paragraph) or "0"
        if num_id and formats_by_num_id.get((num_id, ilvl)) in ORDERED_LIST_FORMATS:
            count += 1
    return count


def _resolve_direct_paragraph_alignment(paragraph) -> str | None:
    paragraph_properties = getattr(paragraph._element, "pPr", None)
    alignment = _find_child_by_local_name(paragraph_properties, "jc")
    return None if alignment is None else alignment.get(qn("w:val"))


def _extract_short_centered_paragraph_texts(
    document: DocxDocument,
    *,
    max_words: int = 18,
    max_chars: int = 160,
) -> set[str]:
    centered_texts: set[str] = set()
    for paragraph in document.paragraphs:
        if _resolve_direct_paragraph_alignment(paragraph) != "center":
            continue
        normalized_text = _normalize_structural_text(paragraph.text)
        if not normalized_text:
            continue
        if len(normalized_text) > max_chars or len(normalized_text.split()) > max_words:
            continue
        centered_texts.add(normalized_text)
    return centered_texts


def _centered_text_similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0

    score = SequenceMatcher(None, left, right).ratio()
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if left_tokens and right_tokens:
        overlap_score = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
        score = max(score, overlap_score)

    if left.startswith("рисунок ") and right.startswith("рисунок "):
        left_label = left.split(" ", 2)[:2]
        right_label = right.split(" ", 2)[:2]
        if left_label == right_label:
            score = max(score, 0.85)
    return score


def _extract_centered_caption_label(text: str) -> str | None:
    match = re.match(r"^(рисунок|рис\.?|figure|fig\.?)\s+([0-9]+(?:\.[0-9]+)*)", text, re.IGNORECASE)
    if match is None:
        return None
    return f"{match.group(1).lower()} {match.group(2)}"


def _classify_centered_fragment(text: str) -> dict[str, str | None]:
    label = _extract_centered_caption_label(text)
    if label is not None:
        return {"kind": "caption", "label": label}
    return {"kind": "general", "label": None}


def _match_centered_structural_texts(
    source_centered_texts: Sequence[str],
    output_centered_texts: Sequence[str],
    *,
    min_similarity: float = 0.55,
) -> tuple[list[str], list[dict[str, object]]]:
    unmatched_output = list(output_centered_texts)
    missing_source: list[str] = []
    matches: list[dict[str, object]] = []

    for source_text in source_centered_texts:
        source_fragment = _classify_centered_fragment(source_text)
        best_index = -1
        best_score = 0.0
        for candidate_index, candidate_text in enumerate(unmatched_output):
            candidate_fragment = _classify_centered_fragment(candidate_text)
            if source_fragment["kind"] != candidate_fragment["kind"]:
                continue

            score = _centered_text_similarity(source_text, candidate_text)
            if source_fragment["kind"] == "caption":
                if source_fragment["label"] and source_fragment["label"] == candidate_fragment["label"]:
                    score = max(score, 0.95)
            else:
                score = max(score, 0.7)

            if score > best_score:
                best_score = score
                best_index = candidate_index
        if best_index >= 0 and best_score >= min_similarity:
            matched_output = unmatched_output.pop(best_index)
            matches.append(
                {
                    "source": source_text,
                    "output": matched_output,
                    "similarity": round(best_score, 3),
                }
            )
            continue
        missing_source.append(source_text)

    return missing_source, matches


def _load_recent_formatting_diagnostics(since_epoch_seconds: float) -> tuple[list[str], list[dict[str, object]]]:
    artifact_paths = document_pipeline._collect_recent_formatting_diagnostics(
        since_epoch_seconds=since_epoch_seconds
    )
    return artifact_paths, _load_formatting_diagnostics_payloads(artifact_paths)


def _load_formatting_diagnostics_payloads(artifact_paths: Sequence[str]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for artifact_path in artifact_paths:
        try:
            payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _extract_run_formatting_diagnostics_paths(event_log: Sequence[Mapping[str, object]]) -> list[str]:
    for event in reversed(event_log):
        if str(event.get("event_id") or "") != "formatting_diagnostics_artifacts_detected":
            continue
        context = event.get("context") or {}
        if not isinstance(context, Mapping):
            continue
        artifact_paths = context.get("artifact_paths") or []
        if not isinstance(artifact_paths, Sequence) or isinstance(artifact_paths, (str, bytes, bytearray)):
            continue
        return [str(path) for path in artifact_paths if isinstance(path, str) and path]
    return []


def evaluate_lietaer_acceptance(
    report: Mapping[str, object],
    *,
    source_docx_bytes: bytes | None = None,
    output_docx_bytes: bytes | None = None,
    mismatch_threshold: int = 0,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def add_check(name: str, passed: bool, **details: object) -> None:
        checks.append({"name": name, "passed": passed, **details})

    result = str(report.get("result") or "")
    output_artifacts = cast(Mapping[str, object], report.get("output_artifacts") or {})
    formatting_diagnostics = cast(Sequence[Mapping[str, object]], report.get("formatting_diagnostics") or [])

    add_check("pipeline_succeeded", result == "succeeded", result=result)
    add_check(
        "output_docx_openable",
        bool(output_artifacts.get("output_docx_openable")),
        output_docx_openable=output_artifacts.get("output_docx_openable"),
    )
    add_check(
        "no_placeholder_markup",
        not bool(output_artifacts.get("output_contains_placeholder_markup")),
        output_contains_placeholder_markup=output_artifacts.get("output_contains_placeholder_markup"),
    )

    worst_unmapped_source_count = 0
    total_caption_heading_conflicts = 0
    for payload in formatting_diagnostics:
        worst_unmapped_source_count = max(
            worst_unmapped_source_count,
            len(cast(Sequence[object], payload.get("unmapped_source_ids") or [])),
        )
        total_caption_heading_conflicts += len(
            cast(Sequence[object], payload.get("caption_heading_conflicts") or [])
        )
    add_check(
        "formatting_diagnostics_threshold",
        worst_unmapped_source_count <= mismatch_threshold and total_caption_heading_conflicts == 0,
        worst_unmapped_source_count=worst_unmapped_source_count,
        mismatch_threshold=mismatch_threshold,
        caption_heading_conflicts=total_caption_heading_conflicts,
        artifact_count=len(formatting_diagnostics),
    )

    if source_docx_bytes and output_docx_bytes:
        source_paragraphs, _ = extract_document_content_from_docx(BytesIO(source_docx_bytes))
        output_paragraphs, _ = extract_document_content_from_docx(BytesIO(output_docx_bytes))
        source_document = Document(BytesIO(source_docx_bytes))
        output_document = Document(BytesIO(output_docx_bytes))

        source_caption_texts = {
            _normalize_structural_text(paragraph.text)
            for paragraph in source_paragraphs
            if paragraph.role == "caption" and _normalize_structural_text(paragraph.text)
        }
        output_heading_texts = {
            _normalize_structural_text(paragraph.text)
            for paragraph in output_paragraphs
            if paragraph.role == "heading" and _normalize_structural_text(paragraph.text)
        }
        caption_heading_regressions = sorted(source_caption_texts & output_heading_texts)
        add_check(
            "captions_not_promoted_to_headings",
            not caption_heading_regressions,
            regressions=caption_heading_regressions,
        )

        source_heading_texts = {
            _normalize_structural_text(paragraph.text)
            for paragraph in source_paragraphs
            if paragraph.role == "heading"
            and _normalize_structural_text(paragraph.text)
            and len(_normalize_structural_text(paragraph.text).split()) <= 10
        }
        output_heading_texts = {
            _normalize_structural_text(paragraph.text)
            for paragraph in output_paragraphs
            if paragraph.role == "heading" and _normalize_structural_text(paragraph.text)
        }
        missing_key_headings = sorted(source_heading_texts - output_heading_texts)
        add_check(
            "key_headings_preserved",
            not missing_key_headings,
            missing=missing_key_headings,
            source_heading_count=len(source_heading_texts),
            output_heading_count=len(output_heading_texts),
        )

        source_centered_texts = sorted(_extract_short_centered_paragraph_texts(source_document))
        output_centered_texts = sorted(_extract_short_centered_paragraph_texts(output_document))
        missing_centered_texts, centered_matches = _match_centered_structural_texts(
            source_centered_texts,
            output_centered_texts,
        )
        add_check(
            "centered_short_paragraphs_preserved",
            not missing_centered_texts,
            missing=missing_centered_texts,
            source_centered_count=len(source_centered_texts),
            output_centered_count=len(output_centered_texts),
            matches=centered_matches,
        )

        source_numbered_count = sum(1 for paragraph in source_paragraphs if paragraph.role == "list" and paragraph.list_kind == "ordered")
        output_numbered_count = _count_ordered_word_numbered_paragraphs(output_document)
        add_check(
            "word_numbering_preserved",
            source_numbered_count == 0 or output_numbered_count >= source_numbered_count,
            source_numbered_count=source_numbered_count,
            output_numbered_count=output_numbered_count,
        )
    else:
        add_check(
            "structural_comparison_available",
            False,
            reason="source_or_output_docx_missing",
        )

    failed_checks = [check["name"] for check in checks if not bool(check["passed"])]
    return {
        "passed": not failed_checks,
        "failed_checks": failed_checks,
        "checks": checks,
    }


def _apply_repeat_count_override(run_profile, repeat_count_override: str):
    if not repeat_count_override:
        return run_profile
    try:
        repeat_count = max(1, int(repeat_count_override))
    except ValueError:
        print(
            f"[warning] invalid DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE={repeat_count_override!r}; using profile default {run_profile.repeat_count}",
            flush=True,
        )
        return run_profile
    return replace(run_profile, repeat_count=repeat_count)


def _build_report_runtime_config(runtime_resolution) -> dict[str, object]:
    return {
        "effective": runtime_resolution.effective.to_dict() if runtime_resolution is not None else None,
        "ui_defaults": runtime_resolution.ui_defaults.to_dict() if runtime_resolution is not None else None,
        "overrides": runtime_resolution.overrides if runtime_resolution is not None else {},
    }


def _serialize_image_asset_forensics(image_assets: Sequence[object]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for asset in image_assets:
        if not hasattr(asset, "source_identity_snapshot"):
            continue
        source_snapshot = asset.source_identity_snapshot()
        runtime_snapshot = asset.runtime_state_snapshot() if hasattr(asset, "runtime_state_snapshot") else None
        final_snapshot = asset.final_selection_snapshot() if hasattr(asset, "final_selection_snapshot") else None

        source_payload = source_snapshot.to_dict() if hasattr(source_snapshot, "to_dict") else {}
        source_bytes = getattr(asset, "original_bytes", None)
        if isinstance(source_bytes, (bytes, bytearray)):
            source_payload["source_sha256"] = hashlib.sha256(bytes(source_bytes)).hexdigest()
            source_payload["source_bytes_size"] = len(source_bytes)

        payload.append(
            {
                "source": source_payload,
                "runtime": runtime_snapshot.to_dict() if hasattr(runtime_snapshot, "to_dict") else None,
                "final_selection": final_snapshot.to_dict() if hasattr(final_snapshot, "to_dict") else None,
            }
        )
    return payload


def _build_image_forensics_report(prepared, runtime_snapshot: Mapping[str, object]) -> dict[str, object]:
    runtime_state = cast(Mapping[str, object], runtime_snapshot.get("state") or {})
    processed_assets = runtime_state.get("image_assets")
    prepared_assets = prepared.image_assets if prepared is not None else []
    return {
        "prepared_assets": _serialize_image_asset_forensics(cast(Sequence[object], prepared_assets)),
        "processed_assets": _serialize_image_asset_forensics(
            cast(Sequence[object], processed_assets) if isinstance(processed_assets, Sequence) else []
        ),
    }


def main() -> None:
    registry = load_validation_registry()
    document_profile_id = os.environ.get("DOCXAI_REAL_DOCUMENT_PROFILE", "lietaer-core").strip() or "lietaer-core"
    requested_run_profile_id = os.environ.get("DOCXAI_REAL_DOCUMENT_RUN_PROFILE", "").strip() or None
    document_profile = registry.get_document_profile(document_profile_id)
    run_profile = registry.resolve_run_profile(document_profile, requested_run_profile_id)
    repeat_count_override = os.environ.get("DOCXAI_REAL_DOCUMENT_REPEAT_COUNT_OVERRIDE", "").strip()
    run_profile = _apply_repeat_count_override(run_profile, repeat_count_override)
    source_path = document_profile.resolved_source_path(PROJECT_ROOT)
    artifact_root = REAL_DOCUMENT_ARTIFACT_ROOT
    if run_profile.repeat_count > 1 and not repeat_count_override:
        _run_repeat_validation(
            document_profile=document_profile,
            run_profile=run_profile,
            source_path=source_path,
            artifact_root=artifact_root,
            requested_run_profile_id=requested_run_profile_id,
        )
        return

    artifact_root.mkdir(parents=True, exist_ok=True)
    run_id = os.environ.get("DOCXAI_REAL_DOCUMENT_FORCED_RUN_ID", "").strip() or _build_run_id(source_path)
    artifact_dir = artifact_root / "runs" / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_prefix = document_profile.artifact_prefix
    output_basename = document_profile.output_basename or f"{source_path.stem}_validated"

    for handler in app_logger.get_logger().handlers:
        if hasattr(handler, "maxBytes"):
            setattr(handler, "maxBytes", 1_000_000_000)

    report_path = artifact_dir / f"{artifact_prefix}_report.json"
    summary_path = artifact_dir / f"{artifact_prefix}_summary.txt"
    progress_path = artifact_dir / f"{artifact_prefix}_progress.json"
    markdown_artifact = artifact_dir / f"{output_basename}.md"
    docx_artifact = artifact_dir / f"{output_basename}.docx"
    latest_report_path = artifact_root / f"{artifact_prefix}_report.json"
    latest_summary_path = artifact_root / f"{artifact_prefix}_summary.txt"
    latest_progress_path = artifact_root / f"{artifact_prefix}_progress.json"
    latest_markdown_path = artifact_root / f"{output_basename}.md"
    latest_docx_path = artifact_root / f"{output_basename}.docx"
    latest_manifest_path = artifact_root / f"{artifact_prefix}_latest.json"

    progress_events = []
    event_log = []
    event_queue: queue.Queue = queue.Queue()
    run_started_at_epoch_seconds = time.time()
    run_started_at_utc = datetime.now(UTC)
    tracker = ValidationProgressTracker(
        run_id=run_id,
        document_profile_id=document_profile.id,
        run_profile_id=run_profile.id,
        validation_tier=run_profile.tier,
        source_path=source_path,
        run_dir=artifact_dir,
        artifact_root=artifact_root,
        progress_path=progress_path,
        latest_progress_path=latest_progress_path,
        latest_manifest_path=latest_manifest_path,
        report_path=report_path,
        summary_path=summary_path,
        markdown_path=markdown_artifact,
        docx_path=docx_artifact,
        latest_report_path=latest_report_path,
        latest_summary_path=latest_summary_path,
        latest_markdown_path=latest_markdown_path,
        latest_docx_path=latest_docx_path,
        started_at_utc=run_started_at_utc,
    )
    tracker.start()
    tracker.emit(
        event_type="start",
        phase="startup",
        stage="Инициализация",
        detail=f"Запуск real-document валидации для профиля {document_profile.id}.",
        progress=0.0,
        metrics={"run_id": run_id},
    )
    formatting_diagnostics_before = _snapshot_formatting_diagnostics_paths()
    runtime = processing_runtime.BackgroundRuntime(event_queue, threading.Event())
    runtime_snapshot = {
        "state": {},
        "finalize": [],
        "activity": [],
        "log": [],
        "status": [],
        "image_log": [],
        "image_reset_count": 0,
    }

    def emit_prepare_progress(**payload: object) -> None:
        progress_events.append({"phase": "prepare", **payload})
        tracker.emit(
            event_type="prepare",
            phase="prepare",
            stage=str(payload.get("stage") or "Подготовка"),
            detail=str(payload.get("detail") or ""),
            progress=_as_float_or_none(payload.get("progress")),
            metrics=cast(Mapping[str, object], payload.get("metrics") or {}),
        )

    def emit_runtime_event(event: object) -> None:
        if isinstance(event, SetProcessingStatusEvent):
            payload = event.payload
            tracker.emit(
                event_type="status",
                phase="process",
                stage=str(payload.get("stage") or "Обработка"),
                detail=str(payload.get("detail") or ""),
                progress=_as_float_or_none(payload.get("progress")),
                metrics={
                    key: payload.get(key)
                    for key in ("current_block", "block_count", "target_chars", "context_chars")
                    if payload.get(key) is not None
                },
            )
        elif isinstance(event, FinalizeProcessingStatusEvent):
            tracker.emit(
                event_type="finalize",
                phase="process",
                stage=event.stage,
                detail=event.detail,
                progress=event.progress,
            )
        elif isinstance(event, AppendLogEvent):
            status = str(event.payload.get("status") or "")
            if status in {"WARN", "ERROR", "DONE"}:
                tracker.emit(
                    event_type="log",
                    phase="process",
                    stage=status,
                    detail=str(event.payload.get("details") or status),
                    metrics={
                        key: event.payload.get(key)
                        for key in ("block_index", "block_count", "target_chars", "context_chars")
                        if event.payload.get(key) is not None
                    },
                )

    runtime_monitor_stop = threading.Event()

    def runtime_monitor_worker() -> None:
        while True:
            if runtime_monitor_stop.is_set() and event_queue.empty():
                return
            try:
                event = event_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            _apply_runtime_event(event, runtime_snapshot)
            emit_runtime_event(event)

    runtime_monitor_thread = threading.Thread(
        target=runtime_monitor_worker,
        name="lietaer-validation-runtime-monitor",
        daemon=True,
    )
    runtime_monitor_thread.start()

    source_bytes = b""
    source_docx_bytes = b""
    app_config = None
    app_config_dict: dict[str, object] = {}
    runtime_resolution = None
    prepared = None
    result = "not_started"
    exception_payload = None

    def log_event_capture(level, event_id, message, **context):
        event_log.append(
            {
                "level": level,
                "event_id": event_id,
                "message": message,
                "context": context,
            }
        )
        if event_id == "block_completed":
            block_index = context.get("block_index")
            block_count = context.get("block_count")
            progress_value = None
            if isinstance(block_index, int) and isinstance(block_count, int) and block_count > 0:
                progress_value = block_index / block_count
            tracker.emit(
                event_type="milestone",
                phase="process",
                stage="Блок завершён",
                detail=f"Блок {block_index} из {block_count} завершён успешно.",
                progress=progress_value,
                metrics={
                    "current_block": block_index,
                    "block_count": block_count,
                    "output_ratio": context.get("output_ratio"),
                },
            )
        elif event_id == "block_rejected":
            tracker.emit(
                event_type="warning",
                phase="process",
                stage="Блок отклонён",
                detail=str(context.get("output_classification") or message),
                metrics={
                    "current_block": context.get("block_index"),
                    "block_count": context.get("block_count"),
                },
            )
        elif event_id == "formatting_diagnostics_artifacts_detected":
            tracker.emit(
                event_type="warning",
                phase="assemble",
                stage="Formatting diagnostics",
                detail="Сохранены formatting diagnostics artifacts для текущего прогона.",
                metrics={"job_count": len(list(context.get("artifact_paths") or []))},
            )

    try:
        source_bytes = source_path.read_bytes()
        tracker.emit(
            event_type="source",
            phase="startup",
            stage="Исходный документ загружен",
            detail=f"Прочитан {source_path.name}.",
            progress=0.02,
            metrics={"target_chars": len(source_bytes)},
        )
        app_config = load_app_config()
        runtime_resolution = resolve_runtime_resolution(app_config, run_profile)
        app_config_dict = apply_runtime_resolution_to_app_config(app_config, runtime_resolution)
        tracker.set_manifest_context(
            runtime_config=runtime_resolution.effective.to_dict(),
            runtime_overrides=runtime_resolution.overrides,
        )
        tracker.emit(
            event_type="config",
            phase="startup",
            stage="Конфигурация загружена",
            detail=(
                f"Модель {runtime_resolution.effective.model}, "
                f"chunk_size={runtime_resolution.effective.chunk_size}, tier={run_profile.tier}."
            ),
            progress=0.05,
            metrics={"job_count": 0},
        )
        validation_service = processing_service.clone_processing_service(
            log_event_fn=log_event_capture,
        )
        result, prepared = validation_service.run_prepared_background_document(
            uploaded_file=UploadedFileStub(source_path.name, source_bytes),
            chunk_size=runtime_resolution.effective.chunk_size,
            image_mode=runtime_resolution.effective.image_mode,
            keep_all_image_variants=runtime_resolution.effective.keep_all_image_variants,
            app_config=app_config_dict,
            model=runtime_resolution.effective.model,
            max_retries=runtime_resolution.effective.max_retries,
            prepare_progress_callback=emit_prepare_progress,
            processing_progress_callback=lambda **payload: progress_events.append({"phase": "process", **payload}),
            runtime=runtime,
        )
        source_docx_bytes = prepared.uploaded_file_bytes
        tracker.emit(
            event_type="prepared",
            phase="prepare",
            stage="Подготовка завершена",
            detail="План обработки собран, запускаю pipeline.",
            progress=0.2,
            metrics={
                "job_count": len(prepared.jobs),
                "target_chars": len(prepared.source_text),
            },
        )
    except Exception as exc:
        exception_payload = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        result = "failed"
        tracker.emit(
            event_type="exception",
            phase="failed",
            stage="Исключение в валидаторе",
            detail=str(exc),
        )
    finally:
        runtime_monitor_stop.set()
        runtime_monitor_thread.join(timeout=3.0)

    drain_runtime_events(event_queue, runtime_snapshot, on_event=emit_runtime_event)

    state = runtime_snapshot.get("state", {})
    final_markdown = str(state.get("latest_markdown") or "")
    latest_docx_bytes = state.get("latest_docx_bytes")
    last_error = str(state.get("last_error") or "") or str((exception_payload or {}).get("message") or "")
    source_chars = len(prepared.source_text) if prepared is not None else 0
    final_markdown_chars = len(final_markdown)
    output_ratio = round(final_markdown_chars / max(source_chars, 1), 3)

    block_completed_events = [
        event for event in event_log if event.get("event_id") == "block_completed"
    ]
    block_rejected_events = [
        event for event in event_log if event.get("event_id") == "block_rejected"
    ]
    block_output_ratios = [
        event.get("context", {}).get("output_ratio")
        for event in block_completed_events
        if isinstance(event.get("context", {}).get("output_ratio"), (int, float))
    ]

    openable_output = False
    output_paragraphs = 0
    output_inline_shapes = 0
    output_visible_text_chars = 0
    output_contains_placeholder_markup = False

    markdown_artifact_path: Path | None = None
    docx_artifact_path: Path | None = None

    if final_markdown:
        markdown_artifact.write_text(final_markdown, encoding="utf-8")
        markdown_artifact_path = markdown_artifact

    if isinstance(latest_docx_bytes, (bytes, bytearray)) and latest_docx_bytes:
        latest_docx_bytes = bytes(latest_docx_bytes)
        docx_artifact.write_bytes(latest_docx_bytes)
        docx_artifact_path = docx_artifact
        try:
            output_doc = Document(BytesIO(latest_docx_bytes))
            openable_output = True
            output_paragraphs = len(output_doc.paragraphs)
            output_inline_shapes = len(output_doc.inline_shapes)
            output_visible_text_chars = len(
                "\n".join(paragraph.text for paragraph in output_doc.paragraphs)
            )
            output_contains_placeholder_markup = (
                "[[DOCX_IMAGE_" in output_doc._element.xml
            )
        except Exception:
            openable_output = False

    formatting_diagnostics_after = _snapshot_formatting_diagnostics_paths()
    snapshot_discovered_paths = _collect_new_formatting_diagnostics_paths(
        formatting_diagnostics_before,
        formatting_diagnostics_after,
    )
    formatting_diagnostics_paths = _extract_run_formatting_diagnostics_paths(event_log)
    formatting_diagnostics_discovery_source = None
    if snapshot_discovered_paths:
        formatting_diagnostics_paths = snapshot_discovered_paths
        formatting_diagnostics_payloads = _load_formatting_diagnostics_payloads(
            formatting_diagnostics_paths
        )
        formatting_diagnostics_discovery_source = "snapshot_diff"
    elif formatting_diagnostics_paths:
        formatting_diagnostics_payloads = _load_formatting_diagnostics_payloads(
            formatting_diagnostics_paths
        )
        formatting_diagnostics_discovery_source = "event_log"
    else:
        formatting_diagnostics_paths, formatting_diagnostics_payloads = _load_recent_formatting_diagnostics(
            run_started_at_epoch_seconds
        )
        formatting_diagnostics_discovery_source = "recent_scan"

    if not snapshot_discovered_paths and formatting_diagnostics_discovery_source != "event_log":
        formatting_diagnostics_payloads = _load_formatting_diagnostics_payloads(formatting_diagnostics_paths)

    run_finished_at_epoch_seconds = time.time()
    run_finished_at_utc = datetime.now(UTC)
    run_duration_seconds = round(run_finished_at_epoch_seconds - run_started_at_epoch_seconds, 3)
    result = "failed" if exception_payload is not None else result

    preparation_payload = {
        "uploaded_filename": prepared.uploaded_filename if prepared is not None else source_path.name,
        "uploaded_file_token": prepared.uploaded_file_token if prepared is not None else None,
        "paragraph_count": len(prepared.paragraphs) if prepared is not None else None,
        "image_count": len(prepared.image_assets) if prepared is not None else None,
        "job_count": len(prepared.jobs) if prepared is not None else None,
        "source_chars": source_chars,
        "cached": prepared.preparation_cached if prepared is not None else None,
        "elapsed_seconds": round(prepared.preparation_elapsed_seconds, 3) if prepared is not None else None,
    }

    report = {
        "run": {
            "run_id": run_id,
            "started_at_utc": run_started_at_utc.isoformat(),
            "finished_at_utc": run_finished_at_utc.isoformat(),
            "duration_seconds": run_duration_seconds,
            "document_profile_id": document_profile.id,
            "run_profile_id": run_profile.id,
            "validation_tier": run_profile.tier,
            "repeat_count": run_profile.repeat_count,
            "artifact_root": _path_for_report(artifact_root),
            "artifact_dir": _path_for_report(artifact_dir),
            "environment": _build_environment_snapshot(),
        },
        "document_profile_id": document_profile.id,
        "run_profile_id": run_profile.id,
        "validation_tier": run_profile.tier,
        "source_document_path": _path_for_report(source_path),
        "source_file": _path_for_report(source_path),
        "artifact_dir": _path_for_report(artifact_dir),
        "progress_path": _path_for_report(progress_path),
        "result": result,
        "runtime_config": _build_report_runtime_config(runtime_resolution),
        "preparation": preparation_payload,
        "runtime": runtime_snapshot,
        "image_forensics": _build_image_forensics_report(prepared, runtime_snapshot),
        "last_error": last_error,
        "exception": exception_payload,
        "failure_classification": None,
        "signals": {
            "heading_only_output_detected": is_heading_only_markdown(final_markdown),
            "heading_only_rejection_logged": bool(block_rejected_events),
            "silent_text_loss_suspected": bool(final_markdown.strip()) and output_ratio < 0.6,
            "output_ratio_vs_source_text": output_ratio,
            "min_block_output_ratio": min(block_output_ratios) if block_output_ratios else None,
            "max_block_output_ratio": max(block_output_ratios) if block_output_ratios else None,
            "image_reset_emitted": runtime_snapshot.get("image_reset_count", 0),
        },
        "output_artifacts": {
            "markdown_path": _path_for_report(markdown_artifact_path),
            "docx_path": _path_for_report(docx_artifact_path),
            "output_docx_openable": openable_output,
            "output_paragraphs": output_paragraphs,
            "output_inline_shapes": output_inline_shapes,
            "output_visible_text_chars": output_visible_text_chars,
            "output_contains_placeholder_markup": output_contains_placeholder_markup,
            "report_json": _path_for_report(report_path),
            "summary_txt": _path_for_report(summary_path),
            "latest_report_json": _path_for_report(latest_report_path),
            "latest_summary_txt": _path_for_report(latest_summary_path),
            "latest_markdown_path": _path_for_report(latest_markdown_path) if markdown_artifact_path is not None else None,
            "latest_docx_path": _path_for_report(latest_docx_path) if docx_artifact_path is not None else None,
            "latest_manifest_json": _path_for_report(latest_manifest_path),
        },
        "formatting_diagnostics_paths": [_path_for_report(Path(path)) for path in formatting_diagnostics_paths],
        "formatting_diagnostics_discovery": {
            "source": formatting_diagnostics_discovery_source,
            "baseline_count": len(formatting_diagnostics_before),
            "after_count": len(formatting_diagnostics_after),
            "new_count": len(snapshot_discovered_paths),
        },
        "formatting_diagnostics": formatting_diagnostics_payloads,
        "progress_events_tail": progress_events[-12:],
        "event_log": event_log[-25:],
        "image_log_tail": runtime_snapshot.get("image_log", [])[-25:],
    }
    report["failure_classification"] = classify_failure(report)
    report["acceptance"] = evaluate_lietaer_acceptance(
        report,
        source_docx_bytes=source_docx_bytes,
        output_docx_bytes=bytes(latest_docx_bytes) if isinstance(latest_docx_bytes, (bytes, bytearray)) else None,
        mismatch_threshold=document_profile.max_unmapped_source_paragraphs,
    )
    sanitized_report = sanitize_for_json(report)
    final_status = "completed" if bool(report["acceptance"]["passed"]) and result == "succeeded" else "failed"

    summary_lines = [
        f"run_id={run_id}",
        f"document_profile_id={document_profile.id}",
        f"run_profile_id={run_profile.id}",
        f"validation_tier={run_profile.tier}",
        f"status={final_status}",
        f"run_started_at_utc={run_started_at_utc.isoformat()}",
        f"run_finished_at_utc={run_finished_at_utc.isoformat()}",
        f"run_duration_seconds={run_duration_seconds}",
        f"source={_path_for_report(source_path)}",
        f"artifact_dir={_path_for_report(artifact_dir)}",
        f"artifact_root={_path_for_report(artifact_root)}",
        f"progress_json={_path_for_report(progress_path)}",
        f"result={report['result']}",
        f"failure_classification={report['failure_classification']}",
        f"runtime_overrides={json.dumps(cast(Mapping[str, object], report['runtime_config']).get('overrides') or {}, ensure_ascii=False, sort_keys=True)}",
        f"paragraph_count={report['preparation']['paragraph_count']}",
        f"image_count={report['preparation']['image_count']}",
        f"job_count={report['preparation']['job_count']}",
        f"source_chars={report['preparation']['source_chars']}",
        f"final_markdown_chars={final_markdown_chars}",
        f"output_ratio_vs_source_text={report['signals']['output_ratio_vs_source_text']}",
        f"min_block_output_ratio={report['signals']['min_block_output_ratio']}",
        f"heading_only_output_detected={report['signals']['heading_only_output_detected']}",
        f"heading_only_rejection_logged={report['signals']['heading_only_rejection_logged']}",
        f"silent_text_loss_suspected={report['signals']['silent_text_loss_suspected']}",
        f"image_reset_emitted={report['signals']['image_reset_emitted']}",
        f"output_docx_openable={report['output_artifacts']['output_docx_openable']}",
        f"output_inline_shapes={report['output_artifacts']['output_inline_shapes']}",
        f"output_contains_placeholder_markup={report['output_artifacts']['output_contains_placeholder_markup']}",
        f"formatting_diagnostics_count={len(formatting_diagnostics_payloads)}",
        f"formatting_diagnostics_discovery_source={formatting_diagnostics_discovery_source}",
        f"acceptance_passed={report['acceptance']['passed']}",
        f"acceptance_failed_checks={','.join(_as_string_list(cast(Mapping[str, object], report['acceptance']).get('failed_checks')))}",
        f"last_error={last_error}",
        f"markdown_path={report['output_artifacts']['markdown_path']}",
        f"docx_path={report['output_artifacts']['docx_path']}",
        f"latest_manifest_json={report['output_artifacts']['latest_manifest_json']}",
        f"python_executable={report['run']['environment']['python_executable']}",
        f"python_version={report['run']['environment']['python_version']}",
        f"pythonpath={report['run']['environment']['pythonpath']}",
        f"virtual_env={report['run']['environment']['virtual_env']}",
        f"workspace_venv_exists={report['run']['environment']['workspace_venv_exists']}",
        f"workspace_venv_win_exists={report['run']['environment']['workspace_venv_win_exists']}",
        f"is_wsl={report['run']['environment']['is_wsl']}",
        f"git_head={report['run']['environment']['git_head']}",
    ]
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    report_path.write_text(
        json.dumps(sanitized_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_latest_alias_artifacts(
        report_path=report_path,
        summary_path=summary_path,
        markdown_artifact=markdown_artifact_path,
        docx_artifact=docx_artifact_path,
        latest_report_path=latest_report_path,
        latest_summary_path=latest_summary_path,
        latest_markdown_path=latest_markdown_path if markdown_artifact_path is not None else None,
        latest_docx_path=latest_docx_path if docx_artifact_path is not None else None,
        latest_manifest_path=latest_manifest_path,
        run_id=run_id,
        run_dir=artifact_dir,
        manifest_payload=cast(Mapping[str, object], tracker._build_manifest_payload_locked()),
    )
    tracker.finalize(
        status=final_status,
        result=str(report["result"]),
        acceptance_passed=bool(report["acceptance"]["passed"]),
        failure_classification=cast(str | None, report["failure_classification"]),
        last_error=last_error,
        detail=(
            f"Acceptance={'passed' if report['acceptance']['passed'] else 'failed'}; report={_path_for_report(report_path)}"
        ),
    )
    tracker.stop()
    _print_terminal_completion_summary(report=cast(Mapping[str, object], report), final_status=final_status)
    if not bool(report["acceptance"]["passed"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
