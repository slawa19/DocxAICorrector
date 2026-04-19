"""Shared retention/pruning helper for runtime artifacts under ``.run/``.

This module centralizes the policy for bounded-growth directories that live under
``.run/``. Writers in :mod:`document`, :mod:`preparation`,
:mod:`structure_validation` и :mod:`formatting_diagnostics_retention` invoke
:func:`prune_artifact_dir` right after persisting a new artifact so that each
family can stay within an explicit age/count budget.

The helper intentionally stays local, synchronous and filesystem-only — there
are no background daemons and no I/O outside the target directory. Pruning is
``no-op`` if the directory does not yet exist.

Policy constants for each family are defined here as the single source of
truth. If a new artifact family is introduced, add its constants in this module
and call :func:`prune_artifact_dir` from the writer. See
``docs/LOGGING_AND_ARTIFACT_RETENTION.md`` for the canonical contract.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path


DEFAULT_JSON_GLOB = "*.json"

# Formatting diagnostics live under ``formatting_diagnostics_retention.py``
# but share the same policy shape. Values here mirror existing runtime
# defaults and are exposed for cross-reference only.
FORMATTING_DIAGNOSTICS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
FORMATTING_DIAGNOSTICS_MAX_COUNT = 100

# Paragraph boundary normalization reports (``document.py``).
PARAGRAPH_BOUNDARY_REPORTS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
PARAGRAPH_BOUNDARY_REPORTS_MAX_COUNT = 300

# Relation normalization reports (``document.py``).
RELATION_NORMALIZATION_REPORTS_MAX_AGE_SECONDS = 7 * 24 * 60 * 60
RELATION_NORMALIZATION_REPORTS_MAX_COUNT = 300

# Paragraph boundary AI review artifacts (``document.py``). Kept longer because
# they are produced only when the AI review mode is explicitly enabled.
PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_AGE_SECONDS = 14 * 24 * 60 * 60
PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_COUNT = 200

# Structure recognition debug artifacts (``preparation.py``).
STRUCTURE_MAPS_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
STRUCTURE_MAPS_MAX_COUNT = 200

# Structure validation gate reports (``structure_validation.py``).
STRUCTURE_VALIDATION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
STRUCTURE_VALIDATION_MAX_COUNT = 200


def prune_artifact_dir(
    *,
    target_dir: Path,
    max_age_seconds: int | None,
    max_count: int | None,
    glob: str = DEFAULT_JSON_GLOB,
    now_epoch_seconds: float | None = None,
    emit_log: bool = True,
) -> list[str]:
    """Prune files in ``target_dir`` matching ``glob`` by age and count.

    Arguments:
        target_dir: absolute or project-relative path to the artifact family dir.
        max_age_seconds: files older than this threshold are deleted. ``None``
            or a negative value disables the age filter.
        max_count: at most this many files are retained after age pruning.
            ``None`` or a negative value disables the count cap. When enforced,
            the oldest files (by mtime) are removed first.
        glob: glob pattern applied inside ``target_dir``.
        now_epoch_seconds: override of ``time.time()`` for deterministic tests.
        emit_log: whether to emit a DEBUG ``artifact_pruned`` event when at
            least one file was removed. Disable in hot paths that already own
            their own logging.

    Returns:
        List of absolute path strings that were removed. Empty if nothing was
        pruned or the directory does not exist.
    """
    if not target_dir.exists() or not target_dir.is_dir():
        return []

    reference_now = time.time() if now_epoch_seconds is None else float(now_epoch_seconds)
    retained: list[tuple[float, Path]] = []
    pruned_paths: list[str] = []

    for artifact_path in target_dir.glob(glob):
        if not artifact_path.is_file():
            continue
        try:
            mtime = artifact_path.stat().st_mtime
        except OSError:
            continue

        age_seconds = max(0.0, reference_now - mtime)
        if max_age_seconds is not None and max_age_seconds >= 0 and age_seconds > max_age_seconds:
            try:
                artifact_path.unlink()
                pruned_paths.append(str(artifact_path))
            except OSError:
                pass
            continue

        retained.append((mtime, artifact_path))

    if max_count is not None and max_count >= 0 and len(retained) > max_count:
        retained.sort(key=lambda item: (item[0], item[1].name))
        overflow = len(retained) - max_count
        for _, artifact_path in retained[:overflow]:
            try:
                artifact_path.unlink()
                pruned_paths.append(str(artifact_path))
            except OSError:
                continue

    if emit_log and pruned_paths:
        _emit_prune_event(
            target_dir=target_dir,
            pruned_paths=pruned_paths,
            max_age_seconds=max_age_seconds,
            max_count=max_count,
        )

    return pruned_paths


def _emit_prune_event(
    *,
    target_dir: Path,
    pruned_paths: list[str],
    max_age_seconds: int | None,
    max_count: int | None,
) -> None:
    # Deferred import avoids a hard dependency loop if the logger itself is
    # initialised later in the startup sequence; the logger module is cheap to
    # import but keeping this lazy mirrors other optional-integration helpers
    # in this codebase.
    try:
        from logger import log_event

        log_event(
            logging.DEBUG,
            "artifact_pruned",
            "Очистка runtime-артефактов выполнена.",
            dir=str(target_dir),
            removed_count=len(pruned_paths),
            max_age_seconds=max_age_seconds,
            max_count=max_count,
        )
    except Exception:
        # Retention must never fail because logging is unavailable.
        pass
