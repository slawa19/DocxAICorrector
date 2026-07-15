from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from ._constants import (
    READER_CLEANUP_DEFAULT_SELECTOR,
    CleanupPolicy,
    _ALLOWED_OPERATIONS,
    _ALLOWED_POLICIES,
    _DEFAULT_CLEANUP_CHUNK_SIZE,
    _DEFAULT_GLOBAL_PLAN_ENABLED,
    _DEFAULT_OVERLAP_BLOCKS_AFTER,
    _DEFAULT_OVERLAP_BLOCKS_BEFORE,
)
from ._models import ReaderCleanupConfig
from ._utils import _coerce_bool, _coerce_float, _coerce_int


def resolve_reader_cleanup_config(*, app_config: Mapping[str, object], fallback_model: str) -> ReaderCleanupConfig:
    raw_policy = str(app_config.get("reader_cleanup_policy", "advisory") or "advisory").strip().lower()
    policy = raw_policy if raw_policy in _ALLOWED_POLICIES else "advisory"
    enabled = bool(app_config.get("reader_cleanup_enabled", False)) and policy != "off"
    model = str(app_config.get("reader_cleanup_model", "") or "").strip() or READER_CLEANUP_DEFAULT_SELECTOR
    return ReaderCleanupConfig(
        enabled=enabled,
        model=model,
        chunk_size=_coerce_int(
            app_config.get("reader_cleanup_chunk_size", _DEFAULT_CLEANUP_CHUNK_SIZE),
            default=_DEFAULT_CLEANUP_CHUNK_SIZE,
            minimum=3000,
        ),
        overlap_blocks_before=_coerce_int(
            app_config.get("reader_cleanup_overlap_blocks_before", _DEFAULT_OVERLAP_BLOCKS_BEFORE),
            default=_DEFAULT_OVERLAP_BLOCKS_BEFORE,
            minimum=0,
        ),
        overlap_blocks_after=_coerce_int(
            app_config.get("reader_cleanup_overlap_blocks_after", _DEFAULT_OVERLAP_BLOCKS_AFTER),
            default=_DEFAULT_OVERLAP_BLOCKS_AFTER,
            minimum=0,
        ),
        global_plan_enabled=_coerce_bool(
            app_config.get("reader_cleanup_global_plan_enabled", _DEFAULT_GLOBAL_PLAN_ENABLED),
            default=_DEFAULT_GLOBAL_PLAN_ENABLED,
        ),
        keep_toc=bool(app_config.get("reader_cleanup_keep_toc", True)),
        drop_back_matter=bool(app_config.get("reader_cleanup_drop_back_matter", False)),
        max_delete_block_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_block_ratio", 0.03), default=0.03),
        max_delete_char_ratio=_coerce_float(app_config.get("reader_cleanup_max_delete_char_ratio", 0.05), default=0.05),
        max_reclassify_block_ratio=_coerce_float(
            app_config.get("reader_cleanup_max_reclassify_block_ratio", 0.05),
            default=0.05,
        ),
        max_failed_chunk_ratio=_coerce_float(
            app_config.get("reader_cleanup_max_failed_chunk_ratio", 1.0),
            default=1.0,
        ),
        max_consecutive_deleted_blocks=_coerce_int(
            app_config.get("reader_cleanup_max_consecutive_deleted_blocks", 3),
            default=3,
            minimum=1,
        ),
        max_deleted_block_chars=_coerce_int(
            app_config.get("reader_cleanup_max_deleted_block_chars", 300),
            default=300,
            minimum=1,
        ),
        policy=cast(CleanupPolicy, policy),
        allowed_operations=_coerce_allowed_operations(app_config.get("reader_cleanup_allowed_operations")),
    )


def _coerce_allowed_operations(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_values: Sequence[object]
    if isinstance(value, str):
        raw_values = [part.strip() for part in value.split(",")]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = value
    else:
        return ()

    allowed: list[str] = []
    for raw_value in raw_values:
        operation = str(raw_value or "").strip()
        if not operation or operation not in _ALLOWED_OPERATIONS or operation in allowed:
            continue
        allowed.append(operation)
    return tuple(allowed)
