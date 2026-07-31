import base64
import os
import sys
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


# Make the repo-root shared bootstrap importable, then pin src first (F5/R29).
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from docxaicorrector_bootstrap import ensure_src_first_import_order

ensure_src_first_import_order(SRC_ROOT)

from docxaicorrector.core.config import ModelRegistry, TextModelConfig
import docxaicorrector.core.config as config


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
        if env_name.startswith("DOCX_AI_") or env_name in {"OPENAI_API_KEY", "OPENROUTER_API_KEY"}:
            monkeypatch.delenv(env_name, raising=False)


@pytest.fixture(autouse=True)
def isolate_formatting_diagnostics_dir(
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep test-run diagnostics out of the operator-facing ``.run`` directory.

    Retention for formatting diagnostics is family-wide (7 days / 100 artifacts),
    so test artifacts written into the real runtime directory crowd out genuine
    operator evidence. Each consumer captures the directory at import time, so
    every module-level copy is redirected here.
    """
    import docxaicorrector.generation.formatting_diagnostics_retention as formatting_diagnostics_retention
    import docxaicorrector.generation.formatting_transfer as formatting_transfer
    import docxaicorrector.pipeline._pipeline as pipeline

    diagnostics_dir = tmp_path_factory.mktemp("formatting_diagnostics")
    monkeypatch.setattr(formatting_diagnostics_retention, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)
    monkeypatch.setattr(formatting_transfer, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)
    monkeypatch.setattr(pipeline, "FORMATTING_DIAGNOSTICS_DIR", diagnostics_dir)


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
