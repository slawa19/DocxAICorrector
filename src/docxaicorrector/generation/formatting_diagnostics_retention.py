import json
import logging
import re
import time
from pathlib import Path
from typing import Literal, Mapping, Sequence
from uuid import uuid4

from docxaicorrector.core.logger import log_event


FORMATTING_DIAGNOSTICS_DIR = Path(".run") / "formatting_diagnostics"
FORMATTING_DIAGNOSTICS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
FORMATTING_DIAGNOSTICS_MAX_COUNT = 100


def get_formatting_diagnostics_dir() -> Path:
    return FORMATTING_DIAGNOSTICS_DIR


def _require_nonempty_identity(value: str | None, *, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized


def _safe_filename_component(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._") or "unknown"
    return normalized[:64]


def collect_owned_formatting_diagnostics(
    *,
    run_id: str,
    source_token: str,
    diagnostics_dir: Path | None = None,
) -> list[str]:
    try:
        expected_run_id = _require_nonempty_identity(run_id, field_name="run_id")
        expected_source_token = _require_nonempty_identity(source_token, field_name="source_token")
    except ValueError:
        # An incomplete legacy context owns nothing; critically, it must not widen
        # collection to directory-wide or time-window discovery.
        return []
    target_dir = diagnostics_dir or get_formatting_diagnostics_dir()
    if not target_dir.exists():
        return []

    owned_artifacts: list[str] = []
    for artifact_path in sorted(target_dir.glob("*.json")):
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        ownership = payload.get("ownership")
        if not isinstance(ownership, dict) or ownership.get("scope") != "live":
            continue
        if ownership.get("run_id") != expected_run_id or ownership.get("source_token") != expected_source_token:
            continue
        owned_artifacts.append(str(artifact_path))
    return owned_artifacts


def write_formatting_diagnostics_artifact(
    *,
    stage: str,
    diagnostics: Mapping[str, object],
    filename_prefix: str | None = None,
    diagnostics_dir: Path | None = None,
    now_epoch_ms: int | None = None,
    scope: Literal["live", "offline"] = "offline",
    run_id: str | None = None,
    source_token: str | None = None,
) -> str | None:
    target_dir = diagnostics_dir or get_formatting_diagnostics_dir()
    generated_at_epoch_ms = int(now_epoch_ms if now_epoch_ms is not None else time.time() * 1000)
    stem = filename_prefix or stage

    try:
        if scope not in {"live", "offline"}:
            raise ValueError("scope must be 'live' or 'offline'")
        ownership: dict[str, str] = {"scope": scope}
        if scope == "live":
            ownership["run_id"] = _require_nonempty_identity(run_id, field_name="run_id")
            ownership["source_token"] = _require_nonempty_identity(source_token, field_name="source_token")
        target_dir.mkdir(parents=True, exist_ok=True)
        filename_parts = [
            _safe_filename_component(stem),
            *(
                [
                    _safe_filename_component(ownership["run_id"]),
                    _safe_filename_component(ownership["source_token"]),
                ]
                if scope == "live"
                else ["offline"]
            ),
            str(generated_at_epoch_ms),
            uuid4().hex,
        ]
        artifact_path = target_dir / f"{'_'.join(filename_parts)}.json"
        payload = {
            **dict(diagnostics),
            "stage": stage,
            "generated_at_epoch_ms": generated_at_epoch_ms,
            "ownership": ownership,
        }
        artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        prune_formatting_diagnostics(diagnostics_dir=target_dir)
        return str(artifact_path)
    except Exception as exc:
        # Fail-open (the run still succeeds without this diagnostic), but never silently:
        # a missing formatting-diagnostics artifact would otherwise look intended.
        log_event(
            logging.WARNING,
            "formatting_diagnostics_write_failed",
            "Failed to write the formatting-diagnostics artifact; continuing without it.",
            stage=stage,
            expected_dir=str(target_dir),
            scope=scope,
            run_id=run_id,
            source_token=source_token,
            error_type=type(exc).__name__,
            error=str(exc),
        )
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
