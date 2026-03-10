"""Tests for the deterministic image reconstruction pipeline."""

import json
import math
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PIL import Image

from image_reconstruction import (
    _draw_arrowhead,
    _hex_to_rgba,
    _parse_scene_graph_json,
    _validate_scene_graph,
    render_scene_graph as _render_scene_graph_impl,
)
from models import ImageAnalysisResult


DEFAULT_TEST_RENDER_CONFIG = {
    "min_canvas_short_side_px": 100,
    "target_min_font_px": 8,
    "max_upscale_factor": 1.0,
}


def render_scene_graph(*args, **kwargs):
    kwargs.setdefault("render_config", DEFAULT_TEST_RENDER_CONFIG)
    return _render_scene_graph_impl(*args, **kwargs)


def _build_minimal_scene_graph(**overrides):
    sg = {
        "canvas": {"width": 200, "height": 100, "background_color": "#FFFFFF"},
        "elements": [],
    }
    sg.update(overrides)
    return sg


def _build_test_png(width=100, height=80, color=(200, 200, 200)):
    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Scene-graph JSON parsing
# ---------------------------------------------------------------------------


class TestParseSceneGraphJson:
    def test_parses_valid_json(self):
        raw = json.dumps({"canvas": {"width": 100, "height": 50}, "elements": []})
        result = _parse_scene_graph_json(raw)
        assert result["canvas"]["width"] == 100

    def test_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps({"canvas": {"width": 10, "height": 10}, "elements": []}) + "\n```"
        result = _parse_scene_graph_json(raw)
        assert result["canvas"]["width"] == 10

    def test_raises_on_invalid_json(self):
        try:
            _parse_scene_graph_json("not json at all")
            assert False, "Should have raised"
        except RuntimeError as exc:
            assert "невалидный JSON" in str(exc)

    def test_raises_on_non_dict(self):
        try:
            _parse_scene_graph_json("[1, 2, 3]")
            assert False, "Should have raised"
        except RuntimeError as exc:
            assert "JSON-объектом" in str(exc)


# ---------------------------------------------------------------------------
# Scene-graph validation
# ---------------------------------------------------------------------------


class TestValidateSceneGraph:
    def test_accepts_valid_scene_graph(self):
        sg = _build_minimal_scene_graph()
        _validate_scene_graph(sg)

    def test_rejects_missing_canvas(self):
        try:
            _validate_scene_graph({"elements": []})
            assert False, "Should have raised"
        except RuntimeError:
            pass

    def test_rejects_zero_dimensions(self):
        try:
            _validate_scene_graph({"canvas": {"width": 0, "height": 100}, "elements": []})
            assert False, "Should have raised"
        except RuntimeError:
            pass

    def test_rejects_missing_elements(self):
        try:
            _validate_scene_graph({"canvas": {"width": 100, "height": 100}})
            assert False, "Should have raised"
        except RuntimeError:
            pass


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------


class TestHexToRgba:
    def test_six_digit_hex(self):
        assert _hex_to_rgba("#FF0000") == (255, 0, 0, 255)

    def test_three_digit_hex(self):
        assert _hex_to_rgba("#F00") == (255, 0, 0, 255)

    def test_eight_digit_hex(self):
        assert _hex_to_rgba("#FF000080") == (255, 0, 0, 128)

    def test_returns_none_for_invalid(self):
        assert _hex_to_rgba("red") is None
        assert _hex_to_rgba(None) is None
        assert _hex_to_rgba("") is None


# ---------------------------------------------------------------------------
# Scene-graph rendering
# ---------------------------------------------------------------------------


