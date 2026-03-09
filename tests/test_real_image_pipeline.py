import base64
import json
import os
import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import load_dotenv
from PIL import Image

import image_generation
from constants import ENV_PATH
from image_analysis import analyze_image


TESTS_DIR = Path(__file__).parent
ARTIFACTS_DIR = TESTS_DIR / "artifacts" / "real_image_pipeline"
REAL_IMAGE_CASES = [
    {
        "filename": "pic1_lietaer.jpg",
        "expected_type": "diagram",
        "expected_prompt_key": "diagram_semantic_redraw",
        "expected_strategy": "deterministic_reconstruction",
        "expected_mode": "semantic_redraw_structured",
        "semantic_allowed": True,
    },
    {
        "filename": "кпсс.jpg",
        "expected_type": "photo",
        "expected_prompt_key": "photo_safe_fallback",
        "expected_strategy": "safe_mode",
        "expected_mode": "safe",
        "semantic_allowed": False,
    },
    {
        "filename": "журналистика факты манипуляции.png",
        "expected_type": "infographic",
        "expected_prompt_key": "infographic_semantic_redraw",
        "expected_strategy": "deterministic_reconstruction",
        "expected_mode": "semantic_redraw_structured",
        "semantic_allowed": True,
    },
]

LIVE_API_ENABLED = os.getenv("DOCX_AI_RUN_LIVE_IMAGE_API_TESTS", "").strip().lower() in {"1", "true", "yes", "on"}

load_dotenv(dotenv_path=ENV_PATH)

PNG_STUB_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAIElEQVR4nGP8z/D/PwMDAwMDEwMDA8N/BoYGBgYGAABd8gT+olr0cQAAAABJRU5ErkJggg=="
)


def _load_image_bytes(filename: str) -> bytes:
    return (TESTS_DIR / filename).read_bytes()


def _resolve_requested_mode(analysis_result) -> str:
    if not analysis_result.semantic_redraw_allowed:
        return "safe"
    if analysis_result.render_strategy in {"semantic_redraw_structured", "deterministic_reconstruction"}:
        return "semantic_redraw_structured"
    return "semantic_redraw_direct"


def _detect_output_extension(image_bytes: bytes) -> str:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if image_bytes.startswith(b"BM"):
        return ".bmp"
    return ".bin"


def _artifact_basename(filename: str) -> str:
    return Path(filename).stem


def _write_pipeline_artifact(case: dict[str, object], candidate: bytes, metadata: dict[str, object]) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = ARTIFACTS_DIR / f"{_artifact_basename(str(case['filename']))}_output{_detect_output_extension(candidate)}"
    output_path.write_bytes(candidate)

    manifest_path = ARTIFACTS_DIR / "manifest.json"
    manifest_data: list[dict[str, object]] = []
    if manifest_path.exists():
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))

    updated = False
    for index, item in enumerate(manifest_data):
        if item.get("filename") == case["filename"]:
            manifest_data[index] = metadata
            updated = True
            break
    if not updated:
        manifest_data.append(metadata)

    manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


class TestRecognitionRealInputs:
    @pytest.mark.parametrize("case", REAL_IMAGE_CASES, ids=lambda case: case["filename"])
    def test_recognizes_expected_real_image_type(self, case):
        image_bytes = _load_image_bytes(case["filename"])

        started_at = time.perf_counter()
        result = analyze_image(image_bytes, model="gpt-4.1")
        elapsed_seconds = time.perf_counter() - started_at

        assert result.image_type == case["expected_type"]
        assert result.prompt_key == case["expected_prompt_key"]
        assert result.render_strategy == case["expected_strategy"]
        assert result.semantic_redraw_allowed is case["semantic_allowed"]
        assert elapsed_seconds < 2.0


