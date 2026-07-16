import json
import os
import threading
import time
import uuid
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

# Retention budgets for the data-bearing result registries (F26). These families
# were previously unbounded, unlike every other ``.run/`` writer in this module.
# The files live two levels deep under the family root
# (``<source_key>/<fingerprint>/<id>.json``) and are keyed by ``segment_id`` /
# ``job_id``, so re-running one document overwrites in place — the unbounded
# growth is the accumulation of stale identity leaves across documents and
# structure revisions. Pruning therefore runs family-wide with a recursive glob.
# Values mirror the long-lived 30-day structure-manifest cache (these registries
# are likewise a resume/reuse cache read by ``load_job_result_registry``); the
# count caps are set well above any single document's segment/job fan-out so a
# live run is never pruned, only historical accumulation.
SEGMENT_RESULT_REGISTRY_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
SEGMENT_RESULT_REGISTRY_MAX_COUNT = 2000
JOB_RESULT_REGISTRY_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
JOB_RESULT_REGISTRY_MAX_COUNT = 2000


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


def _new_run_id() -> str:
    """Short opaque per-run id. Isolates concurrent runs of the same source name
    that would otherwise collide within a single wall-clock second."""
    return uuid.uuid4().hex[:8]


def _build_ui_result_stem(source_name: str, *, created_at: float | None = None, run_id: str | None = None) -> str:
    source_path = Path(source_name)
    stem = _sanitize_artifact_stem(source_path.stem)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() if created_at is None else created_at))
    resolved_run_id = _sanitize_artifact_stem(run_id) if run_id else _new_run_id()
    # run_id precedes the ``.result`` boundary so retention grouping (which strips
    # the ``.result.<ext>`` suffix) keeps every file of one run in one group.
    return f"{timestamp}_{stem}_{resolved_run_id}.result"


def _atomic_write(path: Path, data: bytes | str) -> None:
    """Write to a unique temp sibling then os.replace into place, so a crash
    mid-write never leaves a truncated artifact that reads as delivered."""
    tmp_path = path.parent / f"{path.name}.tmp.{_new_run_id()}"
    try:
        if isinstance(data, bytes):
            tmp_path.write_bytes(data)
        else:
            tmp_path.write_text(data, encoding="utf-8")
        os.replace(tmp_path, path)
    except OSError:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        raise


def _atomic_write_group(entries: Sequence[tuple[Path, bytes | str]]) -> None:
    """Publish a whole artifact group near-atomically.

    Stage EVERY file to a temp sibling first (the slow, failure-prone phase), then
    os.replace them all into place (the publish phase, rename-only). If staging
    fails, nothing is published — no partial group. If the publish phase itself
    fails, already-published members are rolled back. This narrows the window in
    which a hard process crash could leave a partial group to the metadata-only
    rename phase, instead of the previous per-file scheme where a crash between the
    .md and .docx writes left a half-written group."""
    staged: list[tuple[Path, Path]] = []
    try:
        for final_path, data in entries:
            tmp_path = final_path.parent / f"{final_path.name}.tmp.{_new_run_id()}"
            if isinstance(data, bytes):
                tmp_path.write_bytes(data)
            else:
                tmp_path.write_text(data, encoding="utf-8")
            staged.append((tmp_path, final_path))
    except OSError:
        for tmp_path, _ in staged:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise

    published: list[Path] = []
    try:
        for tmp_path, final_path in staged:
            os.replace(tmp_path, final_path)
            published.append(final_path)
    except OSError:
        for final_path in published:
            try:
                final_path.unlink()
            except OSError:
                pass
        for tmp_path, _ in staged:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
        raise


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
        residual_class = ""
        if isinstance(sample, Mapping):
            sample_text = _truncate_review_text(sample.get("text"), limit=180)
            source_text = _truncate_review_text(sample.get("source_text"), limit=180)
            residual_class = str(sample.get("residual_class") or "")
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
        elif residual_class == "short_note_or_marker":
            # Softened wording: a short unmapped fragment is usually a footnote/marker, not a defect.
            lines.append("  Как проверить: похоже на сноску или маркер — найдите этот фрагмент в DOCX и проверьте оформление.")
        else:
            lines.append("  Как проверить: найдите этот фрагмент в DOCX и убедитесь, что стиль и позиция сохранены.")
        if index != len(anchored_items) - 1:
            lines.append("")
    if anchorless_count > 0:
        # FR-006: unlocatable items collapse into a single count instead of empty «» rows.
        if anchored_items:
            lines.append("")
        lines.append(
            f"Мест без локализуемого якоря: {anchorless_count} — проверьте оформление в DOCX "
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
    run_id: str | None = None,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_stem = _build_ui_result_stem(source_name, created_at=created_at, run_id=run_id)
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

    # Stage the whole group to temp, then publish (spec 023): staging/publish
    # exceptions do not leave partial groups; the hard-crash window is narrowed to
    # the rename phase (the previous per-file scheme could leave a half-written
    # group if the process died between the .md and .docx writes).
    group_entries: list[tuple[Path, bytes | str]] = [
        (markdown_path, markdown_text),
        (docx_path, docx_bytes),
    ]
    if narration_text is not None:
        group_entries.append((tts_path, narration_text))
    if quality_warning:
        group_entries.append(
            (
                formatting_review_path,
                _build_formatting_review_text(
                    source_name=source_name,
                    quality_warning=quality_warning,
                    created_at=created_at,
                ),
            )
        )
    if write_meta:
        group_entries.append((meta_path, json.dumps(meta_payload, ensure_ascii=False, indent=2)))
    if result_manifest is not None:
        group_entries.append(
            (manifest_path, json.dumps(_to_jsonable(result_manifest), ensure_ascii=False, indent=2))
        )
    _atomic_write_group(group_entries)

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
    run_id: str | None = None,
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(time.time() if created_at is None else created_at))
    source_path = Path(source_name)
    stem = _sanitize_artifact_stem(source_path.stem)
    resolved_run_id = _sanitize_artifact_stem(run_id) if run_id else _new_run_id()
    manifest_path = output_dir / f"{timestamp}_{stem}_{resolved_run_id}.segments.json"
    _atomic_write(
        manifest_path,
        json.dumps(_to_jsonable(manifest_payload), ensure_ascii=False, indent=2),
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
    # Bound family growth after publishing, mirroring the UI-result and
    # structure-manifest writers. Recursive glob prunes stale identity leaves
    # across the whole family, not just one document's segment folder.
    prune_artifact_dir(
        target_dir=output_dir,
        max_age_seconds=SEGMENT_RESULT_REGISTRY_MAX_AGE_SECONDS,
        max_count=SEGMENT_RESULT_REGISTRY_MAX_COUNT,
        glob="**/*.segment-result.json",
        emit_log=False,
    )
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
    # Bound family growth after publishing, mirroring the UI-result and
    # structure-manifest writers. Recursive glob prunes stale identity leaves
    # across the whole family, not just one document's job folder.
    prune_artifact_dir(
        target_dir=output_dir,
        max_age_seconds=JOB_RESULT_REGISTRY_MAX_AGE_SECONDS,
        max_count=JOB_RESULT_REGISTRY_MAX_COUNT,
        glob="**/*.job-result.json",
        emit_log=False,
    )
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
