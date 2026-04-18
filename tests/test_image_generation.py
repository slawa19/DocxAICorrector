import base64
from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast

import image_generation
from PIL import Image, ImageDraw
from models import ImageAnalysisResult


class RetryableError(Exception):
    status_code = 429


class ServerError(Exception):
    status_code = 500


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
        "text_node_count": 3,
        "extracted_text": "Start -> Review -> Finish",
        "fallback_reason": None,
    }
    payload.update(overrides)
    return ImageAnalysisResult(**payload)


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAIElEQVR4nGP8z/D/PwMDAwMDEwMDA8N/BoYGBgYGAABd8gT+olr0cQAAAABJRU5ErkJggg=="
)


def build_semantic_client(*, images=None, responses=None):
    return SimpleNamespace(
        images=images or SimpleNamespace(),
        responses=responses or SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text="")),
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


def build_square_generated_output_with_edge_markers(size: int = 24) -> bytes:
    image = Image.new("RGB", (size, size), (255, 255, 255))
    for x in range(2, size - 2):
        image.putpixel((x, 1), (20, 180, 40))
        image.putpixel((x, size - 2), (220, 30, 30))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_square_generated_output_with_large_margins(size: int = 24) -> bytes:
    image = Image.new("RGB", (size, size), (244, 242, 236))
    for x in range(5, size - 5):
        for y in range(8, size - 8):
            image.putpixel((x, y), (60, 100, 220))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _detect_edge_bands(restored_image) -> tuple[bool, bool]:
    top_band_detected = False
    bottom_band_detected = False
    for x_coord in range(restored_image.width):
        for y_coord in range(max(1, restored_image.height // 3)):
            top_pixel = restored_image.getpixel((x_coord, y_coord))
            if top_pixel[1] > top_pixel[0] + 40 and top_pixel[1] > top_pixel[2] + 20:
                top_band_detected = True
        for y_coord in range(max(0, restored_image.height - max(1, restored_image.height // 3)), restored_image.height):
            bottom_pixel = restored_image.getpixel((x_coord, y_coord))
            if bottom_pixel[0] > bottom_pixel[1] + 40 and bottom_pixel[0] > bottom_pixel[2] + 40:
                bottom_band_detected = True
    return top_band_detected, bottom_band_detected


def test_generate_image_candidate_safe_enhances_image_bytes():
    original_bytes = build_detailed_png_bytes()
    candidate = image_generation.generate_image_candidate(original_bytes, build_analysis_result(), mode="safe")

    assert candidate.startswith(b"\x89PNG\r\n\x1a\n")
    assert candidate != original_bytes


def test_generate_image_candidate_structured_uses_vision_and_images_generate(monkeypatch):
    captured: dict[str, Any] = {"vision": None, "generate": None}

    class FakeResponsesClient:
        def create(self, **kwargs):
            captured["vision"] = kwargs
            return SimpleNamespace(output_text="Three columns with arrows. Labels: Start, Review, Finish.")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured["generate"] = kwargs
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt="revised prompt",
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate
    assert captured["vision"] is not None
    assert captured["generate"] is not None
    assert captured["vision"]["model"] == image_generation.IMAGE_STRUCTURE_VISION_MODEL
    assert captured["generate"]["model"] == image_generation.IMAGE_GENERATE_MODEL
    assert captured["generate"]["response_format"] == "b64_json"
    assert captured["generate"]["quality"] == "high"
    assert captured["generate"]["size"] == "1024x1024"
    assert captured["generate"]["background"] == "transparent"
    assert captured["generate"]["output_format"] == "png"
    assert "Three columns with arrows" in captured["generate"]["prompt"]
    assert "office-presentation-style diagram" in captured["generate"]["prompt"]
    assert "Start -> Review -> Finish" in captured["generate"]["prompt"]
    with Image.open(BytesIO(candidate)) as generated_image:
        assert generated_image.width > 12
        assert generated_image.height > 12
        assert generated_image.width == generated_image.height


def test_generate_image_candidate_structured_preserves_generated_resolution_without_cropping_edge_content(monkeypatch):
    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="layout description")

    class FakeImagesClient:
        def generate(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_generated_output_with_edge_markers()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.width >= 18
        assert restored_image.height >= 10
        top_band_detected, bottom_band_detected = _detect_edge_bands(restored_image)
        assert top_band_detected
        assert bottom_band_detected


def test_generate_image_candidate_structured_edit_preserves_edge_content_without_generate_fallback(monkeypatch):
    captured: dict[str, Any] = {"edit": None}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured["edit"] = dict(kwargs)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_generated_output_with_edge_markers()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

        def generate(self, **kwargs):
            raise AssertionError("structured edit should not fall back to generate")

    client = build_semantic_client(images=FakeImagesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_structured"),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert captured["edit"] is not None
    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.width >= 18
        assert restored_image.height >= 10
        top_band_detected, bottom_band_detected = _detect_edge_bands(restored_image)
        assert top_band_detected
        assert bottom_band_detected


def test_generate_image_candidate_structured_trims_large_generated_margins_before_restore(monkeypatch):
    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="layout description")

    class FakeImagesClient:
        def generate(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_generated_output_with_large_margins()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.width >= 18
        assert restored_image.height >= 10
        leftmost_blue = restored_image.width
        rightmost_blue = -1
        for y_coord in range(restored_image.height):
            for x_coord in range(restored_image.width):
                pixel = restored_image.getpixel((x_coord, y_coord))
                assert isinstance(pixel, tuple)
                if pixel[2] > pixel[0] + 60 and pixel[2] > pixel[1] + 60:
                    leftmost_blue = min(leftmost_blue, x_coord)
                    rightmost_blue = max(rightmost_blue, x_coord)

        assert leftmost_blue <= 6
        assert rightmost_blue >= restored_image.width - 7


def test_generate_image_candidate_direct_uses_creative_vision_and_images_generate(monkeypatch):
    captured: dict[str, Any] = {"vision": None, "generate": None}

    class FakeResponsesClient:
        def create(self, **kwargs):
            captured["vision"] = kwargs
            return SimpleNamespace(output_text="Creative redraw brief with stronger hierarchy and more editorial composition.")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured["generate"] = kwargs
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    source_bytes = build_detailed_png_bytes()
    candidate = image_generation.generate_image_candidate(
        source_bytes,
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert captured["vision"] is not None
    assert captured["generate"] is not None
    assert captured["vision"]["model"] == image_generation.IMAGE_STRUCTURE_VISION_MODEL
    assert captured["generate"]["model"] == image_generation.IMAGE_GENERATE_MODEL
    assert captured["generate"]["response_format"] == "b64_json"
    assert captured["generate"]["quality"] == "high"
    assert captured["generate"]["size"] == "1024x1024"
    assert captured["generate"]["background"] == "transparent"
    assert captured["generate"]["output_format"] == "png"
    assert "Creative redraw brief" in captured["generate"]["prompt"]
    assert "Do not make it look like an Excel sheet" in captured["generate"]["prompt"]
    with Image.open(BytesIO(candidate)) as edited_image:
        assert edited_image.width > 12
        assert edited_image.height > 12
        assert edited_image.width == edited_image.height


def test_generate_image_candidate_direct_normalizes_dark_outer_background_to_white(monkeypatch):
    image = Image.new("RGB", (24, 24), (0, 0, 0))
    for x_coord in range(5, 19):
        for y_coord in range(5, 19):
            image.putpixel((x_coord, y_coord), (210, 235, 226))
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    restored = image_generation._restore_generated_output(buffer.getvalue(), (24, 24), prefer_light_background=True)

    with Image.open(BytesIO(restored)).convert("RGBA") as normalized_image:
        px0 = normalized_image.getpixel((0, 0))
        px23 = normalized_image.getpixel((23, 23))
        assert isinstance(px0, tuple)
        assert isinstance(px23, tuple)
        assert px0[:3] == (255, 255, 255)
        assert px23[:3] == (255, 255, 255)


def test_trim_generated_outer_padding_skips_trim_when_loss_ratio_is_too_large():
    image = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 0, 99, 99), fill="black")

    trimmed = image_generation._trim_generated_outer_padding(
        image,
        {
            "image_output_trim_tolerance": 20,
            "image_output_trim_padding_ratio": 0.02,
            "image_output_trim_padding_min_px": 4,
            "image_output_trim_max_loss_ratio": 0.15,
        },
    )

    assert trimmed.size == image.size


def test_trim_generated_outer_padding_applies_trim_when_loss_ratio_is_safe():
    image = Image.new("RGB", (100, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 90, 90), fill="black")

    trimmed = image_generation._trim_generated_outer_padding(
        image,
        {
            "image_output_trim_tolerance": 20,
            "image_output_trim_padding_ratio": 0.02,
            "image_output_trim_padding_min_px": 4,
            "image_output_trim_max_loss_ratio": 0.15,
        },
    )

    assert trimmed.size[0] < image.size[0]
    assert trimmed.size[1] < image.size[1]


def test_select_generate_size_uses_fixed_aspect_presets():
    assert image_generation._select_generate_size((400, 400)) == "1024x1024"
    assert image_generation._select_generate_size((800, 400)) == "1536x1024"
    assert image_generation._select_generate_size((400, 800)) == "1024x1536"


def test_select_generate_size_uses_policy_overrides():
    policy = {
        "image_output_generate_candidate_sizes": ("1024x1024", "1024x1792"),
    }

    assert image_generation._select_generate_size((400, 400), policy) == "1024x1024"
    assert image_generation._select_generate_size((800, 400), policy) == "1024x1024"
    assert image_generation._select_generate_size((400, 800), policy) == "1024x1792"


def test_extract_supported_generate_size_fallback_prefers_nearest_supported_size():
    fallback = image_generation._extract_supported_generate_size_fallback(
        "Error code: 400 - {'error': {'message': \"Invalid value: '1536x1024'. Supported values are: '1024x1024', '1024x1792'.\", 'param': 'size'}}",
        "1536x1024",
        fallback_sizes=("1024x1792", "1024x1024"),
    )

    assert fallback == "1024x1024"


def test_extract_supported_edit_size_fallback_prefers_nearest_supported_size():
    fallback = image_generation._extract_supported_size_fallback(
        "Error code: 400 - {'error': {'message': \"Invalid value: '1536x1024'. Supported values are: '512x512', '1024x1024'.\", 'param': 'size'}}",
        "1536x1024",
        fallback_sizes=("512x512", "1024x1024"),
    )

    assert fallback == "1024x1024"


def test_generate_image_candidate_uses_provided_client(monkeypatch):
    provided_client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(output_text="creative redraw brief")
        ),
        images=SimpleNamespace(
            generate=lambda **kwargs: SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )
        )
    )

    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=provided_client,
    )

    assert candidate


def test_generate_image_candidate_direct_passes_source_image_to_vision_for_jpeg_input(monkeypatch):
    captured: dict[str, Any] = {"vision": None}

    class FakeResponsesClient:
        def create(self, **kwargs):
            captured["vision"] = kwargs
            return SimpleNamespace(output_text="creative redraw brief")

    class FakeImagesClient:
        def generate(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_jpeg_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert captured["vision"] is not None
    image_payload = captured["vision"]["input"][1]["content"][1]["image_url"]
    assert image_payload.startswith("data:image/jpeg;base64,")


def test_generate_image_candidate_direct_falls_back_to_direct_edit_then_structured_generate(monkeypatch):
    captured = {}

    class FakeResponsesClient:
        def create(self, **kwargs):
            captured["vision"] = kwargs
            return SimpleNamespace(output_text="Fallback structured description")

    class FakeImagesClient:
        def __init__(self):
            self.generate_called = 0

        def edit(self, **kwargs):
            captured["edit"] = kwargs
            raise RuntimeError("Invalid value: 'gpt-image-1'. Value must be 'dall-e-2'.")

        def generate(self, **kwargs):
            self.generate_called += 1
            captured.setdefault("generate_calls", []).append(kwargs)
            if self.generate_called == 1:
                raise RuntimeError("temporary creative generate failure")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct", contains_text=True),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert captured["edit"]["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured["generate_calls"][1]["model"] == image_generation.IMAGE_GENERATE_MODEL
    assert "Fallback structured description" in captured["generate_calls"][1]["prompt"]


def test_generate_image_candidate_direct_preserves_aspect_ratio_without_downscaling_back_to_source(monkeypatch):
    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="creative redraw brief")

    class FakeImagesClient:
        def generate(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    source_bytes = build_rectangular_png_bytes()
    candidate = image_generation.generate_image_candidate(
        source_bytes,
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=client,
    )

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.width >= 18
        assert restored_image.height >= 10
        assert abs((restored_image.width / restored_image.height) - (18 / 10)) < 0.2


def test_generate_image_candidate_direct_retries_without_unknown_optional_param(monkeypatch):
    captured_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="creative redraw brief")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if len(captured_calls) == 1 and "quality" in kwargs:
                raise TypeError("Images.generate() got an unexpected keyword argument 'quality'")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert len(captured_calls) == 2
    assert "quality" in captured_calls[0]
    assert "quality" not in captured_calls[1]


def test_generate_image_candidate_direct_retries_after_retryable_error(monkeypatch):
    captured_calls = []
    sleep_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="creative redraw brief")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if len(captured_calls) == 1:
                raise RetryableError("rate limited")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert len(captured_calls) == 2
    assert sleep_calls == [1]
    assert captured_calls[0]["timeout"] == image_generation.IMAGE_API_TIMEOUT_SECONDS


