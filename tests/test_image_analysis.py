from io import BytesIO

from PIL import Image, ImageDraw

import image_analysis


class _FakeResponsesClient:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.responses = self

    def create(self, **kwargs):
        class _Response:
            def __init__(self, output_text: str):
                self.output_text = output_text

        return _Response(self.output_text)


def _make_diagram_like_jpeg() -> bytes:
    image = Image.new("RGB", (480, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 50, 180, 120), outline="black", width=4)
    draw.rectangle((280, 50, 420, 120), outline="black", width=4)
    draw.rectangle((160, 200, 300, 270), outline="black", width=4)
    draw.line((180, 85, 280, 85), fill="black", width=4)
    draw.line((350, 120, 230, 200), fill="black", width=4)
    draw.line((110, 120, 230, 200), fill="black", width=4)
    draw.rectangle((70, 72, 150, 84), fill="black")
    draw.rectangle((310, 72, 390, 84), fill="black")
    draw.rectangle((190, 222, 270, 234), fill="black")
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _make_photo_like_jpeg() -> bytes:
    image = Image.new("RGB", (480, 320))
    draw = ImageDraw.Draw(image)
    for x in range(480):
        for y in range(320):
            draw.point((x, y), fill=((x * 3) % 256, (y * 5) % 256, ((x + y) * 2) % 256))
    output = BytesIO()
    image.save(output, format="JPEG", quality=90)
    return output.getvalue()


def _make_screenshot_like_png() -> bytes:
    image = Image.new("RGB", (480, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 479, 42), fill=(32, 78, 145))
    draw.rectangle((24, 72, 220, 132), outline=(210, 210, 210), width=2, fill=(248, 248, 248))
    draw.rectangle((248, 72, 456, 132), outline=(210, 210, 210), width=2, fill=(248, 248, 248))
    draw.rectangle((24, 156, 456, 288), outline=(220, 220, 220), width=2, fill=(252, 252, 252))
    for y_coord in (86, 98, 110, 182, 196, 210, 224):
        draw.line((40, y_coord, 200, y_coord), fill=(80, 80, 80), width=2)
    for y_coord in (86, 98, 110):
        draw.line((264, y_coord, 420, y_coord), fill=(80, 80, 80), width=2)
    draw.rectangle((312, 238, 432, 270), fill=(46, 125, 50))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_analyze_image_allows_semantic_redraw_for_diagram_like_jpeg():
    result = image_analysis.analyze_image(_make_diagram_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg")

    assert result.image_type == "diagram"
    assert result.semantic_redraw_allowed is True
    assert result.prompt_key == "diagram_semantic_redraw"
    assert result.render_strategy == "semantic_redraw_structured"


def test_analyze_image_keeps_photo_like_jpeg_in_safe_mode():
    result = image_analysis.analyze_image(_make_photo_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg")

    assert result.image_type == "photo"
    assert result.semantic_redraw_allowed is False
    assert result.prompt_key == "photo_safe_fallback"
    assert result.render_strategy == "safe_mode"


def test_analyze_image_routes_screenshot_like_png_to_safe_mode():
    result = image_analysis.analyze_image(_make_screenshot_like_png(), model="gpt-4.1", mime_type="image/png")

    assert result.image_type == "screenshot"
    assert result.semantic_redraw_allowed is False
    assert result.prompt_key == "screenshot_safe_fallback"
    assert result.render_strategy == "safe_mode"


def test_analyze_image_uses_vision_labels_when_available():
    client = _FakeResponsesClient(
        '{"image_type":"diagram","image_subtype":"flowchart","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.94,"structured_parse_confidence":0.91,'
        '"prompt_key":"diagram_semantic_redraw","render_strategy":"semantic_redraw_structured",'
        '"structure_summary":"three boxes connected by arrows","extracted_labels":["Start","Review","Finish"],'
        '"fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.image_type == "diagram"
    assert result.semantic_redraw_allowed is True
    assert result.extracted_labels == ["Start", "Review", "Finish"]
    assert result.contains_text is True