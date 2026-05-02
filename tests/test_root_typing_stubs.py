from __future__ import annotations

from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_STUB_PATH = PROJECT_ROOT / "app.pyi"

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
}


def test_app_stub_is_the_only_remaining_root_typing_stub() -> None:
    root_stub_names = sorted(path.name for path in PROJECT_ROOT.glob("*.pyi"))

    assert root_stub_names == ["app.pyi"]


def test_app_stub_targets_package_contract() -> None:
    stub_text = APP_STUB_PATH.read_text(encoding="utf-8")

    assert "from docxaicorrector.ui._app import *" in stub_text

    for expected_line in EXPECTED_MANUAL_REEXPORTS["app.pyi"]:
        assert expected_line in stub_text
