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


def _make_photo_like_png() -> bytes:
    image = Image.new("RGB", (480, 320))
    draw = ImageDraw.Draw(image)
    for x in range(480):
        for y in range(320):
            draw.point((x, y), fill=((x * 3) % 256, (y * 5) % 256, ((x + y) * 2) % 256))
    output = BytesIO()
    image.save(output, format="PNG")
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


def _make_infographic_like_png() -> bytes:
    """Bright, colorful PNG that the heuristic will classify as infographic."""
    image = Image.new("RGB", (480, 680), (240, 60, 60))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 460, 120), fill=(255, 200, 0))
    for row in range(4):
        y0 = 140 + row * 130
        draw.rectangle((20, y0, 220, y0 + 110), fill=(80, 160, 240))
        draw.rectangle((260, y0, 460, y0 + 110), fill=(80, 220, 130))
    for x in range(0, 480, 12):
        draw.line((x, 0, x, 680), fill=(255, 255, 255, 30), width=1)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_analyze_image_allows_semantic_redraw_for_diagram_like_jpeg():
    result = image_analysis.analyze_image(_make_diagram_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg")

    assert result.image_type == "diagram"
    assert result.semantic_redraw_allowed is True
    assert result.prompt_key == "diagram_semantic_redraw"
    assert result.render_strategy == "deterministic_reconstruction"


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


def test_analyze_image_keeps_photo_like_png_in_safe_mode_without_vision():
    result = image_analysis.analyze_image(_make_photo_like_png(), model="gpt-4.1", mime_type="image/png", enable_vision=False)

    assert result.image_type == "mixed_or_ambiguous"
    assert result.semantic_redraw_allowed is False
    assert result.prompt_key == "mixed_or_ambiguous_fallback"
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


def test_analyze_image_normalizes_bypass_route_from_vision_payload():
    client = _FakeResponsesClient(
        '{"image_type":"dense_document_or_table","image_subtype":"dense_table","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.93,"structured_parse_confidence":0.88,'
        '"prompt_key":"diagram_semantic_redraw","recommended_route":"bypass",'
        '"structure_summary":"dense table with many textual cells","extracted_labels":["A","B"],'
        '"text_node_count":26,"extracted_text":"A | B | C","fallback_reason":"text_density_too_high"}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.image_type == "dense_document_or_table"
    assert result.render_strategy == "safe_mode"
    assert result.semantic_redraw_allowed is False
    assert result.text_node_count == 26
    assert result.extracted_text == "A | B | C"


def test_analyze_image_applies_dense_text_routing_override_for_text_heavy_infographic():
    """When Vision reports ≥ DENSE_TEXT_BYPASS_THRESHOLD text nodes on an infographic,
    the merged result must be forced to safe_mode even if Vision said semantic_redraw_allowed=True."""
    client = _FakeResponsesClient(
        '{"image_type":"infographic","image_subtype":"editorial_infographic","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.88,"structured_parse_confidence":0.70,'
        '"prompt_key":"infographic_semantic_redraw","render_strategy":"semantic_redraw_direct",'
        '"structure_summary":"multi-column infographic with many text blocks",'
        '"extracted_labels":["A","B","C"],'
        '"text_node_count":22,"extracted_text":"headline | stat | body","fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_infographic_like_png(),
        model="gpt-4.1",
        mime_type="image/png",
        client=client,
        enable_vision=True,
    )

    assert result.render_strategy == "safe_mode"
    assert result.semantic_redraw_allowed is False
    assert result.text_node_count == 22
    assert result.fallback_reason is not None and "dense_text_bypass" in result.fallback_reason


def test_analyze_image_routes_dense_non_latin_infographic_to_safe_mode():
    client = _FakeResponsesClient(
        '{"image_type":"infographic","image_subtype":"comparison_chart","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.9,"structured_parse_confidence":0.8,'
        '"prompt_key":"infographic_semantic_redraw","recommended_route":"semantic_parse",'
        '"structure_summary":"comparison infographic with many text blocks",'
        '"extracted_labels":["Факти","Маніпуляції","Висновок"],'
        '"text_node_count":15,"extracted_text":"Факти проти маніпуляцій","fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_infographic_like_png(),
        model="gpt-4.1",
        mime_type="image/png",
        client=client,
        enable_vision=True,
        dense_text_bypass_threshold=18,
        non_latin_text_bypass_threshold=12,
    )

    assert result.render_strategy == "safe_mode"
    assert result.semantic_redraw_allowed is False
    assert result.text_node_count == 15
    assert result.fallback_reason is not None and "dense_non_latin_text_bypass" in result.fallback_reason


def test_analyze_image_normalizes_generic_semantic_redraw_to_reconstruction():
    client = _FakeResponsesClient(
        '{"image_type":"diagram","image_subtype":"comparative_matrix","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.9,"structured_parse_confidence":0.85,'
        '"prompt_key":"diagram_semantic_redraw","render_strategy":"semantic_redraw",'
        '"structure_summary":"three-column comparison table","extracted_labels":["A","B"],'
        '"text_node_count":6,"extracted_text":"A B","fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.render_strategy == "deterministic_reconstruction"
    assert result.semantic_redraw_allowed is True


def test_analyze_image_normalizes_prompt_key_like_semantic_redraw_route_to_reconstruction():
    client = _FakeResponsesClient(
        '{"image_type":"diagram","image_subtype":"comparative_matrix","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.9,"structured_parse_confidence":0.85,'
        '"prompt_key":"diagram_semantic_redraw","render_strategy":"diagram_semantic_redraw",'
        '"structure_summary":"three-column comparison table","extracted_labels":["A","B"],'
        '"text_node_count":6,"extracted_text":"A B","fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.render_strategy == "deterministic_reconstruction"
    assert result.semantic_redraw_allowed is True