def test_generate_image_candidate_direct_stops_when_model_call_budget_is_exhausted(monkeypatch):
    captured_calls = []
    sleep_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="creative redraw brief")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            raise RetryableError("rate limited")

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    try:
        image_generation.generate_image_candidate(
            build_detailed_png_bytes(),
            build_analysis_result(render_strategy="semantic_redraw_direct"),
            mode="semantic_redraw_direct",
            client=client,
            budget=image_generation.ImageModelCallBudget(max_calls=1),
        )
    except image_generation.ImageModelCallBudgetExceeded as exc:
        assert "budget exhausted" in str(exc)
    else:
        raise AssertionError("Expected ImageModelCallBudgetExceeded when retry budget is exhausted")

    assert len(captured_calls) == 0
    assert sleep_calls == []


def test_call_images_edit_consumes_budget_once_after_adaptation_retry():
    calls = []

    class Budget:
        def __init__(self):
            self.used_calls = 0

        def ensure_available(self, operation_name):
            return None

        def consume(self, operation_name):
            self.used_calls += 1

    class FakeImagesClient:
        def edit(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise TypeError("Images.edit() got an unexpected keyword argument 'input_fidelity'")
            return SimpleNamespace(data=[])

    budget = Budget()
    result = image_generation._call_images_edit(
        SimpleNamespace(images=FakeImagesClient()),
        {"model": "gpt-image-1", "image": [b"x"], "prompt": "p", "input_fidelity": "high"},
        budget=cast(image_generation.ImageModelCallBudget, budget),
    )

    assert isinstance(result, SimpleNamespace)
    assert len(calls) == 2
    assert "input_fidelity" in calls[0]
    assert "input_fidelity" not in calls[1]
    assert budget.used_calls == 1


def test_call_images_generate_consumes_budget_once_after_adaptation_retry():
    calls = []

    class Budget:
        def __init__(self):
            self.used_calls = 0

        def ensure_available(self, operation_name):
            return None

        def consume(self, operation_name):
            self.used_calls += 1

    class FakeImagesClient:
        def generate(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise TypeError("Images.generate() got an unexpected keyword argument 'quality'")
            return SimpleNamespace(data=[])

    budget = Budget()
    result = image_generation._call_images_generate(
        SimpleNamespace(images=FakeImagesClient()),
        {"model": "gpt-image-1", "prompt": "p", "quality": "high"},
        budget=cast(image_generation.ImageModelCallBudget, budget),
    )

    assert isinstance(result, SimpleNamespace)
    assert len(calls) == 2
    assert "quality" in calls[0]
    assert "quality" not in calls[1]
    assert budget.used_calls == 1


def test_call_responses_create_consumes_budget_once_after_timeout_adaptation():
    calls = []

    class Budget:
        def __init__(self):
            self.used_calls = 0

        def ensure_available(self, operation_name):
            return None

        def consume(self, operation_name):
            self.used_calls += 1

    class FakeResponsesClient:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise TypeError("unexpected keyword argument 'timeout'")
            return SimpleNamespace(output_text="ok")

    budget = Budget()
    result = image_generation._call_responses_create(
        SimpleNamespace(responses=FakeResponsesClient()),
        {"model": "gpt-4.1", "input": []},
        budget=cast(image_generation.ImageModelCallBudget, budget),
    )

    assert result.output_text == "ok"
    assert len(calls) == 2
    assert "timeout" in calls[0]
    assert "timeout" not in calls[1]
    assert budget.used_calls == 1


def test_call_responses_create_retries_without_temperature_and_logs_once(monkeypatch):
    calls = []
    log_calls = []

    class UnsupportedTemperatureError(Exception):
        status_code = 400

    class FakeResponsesClient:
        def create(self, **kwargs):
            calls.append(dict(kwargs))
            if len(calls) == 1:
                raise UnsupportedTemperatureError("Unsupported parameter: 'temperature' is not supported with this model.")
            return SimpleNamespace(output_text="ok")

    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: log_calls.append((args, kwargs)))

    result = image_generation._call_responses_create(
        SimpleNamespace(responses=FakeResponsesClient()),
        {"model": "gpt-4.1", "input": [], "temperature": 0.0},
    )

    assert result.output_text == "ok"
    assert calls == [
        {"model": "gpt-4.1", "input": [], "temperature": 0.0, "timeout": image_generation.IMAGE_API_TIMEOUT_SECONDS},
        {"model": "gpt-4.1", "input": [], "timeout": image_generation.IMAGE_API_TIMEOUT_SECONDS},
    ]
    removed_param_logs = [entry for entry in log_calls if entry[1].get("removed_param") == "temperature"]
    assert len(removed_param_logs) == 1



def test_generate_image_candidate_direct_retries_with_shorter_prompt(monkeypatch):
    captured_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="creative redraw brief")

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once:
                self.failed_once = True
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': \"Invalid 'prompt': string too long. Expected a string with maximum length 1000, but got a string with length 1635 instead.\"}}"
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct", structure_summary="x" * 1500),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert len(captured_calls) == 2
    assert len(captured_calls[0]["prompt"]) > 1000
    assert len(captured_calls[1]["prompt"]) <= 1000


