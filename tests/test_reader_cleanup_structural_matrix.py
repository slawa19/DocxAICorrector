from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_matrix_module() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run-reader-cleanup-structural-matrix.py"
    spec = importlib.util.spec_from_file_location("reader_cleanup_structural_matrix", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_score_counts_structural_repairs_by_effect_not_exact_operation_shape() -> None:
    matrix = _load_matrix_module()
    raw_markdown = (
        "Префикс Экономические последствия концентрации богатства тело абзаца.\n\n"
        "Префикс Последствия для устойчивости тело абзаца.\n\n"
        "пять пагубных процессов 1. первый 2. второй 3. третий 4. четвертый 5. пятый\n\n"
        "Текст с маркером.25\n\nЕще текст.43\n\nФинальный текст.44"
    )
    cleaned_markdown = (
        "### Экономические последствия концентрации богатства\n\n"
        "тело абзаца.\n\n"
        "# Последствия для устойчивости\n\n"
        "тело абзаца.\n\n"
        "пять пагубных процессов\n"
        "1. первый\n"
        "2. второй\n"
        "3. третий\n"
        "4. четвертый\n"
        "5. пятый\n\n"
        "Текст с маркером.\n\n25\n\nЕще текст.\n\n43\n\nФинальный текст.\n\n44"
    )

    score = matrix._score(
        raw_markdown,
        cleaned_markdown,
        {
            "accepted_cleanup_operations": [{"id": "b1"}, {"id": "b2"}],
            "ignored_cleanup_operations": [],
            "image_reconciliation": {
                "touched": False,
                "before_image_id_count": 2,
                "after_image_id_count": 2,
            },
        },
        12.3456,
    )

    assert score["caught"] == {
        "fused_heading_wealth_concentration": True,
        "fused_heading_sustainability": True,
        "broken_five_processes_list": True,
        "footnote_markers_detached": True,
    }
    assert score["caught_count"] == 4
    assert score["false_positive_count"] == 0
    assert score["containment_violation_count"] == 0
    assert score["images_touched"] is False
    assert score["elapsed_seconds"] == 12.346


def test_score_rejects_unfixed_structural_shapes_and_counts_only_containment_as_false() -> None:
    matrix = _load_matrix_module()
    broken_markdown = (
        "Префикс Экономические последствия концентрации богатства тело абзаца.\n\n"
        "Префикс Последствия для устойчивости тело абзаца.\n\n"
        "пять пагубных процессов 1. первый 2. второй 3. третий 4. четвертый 5. пятый\n\n"
        "Текст с маркером.25\n\nЕще текст.43\n\nФинальный текст.44"
    )

    score = matrix._score(
        broken_markdown,
        broken_markdown,
        {
            "accepted_cleanup_operations": [{"id": "non_target_structural_annotation"}],
            "ignored_cleanup_operations": [
                {"id": "b1", "ignored_reason": "visible_content_containment_failed"},
                {"id": "b2", "ignored_reason": "low_confidence"},
            ],
            "image_reconciliation": {"touched": True, "before_image_id_count": 1, "after_image_id_count": 1},
        },
        1.0,
    )

    assert score["caught"] == {
        "fused_heading_wealth_concentration": False,
        "fused_heading_sustainability": False,
        "broken_five_processes_list": False,
        "footnote_markers_detached": False,
    }
    assert score["caught_count"] == 0
    assert score["false_positive_count"] == 1
    assert score["containment_violation_count"] == 1
    assert score["accepted_operation_count"] == 1
    assert score["ignored_operation_count"] == 2
    assert score["images_touched"] is True


def test_layout_mode_metadata_selects_real_pseudo_or_both_signals() -> None:
    matrix = _load_matrix_module()
    metadata = {
        0: {
            "paragraph_id": "p0001",
            "layout_signals": {
                "source_block_index": 7,
                "font_size_pt": 16.0,
                "is_bold": True,
                "pseudo": {
                    "standalone_short_line": True,
                    "looks_like_superscript_marker": False,
                },
            },
        }
    }

    none = matrix._metadata_for_layout_mode(metadata, layout_mode="none")
    pseudo = matrix._metadata_for_layout_mode(metadata, layout_mode="pseudo")
    real = matrix._metadata_for_layout_mode(metadata, layout_mode="real")
    both = matrix._metadata_for_layout_mode(metadata, layout_mode="both")

    assert none == {0: {"paragraph_id": "p0001"}}
    assert pseudo[0]["layout_signals"] == {
        "source_block_index": 7,
        "standalone_short_line": True,
        "looks_like_superscript_marker": False,
    }
    assert real[0]["layout_signals"] == {
        "font_size_pt": 16.0,
        "is_bold": True,
        "source_block_index": 7,
    }
    assert both[0]["layout_signals"] == {
        "source_block_index": 7,
        "font_size_pt": 16.0,
        "is_bold": True,
        "pseudo_standalone_short_line": True,
        "pseudo_looks_like_superscript_marker": False,
    }
