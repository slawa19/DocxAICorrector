"""Quality-report retention I/O (spec 031 Cluster E).

Behaviour-preserving extraction from ``pipeline/late_phases.py``: the quality-report
output directory constants plus the age/count pruning and artifact-write helpers.
``late_phases`` re-exports these names so ``late_phases.<name>`` keeps resolving for
the test namespace and the harness importer.

There is no module-level mutable state: ``QUALITY_REPORTS_DIR`` /
``QUALITY_REPORTS_MAX_AGE_SECONDS`` / ``QUALITY_REPORTS_MAX_COUNT`` are immutable
constants. ``_write_quality_report_artifact`` reads ``QUALITY_REPORTS_DIR`` from THIS
module, so tests that redirect the output directory must patch it here.
"""

import json
import re
import time
from collections.abc import Mapping
from pathlib import Path


QUALITY_REPORTS_DIR = Path(".run") / "quality_reports"
QUALITY_REPORTS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
QUALITY_REPORTS_MAX_COUNT = 100


def _prune_quality_reports(*, target_dir: Path, now_epoch_seconds: float | None = None) -> None:
    if not target_dir.exists():
        return
    reference_now = time.time() if now_epoch_seconds is None else now_epoch_seconds
    retained: list[tuple[float, Path]] = []
    for artifact_path in target_dir.glob("*.json"):
        try:
            mtime = artifact_path.stat().st_mtime
        except OSError:
            continue
        if max(0.0, reference_now - mtime) > QUALITY_REPORTS_MAX_AGE_SECONDS:
            try:
                artifact_path.unlink()
            except OSError:
                pass
            continue
        retained.append((mtime, artifact_path))
    if len(retained) <= QUALITY_REPORTS_MAX_COUNT:
        return
    retained.sort(key=lambda item: (item[0], item[1].name))
    for _, artifact_path in retained[: len(retained) - QUALITY_REPORTS_MAX_COUNT]:
        try:
            artifact_path.unlink()
        except OSError:
            continue


def _write_quality_report_artifact(*, source_name: str, payload: Mapping[str, object]) -> str | None:
    try:
        QUALITY_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source_name or "document").strip("_") or "document"
        generated_at_epoch_ms = int(time.time() * 1000)
        artifact_path = QUALITY_REPORTS_DIR / f"{safe_name}_{generated_at_epoch_ms}.json"
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        _prune_quality_reports(target_dir=QUALITY_REPORTS_DIR)
        return str(artifact_path)
    except Exception:
        return None
