import base64
from io import BytesIO
from types import SimpleNamespace

import image_generation
from PIL import Image
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


def test_generate_image_candidate_safe_enhances_image_bytes():
    original_bytes = build_detailed_png_bytes()
    candidate = image_generation.generate_image_candidate(original_bytes, build_analysis_result(), mode="safe")

    assert candidate.startswith(b"\x89PNG\r\n\x1a\n")
    assert candidate != original_bytes


def test_generate_image_candidate_structured_uses_vision_and_images_generate(monkeypatch):
    captured = {"vision": None, "generate": None}

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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate
    assert captured["vision"]["model"] == image_generation.IMAGE_STRUCTURE_VISION_MODEL
    assert captured["generate"]["model"] == image_generation.IMAGE_GENERATE_MODEL
    assert captured["generate"]["response_format"] == "b64_json"
    assert captured["generate"]["quality"] == "high"
    assert "Three columns with arrows" in captured["generate"]["prompt"]
    assert "Generate a brand-new clean vector-style diagram from scratch" in captured["generate"]["prompt"]
    assert "Start -> Review -> Finish" in captured["generate"]["prompt"]
    with Image.open(BytesIO(candidate)) as generated_image:
        assert generated_image.size == (12, 12)


def test_generate_image_candidate_structured_restores_original_size_without_cropping_edge_content(monkeypatch):
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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.size == (18, 10)
        top_band_detected = False
        bottom_band_detected = False
        for x_coord in range(restored_image.width):
            for y_coord in range(min(2, restored_image.height)):
                top_pixel = restored_image.getpixel((x_coord, y_coord))
                if top_pixel[1] > top_pixel[0] + 40 and top_pixel[1] > top_pixel[2] + 20:
                    top_band_detected = True
            for y_coord in range(max(0, restored_image.height - 2), restored_image.height):
                bottom_pixel = restored_image.getpixel((x_coord, y_coord))
                if bottom_pixel[0] > bottom_pixel[1] + 40 and bottom_pixel[0] > bottom_pixel[2] + 40:
                    bottom_band_detected = True

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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.size == (18, 10)
        leftmost_blue = restored_image.width
        rightmost_blue = -1
        for y_coord in range(restored_image.height):
            for x_coord in range(restored_image.width):
                pixel = restored_image.getpixel((x_coord, y_coord))
                if pixel[2] > pixel[0] + 60 and pixel[2] > pixel[1] + 60:
                    leftmost_blue = min(leftmost_blue, x_coord)
                    rightmost_blue = max(rightmost_blue, x_coord)

        assert leftmost_blue <= 4
        assert rightmost_blue >= restored_image.width - 5


def test_generate_image_candidate_direct_uses_openai_edit_with_file_list(monkeypatch):
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

    source_bytes = build_detailed_png_bytes()
    candidate = image_generation.generate_image_candidate(
        source_bytes,
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert captured["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured["response_format"] == "b64_json"
    assert captured["quality"] == "high"
    assert isinstance(captured["image"], list)
    assert len(captured["image"]) == 1
    assert captured["image"][0].name == "source.png"
    assert captured["size"] == "auto"
    with Image.open(BytesIO(candidate)) as edited_image:
        assert edited_image.size == (12, 12)


def test_generate_image_candidate_uses_provided_client_without_calling_get_client(monkeypatch):
    provided_client = SimpleNamespace(
        images=SimpleNamespace(
            edit=lambda **kwargs: SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )
        )
    )

    monkeypatch.setattr(image_generation, "get_client", lambda: (_ for _ in ()).throw(AssertionError("should reuse provided client")))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
        client=provided_client,
    )

    assert candidate


def test_generate_image_candidate_direct_uploads_png_even_for_jpeg_input(monkeypatch):
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

    candidate = image_generation.generate_image_candidate(
        build_detailed_jpeg_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert captured["image"][0].name == "source.png"
    with Image.open(captured["image"][0]) as uploaded_image:
        assert uploaded_image.format == "PNG"


def test_generate_image_candidate_direct_falls_back_to_structured_generate(monkeypatch):
    captured = {}

    class FakeResponsesClient:
        def create(self, **kwargs):
            captured["vision"] = kwargs
            return SimpleNamespace(output_text="Fallback structured description")

    class FakeImagesClient:
        def __init__(self):
            self.edit_called = False

        def edit(self, **kwargs):
            self.edit_called = True
            captured["edit"] = kwargs
            raise RuntimeError("Invalid value: 'gpt-image-1'. Value must be 'dall-e-2'.")

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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct", contains_text=True),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert captured["edit"]["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured["generate"]["model"] == image_generation.IMAGE_GENERATE_MODEL
    assert "Fallback structured description" in captured["generate"]["prompt"]


def test_generate_image_candidate_direct_restores_original_dimensions_after_square_edit(monkeypatch):
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
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
    )

    with Image.open(captured["image"][0]) as uploaded_image:
        assert uploaded_image.size == (18, 18)

    with Image.open(BytesIO(candidate)) as restored_image:
        assert restored_image.size == (18, 10)