def test_generate_image_candidate_direct_does_not_force_reconstruction_for_direct_mode(monkeypatch):
    calls = {"creative": 0, "reconstruct": 0}

    monkeypatch.setattr(
        image_generation,
        "_generate_creative_candidate",
        lambda *args, **kwargs: calls.__setitem__("creative", calls["creative"] + 1) or PNG_BYTES,
    )
    monkeypatch.setattr(
        image_generation,
        "_generate_reconstructed_candidate",
        lambda *args, **kwargs: calls.__setitem__("reconstruct", calls["reconstruct"] + 1) or PNG_BYTES,
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    client = build_semantic_client(images=SimpleNamespace(), responses=SimpleNamespace())

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="deterministic_reconstruction"),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate == PNG_BYTES
    assert calls["creative"] == 1
    assert calls["reconstruct"] == 0


def test_generate_image_candidate_structured_retries_with_shorter_prompt(monkeypatch):
    captured_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="layout description " + ("x" * 1400))

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once:
                self.failed_once = True
                raise RuntimeError("Error code: 400 - {'error': {'message': \"Invalid 'prompt': string too long. Expected a string with maximum length 1000, but got a string with length 1635 instead.\"}}")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate
    assert len(captured_calls) == 2
    assert len(captured_calls[0]["prompt"]) > 1000
    assert len(captured_calls[1]["prompt"]) <= 1000