class TestRenderSceneGraph:
    def test_renders_empty_canvas(self):
        sg = _build_minimal_scene_graph()
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)
            assert img.format == "PNG"

    def test_invalid_background_color_falls_back_to_white(self):
        sg = _build_minimal_scene_graph(canvas={"width": 200, "height": 100, "background_color": "not-a-color"})
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.getpixel((0, 0)) == (255, 255, 255, 255)

    def test_renders_rect_element(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "r1",
                    "type": "rect",
                    "x": 10,
                    "y": 10,
                    "width": 80,
                    "height": 40,
                    "fill": "#0000FF",
                    "stroke": "#000000",
                    "stroke_width": 2,
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            pixel = img.getpixel((50, 30))
            assert pixel[2] > 200

    def test_renders_text_element(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "t1",
                    "type": "text",
                    "x": 10,
                    "y": 10,
                    "width": 180,
                    "height": 30,
                    "text_content": "Hello",
                    "font_size": 14,
                    "font_color": "#000000",
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)

    def test_renders_left_aligned_text(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "t1",
                    "type": "text",
                    "x": 20,
                    "y": 10,
                    "width": 160,
                    "height": 30,
                    "text_content": "Hello",
                    "font_size": 18,
                    "font_color": "#000000",
                    "text_align": "left",
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            dark_columns = [
                x_coord
                for x_coord in range(img.width)
                if any(img.getpixel((x_coord, y_coord))[:3] != (255, 255, 255) for y_coord in range(img.height))
            ]
            assert min(dark_columns) < 40

    def test_renders_arrow_element(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "a1",
                    "type": "arrow",
                    "x1": 10,
                    "y1": 50,
                    "x2": 190,
                    "y2": 50,
                    "stroke": "#000000",
                    "stroke_width": 2,
                    "marker_end": "arrowhead",
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            pixel = img.getpixel((100, 50))
            assert pixel[0] < 50

    def test_renders_table_element(self):
        sg = _build_minimal_scene_graph(
            canvas={"width": 300, "height": 200, "background_color": "#FFFFFF"},
            elements=[
                {
                    "id": "tbl1",
                    "type": "table",
                    "x": 10,
                    "y": 10,
                    "width": 280,
                    "height": 180,
                    "rows": 2,
                    "cols": 2,
                    "stroke": "#000000",
                    "stroke_width": 1,
                    "z_index": 1,
                    "cells": [
                        {"row": 0, "col": 0, "text": "A", "bold": True, "fill": "#E0E0E0"},
                        {"row": 0, "col": 1, "text": "B", "bold": False},
                        {"row": 1, "col": 0, "text": "C", "bold": False},
                        {"row": 1, "col": 1, "text": "D", "bold": False},
                    ],
                }
            ],
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (300, 200)

    def test_renders_rounded_rect(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "rr1",
                    "type": "rounded_rect",
                    "x": 10,
                    "y": 10,
                    "width": 80,
                    "height": 40,
                    "fill": "#00FF00",
                    "corner_radius": 8,
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)

    def test_renders_diamond(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "d1",
                    "type": "diamond",
                    "x": 50,
                    "y": 10,
                    "width": 80,
                    "height": 80,
                    "fill": "#FFFF00",
                    "stroke": "#000000",
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)

    def test_renders_ellipse(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "el1",
                    "type": "ellipse",
                    "x": 10,
                    "y": 10,
                    "width": 80,
                    "height": 40,
                    "fill": "#FF00FF",
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)

    def test_renders_group_with_children(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "g1",
                    "type": "group",
                    "x": 0,
                    "y": 0,
                    "width": 200,
                    "height": 100,
                    "z_index": 0,
                    "children": [
                        {
                            "id": "g1_r1",
                            "type": "rect",
                            "x": 10,
                            "y": 10,
                            "width": 40,
                            "height": 30,
                            "fill": "#FF0000",
                            "z_index": 0,
                        },
                    ],
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)

    def test_resizes_to_original_size(self):
        sg = _build_minimal_scene_graph()
        png_bytes = render_scene_graph(sg, original_size=(400, 200))
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (400, 200)

    def test_uses_source_background_when_vlm_background_is_implausible(self):
        sg = _build_minimal_scene_graph(canvas={"width": 200, "height": 100, "background_color": "#000000"})
        source_png = _build_test_png(width=200, height=100, color=(255, 255, 255))

        png_bytes = render_scene_graph(
            sg,
            source_image_bytes=source_png,
            render_config={
                "background_sample_ratio": 0.05,
                "background_color_distance_threshold": 10.0,
                "background_uniformity_threshold": 1.0,
            },
        )

        with Image.open(BytesIO(png_bytes)) as img:
            assert img.getpixel((0, 0)) == (255, 255, 255, 255)

    def test_does_not_draw_default_black_border_for_invisible_rect(self):
        sg = _build_minimal_scene_graph(
            canvas={"width": 200, "height": 100, "background_color": "#FFFFFF"},
            elements=[
                {
                    "id": "bg",
                    "type": "rect",
                    "x": 0,
                    "y": 0,
                    "width": 200,
                    "height": 100,
                    "fill": None,
                    "stroke": None,
                    "z_index": 0,
                }
            ],
        )

        png_bytes = render_scene_graph(sg)

        with Image.open(BytesIO(png_bytes)) as img:
            assert img.getpixel((0, 0)) == (255, 255, 255, 255)
            assert img.getpixel((199, 99)) == (255, 255, 255, 255)

    def test_insets_full_canvas_table_frame_away_from_edges(self):
        sg = _build_minimal_scene_graph(
            canvas={"width": 200, "height": 100, "background_color": "#FFFFFF"},
            elements=[
                {
                    "id": "tbl",
                    "type": "table",
                    "x": 0,
                    "y": 0,
                    "width": 200,
                    "height": 100,
                    "rows": 1,
                    "cols": 1,
                    "fill": "#FFFFFF",
                    "stroke": "#000000",
                    "stroke_width": 1,
                    "cells": [{"row": 0, "col": 0, "text": "A"}],
                    "z_index": 0,
                }
            ],
        )

        png_bytes = render_scene_graph(sg)

        with Image.open(BytesIO(png_bytes)) as img:
            assert img.getpixel((0, 0)) == (255, 255, 255, 255)
            assert img.getpixel((1, 1))[0] < 32

    def test_upscales_low_resolution_scene_for_text_legibility(self):
        sg = _build_minimal_scene_graph(
            canvas={"width": 200, "height": 100, "background_color": "#FFFFFF"},
            elements=[
                {
                    "id": "t1",
                    "type": "text",
                    "x": 10,
                    "y": 10,
                    "width": 180,
                    "height": 40,
                    "text_content": "Small text",
                    "font_size": 8,
                    "font_color": "#000000",
                    "z_index": 1,
                }
            ],
        )

        png_bytes = render_scene_graph(
            sg,
            original_size=(200, 100),
            render_config={
                "min_canvas_short_side_px": 100,
                "target_min_font_px": 16,
                "max_upscale_factor": 3.0,
            },
        )

        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (512, 256)

    def test_z_order_sorting(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {"id": "bg", "type": "rect", "x": 0, "y": 0, "width": 200, "height": 100, "fill": "#0000FF", "z_index": 0},
                {"id": "fg", "type": "rect", "x": 50, "y": 25, "width": 100, "height": 50, "fill": "#FF0000", "z_index": 1},
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            pixel = img.getpixel((100, 50))
            assert pixel[0] > 200

    def test_renders_icon_placeholder(self):
        sg = _build_minimal_scene_graph(
            elements=[
                {
                    "id": "ic1",
                    "type": "icon_placeholder",
                    "x": 10,
                    "y": 10,
                    "width": 30,
                    "height": 30,
                    "text_content": "Logo",
                    "z_index": 1,
                }
            ]
        )
        png_bytes = render_scene_graph(sg)
        with Image.open(BytesIO(png_bytes)) as img:
            assert img.size == (200, 100)


# ---------------------------------------------------------------------------
# Integration: analysis → reconstruction routing
# ---------------------------------------------------------------------------


class TestReconstructionRouting:
    def test_diagram_like_jpeg_analysis_sets_deterministic_strategy(self):
        from image_analysis import analyze_image

        jpeg_bytes = _build_diagram_like_jpeg()
        client = SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    output_text=(
                        '{"image_type":"diagram","image_subtype":"comparison_matrix","contains_text":true,'
                        '"semantic_redraw_allowed":true,"confidence":0.9,"structured_parse_confidence":0.85,'
                        '"prompt_key":"diagram_semantic_redraw","render_strategy":"diagram_semantic_redraw",'
                        '"recommended_route":"diagram_semantic_redraw","structure_summary":"comparison diagram",'
                        '"extracted_labels":["A","B"],"text_node_count":6,"extracted_text":"A B","fallback_reason":null}'
                    )
                )
            )
        )
        result = analyze_image(jpeg_bytes, model="test-model", mime_type="image/jpeg", client=client)
        assert result.render_strategy == "deterministic_reconstruction"
        assert result.semantic_redraw_allowed is True

    def test_photo_analysis_keeps_safe_strategy(self):
        from image_analysis import analyze_image

        jpeg_bytes = _build_photo_like_jpeg()
        result = analyze_image(jpeg_bytes, model="test-model", mime_type="image/jpeg")
        assert result.render_strategy == "safe_mode"


def _build_diagram_like_png():
    """Build a PNG that looks like a diagram: mostly white, strong edges."""
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 80, 60], outline=(0, 0, 0), width=2)
    draw.rectangle([120, 20, 180, 60], outline=(0, 0, 0), width=2)
    draw.line([(80, 40), (120, 40)], fill=(0, 0, 0), width=2)
    draw.rectangle([20, 120, 80, 160], outline=(0, 0, 0), width=2)
    draw.line([(50, 60), (50, 120)], fill=(0, 0, 0), width=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _build_diagram_like_jpeg():
    img = Image.open(BytesIO(_build_diagram_like_png())).convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _build_photo_like_jpeg():
    """Build a JPEG that looks like a photo: lots of colors, no strong geometry."""
    import random

    random.seed(42)
    img = Image.new("RGB", (200, 200))
    for x in range(200):
        for y in range(200):
            img.putpixel((x, y), (random.randint(50, 200), random.randint(30, 180), random.randint(20, 150)))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Generation routing to reconstruction
# ---------------------------------------------------------------------------


class TestGenerationReconstructionPath:
    def test_reconstruction_strategy_triggers_reconstruction(self):
        """When render_strategy is deterministic_reconstruction, the generation
        function should attempt reconstruction instead of DALL-E semantic redraw."""
        analysis = ImageAnalysisResult(
            image_type="table",
            image_subtype=None,
            contains_text=True,
            semantic_redraw_allowed=True,
            confidence=0.85,
            structured_parse_confidence=0.8,
            prompt_key="table_semantic_redraw",
            render_strategy="deterministic_reconstruction",
            structure_summary="boxes and arrows",
            extracted_labels=["A", "B"],
        )
        png_bytes = _build_test_png()

        mock_scene_graph = _build_minimal_scene_graph(
            canvas={"width": 100, "height": 80, "background_color": "#FFFFFF"},
            elements=[
                {"id": "r1", "type": "rect", "x": 10, "y": 10, "width": 30, "height": 20, "fill": "#0000FF", "z_index": 0}
            ],
        )
        rendered_png = render_scene_graph(mock_scene_graph, original_size=(100, 80))

        with patch("image_generation._generate_reconstructed_candidate", return_value=rendered_png) as mock_recon:
            from image_generation import generate_image_candidate

            result = generate_image_candidate(png_bytes, analysis, mode="semantic_redraw_structured")
            mock_recon.assert_called_once()
            with Image.open(BytesIO(result)) as img:
                assert img.size == (100, 80)

    def test_reconstruction_fallback_to_safe_on_error(self):
        """If reconstruction fails, safe fallback should be used."""
        analysis = ImageAnalysisResult(
            image_type="table",
            image_subtype=None,
            contains_text=True,
            semantic_redraw_allowed=True,
            confidence=0.85,
            structured_parse_confidence=0.8,
            prompt_key="table_semantic_redraw",
            render_strategy="deterministic_reconstruction",
            structure_summary="boxes",
            extracted_labels=[],
        )
        png_bytes = _build_test_png()

        with patch(
            "image_generation.reconstruct_image",
            side_effect=RuntimeError("VLM API unavailable"),
        ):
            from image_generation import generate_image_candidate

            result = generate_image_candidate(png_bytes, analysis, mode="semantic_redraw_structured")
            assert result is not None
            assert len(result) > 0
            with Image.open(BytesIO(result)) as img:
                assert img.size == (100, 80)

    def test_safe_mode_bypasses_reconstruction(self):
        """Safe mode should never trigger reconstruction."""
        analysis = ImageAnalysisResult(
            image_type="diagram",
            image_subtype=None,
            contains_text=True,
            semantic_redraw_allowed=True,
            confidence=0.85,
            structured_parse_confidence=0.8,
            prompt_key="diagram_semantic_redraw",
            render_strategy="deterministic_reconstruction",
            structure_summary="boxes",
            extracted_labels=[],
        )
        png_bytes = _build_test_png()

        with patch("image_generation._generate_reconstructed_candidate") as mock_recon:
            from image_generation import generate_image_candidate

            result = generate_image_candidate(png_bytes, analysis, mode="safe")
            mock_recon.assert_not_called()
            assert result is not None
