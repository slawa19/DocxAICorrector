from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw

import docxaicorrector.image.analysis as image_analysis
import docxaicorrector.image.generation as image_generation


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

    # Spec 062 enum guard: a type outside ANALYSIS_IMAGE_TYPES no longer passes through
    # raw; it becomes mixed_or_ambiguous, on which a safe_mode route stays hard.
    assert result.image_type == "mixed_or_ambiguous"
    assert result.render_strategy == "safe_mode"
    assert result.semantic_redraw_allowed is False
    assert result.text_node_count == 26
    assert result.extracted_text == "A | B | C"


def test_analyze_image_applies_dense_text_routing_override_for_text_heavy_infographic():
    """When Vision reports ≥ DENSE_TEXT_BYPASS_THRESHOLD text nodes on an infographic,
    the bypass is recorded as ADVISORY (spec 062 FR-011): ``semantic_redraw_allowed`` is
    cleared and ``fallback_reason`` carries the advisory prefix, but ``render_strategy``
    keeps the analysis value instead of being overwritten with ``safe_mode``."""
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

    assert result.render_strategy == "deterministic_reconstruction"
    assert result.semantic_redraw_allowed is False
    assert result.text_node_count == 22
    assert result.fallback_reason is not None and "dense_text_bypass" in result.fallback_reason


def test_analyze_image_marks_dense_non_latin_infographic_as_advisory_bypass():
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

    assert result.render_strategy == "deterministic_reconstruction"
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


