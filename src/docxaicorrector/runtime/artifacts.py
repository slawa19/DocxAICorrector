import json
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from docxaicorrector.core.constants import JOB_RESULT_REGISTRY_DIR, SEGMENT_RESULT_REGISTRY_DIR, STRUCTURE_MANIFESTS_DIR, UI_RESULT_ARTIFACTS_DIR
from docxaicorrector.runtime.artifact_retention import (
    STRUCTURE_MANIFESTS_MAX_AGE_SECONDS,
    STRUCTURE_MANIFESTS_MAX_COUNT,
    prune_artifact_dir,
    UI_RESULT_ARTIFACTS_MAX_AGE_SECONDS,
    UI_RESULT_ARTIFACTS_MAX_COUNT,
    prune_ui_result_artifact_groups,
)


class AppReadyMarkerWriter:
    def __init__(self, *, path: Path, freshness_window_seconds: float = 15.0, time_fn=None):
        self._path = path
        self._freshness_window_seconds = float(freshness_window_seconds)
        self._time_fn = time_fn or time.time
        self._lock = threading.Lock()
        self._last_write_monotonic = 0.0

    def mark_ready(self) -> bool:
        now = float(self._time_fn())
        with self._lock:
            if self._last_write_monotonic and (now - self._last_write_monotonic) < self._freshness_window_seconds:
                return False
            self._last_write_monotonic = now

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(f"{now:.6f}\n", encoding="utf-8")
        return True


def _sanitize_artifact_stem(value: str) -> str:
    sanitized = "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value.strip())
    compacted = "_".join(part for part in sanitized.split("_") if part)
    return compacted[:80] or "document"


def _build_ui_result_stem(source_name: str, *, created_at: float | None = None) -> str:
    source_path = Path(source_name)
    stem = _sanitize_artifact_stem(source_path.stem)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() if created_at is None else created_at))
    return f"{timestamp}_{stem}.result"