def test_generate_image_candidate_direct_retries_without_unknown_optional_param(monkeypatch):
    captured_calls = []

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if len(captured_calls) == 1 and "quality" in kwargs:
                raise TypeError("Images.edit() got an unexpected keyword argument 'quality'")
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

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert len(captured_calls) == 2
    assert "quality" in captured_calls[0]
    assert "quality" not in captured_calls[1]


def test_generate_image_candidate_direct_retries_after_retryable_error(monkeypatch):
    captured_calls = []
    sleep_calls = []

    class FakeImagesClient:
        def edit(self, **kwargs):
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

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct"),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert len(captured_calls) == 2
    assert sleep_calls == [1]
    assert captured_calls[0]["timeout"] == image_generation.IMAGE_API_TIMEOUT_SECONDS


def test_generate_image_candidate_direct_stops_when_model_call_budget_is_exhausted(monkeypatch):
    captured_calls = []
    sleep_calls = []

    class FakeImagesClient:
        def edit(self, **kwargs):
            captured_calls.append(dict(kwargs))
            raise RetryableError("rate limited")

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    try:
        image_generation.generate_image_candidate(
            build_detailed_png_bytes(),
            build_analysis_result(render_strategy="semantic_redraw_direct"),
            mode="semantic_redraw_direct",
            budget=image_generation.ImageModelCallBudget(max_calls=1),
        )
    except image_generation.ImageModelCallBudgetExceeded as exc:
        assert "budget exhausted" in str(exc)
    else:
        raise AssertionError("Expected ImageModelCallBudgetExceeded when retry budget is exhausted")

    assert len(captured_calls) == 1
    assert sleep_calls == []


def test_generate_image_candidate_direct_retries_with_shorter_prompt(monkeypatch):
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
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct", structure_summary="x" * 1500),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert len(captured_calls) == 2
    assert len(captured_calls[0]["prompt"]) > 1000
    assert len(captured_calls[1]["prompt"]) <= 1000


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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate
    assert len(vision_calls) == 2
    assert sleep_calls == [1]
    assert vision_calls[0]["timeout"] == image_generation.IMAGE_API_TIMEOUT_SECONDS


def test_generate_image_candidate_structured_retries_with_fallback_size(monkeypatch):
    captured_calls = []

    class FakeResponsesClient:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="layout description")

    class FakeImagesClient:
        def __init__(self):
            self.failed_once = False

        def generate(self, **kwargs):
            captured_calls.append(dict(kwargs))
            if not self.failed_once and kwargs.get("size") == "auto":
                self.failed_once = True
                raise RuntimeError(
                    "Error code: 400 - {'error': {'message': \"Invalid value: 'auto'. Supported values are: '1536x1024', '1024x1536', '1024x1024'.\", 'param': 'size'}}"
                )
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        b64_json=base64.b64encode(build_square_semantic_output_bytes()).decode("ascii"),
                        revised_prompt=None,
                    )
                ]
            )

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(structure_summary="x" * 1500),
        mode="semantic_redraw_structured",
    )

    assert candidate
    assert len(captured_calls) == 2
    assert captured_calls[0]["size"] == "auto"
    assert captured_calls[1]["size"] == "1536x1024"


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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(image_generation.time, "sleep", sleep_calls.append)

    candidate = image_generation.generate_image_candidate(
        build_rectangular_png_bytes(),
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate
    assert len(captured_calls) == 2
    assert sleep_calls == [1]
    assert captured_calls[0]["timeout"] == image_generation.IMAGE_API_TIMEOUT_SECONDS


def test_generate_image_candidate_semantic_falls_back_to_safe_when_redraw_is_forbidden(monkeypatch):
    monkeypatch.setattr(image_generation, "get_client", lambda: (_ for _ in ()).throw(AssertionError("should not call client")))

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

    monkeypatch.setattr(
        image_generation,
        "get_client",
        lambda: SimpleNamespace(images=FakeImagesClient(), responses=FakeResponsesClient()),
    )
    monkeypatch.setattr(image_generation, "reconstruct_image", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="deterministic_reconstruction"),
        mode="semantic_redraw_structured",
        prefer_deterministic_reconstruction=False,
    )

    assert candidate
    assert captured["vision"]["model"] == image_generation.IMAGE_STRUCTURE_VISION_MODEL
    assert captured["generate"]["model"] == image_generation.IMAGE_GENERATE_MODEL


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

    monkeypatch.setattr(image_generation, "get_client", lambda: SimpleNamespace(images=FakeImagesClient()))
    monkeypatch.setattr(image_generation, "log_event", lambda *args, **kwargs: None)

    candidate = image_generation.generate_image_candidate(
        build_detailed_png_bytes(),
        build_analysis_result(render_strategy="semantic_redraw_direct", extracted_text="Факты -> Анализ -> Вывод"),
        mode="semantic_redraw_direct",
    )

    assert candidate
    assert "Факты -> Анализ -> Вывод" in captured["prompt"]