def test_generate_image_candidate_structured_retries_vision_request_after_retryable_error(monkeypatch):
    sleep_calls = []
    vision_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            vision_calls.append(dict(kwargs))
            if len(vision_calls) == 1:
                raise RetryableError("rate limited")
            return SimpleNamespace(output_text="layout description")

    class FakeImagesClient:
        def generate(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate
    assert len(vision_calls) == 2
    assert sleep_calls == [1]
    assert vision_calls[0]["timeout"] == image_generation.IMAGE_API_TIMEOUT_SECONDS


def test_generate_image_candidate_structured_reads_nested_vision_output(monkeypatch):
    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        content=[SimpleNamespace(type="output_text", text="layout description from nested output")]
                    )
                ]
            )

    class FakeImagesClient:
        def generate(self, **kwargs):
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate


def test_generate_image_candidate_structured_falls_back_to_reconstruction_after_incomplete_vision_response(monkeypatch):
    class IncompleteResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

    reconstruction_calls = []

    def fake_reconstruct_image(*args, **kwargs):
        reconstruction_calls.append((args, kwargs))
        return build_square_semantic_output_bytes(), {"elements": []}

    client = build_semantic_client(images=SimpleNamespace(), responses=IncompleteResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation, "reconstruct_image", fake_reconstruct_image)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(
            image_type="table",
            prompt_key="table_semantic_redraw",
            render_strategy="deterministic_reconstruction",
        ),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate == build_square_semantic_output_bytes()
    assert len(reconstruction_calls) == 1