def _truncate_review_text(value: object, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _build_formatting_review_text(
    *,
    source_name: str,
    quality_warning: Mapping[str, object] | None,
    created_at: float | None,
) -> str:
    timestamp = datetime.fromtimestamp(time.time() if created_at is None else created_at).isoformat(timespec="seconds")
    items = list(quality_warning.get("formatting_review_items") or []) if quality_warning else []
    review_count = int((quality_warning or {}).get("formatting_review_required_count") or len(items) or 0)
    fix_count = sum(
        int(item.get("aggregate_count") if "aggregate_count" in item else item.get("count", 1))
        for item in items
        if isinstance(item, Mapping) and str(item.get("severity") or "review") == "fix"
    )
    manual_review_count = max(review_count - fix_count, 0)
    lines = [
        f"Проверка оформления — {Path(source_name).name or 'document'}",
        f"Дата: {timestamp}",
        f"Итог: {fix_count} на правку / {manual_review_count} на проверку",
        "",
        "Что значат пометки: [ПРОВЕРКА] — желательно открыть место в DOCX и проверить оформление.",
        "",
        "-" * 70,
    ]
    if not items:
        lines.extend(
            [
                "[OK] Расхождений оформления для ручной проверки не найдено.",
                "-" * 70,
                "Всего: ПРАВКА 0 · ПРОВЕРКА 0 · КРИТ 0",
            ]
        )
        return "\n".join(lines) + "\n"

    for index, item in enumerate(items, start=1):
        if not isinstance(item, Mapping):
            continue
        marker = "[ПРАВКА]" if str(item.get("severity") or "review") == "fix" else "[ПРОВЕРКА]"
        label = _truncate_review_text(item.get("label") or "Абзац требует проверки оформления", limit=100)
        sample = item.get("sample")
        sample_text = ""
        if isinstance(sample, Mapping):
            sample_text = _truncate_review_text(sample.get("text"), limit=180)
        count = int(item.get("aggregate_count") if "aggregate_count" in item else item.get("count", 1))
        lines.append(f"{marker} {label}")
        if sample_text:
            lines.append(f"  В выводе: «{sample_text}»")
        elif count > 1:
            lines.append(f"  Количество: {count}")
        lines.append("  Как проверить: найдите этот фрагмент в DOCX и убедитесь, что стиль и позиция сохранены.")
        if index != len(items):
            lines.append("")
    lines.extend(
        [
            "-" * 70,
            f"Всего: ПРАВКА {fix_count} · ПРОВЕРКА {manual_review_count} · КРИТ 0",
        ]
    )
    return "\n".join(lines) + "\n"


def write_ui_result_artifacts(
    *,
    source_name: str,
    markdown_text: str,
    docx_bytes: bytes,
    narration_text: str | None = None,
    quality_warning: Mapping[str, object] | None = None,
    assembly_mode: str | None = None,
    selected_segment_count: int | None = None,
    result_manifest: Mapping[str, object] | None = None,
    output_dir: Path = UI_RESULT_ARTIFACTS_DIR,
    created_at: float | None = None,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_stem = _build_ui_result_stem(source_name, created_at=created_at)
    markdown_path = output_dir / f"{artifact_stem}.md"
    docx_path = output_dir / f"{artifact_stem}.docx"
    tts_path = output_dir / f"{artifact_stem}.tts.txt"
    meta_path = output_dir / f"{artifact_stem}.meta.json"
    manifest_path = output_dir / f"{artifact_stem}.manifest.json"
    formatting_review_path = output_dir / f"{artifact_stem}.formatting_review.txt"

    meta_payload: dict[str, object] = {"version": 1}
    if assembly_mode is not None:
        meta_payload["assembly_mode"] = assembly_mode
    if selected_segment_count is not None:
        meta_payload["selected_segment_count"] = selected_segment_count
    if quality_warning:
        meta_payload["quality_warning"] = quality_warning
    write_meta = len(meta_payload) > 1

    markdown_path.write_text(markdown_text, encoding="utf-8")
    try:
        docx_path.write_bytes(docx_bytes)
        if narration_text is not None:
            tts_path.write_text(narration_text, encoding="utf-8")
        if quality_warning:
            formatting_review_path.write_text(
                _build_formatting_review_text(
                    source_name=source_name,
                    quality_warning=quality_warning,
                    created_at=created_at,
                ),
                encoding="utf-8",
            )
        if write_meta:
            meta_path.write_text(
                json.dumps(meta_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        if result_manifest is not None:
            manifest_path.write_text(
                json.dumps(_to_jsonable(result_manifest), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    except OSError:
        try:
            if markdown_path.exists():
                markdown_path.unlink()
            if docx_path.exists():
                docx_path.unlink()
            if tts_path.exists():
                tts_path.unlink()
            if meta_path.exists():
                meta_path.unlink()
            if manifest_path.exists():
                manifest_path.unlink()
            if formatting_review_path.exists():
                formatting_review_path.unlink()
        except OSError:
            pass
        raise

    prune_ui_result_artifact_groups(
        target_dir=output_dir,
        max_age_seconds=UI_RESULT_ARTIFACTS_MAX_AGE_SECONDS,
        max_count=UI_RESULT_ARTIFACTS_MAX_COUNT,
        emit_log=False,
    )
    artifact_paths = {
        "markdown_path": str(markdown_path),
        "docx_path": str(docx_path),
    }
    if narration_text is not None:
        artifact_paths["tts_text_path"] = str(tts_path)
    if write_meta:
        artifact_paths["metadata_path"] = str(meta_path)
    if quality_warning:
        artifact_paths["formatting_review_path"] = str(formatting_review_path)
    if result_manifest is not None:
        artifact_paths["manifest_path"] = str(manifest_path)
    return artifact_paths


def write_structure_manifest_artifact(
    *,
    source_name: str,
    manifest_payload: Mapping[str, object],
    output_dir: Path = STRUCTURE_MANIFESTS_DIR,
    created_at: float | None = None,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() if created_at is None else created_at))
    source_path = Path(source_name)
    stem = _sanitize_artifact_stem(source_path.stem)
    manifest_path = output_dir / f"{timestamp}_{stem}.segments.json"
    manifest_path.write_text(
        json.dumps(_to_jsonable(manifest_payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    prune_artifact_dir(
        target_dir=output_dir,
        max_age_seconds=STRUCTURE_MANIFESTS_MAX_AGE_SECONDS,
        max_count=STRUCTURE_MANIFESTS_MAX_COUNT,
        glob="*.json",
        emit_log=False,
    )
    return str(manifest_path)


def write_segment_result_registry(
    *,
    records: Sequence[Mapping[str, object]],
    output_dir: Path = SEGMENT_RESULT_REGISTRY_DIR,
) -> dict[str, str]:
    persisted_paths: dict[str, str] = {}
    for record in records:
        prepared_source_key = str(record.get("prepared_source_key") or "").strip()
        structure_fingerprint = str(record.get("structure_fingerprint") or "").strip()
        segment_id = str(record.get("segment_id") or "").strip()
        if not prepared_source_key or not structure_fingerprint or not segment_id:
            continue
        target_dir = (
            output_dir
            / _sanitize_artifact_stem(prepared_source_key)
            / _sanitize_artifact_stem(structure_fingerprint)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = target_dir / f"{_sanitize_artifact_stem(segment_id)}.segment-result.json"
        artifact_path.write_text(
            json.dumps(_to_jsonable(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        persisted_paths[segment_id] = str(artifact_path)
    return persisted_paths


def write_job_result_registry(
    *,
    records: Sequence[Mapping[str, object]],
    output_dir: Path = JOB_RESULT_REGISTRY_DIR,
) -> dict[str, str]:
    persisted_paths: dict[str, str] = {}
    for record in records:
        prepared_source_key = str(record.get("prepared_source_key") or "").strip()
        structure_fingerprint = str(record.get("structure_fingerprint") or "").strip()
        job_id = str(record.get("job_id") or "").strip()
        if not prepared_source_key or not structure_fingerprint or not job_id:
            continue
        target_dir = (
            output_dir
            / _sanitize_artifact_stem(prepared_source_key)
            / _sanitize_artifact_stem(structure_fingerprint)
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = target_dir / f"{_sanitize_artifact_stem(job_id)}.job-result.json"
        artifact_path.write_text(
            json.dumps(_to_jsonable(record), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        persisted_paths[job_id] = str(artifact_path)
    return persisted_paths


def load_job_result_registry(
    *,
    prepared_source_key: str,
    structure_fingerprint: str,
    input_dir: Path = JOB_RESULT_REGISTRY_DIR,
) -> dict[str, dict[str, object]]:
    normalized_source_key = _sanitize_artifact_stem(prepared_source_key)
    normalized_fingerprint = _sanitize_artifact_stem(structure_fingerprint)
    if not normalized_source_key or not normalized_fingerprint:
        return {}

    target_dir = input_dir / normalized_source_key / normalized_fingerprint
    if not target_dir.exists():
        return {}

    records_by_job_id: dict[str, tuple[float, dict[str, object]]] = {}
    for artifact_path in target_dir.glob("*.job-result.json"):
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        job_id = str(payload.get("job_id") or "").strip()
        status = str(payload.get("status") or "").strip()
        if not job_id or not status:
            continue
        precedence_timestamp = _resolve_job_result_precedence_timestamp(artifact_path=artifact_path, payload=payload)
        previous = records_by_job_id.get(job_id)
        if previous is None or precedence_timestamp >= previous[0]:
            records_by_job_id[job_id] = (precedence_timestamp, payload)
    return {job_id: payload for job_id, (_, payload) in records_by_job_id.items()}


def _resolve_job_result_precedence_timestamp(*, artifact_path: Path, payload: Mapping[str, object]) -> float:
    raw_updated_at = str(payload.get("updated_at") or "").strip()
    if raw_updated_at:
        normalized_updated_at = raw_updated_at.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized_updated_at).timestamp()
        except ValueError:
            pass
    try:
        return artifact_path.stat().st_mtime
    except OSError:
        return 0.0


def _to_jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value
