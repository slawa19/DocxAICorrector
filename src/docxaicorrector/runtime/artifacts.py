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


# Severity is the single source of truth for how an item renders and is counted:
# "fix" → [ПРАВКА] (formatting nit), "review" → [ПРОВЕРКА] (open and check),
# "defect" → [КРИТ] (content defect, e.g. a translated paragraph mapped to the wrong source).
_REVIEW_SEVERITY_MARKERS = {"fix": "[ПРАВКА]", "review": "[ПРОВЕРКА]", "defect": "[КРИТ]"}


def _review_item_severity(item: Mapping[str, object]) -> str:
    severity = str(item.get("severity") or "review")
    return severity if severity in _REVIEW_SEVERITY_MARKERS else "review"


def _review_item_count(item: Mapping[str, object]) -> int:
    value = item.get("aggregate_count") if "aggregate_count" in item else item.get("count", 1)
    if not isinstance(value, (int, float, str)):
        return 1
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 1


def _review_item_anchor_usable(item: Mapping[str, object]) -> bool:
    # FR-006: an item whose anchor holds no locatable text is flagged upstream with
    # sample.anchor_usable=False so it is counted, not printed as an empty «» row.
    sample = item.get("sample")
    return not (isinstance(sample, Mapping) and sample.get("anchor_usable") is False)


def _build_formatting_review_text(
    *,
    source_name: str,
    quality_warning: Mapping[str, object] | None,
    created_at: float | None,
) -> str:
    timestamp = datetime.fromtimestamp(time.time() if created_at is None else created_at).isoformat(timespec="seconds")
    raw_items = list(quality_warning.get("formatting_review_items") or []) if quality_warning else []
    items = [item for item in raw_items if isinstance(item, Mapping)]
    counts = {"fix": 0, "review": 0, "defect": 0}
    for item in items:
        counts[_review_item_severity(item)] += _review_item_count(item)
    totals_line = f"Всего: ПРАВКА {counts['fix']} · ПРОВЕРКА {counts['review']} · КРИТ {counts['defect']}"
    lines = [
        f"Проверка оформления — {Path(source_name).name or 'document'}",
        f"Дата: {timestamp}",
        f"Итог: {counts['fix']} на правку / {counts['review']} на проверку / {counts['defect']} критично",
        "",
        "Что значат пометки: [ПРАВКА] — оформление желательно поправить; "
        "[ПРОВЕРКА] — откройте место в DOCX и проверьте оформление; "
        "[КРИТ] — перевод мог встать не к тому абзацу, проверьте смысл.",
        "",
        "-" * 70,
    ]
    if not items:
        lines.extend(
            [
                "[OK] Расхождений оформления для ручной проверки не найдено.",
                "-" * 70,
                totals_line,
            ]
        )
        return "\n".join(lines) + "\n"

    anchored_items = [item for item in items if _review_item_anchor_usable(item)]
    anchorless_count = sum(
        _review_item_count(item) for item in items if not _review_item_anchor_usable(item)
    )

    for index, item in enumerate(anchored_items):
        severity = _review_item_severity(item)
        marker = _REVIEW_SEVERITY_MARKERS[severity]
        label = _truncate_review_text(item.get("label") or "Абзац требует проверки оформления", limit=100)
        sample = item.get("sample")
        sample_text = ""
        source_text = ""
        if isinstance(sample, Mapping):
            sample_text = _truncate_review_text(sample.get("text"), limit=180)
            source_text = _truncate_review_text(sample.get("source_text"), limit=180)
        count = _review_item_count(item)
        action_style = item.get("action_style")
        lines.append(f"{marker} {label}")
        if source_text:
            lines.append(f"  Исходный абзац: «{source_text}»")
        if sample_text:
            lines.append(f"  В выводе: «{sample_text}»")
        elif count > 1:
            lines.append(f"  Количество: {count}")
        if isinstance(action_style, str) and action_style:
            # FR-005: name the concrete manual action for a demoted structural paragraph.
            lines.append(f"  Как исправить: примените стиль «{action_style}» к этому абзацу в DOCX.")
        elif severity == "defect":
            lines.append("  Как проверить: найдите этот абзац в DOCX — перевод мог встать не к тому исходному абзацу.")
        else:
            lines.append("  Как проверить: найдите этот фрагмент в DOCX и убедитесь, что стиль и позиция сохранены.")
        if index != len(anchored_items) - 1:
            lines.append("")
    if anchorless_count > 0:
        # FR-006: unlocatable items collapse into a single count instead of empty «» rows.
        if anchored_items:
            lines.append("")
        lines.append(
            f"{anchorless_count} мест без локализуемого якоря — проверьте оформление в DOCX "
            "вручную (точный фрагмент для поиска отсутствует)."
        )
    lines.extend(
        [
            "-" * 70,
            totals_line,
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
