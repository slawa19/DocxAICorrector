import json
import time
from pathlib import Path
from typing import Mapping, Sequence


FORMATTING_DIAGNOSTICS_DIR = Path(".run") / "formatting_diagnostics"
FORMATTING_DIAGNOSTICS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
FORMATTING_DIAGNOSTICS_MAX_COUNT = 100


def get_formatting_diagnostics_dir() -> Path:
    return FORMATTING_DIAGNOSTICS_DIR


def collect_recent_formatting_diagnostics(*, since_epoch_seconds: float, diagnostics_dir: Path | None = None) -> list[str]:
    target_dir = diagnostics_dir or get_formatting_diagnostics_dir()
    if not target_dir.exists():
        return []

    recent_artifacts: list[str] = []
    threshold = max(0.0, since_epoch_seconds - 1.0)
    for artifact_path in sorted(target_dir.glob("*.json")):
        try:
            if artifact_path.stat().st_mtime >= threshold:
                recent_artifacts.append(str(artifact_path))
        except OSError:
            continue
    return recent_artifacts


def write_formatting_diagnostics_artifact(
    *,
    stage: str,
    diagnostics: Mapping[str, object],
    filename_prefix: str | None = None,
    diagnostics_dir: Path | None = None,
    now_epoch_ms: int | None = None,
) -> str | None:
    target_dir = diagnostics_dir or get_formatting_diagnostics_dir()
    generated_at_epoch_ms = int(now_epoch_ms if now_epoch_ms is not None else time.time() * 1000)
    stem = filename_prefix or stage

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = target_dir / f"{stem}_{generated_at_epoch_ms}.json"
        payload = {
            "stage": stage,
            "generated_at_epoch_ms": generated_at_epoch_ms,
            **dict(diagnostics),
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_formatting_diagnostics(diagnostics_dir=target_dir)
        return str(artifact_path)
    except Exception:
        return None


def prune_formatting_diagnostics(
    *,
    diagnostics_dir: Path | None = None,
    now_epoch_seconds: float | None = None,
    max_age_seconds: int = FORMATTING_DIAGNOSTICS_MAX_AGE_SECONDS,
    max_count: int = FORMATTING_DIAGNOSTICS_MAX_COUNT,
) -> list[str]:
    target_dir = diagnostics_dir or get_formatting_diagnostics_dir()
    if not target_dir.exists():
        return []

    reference_now = time.time() if now_epoch_seconds is None else now_epoch_seconds
    retained: list[tuple[float, Path]] = []
    pruned_paths: list[str] = []

    for artifact_path in target_dir.glob("*.json"):
        try:
            mtime = artifact_path.stat().st_mtime
        except OSError:
            continue

        age_seconds = max(0.0, reference_now - mtime)
        if max_age_seconds >= 0 and age_seconds > max_age_seconds:
            try:
                artifact_path.unlink()
                pruned_paths.append(str(artifact_path))
            except OSError:
                pass
            continue

        retained.append((mtime, artifact_path))

    if max_count >= 0 and len(retained) > max_count:
        retained.sort(key=lambda item: (item[0], item[1].name))
        overflow = len(retained) - max_count
        for _, artifact_path in retained[:overflow]:
            try:
                artifact_path.unlink()
                pruned_paths.append(str(artifact_path))
            except OSError:
                continue

    return pruned_paths


def load_formatting_diagnostics_payloads(artifact_paths: Sequence[str]) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []

    for artifact_path in artifact_paths:
        try:
            payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)

    return payloads