def test_generate_image_candidate_structured_uses_fixed_generate_size_without_auto_retry(monkeypatch):
    captured_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="layout description")

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once and kwargs.get("size") == "1536x1024":
                self.failed_once = True
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': \"Invalid value: '1536x1024'. Supported values are: '1024x1024'.\", 'param': 'size'}}"
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(structure_summary="x" * 1500),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate
    assert len(captured_calls) == 2
    assert captured_calls[0]["size"] == "1536x1024"
    assert captured_calls[1]["size"] == "1024x1024"


def test_generate_image_candidate_structured_retries_generate_request_after_server_error(monkeypatch):
    captured_calls = []
    sleep_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="layout description")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if len(captured_calls) == 1:
                raise ServerError("server error")
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate
    assert len(captured_calls) == 2
    assert sleep_calls == [1]
    assert captured_calls[0]["timeout"] == image_generation.IMAGE_API_TIMEOUT_SECONDS


def test_generate_image_candidate_semantic_falls_back_to_safe_when_redraw_is_forbidden(monkeypatch):
    candidate = image_generation.generate_image_candidate(
        PNG_BYTES,
        build_analysis_result(semantic_redraw_allowed=False),
        mode="semantic_redraw_direct",
    )

    assert candidate.startswith(b"\x89PNG\r\n\x1a\n")


