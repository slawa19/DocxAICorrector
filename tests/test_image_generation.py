import base64
from io import BytesIO
from types import SimpleNamespace

import image_generation
from PIL import Image
from models import ImageAnalysisResult


def build_analysis_result(**overrides):
    payload = {
        "image_type": "diagram",
        "image_subtype": None,
        "contains_text": True,
        "semantic_redraw_allowed": True,
        "confidence": 0.95,
        "structured_parse_confidence": 0.9,
        "prompt_key": "diagram_semantic_redraw",
        "render_strategy": "semantic_redraw_structured",
        "structure_summary": "three boxes connected by arrows",
        "extracted_labels": ["Start", "Review", "Finish"],
        "fallback_reason": None,
    }
    payload.update(overrides)
    return ImageAnalysisResult(**payload)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAIElEQVR4nGP8z/D/PwMDAwMDEwMDA8N/BoYGBgYGAABd8gT+olr0cQAAAABJRU5ErkJggg=="
)


def build_detailed_png_bytes() -> bytes:
    image = Image.new("RGB", (12, 12))
    for x in range(12):
        for y in range(12):
            image.putpixel((x, y), (x * 20, y * 18, min(255, (x + y) * 11)))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_detailed_jpeg_bytes() -> bytes:
    image = Image.new("RGB", (16, 16))
    for x in range(16):
        for y in range(16):
            image.putpixel((x, y), (x * 12, y * 10, min(255, (x + y) * 8)))
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def build_rectangular_png_bytes() -> bytes:
    image = Image.new("RGB", (18, 10), (255, 255, 255))
    for x in range(18):
        image.putpixel((x, 5), (10, 40, 160))
    for y in range(10):
        image.putpixel((9, y), (160, 40, 10))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_square_semantic_output_bytes(size: int = 24) -> bytes:
    image = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    for x in range(3, size - 3):
        image.putpixel((x, size // 2), (20, 60, 160, 255))
    for y in range(4, size - 4):
        image.putpixel((size // 2, y), (180, 60, 20, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_generate_image_candidate_safe_enhances_image_bytes():
    original_bytes = build_detailed_png_bytes()
    candidate = image_generation.generate_image_candidate(original_bytes, build_analysis_result(), mode="safe")

    assert candidate.startswith(b"\x89PNG\r\n\x1a\n")
    assert candidate != original_bytes


def test_generate_image_candidate_semantic_uses_openai_edit(monkeypatch):
    captured = {}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-redrawn").decode("ascii"),
                        revised_prompt="revised prompt",
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-redrawn"
    assert captured["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured["input_fidelity"] == "high"
    assert captured["quality"] == "high"
    assert captured["output_format"] == "png"
    assert captured["response_format"] == "b64_json"
    assert "three boxes connected by arrows" in captured["prompt"]
    assert "Start, Review, Finish" in captured["prompt"]
    assert "Preserve visible text verbatim" in captured["prompt"]
    assert "fully reconstruct the diagram from scratch" in captured["prompt"]
    assert "Do not merely upscale" in captured["prompt"]


def test_generate_image_candidate_semantic_uploads_png_even_for_jpeg_input(monkeypatch):
    captured = {}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-jpeg-source").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_jpeg_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-jpeg-source"
    assert captured["image"][0] == "source.png"
    assert captured["image"][2] == "image/png"


def test_generate_image_candidate_semantic_normalizes_png_input_for_edit_compatibility(monkeypatch):
    captured = {}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-png-source").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    source_bytes = build_detailed_png_bytes()
    candidate = image_generation.generate_image_candidate(
        source_bytes,
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-png-source"
    assert captured["image"][0] == "source.png"
    assert captured["image"][2] == "image/png"
    assert captured["image"][1].startswith(b"\x89PNG\r\n\x1a\n")


def test_generate_image_candidate_semantic_uses_high_fidelity_for_text_heavy_direct_mode(monkeypatch):
    captured = {}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-direct").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_structured", contains_text=True),
        mode="semantic_redraw_direct",
    )

    assert candidate == PNG_BYTES + b"-direct"
    assert captured["input_fidelity"] == "high"
    assert captured["quality"] == "high"
    assert captured["output_format"] == "png"


def test_generate_image_candidate_semantic_restores_original_dimensions_after_square_edit(monkeypatch):
    captured = {}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    source_bytes = build_rectangular_png_bytes()
    candidate = image_generation.generate_image_candidate(
        source_bytes,
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    with Image.open(BytesIO(captured["image"][1])) as uploaded_image:
        assert uploaded_image.size == (18, 18)

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.size == (18, 10)


def test_generate_image_candidate_semantic_retries_without_moderation_for_older_sdk(monkeypatch):
    captured_calls = []

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if "moderation" in kwargs:
                raise TypeError("Images.edit() got an unexpected keyword argument 'moderation'")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-compat").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-compat"
    assert len(captured_calls) == 2
    assert "moderation" in captured_calls[0]
    assert "moderation" not in captured_calls[1]


def test_generate_image_candidate_semantic_retries_without_unknown_api_param(monkeypatch):
    captured_calls = []

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once and "input_fidelity" in kwargs:
                self.failed_once = True
                raise RuntimeError("Error code: 400 - {'error': {'message': \"Unknown parameter: 'input_fidelity'.\"}}")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-api-compat").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-api-compat"
    assert len(captured_calls) == 2
    assert "input_fidelity" in captured_calls[0]
    assert "input_fidelity" not in captured_calls[1]


def test_generate_image_candidate_semantic_retries_with_fallback_model(monkeypatch):
    captured_calls = []

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once and kwargs.get("model") == image_generation.IMAGE_EDIT_MODEL:
                self.failed_once = True
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': \"Invalid value: 'gpt-image-1'. Value must be 'dall-e-2'.\"}}"
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-fallback-model").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-fallback-model"
    assert len(captured_calls) == 2
    assert captured_calls[0]["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured_calls[1]["model"] == "dall-e-2"


def test_generate_image_candidate_semantic_retries_with_shorter_prompt(monkeypatch):
    captured_calls = []

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once:
                self.failed_once = True
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': \"Invalid 'prompt': string too long. Expected a string with maximum length 1000, but got a string with length 1635 instead.\"}}"
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-short-prompt").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(structure_summary="x" * 1500),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-short-prompt"
    assert len(captured_calls) == 2
    assert len(captured_calls[0]["prompt"]) > 1000
    assert len(captured_calls[1]["prompt"]) <= 1000


def test_generate_image_candidate_semantic_retries_with_fallback_size(monkeypatch):
    captured_calls = []

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once and kwargs.get("size") == "auto":
                self.failed_once = True
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': \"Invalid value: 'auto'. Supported values are: '256x256', '512x512', and '1024x1024'.\", 'param': 'size'}}"
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(PNG_BYTES + b"-fallback-size").decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-fallback-size"
    assert len(captured_calls) == 2
    assert captured_calls[0]["size"] == "auto"
    assert captured_calls[1]["size"] == "1024x1024"


def test_generate_image_candidate_semantic_falls_back_to_safe_when_redraw_is_forbidden(monkeypatch):
    monkeypatch.setattr(image_generation, "get_client", lambda: (_ for _ in ()).throw(AssertionError("should not call client")))

    candidate = image_generation.generate_image_candidate(
        PNG_BYTES,
        build_analysis_result(semantic_redraw_allowed=False),
        mode="semantic_redraw_direct",
    )

    assert candidate.startswith(b"\x89PNG\r\n\x1a\n")