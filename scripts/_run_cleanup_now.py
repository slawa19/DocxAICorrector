"""One-shot cleanup runner: prune all bounded ``.run/`` artifact families.

Invoked manually to apply the retention policies retroactively after the
writers were wired up. Not part of the runtime startup path.
"""
from __future__ import annotations

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT_DIR / "src"


def _ensure_src_first_import_order(root_dir: Path, src_root: Path) -> None:
    root_dir_str = str(root_dir)
    src_root_str = str(src_root)
    sys.path[:] = [entry for entry in sys.path if entry not in {root_dir_str, src_root_str}]
    sys.path.insert(0, root_dir_str)
    sys.path.insert(0, src_root_str)


_ensure_src_first_import_order(ROOT_DIR, SRC_ROOT)

from docxaicorrector.runtime.artifact_retention import (
    LAYOUT_CLEANUP_REPORTS_MAX_AGE_SECONDS,
    LAYOUT_CLEANUP_REPORTS_MAX_COUNT,
    PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_AGE_SECONDS,
    PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_COUNT,
    PARAGRAPH_BOUNDARY_REPORTS_MAX_AGE_SECONDS,
    PARAGRAPH_BOUNDARY_REPORTS_MAX_COUNT,
    RELATION_NORMALIZATION_REPORTS_MAX_AGE_SECONDS,
    RELATION_NORMALIZATION_REPORTS_MAX_COUNT,
    STRUCTURE_MAPS_MAX_AGE_SECONDS,
    STRUCTURE_MAPS_MAX_COUNT,
    STRUCTURE_VALIDATION_MAX_AGE_SECONDS,
    STRUCTURE_VALIDATION_MAX_COUNT,
    prune_artifact_dir,
)

TARGETS = [
    (Path(".run/paragraph_boundary_reports"), PARAGRAPH_BOUNDARY_REPORTS_MAX_AGE_SECONDS, PARAGRAPH_BOUNDARY_REPORTS_MAX_COUNT),
    (Path(".run/relation_normalization_reports"), RELATION_NORMALIZATION_REPORTS_MAX_AGE_SECONDS, RELATION_NORMALIZATION_REPORTS_MAX_COUNT),
    (Path(".run/layout_cleanup_reports"), LAYOUT_CLEANUP_REPORTS_MAX_AGE_SECONDS, LAYOUT_CLEANUP_REPORTS_MAX_COUNT),
    (Path(".run/paragraph_boundary_ai_review"), PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_AGE_SECONDS, PARAGRAPH_BOUNDARY_AI_REVIEW_MAX_COUNT),
    (Path(".run/structure_maps"), STRUCTURE_MAPS_MAX_AGE_SECONDS, STRUCTURE_MAPS_MAX_COUNT),
    (Path(".run/structure_validation"), STRUCTURE_VALIDATION_MAX_AGE_SECONDS, STRUCTURE_VALIDATION_MAX_COUNT),
]


def main() -> None:
    for target, age, count in TARGETS:
        pruned = prune_artifact_dir(
            target_dir=target,
            max_age_seconds=age,
            max_count=count,
            emit_log=False,
        )
        print(f"{target}: removed {len(pruned)} files")


if __name__ == "__main__":
    main()
