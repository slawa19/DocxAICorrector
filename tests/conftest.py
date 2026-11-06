import atexit
import base64
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

# Spec 061 FR-020: redirect the runtime-artifact root ONCE, before the package is first
# imported. ``core/constants.py`` reads ``DOCX_AI_RUN_DIR`` at import, and every module that
# copies a run-directory constant at import copies the redirected value, so the suite never
# writes into the operator's ``.run`` (before this, a full run left 155 files in
# ``.run/ui_results`` against a retention ceiling of 80 stems). The variable stays in
# ``os.environ`` for the whole session (``isolate_repo_dotenv`` spares it), so subprocesses
# a test spawns inherit the same root. This module is executed twice per session — as
# pytest's ``conftest`` and again as ``tests.conftest`` by test modules that import its
# constants — so the second execution must adopt the root the first one created, not make
# a new one the already-imported constants never see.
_SESSION_RUN_DIR_MARKER = "_DOCXAI_TEST_SESSION_RUN_DIR"
_session_run_dir = os.environ.get(_SESSION_RUN_DIR_MARKER, "")
if _session_run_dir and os.environ.get("DOCX_AI_RUN_DIR") == _session_run_dir:
    TEST_RUN_DIR = Path(_session_run_dir)
else:
    TEST_RUN_DIR = Path(tempfile.mkdtemp(prefix="docxai-test-run-")).resolve()
    os.environ["DOCX_AI_RUN_DIR"] = str(TEST_RUN_DIR)
    os.environ[_SESSION_RUN_DIR_MARKER] = str(TEST_RUN_DIR)
    atexit.register(shutil.rmtree, TEST_RUN_DIR, True)


# Make the repo-root shared bootstrap importable, then pin src first (F5/R29).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from docxaicorrector_bootstrap import ensure_src_first_import_order

ensure_src_first_import_order(SRC_ROOT)

from docxaicorrector.core.config import ModelRegistry, TextModelConfig
import docxaicorrector.core.config as config
import docxaicorrector.core.constants as _constants

if _constants.RUN_DIR != TEST_RUN_DIR:  # pragma: no cover - fails loudly, never silently
    raise pytest.UsageError(
        "docxaicorrector was imported before tests/conftest.py set DOCX_AI_RUN_DIR; "
        f"RUN_DIR={_constants.RUN_DIR} would let the suite write into the operator's .run."
    )


TEST_TEXT_MODEL_DEFAULT = "openrouter:google/gemini-3.1-flash-lite-preview"
TEST_TEXT_MODEL_OPTIONS = ("gpt-5.4", "gpt-5.4-mini")
TEST_STRUCTURE_RECOGNITION_MODEL = "gpt-5-mini"
TEST_IMAGE_ANALYSIS_MODEL = "gpt-5.4-mini"
TEST_IMAGE_VALIDATION_MODEL = "gpt-5.4-mini"
TEST_IMAGE_RECONSTRUCTION_MODEL = "gpt-5.4-mini"
TEST_IMAGE_GENERATION_MODEL = "gpt-image-1.5"
TEST_IMAGE_EDIT_MODEL = "gpt-image-1.5"
TEST_IMAGE_GENERATION_VISION_MODEL = "gpt-5.4-mini"


@pytest.fixture(autouse=True)
def isolate_repo_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent local repo .env values from leaking into tests by default."""
    monkeypatch.setattr(config, "ENV_PATH", PROJECT_ROOT / "__missing_test__.env")
    for env_name in tuple(os.environ):
        if env_name == _constants.RUN_DIR_ENV_VAR:
            continue
        if env_name.startswith("DOCX_AI_") or env_name in {"OPENAI_API_KEY", "OPENROUTER_API_KEY"}:
            monkeypatch.delenv(env_name, raising=False)


@pytest.fixture
def fake_png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK3cAAAAASUVORK5CYII="
    )


class SessionState(dict):  # type: ignore[type-arg]
    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


@pytest.fixture
def make_session_state():
    return SessionState


@pytest.fixture
def resolved_test_model_registry() -> ModelRegistry:
    return ModelRegistry(
        text=TextModelConfig(default=TEST_TEXT_MODEL_DEFAULT, options=TEST_TEXT_MODEL_OPTIONS),
        structure_recognition=TEST_STRUCTURE_RECOGNITION_MODEL,
        image_analysis=TEST_IMAGE_ANALYSIS_MODEL,
        image_validation=TEST_IMAGE_VALIDATION_MODEL,
        image_reconstruction=TEST_IMAGE_RECONSTRUCTION_MODEL,
        image_generation=TEST_IMAGE_GENERATION_MODEL,
        image_edit=TEST_IMAGE_EDIT_MODEL,
        image_generation_vision=TEST_IMAGE_GENERATION_VISION_MODEL,
    )
