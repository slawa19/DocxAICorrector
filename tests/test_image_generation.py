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
        PNG_BYTES,
        build_analysis_result(),
        mode="semantic_redraw_structured",
    )

    assert candidate == PNG_BYTES + b"-redrawn"
    assert captured["model"] == image_generation.IMAGE_EDIT_MODEL
    assert captured["input_fidelity"] == "high"
    assert captured["quality"] == "high"
    assert captured["response_format"] == "b64_json"
    assert "three boxes connected by arrows" in captured["prompt"]
    assert "Start, Review, Finish" in captured["prompt"]


def test_generate_image_candidate_semantic_falls_back_to_safe_when_redraw_is_forbidden(monkeypatch):
    monkeypatch.setattr(image_generation, "get_client", lambda: (_ for _ in ()).throw(AssertionError("should not call client")))

    candidate = image_generation.generate_image_candidate(
        PNG_BYTES,
        build_analysis_result(semantic_redraw_allowed=False),
        mode="semantic_redraw_direct",
    )

    assert candidate.startswith(b"\x89PNG\r\n\x1a\n")