def test_analyze_image_falls_back_to_heuristic_prompt_key_when_vision_returns_unknown_key():
    client = _FakeResponsesClient(
        '{"image_type":"diagram","image_subtype":"flowchart","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.94,"structured_parse_confidence":0.91,'
        '"prompt_key":"diagram","render_strategy":"semantic_redraw_structured",'
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

    assert result.prompt_key == "diagram_semantic_redraw"
    assert result.image_type == "diagram"
    assert result.semantic_redraw_allowed is True


def test_analyze_image_unknown_prompt_key_still_allows_prompt_profile_loading_downstream():
    client = _FakeResponsesClient(
        '{"image_type":"diagram","image_subtype":"flowchart","contains_text":true,'
        '"semantic_redraw_allowed":true,"confidence":0.94,"structured_parse_confidence":0.91,'
        '"prompt_key":"diagram","render_strategy":"semantic_redraw_structured",'
        '"structure_summary":"three boxes connected by arrows","extracted_labels":["Start","Review","Finish"],'
        '"fallback_reason":null}'
    )
    source_bytes = _make_diagram_like_jpeg()

    result = image_analysis.analyze_image(
        source_bytes,
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    candidate_bytes = image_generation.generate_image_candidate(
        source_bytes,
        result,
        mode="safe",
    )

    assert result.prompt_key == "diagram_semantic_redraw"
    assert isinstance(candidate_bytes, bytes)
    assert candidate_bytes


def test_analyze_image_handles_string_booleans_from_vision_payload():
    client = _FakeResponsesClient(
        '{"image_type":"diagram","image_subtype":"flowchart","contains_text":"false",'
        '"semantic_redraw_allowed":"false","confidence":0.94,"structured_parse_confidence":0.91,'
        '"prompt_key":"diagram_semantic_redraw","render_strategy":"semantic_redraw_structured",'
        '"structure_summary":"three boxes connected by arrows","extracted_labels":["Start"],'
        '"fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.semantic_redraw_allowed is False
    assert result.contains_text is True


def test_analyze_image_handles_null_or_scalar_vision_fields_without_crashing():
    client = _FakeResponsesClient(
        '{"image_type":null,"image_subtype":null,"contains_text":null,'
        '"semantic_redraw_allowed":true,"confidence":0.94,"structured_parse_confidence":0.91,'
        '"prompt_key":"diagram_semantic_redraw","render_strategy":"semantic_redraw_structured",'
        '"structure_summary":null,"extracted_labels":"Start","fallback_reason":null}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.image_type == "diagram"
    assert result.image_subtype == "jpeg_diagram_like"
    assert result.structure_summary == "JPEG image with diagram-like visual features; structure not analysed."
    assert result.extracted_labels == ["Start"]


def test_analyze_image_logs_and_falls_back_when_vision_errors(monkeypatch):
    logged_events = []

    class FailingClient:
        class Responses:
            def create(self, **kwargs):
                raise RuntimeError("vision boom")

        responses = Responses()

    monkeypatch.setattr(image_analysis, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=FailingClient(),
        enable_vision=True,
    )

    assert result.image_type == "diagram"
    assert result.render_strategy == "deterministic_reconstruction"
    assert logged_events == [
        (
            "image_analysis_vision_fallback_after_error",
            {
                "model": "gpt-4.1",
                "mime_type": "image/jpeg",
                "error_type": "RuntimeError",
                "error_message": "vision boom",
                "error_code": None,
                "response_stage": "vision_analysis",
            },
        )
    ]


def test_analyze_image_reads_nested_response_output_for_json_payload():
    class NestedOutputClient:
        class Responses:
            def create(self, **kwargs):
                return SimpleNamespace(
                    output=[
                        SimpleNamespace(
                            content=[
                                SimpleNamespace(
                                    type="output_text",
                                    text='{"image_type":"diagram","image_subtype":null,"contains_text":true,'
                                    '"semantic_redraw_allowed":true,"confidence":0.9,'
                                    '"structured_parse_confidence":0.8,"prompt_key":"diagram_semantic_redraw",'
                                    '"render_strategy":"deterministic_reconstruction","structure_summary":"nested output",'
                                    '"extracted_labels":["A"],"text_node_count":1,"extracted_text":"A","fallback_reason":null}'
                                )
                            ]
                        )
                    ]
                )

        responses = Responses()

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=NestedOutputClient(),
        enable_vision=True,
    )

    assert result.structure_summary == "nested output"
    assert result.extracted_labels == ["A"]


def test_analyze_image_logs_and_falls_back_when_vision_returns_incomplete_response(monkeypatch):
    logged_events = []

    class IncompleteClient:
        class Responses:
            def create(self, **kwargs):
                return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

        responses = Responses()

    monkeypatch.setattr(image_analysis, "log_event", lambda level, event, message, **context: logged_events.append((event, context)))

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=IncompleteClient(),
        enable_vision=True,
    )

    assert result.image_type == "diagram"
    assert logged_events[0][0] == "image_analysis_vision_fallback_after_error"
    assert logged_events[0][1]["error_message"] == "Vision analysis returned incomplete output."
    assert logged_events[0][1]["error_code"] == "incomplete_response"
    assert logged_events[0][1]["response_stage"] == "vision_analysis"


def test_extract_visual_features_rejects_oversized_header_before_decode(monkeypatch):
    """An image whose header reports oversized dimensions is rejected BEFORE
    the pixel decode (.load()) runs, a WARNING is logged, and the skip result
    (None visual features) is returned."""
    image_bytes = _make_diagram_like_jpeg()  # 480x320

    load_calls = {"count": 0}
    real_load = Image.Image.load

    def spy_load(self, *args, **kwargs):
        load_calls["count"] += 1
        return real_load(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "load", spy_load)
    # Shrink the dimension budget so the ordinary synthetic image trips it.
    monkeypatch.setattr(image_analysis, "MAX_IMAGE_DIMENSION_PX", 100)

    logged_events = []
    monkeypatch.setattr(
        image_analysis,
        "log_event",
        lambda level, event, message, **context: logged_events.append((event, context)),
    )

    features = image_analysis._extract_visual_features(image_bytes)

    assert features is None
    assert load_calls["count"] == 0
    assert logged_events and logged_events[0][0] == "image_pixel_budget_exceeded"
    assert logged_events[0][1]["width"] == 480
    assert logged_events[0][1]["height"] == 320
    assert logged_events[0][1]["stage"] == "image_visual_feature_extraction"


def test_extract_visual_features_rejects_by_megapixel_budget(monkeypatch):
    """Rejection also fires on the megapixel budget even when per-side
    dimensions are individually under MAX_IMAGE_DIMENSION_PX."""
    image_bytes = _make_diagram_like_jpeg()  # 480x320 -> 0.1536 MP

    monkeypatch.setattr(image_analysis, "MAX_IMAGE_MEGAPIXELS", 0.1)

    logged_events = []
    monkeypatch.setattr(
        image_analysis,
        "log_event",
        lambda level, event, message, **context: logged_events.append((event, context)),
    )

    features = image_analysis._extract_visual_features(image_bytes)

    assert features is None
    assert logged_events and logged_events[0][0] == "image_pixel_budget_exceeded"


def test_extract_visual_features_surfaces_decompression_bomb(monkeypatch):
    """A real DecompressionBombError raised while reading the header is logged
    (surfaced), not silently swallowed, and the image is skipped."""

    def boom(*args, **kwargs):
        raise Image.DecompressionBombError("bomb")

    monkeypatch.setattr(image_analysis.Image, "open", boom)

    logged_events = []
    monkeypatch.setattr(
        image_analysis,
        "log_event",
        lambda level, event, message, **context: logged_events.append((event, context)),
    )

    features = image_analysis._extract_visual_features(b"irrelevant-bytes")

    assert features is None
    assert logged_events and logged_events[0][0] == "image_pixel_budget_decompression_bomb"
    assert logged_events[0][1]["error_type"] == "DecompressionBombError"


def test_extract_visual_features_processes_normal_image_within_budget():
    """A normally-sized image still decodes and yields visual features (the
    guard does not disturb existing behaviour)."""
    features = image_analysis._extract_visual_features(_make_diagram_like_jpeg())

    assert features is not None
    assert {"white_ratio", "edge_ratio", "bright_ratio"} <= set(features)


class _NoCallResponsesClient:
    """Vision client that fails loudly if the API is ever invoked."""

    def __init__(self):
        self.responses = self

    def create(self, **kwargs):
        raise AssertionError("vision API must not be called for an over-budget image")


def test_analyze_image_over_budget_skips_base64_and_vision(monkeypatch):
    """An oversized image handed to analyze_image is NOT base64-encoded and NOT
    sent to the vision API: a WARNING is logged and a safe degraded result is
    returned (finding F8)."""
    # Shrink the per-side budget so the ordinary synthetic image trips it.
    monkeypatch.setattr(image_analysis, "MAX_IMAGE_DIMENSION_PX", 100)

    b64_calls = {"count": 0}
    real_b64encode = image_analysis.base64.b64encode

    def spy_b64encode(data, *args, **kwargs):
        b64_calls["count"] += 1
        return real_b64encode(data, *args, **kwargs)

    monkeypatch.setattr(image_analysis.base64, "b64encode", spy_b64encode)

    logged_events = []
    monkeypatch.setattr(
        image_analysis,
        "log_event",
        lambda level, event, message, **context: logged_events.append((event, context)),
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),  # 480x320, over the shrunk 100px budget
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=_NoCallResponsesClient(),
        enable_vision=True,
    )

    # No base64 encode -> nothing was uploaded to the vision API.
    assert b64_calls["count"] == 0
    assert result.render_strategy == "safe_mode"
    assert result.semantic_redraw_allowed is False
    assert result.fallback_reason == "pixel_budget_exceeded"
    assert any(event == "image_analysis_skipped_over_budget" for event, _ in logged_events)


def test_analyze_image_within_budget_still_calls_vision():
    """A normally-sized image is unaffected by the gate and still reaches the
    vision path (behaviour preserved)."""
    client = _FakeResponsesClient(
        '{"image_type":"diagram","semantic_redraw_allowed":true,'
        '"prompt_key":"diagram_semantic_redraw","render_strategy":"semantic_redraw_structured",'
        '"structure_summary":"three boxes","extracted_labels":["Start","Finish"]}'
    )

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert result.extracted_labels == ["Start", "Finish"]


def test_image_budget_admits_within_document_total():
    budget = image_analysis.ImageBudget(max_total_megapixels=1.0)

    assert budget.admit(_make_diagram_like_jpeg(), stage="doc") is True
    assert budget.admitted_images == 1
    assert budget.used_megapixels > 0.0


def test_image_budget_skips_once_document_total_exceeded(monkeypatch):
    """Two individually-legal images whose combined footprint exceeds the
    document cap: the second is skipped with a WARNING (finding F8, part 2)."""
    logged_events = []
    monkeypatch.setattr(
        image_analysis,
        "log_event",
        lambda level, event, message, **context: logged_events.append((event, context)),
    )
    # 480x320 -> 0.1536 MP each; cap admits one but not two.
    budget = image_analysis.ImageBudget(max_total_megapixels=0.2)

    assert budget.admit(_make_diagram_like_jpeg(), stage="doc") is True
    assert budget.admit(_make_diagram_like_jpeg(), stage="doc") is False
    assert budget.admitted_images == 1
    assert budget.skipped_images == 1
    assert any(event == "image_document_pixel_budget_exceeded" for event, _ in logged_events)


def test_image_budget_rejects_per_image_over_budget(monkeypatch):
    """A single over-per-image-budget image is rejected by admit and not charged
    against the document total."""
    monkeypatch.setattr(image_analysis, "MAX_IMAGE_DIMENSION_PX", 100)
    budget = image_analysis.ImageBudget()

    assert budget.admit(_make_diagram_like_jpeg(), stage="doc") is False
    assert budget.skipped_images == 1
    assert budget.used_megapixels == 0.0


# --- spec 062 P1: analysis prompt, structural fallback, advisory bypass -------------


class _CapturingResponsesClient:
    def __init__(self, output_text: str):
        self.output_text = output_text
        self.requests: list[dict] = []
        self.responses = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


def _vision_user_text(request: dict) -> str:
    user_message = request["input"][1]
    return next(part["text"] for part in user_message["content"] if part["type"] == "input_text")


def test_vision_analysis_prompt_names_allowed_values_and_registry_keys():
    """FR-008: the prompt names every value routing keys on, takes prompt keys from the
    registry, drops the duplicate ``render_strategy`` key and the heuristic baseline.
    Fails on the old prompt, which listed bare key names without allowed values."""
    from docxaicorrector.image.prompts import load_image_prompt_registry

    client = _CapturingResponsesClient('{"image_type":"diagram","semantic_redraw_allowed":true}')
    image_analysis.analyze_image(
        _make_diagram_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg", client=client, enable_vision=True
    )

    text = _vision_user_text(client.requests[0])
    for prompt_key in load_image_prompt_registry()["prompts"]:
        assert f'"{prompt_key}"' in text
    for image_type in image_analysis.ANALYSIS_IMAGE_TYPES:
        assert f'"{image_type}"' in text
    for route in image_analysis.ANALYSIS_ROUTES:
        assert f'"{route}"' in text
    assert "render_strategy" not in text
    assert "Heuristic baseline" not in text
    assert "`text_node_count`: integer count of separate text blocks" in text
    # FR-020: the copy rule is script-agnostic, not tied to three named languages.
    assert image_analysis.TEXT_COPY_RULE in text
    assert "Cyrillic, Ukrainian, and Russian" not in text
    # FR-024 (P2, done after the Cyrillic gate passed for the structured mode): the
    # dense-text sentence is gone; test_vision_analysis_prompts_never_send_dense_or_non_latin_text_to_safe
    # checks both prompts.
    assert "If text is too dense for faithful redraw, set recommended_route to safe_mode." not in text


def test_valid_prompt_keys_follow_the_registry(monkeypatch):
    """FR-022: the parser's accepted keys are the registry's keys, not a hand-kept copy."""
    monkeypatch.setattr(
        image_analysis,
        "load_image_prompt_registry",
        lambda: {"prompts": {"diagram_semantic_redraw": {}, "only_in_registry": {}}},
    )

    assert image_analysis.valid_prompt_keys() == ("diagram_semantic_redraw", "only_in_registry")
    heuristic = image_analysis._build_heuristic_analysis("image/jpeg", None)
    coerced = image_analysis._coerce_vision_analysis_payload({"prompt_key": "only_in_registry"}, heuristic)
    assert coerced.prompt_key == "only_in_registry"
    rejected = image_analysis._coerce_vision_analysis_payload({"prompt_key": "chart_semantic_redraw"}, heuristic)
    assert rejected.prompt_key == heuristic.prompt_key


def test_normalize_render_strategy_has_no_model_name_branch_and_rejects_unknown_routes():
    """FR-008 (W9, D8): ``gpt-…`` no longer means "structured redraw", and an unknown route
    keeps the heuristic strategy instead of passing through raw."""
    assert image_analysis._normalize_render_strategy("gpt-image-1", "safe_mode") == ("safe_mode", False)
    assert image_analysis._normalize_render_strategy("freestyle", "safe_mode") == ("safe_mode", False)
    # Counter-proof: every route the prompt offers is still honoured.
    assert image_analysis._normalize_render_strategy("semantic_redraw_direct", "safe_mode") == (
        "semantic_redraw_direct",
        False,
    )
    assert image_analysis._normalize_render_strategy("semantic_redraw_structured", "safe_mode") == (
        "semantic_redraw_structured",
        False,
    )
    assert image_analysis._normalize_render_strategy("deterministic_reconstruction", "safe_mode") == (
        "deterministic_reconstruction",
        False,
    )
    assert image_analysis._normalize_render_strategy("safe_mode", "deterministic_reconstruction") == ("safe_mode", True)


def test_diagram_jpeg_with_failed_vision_gets_structural_fallback_and_still_routes():
    """FR-009 anti-vacuum: the heuristic no longer invents "three boxes connected by arrows"
    for every diagram-like JPEG, and the image still routes as a redrawable diagram."""

    class FailingClient:
        class Responses:
            def create(self, **kwargs):
                raise RuntimeError("vision boom")

        responses = Responses()

    result = image_analysis.analyze_image(
        _make_diagram_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg", client=FailingClient(), enable_vision=True
    )

    assert "three boxes" not in result.structure_summary
    assert not any(character.isdigit() for character in result.structure_summary)
    for content_word in ("box", "arrow", "three", "connected"):
        assert content_word not in result.structure_summary.lower()
    assert "structure not analysed" in result.structure_summary
    # Routing is unchanged by the new summary.
    assert result.image_type == "diagram"
    assert result.prompt_key == "diagram_semantic_redraw"
    assert result.render_strategy == "deterministic_reconstruction"
    assert result.semantic_redraw_allowed is True


def test_non_latin_detector_keys_on_script_not_on_code_point():
    """FR-011 (D9): Latin letters with diacritics are Latin; Cyrillic, Greek and CJK are not.
    The old ``ord > 127`` check returned True for the first case."""
    assert image_analysis._contains_non_latin_text("Größe der Straße, école, łódź, niño", []) is False
    assert image_analysis._contains_non_latin_text("Plain ASCII 123", []) is False
    assert image_analysis._contains_non_latin_text("", ["Факти"]) is True
    assert image_analysis._contains_non_latin_text("Ελληνικά", []) is True
    assert image_analysis._contains_non_latin_text("中文标签", []) is True


def test_dense_latin_diacritics_infographic_does_not_trip_non_latin_bypass():
    client = _FakeResponsesClient(
        '{"image_type":"infographic","contains_text":true,"semantic_redraw_allowed":true,'
        '"prompt_key":"infographic_semantic_redraw","recommended_route":"semantic_redraw_direct",'
        '"structure_summary":"infographic","extracted_labels":["Größe","Straße","Übersicht"],'
        '"text_node_count":14,"extracted_text":"Größe und Übersicht","fallback_reason":null}'
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

    assert result.fallback_reason is None
    assert result.semantic_redraw_allowed is True


def _analyze_with_vision_payload(payload: str):
    return image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="gpt-4.1",
        mime_type="image/jpeg",
        client=_FakeResponsesClient(payload),
        enable_vision=True,
        dense_text_bypass_threshold=18,
        non_latin_text_bypass_threshold=12,
    )


def test_dense_table_keeps_reconstruction_route_in_structured_mode(monkeypatch):
    """Anti-regression (spec 062, FR-011/FR-012): a table with ≥ 18 text nodes goes to
    deterministic reconstruction in ``semantic_redraw_structured``; before the fix the bypass
    overwrote ``render_strategy`` with ``safe_mode`` and the table lost the PIL route."""
    from docxaicorrector.image.pipeline_policy import build_generation_analysis

    analysis = _analyze_with_vision_payload(
        '{"image_type":"table","contains_text":true,"semantic_redraw_allowed":true,'
        '"prompt_key":"table_semantic_redraw","recommended_route":"deterministic_reconstruction",'
        '"structure_summary":"table with 6 rows and 4 columns","extracted_labels":["A","B"],'
        '"text_node_count":22,"extracted_text":"A B","fallback_reason":null}'
    )
    assert analysis.fallback_reason == "dense_text_bypass:22_nodes"

    reconstruction_calls = []
    monkeypatch.setattr(
        image_generation,
        "_generate_reconstructed_candidate",
        lambda image_bytes, analysis, **kwargs: reconstruction_calls.append(analysis) or b"reconstructed",
    )

    def _no_semantic(*args, **kwargs):
        raise AssertionError("dense table must not take the generative route")

    monkeypatch.setattr(image_generation, "_generate_semantic_candidate", _no_semantic)

    candidate = image_generation.generate_image_candidate(
        _make_diagram_like_jpeg(),
        build_generation_analysis(analysis),
        mode="semantic_redraw_structured",
        client=object(),
    )

    assert candidate == b"reconstructed"
    assert len(reconstruction_calls) == 1


def test_model_safe_route_table_keeps_reconstruction_when_heuristic_saw_a_screenshot(monkeypatch):
    """Acceptance review 2026-11-07, finding 2: the routing guard restored the HEURISTIC's
    ``render_strategy``. When the heuristic typed the raster table a screenshot, that was
    ``safe_mode``, so the restored redraw skipped reconstruction and the dense table went
    to the generative path (FR-012). The review's exact input."""
    from dataclasses import replace

    from docxaicorrector.image.pipeline_policy import build_generation_analysis, should_attempt_semantic_redraw

    screenshot_heuristic = replace(
        image_analysis._build_heuristic_analysis("image/png", None),
        image_type="screenshot",
        prompt_key="screenshot_safe_fallback",
        render_strategy="safe_mode",
        semantic_redraw_allowed=False,
    )
    monkeypatch.setattr(image_analysis, "_build_heuristic_analysis", lambda *args, **kwargs: screenshot_heuristic)

    analysis = _analyze_with_vision_payload(
        '{"image_type":"table","contains_text":true,"semantic_redraw_allowed":false,'
        '"prompt_key":"table_semantic_redraw","recommended_route":"safe_mode",'
        '"structure_summary":"table with 6 rows and 4 columns","extracted_labels":["A","B"],'
        '"text_node_count":22,"extracted_text":"A B","fallback_reason":"Dense table."}'
    )

    assert analysis.image_type == "table"
    assert analysis.render_strategy == "deterministic_reconstruction"
    assert should_attempt_semantic_redraw(analysis, "semantic_redraw_structured") is True

    reconstruction_calls = []
    monkeypatch.setattr(
        image_generation,
        "_generate_reconstructed_candidate",
        lambda image_bytes, analysis, **kwargs: reconstruction_calls.append(analysis) or b"reconstructed",
    )

    def _no_semantic(*args, **kwargs):
        raise AssertionError("a dense table must take the PIL reconstruction route")

    monkeypatch.setattr(image_generation, "_generate_semantic_candidate", _no_semantic)

    candidate = image_generation.generate_image_candidate(
        _make_diagram_like_jpeg(),
        build_generation_analysis(analysis),
        mode="semantic_redraw_structured",
        client=object(),
    )

    assert candidate == b"reconstructed"
    assert len(reconstruction_calls) == 1


def test_model_safe_route_keeps_a_heuristic_redraw_strategy():
    """Counter-proof for the test above: when the heuristic already named a redraw route,
    the guard keeps it rather than forcing reconstruction."""
    from dataclasses import replace

    heuristic = replace(
        image_analysis._build_heuristic_analysis("image/png", None),
        image_type="chart",
        render_strategy="semantic_redraw_direct",
    )
    payload: dict[str, object] = {"image_type": "chart", "recommended_route": "safe_mode", "fallback_reason": "Dense chart."}

    analysis = image_analysis._coerce_vision_analysis_payload(payload, heuristic)

    assert analysis.fallback_reason == "model_safe_route:Dense chart."
    assert analysis.render_strategy == "semantic_redraw_direct"


def test_photo_or_screenshot_is_never_redrawn_even_when_the_answer_allows_it():
    """Acceptance review 2026-11-07 (note on ``pipeline_policy.py:28``): a contradictory
    answer — ``photo`` with ``semantic_redraw_allowed=true`` and a redraw prompt key — passed
    the flag check. The type is an absolute guard now."""
    from dataclasses import replace

    from docxaicorrector.image.pipeline_policy import should_attempt_semantic_redraw

    redrawable = replace(
        image_analysis._build_heuristic_analysis("image/png", None),
        image_type="diagram",
        semantic_redraw_allowed=True,
        prompt_key="diagram_semantic_redraw",
        render_strategy="semantic_redraw_structured",
    )
    assert should_attempt_semantic_redraw(redrawable, "semantic_redraw_structured") is True
    for image_type in ("photo", "screenshot"):
        contradictory = replace(redrawable, image_type=image_type)
        for mode in ("semantic_redraw_structured", "semantic_redraw_direct", "compare_all"):
            assert should_attempt_semantic_redraw(contradictory, mode) is False, (image_type, mode)


def test_dense_photo_does_not_reach_reconstruction(monkeypatch):
    """Counter-proof for the test above: the same text-node count on a photo does not
    send it to reconstruction (nor to a generative redraw)."""
    from docxaicorrector.image.pipeline_policy import build_generation_analysis

    analysis = _analyze_with_vision_payload(
        '{"image_type":"photo","contains_text":true,"semantic_redraw_allowed":false,'
        '"prompt_key":"photo_safe_fallback","recommended_route":"safe_mode",'
        '"structure_summary":"street photo with signs","extracted_labels":["A"],'
        '"text_node_count":22,"extracted_text":"A","fallback_reason":null}'
    )

    def _forbidden(*args, **kwargs):
        raise AssertionError("photo must stay on the safe route")

    monkeypatch.setattr(image_generation, "_generate_reconstructed_candidate", _forbidden)
    monkeypatch.setattr(image_generation, "_generate_semantic_candidate", _forbidden)

    candidate = image_generation.generate_image_candidate(
        _make_diagram_like_jpeg(),
        build_generation_analysis(analysis),
        mode="semantic_redraw_structured",
        client=object(),
    )

    assert isinstance(candidate, bytes) and candidate


# --- spec 062 P2: FR-024, the routing guard and the enum guard ------------------------------

# The raw vision payloads ``gpt-6.1-terra`` returned in the spec 062 image comparison
# (2026-11-07, ``analysis/analysis_gpt-6.1-terra.json``) for the Cyrillic infographic and for
# the dense chart img_027. Both carry ``semantic_redraw_allowed: false`` WITH
# ``recommended_route: "safe_mode"``, as did sol's; mini typed the same images as redrawable.
_TERRA_INFOGRAPHIC_PAYLOAD = {
    "image_type": "infographic",
    "image_subtype": "Ukrainian facts-versus-manipulation comparison poster",
    "contains_text": True,
    "semantic_redraw_allowed": False,
    "confidence": 0.99,
    "structured_parse_confidence": 0.84,
    "prompt_key": "infographic_semantic_redraw",
    "recommended_route": "safe_mode",
    "structure_summary": (
        "One comparison infographic contains five annotated groups, one central illustration, "
        "one news label, and three organization logos."
    ),
    "extracted_labels": [
        "ФАКТИ VS МАНІПУЛЯЦІЇ",
        "не вказано",
        "підміняється",
        "Фактична інформація",
        "Категоричний висновок",
        "вставні слова та епітети",
        "НОВИНА",
        "Вказується",
        "неможливо",
        "можливо",
        "Оціночні судження",
        "Конкретні факти",
    ],
    "text_node_count": 21,
    "extracted_text": "ФАКТИ VS МАНІПУЛЯЦІЇ\nЯк зрозуміти, що у новині використовуються оціночні судження?",
    "fallback_reason": "Dense Cyrillic comparison poster with complex decorative illustration and small logo text.",
}
_TERRA_CHART_PAYLOAD = {
    "image_type": "chart",
    "image_subtype": "stacked area chart",
    "contains_text": True,
    "semantic_redraw_allowed": False,
    "confidence": 0.9,
    "structured_parse_confidence": 0.8,
    "prompt_key": "chart_semantic_redraw",
    "recommended_route": "safe_mode",
    "structure_summary": "A stacked area chart with 4 series, 13 y ticks and 37 x ticks.",
    "extracted_labels": ["1970", "1975", "1980"],
    "text_node_count": 56,
    "extracted_text": "1970 1975 1980",
    "fallback_reason": "Exact series values cannot be recovered reliably from the image.",
}


def _analyze_payload(payload: dict) -> "image_analysis.ImageAnalysisResult":
    import json

    return _analyze_with_vision_payload(json.dumps(payload, ensure_ascii=False))


def _system_text(request: dict) -> str:
    system_message = request["input"][0]
    return next(part["text"] for part in system_message["content"] if part["type"] == "input_text")


def test_vision_analysis_prompts_never_send_dense_or_non_latin_text_to_safe():
    """FR-024 (D2): neither prompt tells the model to prefer safe_mode for dense or
    non-Latin text. Fails on the old prompts ("especially in Cyrillic or mixed non-Latin
    text, should prefer safe_mode"; "If text is too dense ... safe_mode")."""
    client = _CapturingResponsesClient('{"image_type":"diagram","semantic_redraw_allowed":true}')
    image_analysis.analyze_image(
        _make_diagram_like_jpeg(), model="gpt-4.1", mime_type="image/jpeg", client=client, enable_vision=True
    )

    system_text = _system_text(client.requests[0])
    user_text = _vision_user_text(client.requests[0])
    for text in (system_text, user_text):
        assert "Cyrillic" not in text
        assert "non-Latin" not in text
        assert "too dense" not in text
        assert "Dense" not in text
    # Anti-vacuum: the photo/screenshot advice survives, so safe_mode is still offered.
    assert "Screenshots and photos should usually stay in safe_mode" in system_text
    assert '"safe_mode"' in user_text


def test_model_safe_route_on_redrawable_type_is_advisory_in_semantic_modes(monkeypatch):
    """Routing guard: terra's safe_mode for the Cyrillic infographic no longer switches the
    redraw off in the semantic modes the user chose; ``safe`` still makes no redraw."""
    from docxaicorrector.image.pipeline_policy import (
        build_generation_analysis,
        is_advisory_safe_fallback,
        should_attempt_semantic_redraw,
    )

    analysis = _analyze_payload(_TERRA_INFOGRAPHIC_PAYLOAD)

    assert analysis.image_type == "infographic"
    assert analysis.semantic_redraw_allowed is False
    assert analysis.fallback_reason == (
        "model_safe_route:Dense Cyrillic comparison poster with complex decorative illustration and small logo text."
    )
    assert analysis.render_strategy != "safe_mode"
    assert is_advisory_safe_fallback(analysis) is True
    assert should_attempt_semantic_redraw(analysis, "semantic_redraw_structured") is True
    assert should_attempt_semantic_redraw(analysis, "semantic_redraw_direct") is True
    assert should_attempt_semantic_redraw(analysis, "safe") is False
    assert should_attempt_semantic_redraw(analysis, "no_change") is False

    semantic_calls: list[str] = []

    def _fake_semantic(image_bytes, generation_analysis, *, requested_mode, **kwargs):
        semantic_calls.append(requested_mode)
        return b"redrawn"

    monkeypatch.setattr(image_generation, "_generate_semantic_candidate", _fake_semantic)
    candidate = image_generation.generate_image_candidate(
        _make_diagram_like_jpeg(),
        build_generation_analysis(analysis),
        mode="semantic_redraw_structured",
        client=object(),
    )

    assert candidate == b"redrawn"
    assert semantic_calls == ["semantic_redraw_structured"]


def test_model_safe_route_on_dense_chart_is_advisory():
    """The second terra shape: the chart's free reason is about the series values."""
    from docxaicorrector.image.pipeline_policy import build_generation_analysis, should_attempt_semantic_redraw

    analysis = _analyze_payload(_TERRA_CHART_PAYLOAD)

    assert analysis.fallback_reason is not None
    assert analysis.fallback_reason.startswith("model_safe_route:")
    assert should_attempt_semantic_redraw(analysis, "semantic_redraw_structured") is True
    assert build_generation_analysis(analysis).semantic_redraw_allowed is True


def test_model_safe_route_without_reason_is_still_advisory():
    payload = dict(_TERRA_CHART_PAYLOAD, fallback_reason=None)

    analysis = _analyze_payload(payload)

    assert analysis.fallback_reason == "model_safe_route:unspecified"


def test_model_safe_route_on_photo_screenshot_or_unknown_type_stays_hard(monkeypatch):
    """Anti-vacuum for the routing guard: a photo, a screenshot and an out-of-enum type the
    model sent to safe_mode get no redraw in any semantic mode."""
    from docxaicorrector.image.pipeline_policy import build_generation_analysis, should_attempt_semantic_redraw

    def _forbidden(*args, **kwargs):
        raise AssertionError("a photo, screenshot or unclassified image must stay on the safe route")

    monkeypatch.setattr(image_generation, "_generate_semantic_candidate", _forbidden)
    monkeypatch.setattr(image_generation, "_generate_reconstructed_candidate", _forbidden)

    for image_type, prompt_key in (
        ("photo", "photo_safe_fallback"),
        ("screenshot", "screenshot_safe_fallback"),
        ("logo", "mixed_or_ambiguous_fallback"),
    ):
        payload = dict(
            _TERRA_INFOGRAPHIC_PAYLOAD,
            image_type=image_type,
            prompt_key=prompt_key,
            fallback_reason="Cover page with text and logo.",
        )
        analysis = _analyze_payload(payload)

        assert analysis.render_strategy == "safe_mode"
        assert analysis.semantic_redraw_allowed is False
        assert analysis.fallback_reason == "Cover page with text and logo."
        for mode in ("semantic_redraw_structured", "semantic_redraw_direct", "compare_all"):
            assert should_attempt_semantic_redraw(analysis, mode) is False
        candidate = image_generation.generate_image_candidate(
            _make_diagram_like_jpeg(),
            build_generation_analysis(analysis),
            mode="semantic_redraw_structured",
            client=object(),
        )
        assert isinstance(candidate, bytes) and candidate


def test_image_type_outside_the_enum_becomes_mixed_or_ambiguous_with_warning(monkeypatch):
    """Enum guard (comparison finding 6: mini answered "logo" for 2 of 43 book images)."""
    logged: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(
        image_analysis,
        "log_event",
        lambda level, event, message, **context: logged.append((level, event, context)),
    )
    heuristic = image_analysis._build_heuristic_analysis("image/jpeg", None)

    logo = image_analysis._coerce_vision_analysis_payload({"image_type": "logo"}, heuristic)
    assert logo.image_type == "mixed_or_ambiguous"
    assert [(level, event) for level, event, _ in logged] == [(30, "image_analysis_image_type_out_of_enum")]
    assert logged[0][2]["image_type"] == "logo"

    logged.clear()
    # Counter-proof: allowed values (any case) pass without a warning; a missing value keeps
    # the heuristic type as before.
    assert image_analysis._coerce_vision_analysis_payload({"image_type": "Diagram"}, heuristic).image_type == "diagram"
    assert image_analysis._coerce_vision_analysis_payload({"image_type": "table"}, heuristic).image_type == "table"
    assert image_analysis._coerce_vision_analysis_payload({}, heuristic).image_type == heuristic.image_type
    assert logged == []


def test_analysis_request_carries_the_api_model_id_without_provider_prefix():
    """Acceptance review 2026-11-07, finding 3: a valid ``openai:`` selector reached the
    Responses API as is; the request carries the bare id."""
    client = _CapturingResponsesClient('{"image_type":"diagram","semantic_redraw_allowed":true}')

    image_analysis.analyze_image(
        _make_diagram_like_jpeg(),
        model="openai:gpt-5.4-mini",
        mime_type="image/jpeg",
        client=client,
        enable_vision=True,
    )

    assert client.requests[0]["model"] == "gpt-5.4-mini"
