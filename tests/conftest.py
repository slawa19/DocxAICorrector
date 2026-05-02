import base64
import sys
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"


def _ensure_src_first_import_order(src_root: Path) -> None:
    src_root_str = str(src_root)
    sys.path[:] = [entry for entry in sys.path if entry != src_root_str]
    sys.path.insert(0, src_root_str)


_ensure_src_first_import_order(SRC_ROOT)

from docxaicorrector.core.config import ModelRegistry, TextModelConfig


TEST_TEXT_MODEL_DEFAULT = "gpt-5.4-mini"
TEST_TEXT_MODEL_OPTIONS = ("gpt-5.4", "gpt-5.4-mini")
TEST_STRUCTURE_RECOGNITION_MODEL = "gpt-5-mini"
TEST_IMAGE_ANALYSIS_MODEL = "gpt-5.4-mini"
TEST_IMAGE_VALIDATION_MODEL = "gpt-5.4-mini"
TEST_IMAGE_RECONSTRUCTION_MODEL = "gpt-5.4-mini"
TEST_IMAGE_GENERATION_MODEL = "gpt-image-1.5"
TEST_IMAGE_EDIT_MODEL = "gpt-image-1.5"
TEST_IMAGE_GENERATION_VISION_MODEL = "gpt-5.4-mini"


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
