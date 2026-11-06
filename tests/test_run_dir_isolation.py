"""The test suite never writes into the operator's ``.run`` (spec 061 FR-020, User Story 6-1).

Before the fix ``RUN_DIR`` and its sub-directories were import-time constants with no override,
and ``tests/conftest.py`` redirected two artifact families by name; ``UI_RESULT_ARTIFACTS_DIR``
was not one of them, and a suite run left 155 test files in ``.run/ui_results/`` against a
retention ceiling of 80 stems — evicting genuine operator evidence. Now the root is read once
from ``DOCX_AI_RUN_DIR`` and ``conftest.py`` sets it before the package is first imported, so
every constant derived from it — including the copies other modules captured at import — lands
under a per-session temporary root.
"""

from __future__ import annotations

import inspect
import os
from pathlib import Path

import docxaicorrector.core.constants as constants
import docxaicorrector.core.logger as logger
import docxaicorrector.generation.formatting_diagnostics_retention as formatting_diagnostics_retention
import docxaicorrector.generation.marker_attempt_capture as marker_attempt_capture
import docxaicorrector.pipeline.reassembly as reassembly
import docxaicorrector.processing.restart_store as restart_store
import docxaicorrector.runtime.artifacts as runtime_artifacts
import docxaicorrector.runtime.state as runtime_state
import docxaicorrector.structure.validation as structure_validation

from tests.conftest import TEST_RUN_DIR


REPO_RUN_DIR = constants.BASE_DIR / ".run"

RUN_DIR_CONSTANT_NAMES = (
    "RUN_DIR",
    "UI_RESULT_ARTIFACTS_DIR",
    "STRUCTURE_MANIFESTS_DIR",
    "SEGMENT_RESULT_REGISTRY_DIR",
    "JOB_RESULT_REGISTRY_DIR",
    "APP_LOG_PATH",
    "APP_READY_PATH",
)


def _is_under(path: Path, root: Path) -> bool:
    return Path(path).resolve().is_relative_to(root.resolve())


def _default_of(function: object, parameter: str) -> Path:
    default = inspect.signature(function).parameters[parameter].default  # type: ignore[arg-type]
    assert isinstance(default, Path)
    return default


def test_the_suite_root_is_a_temporary_directory_outside_the_repository() -> None:
    assert os.environ[constants.RUN_DIR_ENV_VAR] == str(TEST_RUN_DIR)
    assert constants.RUN_DIR == TEST_RUN_DIR
    assert not _is_under(TEST_RUN_DIR, constants.BASE_DIR)


def test_every_run_directory_constant_resolves_under_the_temporary_root() -> None:
    for name in RUN_DIR_CONSTANT_NAMES:
        value = getattr(constants, name)
        assert _is_under(value, TEST_RUN_DIR), f"{name} = {value} escapes the suite root {TEST_RUN_DIR}"
        assert not _is_under(value, REPO_RUN_DIR), f"{name} = {value} points into the repository .run"


def test_module_level_copies_captured_at_import_follow_the_redirected_root() -> None:
    # The reason a per-family redirect was ever needed: these modules copy the constant at
    # import. With the root redirected before the first import, every copy is already right.
    captured = {
        "logger.RUN_DIR": logger.RUN_DIR,
        "logger.APP_LOG_PATH": logger.APP_LOG_PATH,
        "runtime.state.APP_LOG_PATH": runtime_state.APP_LOG_PATH,
        "restart_store.RUN_DIR": restart_store.RUN_DIR,
        "structure.validation debug dir": structure_validation._STRUCTURE_VALIDATION_DEBUG_DIR,
        "write_ui_result_artifacts(output_dir=)": _default_of(runtime_artifacts.write_ui_result_artifacts, "output_dir"),
        "reassembly input_dir default": _default_of(reassembly.load_segment_result_records, "input_dir"),
    }
    for label, value in captured.items():
        assert _is_under(value, TEST_RUN_DIR), f"{label} = {value} escapes the suite root"


def test_families_outside_the_shared_root_are_still_redirected_per_test() -> None:
    # Anti-vacuum for keeping the two conftest fixtures: these two families are NOT derived
    # from RUN_DIR (they are cwd-relative ``Path(".run") / ...`` in generation/), so the root
    # redirect does not reach them and the fixture must.
    for value in (
        formatting_diagnostics_retention.FORMATTING_DIAGNOSTICS_DIR,
        marker_attempt_capture.MARKER_ATTEMPT_DIAGNOSTICS_DIR,
    ):
        assert value.is_absolute()
        assert not _is_under(value, REPO_RUN_DIR)


def test_resolve_run_dir_defaults_to_the_working_root_and_honours_the_override(tmp_path: Path) -> None:
    base = tmp_path / "home"
    assert constants.resolve_run_dir(base, environ={}) == base / ".run"
    assert constants.resolve_run_dir(base, environ={constants.RUN_DIR_ENV_VAR: "   "}) == base / ".run"
    override = tmp_path / "elsewhere"
    assert constants.resolve_run_dir(base, environ={constants.RUN_DIR_ENV_VAR: str(override)}) == override.resolve()