class TestRedrawRoutingRealInputs:
    @pytest.mark.parametrize("case", REAL_IMAGE_CASES, ids=lambda case: case["filename"])
    def test_routes_to_expected_processing_mode_without_full_app(self, monkeypatch, case):
        image_bytes = _load_image_bytes(case["filename"])
        analysis_result = analyze_image(image_bytes, model="gpt-4.1")
        requested_mode = _resolve_requested_mode(analysis_result)

        assert requested_mode == case["expected_mode"]

        if requested_mode == "safe":
            candidate = image_generation.generate_image_candidate(image_bytes, analysis_result, mode=requested_mode)
            assert candidate
            return

        if analysis_result.render_strategy == "deterministic_reconstruction":
            with Image.open(BytesIO(image_bytes)) as original_image:
                original_size = original_image.size
            stub_image = Image.new("RGB", original_size, (200, 200, 200))
            stub_buf = BytesIO()
            stub_image.save(stub_buf, format="PNG")
            stub_png = stub_buf.getvalue()

            monkeypatch.setattr(
                image_generation,
                "reconstruct_image",
                lambda img_bytes, **kwargs: (stub_png, {"canvas": {"width": original_size[0], "height": original_size[1]}, "elements": []}),
            )
            monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

            started_at = time.perf_counter()
            candidate = image_generation.generate_image_candidate(image_bytes, analysis_result, mode=requested_mode)
            elapsed_seconds = time.perf_counter() - started_at

            assert candidate
            with Image.open(BytesIO(candidate)) as candidate_image:
                assert candidate_image.size == original_size
            assert elapsed_seconds < 2.0
            return

        captured = {}

        class FakeImagesClient:
            def edit(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    data=[SimpleNamespace(b64_json=base64.b64encode(PNG_STUB_BYTES).decode("ascii"), revised_prompt=None)]
                )

        monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
        monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

        started_at = time.perf_counter()
        candidate = image_generation.generate_image_candidate(image_bytes, analysis_result, mode=requested_mode)
        elapsed_seconds = time.perf_counter() - started_at

        assert candidate
        with Image.open(BytesIO(image_bytes)) as original_image, Image.open(BytesIO(candidate)) as candidate_image:
            assert candidate_image.size == original_image.size
        assert captured["model"] == image_generation.IMAGE_EDIT_MODEL
        assert captured["response_format"] == "b64_json"
        if requested_mode == "semantic_redraw_structured":
            assert captured["input_fidelity"] == "high"
            assert captured["quality"] == "high"
        else:
            assert captured["input_fidelity"] in {"low", "high"}
        assert elapsed_seconds < 1.0

    @pytest.mark.skipif(not LIVE_API_ENABLED, reason="Set DOCX_AI_RUN_LIVE_IMAGE_API_TESTS=1 to run live image API smoke tests.")
    @pytest.mark.parametrize("case", [case for case in REAL_IMAGE_CASES if case["expected_mode"] != "safe"], ids=lambda case: case["filename"])
    def test_live_redraw_api_smoke_and_timing(self, case):
        image_bytes = _load_image_bytes(case["filename"])
        analysis_result = analyze_image(image_bytes, model="gpt-4.1")
        requested_mode = _resolve_requested_mode(analysis_result)

        started_at = time.perf_counter()
        candidate = image_generation.generate_image_candidate(image_bytes, analysis_result, mode=requested_mode)
        elapsed_seconds = time.perf_counter() - started_at

        print(
            {
                "filename": case["filename"],
                "image_type": analysis_result.image_type,
                "requested_mode": requested_mode,
                "elapsed_seconds": round(elapsed_seconds, 2),
                "bytes_in": len(image_bytes),
                "bytes_out": len(candidate),
            }
        )

        assert candidate
        assert candidate != image_bytes


class TestLiveFullImagePipelineArtifacts:
    @pytest.mark.skipif(not LIVE_API_ENABLED, reason="Set DOCX_AI_RUN_LIVE_IMAGE_API_TESTS=1 to run live full image pipeline tests.")
    @pytest.mark.parametrize("case", REAL_IMAGE_CASES, ids=lambda case: case["filename"])
    def test_live_full_pipeline_saves_final_image_artifact(self, case):
        image_bytes = _load_image_bytes(case["filename"])

        analysis_started_at = time.perf_counter()
        analysis_result = analyze_image(image_bytes, model="gpt-4.1")
        analysis_elapsed_seconds = time.perf_counter() - analysis_started_at

        requested_mode = _resolve_requested_mode(analysis_result)

        generation_started_at = time.perf_counter()
        candidate = image_generation.generate_image_candidate(image_bytes, analysis_result, mode=requested_mode)
        generation_elapsed_seconds = time.perf_counter() - generation_started_at

        metadata = {
            "filename": case["filename"],
            "recognized_type": analysis_result.image_type,
            "requested_mode": requested_mode,
            "prompt_key": analysis_result.prompt_key,
            "render_strategy": analysis_result.render_strategy,
            "semantic_redraw_allowed": analysis_result.semantic_redraw_allowed,
            "analysis_elapsed_seconds": round(analysis_elapsed_seconds, 3),
            "generation_elapsed_seconds": round(generation_elapsed_seconds, 3),
            "bytes_in": len(image_bytes),
            "bytes_out": len(candidate),
        }
        output_path = _write_pipeline_artifact(case, candidate, metadata)

        print({**metadata, "saved_to": str(output_path)})

        assert candidate
        assert output_path.exists()
        if requested_mode != "safe":
            assert candidate != image_bytes