def test_generate_image_candidate_uses_legacy_semantic_path_when_reconstruction_disabled(monkeypatch):
    captured = {}

    class FakeResponsesClient:
        def create(self, **kwargs):
            captured["vision"] = kwargs
            return SimpleNamespace(output_text="Legacy structured description")

    class FakeImagesClient:
        def generate(self, **kwargs):
            captured["generate"] = kwargs
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient(), responses=FakeResponsesClient())
    monkeypatch.setattr(image_generation, "reconstruct_image", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="deterministic_reconstruction"),
        mode="semantic_redraw_structured",
        client=client,
        prefer_deterministic_reconstruction=False,
    )

    assert candidate
    assert captured["vision"]["model"] == image_generation.IMAGE_STRUCTURE_VISION_MODEL
    assert captured["generate"]["model"] == image_generation.IMAGE_GENERATE_MODEL


def test_generate_image_candidate_structured_prefers_high_fidelity_edit_before_generate(monkeypatch):
    captured = {}

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured["edit"] = kwargs
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    client = build_semantic_client(images=FakeImagesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_structured"),
        mode="semantic_redraw_structured",
        client=client,
    )

    assert candidate
    assert captured["edit"]["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured["edit"]["input_fidelity"] == "high"
    assert captured["edit"]["output_format"] == "png"


def test_generate_image_candidate_direct_includes_extracted_text_in_prompt(monkeypatch):
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

    client = build_semantic_client(images=FakeImagesClient())
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct", extracted_text="Факты -> Анализ -> Вывод"),
        mode="semantic_redraw_direct",
        client=client,
    )

    assert candidate
    assert "Факты -> Анализ -> Вывод" in captured["prompt"]
