from __future__ import annotations

from pathlib import Path
import re

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPORT_MODULE_TARGET_RE = re.compile(r'import_module\("([^"]+)"\)')
TARGET_ASSIGN_RE = re.compile(r'^_TARGET\s*=\s*"([^"]+)"', re.MULTILINE)

EXPECTED_MANUAL_REEXPORTS: dict[str, tuple[str, ...]] = {
    "app.pyi": (
        "from docxaicorrector.ui._app import _apply_pending_recommended_widget_state as _apply_pending_recommended_widget_state",
        "from docxaicorrector.ui._app import _assess_text_transform as _assess_text_transform",
        "from docxaicorrector.ui._app import _build_recommended_text_settings_notice as _build_recommended_text_settings_notice",
        "from docxaicorrector.ui._app import _CLEANUP_THREAD_STARTED as _CLEANUP_THREAD_STARTED",
        "from docxaicorrector.ui._app import _mark_app_ready as _mark_app_ready",
        "from docxaicorrector.ui._app import _maybe_apply_file_recommendations as _maybe_apply_file_recommendations",
        "from docxaicorrector.ui._app import _render_processing_controls as _render_processing_controls",
        "from docxaicorrector.ui._app import _resolve_sidebar_settings as _resolve_sidebar_settings",
        "from docxaicorrector.ui._app import _schedule_stale_persisted_sources_cleanup as _schedule_stale_persisted_sources_cleanup",
        "from docxaicorrector.ui._app import _should_render_recommended_text_settings_notice as _should_render_recommended_text_settings_notice",
        "from docxaicorrector.ui._app import _start_background_processing as _start_background_processing",
        "from docxaicorrector.ui._app import _store_preparation_summary as _store_preparation_summary",
    ),
    "application_flow.pyi": (
        "from docxaicorrector.ui.application_flow import PreparedRunContext as PreparedRunContext",
    ),
    "real_document_validation_profiles.pyi": (
        "from docxaicorrector.validation.profiles import PROJECT_ROOT as PROJECT_ROOT",
    ),
    "real_document_validation_structural.pyi": (
        "from docxaicorrector.validation.structural import _apply_prepared_metric_fields as _apply_prepared_metric_fields",
        "from docxaicorrector.validation.structural import _build_structural_checks as _build_structural_checks",
        "from docxaicorrector.validation.structural import processing_runtime as processing_runtime",
    ),
    "ui.pyi": (
        "from docxaicorrector.ui._ui import _mdpreview_key as _mdpreview_key",
        "from docxaicorrector.ui._ui import _render_activity_feed as _render_activity_feed",
    ),
}


def _iter_root_stub_paths() -> list[Path]:
    return sorted((Path(path) for path in PROJECT_ROOT.glob("*.pyi")), key=lambda path: path.name)


def _extract_target_module_from_root_module(module_path: Path) -> str:
    module_text = module_path.read_text(encoding="utf-8")

    import_module_match = IMPORT_MODULE_TARGET_RE.search(module_text)
    if import_module_match is not None:
        return import_module_match.group(1)

    target_assign_match = TARGET_ASSIGN_RE.search(module_text)
    if target_assign_match is not None:
        return target_assign_match.group(1)

    raise AssertionError(f"Could not determine migrated target module for {module_path.name}")


def test_each_root_typing_stub_has_matching_root_python_module() -> None:
    missing_python_modules: list[str] = []

    for stub_path in _iter_root_stub_paths():
        module_path = stub_path.with_suffix(".py")
        if not module_path.exists():
            missing_python_modules.append(stub_path.name)

    assert missing_python_modules == []


@pytest.mark.parametrize(
    "stub_path",
    _iter_root_stub_paths(),
)
def test_root_typing_stub_targets_match_root_module_contract(stub_path: Path) -> None:
    module_path = stub_path.with_suffix(".py")
    target_module = _extract_target_module_from_root_module(module_path)
    stub_text = stub_path.read_text(encoding="utf-8")

    assert f"from {target_module} import *" in stub_text

    for expected_line in EXPECTED_MANUAL_REEXPORTS.get(stub_path.name, ()):
        assert expected_line in stub_text
