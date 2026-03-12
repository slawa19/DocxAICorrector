"""Deterministic image reconstruction via VLM scene-graph extraction + PIL rendering.

This module replaces hallucination-prone generative redraw with a two-step pipeline:
1. A multimodal VLM extracts a structured JSON scene graph from the source image.
2. PIL renders the scene graph to a pixel-identical PNG — no generative model involved.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import math
import os
from io import BytesIO
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from constants import PROMPTS_DIR
from image_shared import detect_image_mime_type
from logger import log_event

SCENE_GRAPH_PROMPT_PATH = PROMPTS_DIR / "scene_graph_extraction.txt"
DEFAULT_RECONSTRUCTION_MODEL = "gpt-4.1"
DEFAULT_RECONSTRUCTION_MIN_CANVAS_SHORT_SIDE_PX = 900
DEFAULT_RECONSTRUCTION_TARGET_MIN_FONT_PX = 18
DEFAULT_RECONSTRUCTION_MAX_UPSCALE_FACTOR = 3.0
DEFAULT_RECONSTRUCTION_BACKGROUND_SAMPLE_RATIO = 0.04
DEFAULT_RECONSTRUCTION_BACKGROUND_COLOR_DISTANCE_THRESHOLD = 48.0
DEFAULT_RECONSTRUCTION_BACKGROUND_UNIFORMITY_THRESHOLD = 10.0
DEFAULT_FONT_FAMILY = "sans"
WINDOWS_FONT_DIR = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
COMMON_SANS_FONTS = {
    "sans": {
        False: [
            WINDOWS_FONT_DIR / "segoeui.ttf",
            WINDOWS_FONT_DIR / "calibri.ttf",
            WINDOWS_FONT_DIR / "arial.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        ],
        True: [
            WINDOWS_FONT_DIR / "segoeuib.ttf",
            WINDOWS_FONT_DIR / "calibrib.ttf",
            WINDOWS_FONT_DIR / "arialbd.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        ],
    },
    "serif": {
        False: [
            WINDOWS_FONT_DIR / "times.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        ],
        True: [
            WINDOWS_FONT_DIR / "timesbd.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
        ],
    },
    "mono": {
        False: [
            WINDOWS_FONT_DIR / "consola.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ],
        True: [
            WINDOWS_FONT_DIR / "consolab.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
        ],
    },
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconstruct_image(
    image_bytes: bytes,
    *,
    model: str = DEFAULT_RECONSTRUCTION_MODEL,
    mime_type: str | None = None,
    client=None,
    render_config: dict[str, object] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """End-to-end deterministic reconstruction.

    Returns ``(png_bytes, scene_graph_dict)``.  Raises on unrecoverable
    errors so that callers can fall back to safe mode.
    """
    scene_graph = extract_scene_graph(image_bytes, model=model, mime_type=mime_type, client=client)
    original_size = _get_image_size(image_bytes)
    rendered_bytes = render_scene_graph(
        scene_graph,
        original_size=original_size,
        source_image_bytes=image_bytes,
        render_config=render_config,
    )
    log_event(
        logging.INFO,
        "image_reconstruction_completed",
        "Детерминированная реконструкция завершена.",
        element_count=len(scene_graph.get("elements", [])),
        canvas=scene_graph.get("canvas"),
    )
    return rendered_bytes, scene_graph


# ---------------------------------------------------------------------------
# Step 1 — VLM scene-graph extraction
# ---------------------------------------------------------------------------


def extract_scene_graph(
    image_bytes: bytes,
    *,
    model: str = DEFAULT_RECONSTRUCTION_MODEL,
    mime_type: str | None = None,
    client=None,
) -> dict[str, Any]:
    """Call a multimodal VLM to extract a structured JSON scene graph."""
    if client is None:
        raise RuntimeError("Scene graph extraction requires an explicit client.")

    prompt_text = _load_scene_graph_prompt()
    data_uri = _image_bytes_to_data_uri(image_bytes, mime_type)

    response = client.responses.create(
        model=model,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt_text},
                    {"type": "input_image", "image_url": data_uri},
                ],
            }
        ],
        temperature=0.0,
    )

    raw_text: str = _extract_response_text(response)
    scene_graph = _parse_scene_graph_json(raw_text)
    _validate_scene_graph(scene_graph)

    log_event(
        logging.INFO,
        "scene_graph_extracted",
        "Извлечен scene graph из изображения через VLM.",
        model=model,
        element_count=len(scene_graph.get("elements", [])),
    )
    return scene_graph


# ---------------------------------------------------------------------------
# Step 2 — deterministic PIL rendering
# ---------------------------------------------------------------------------

_FALLBACK_FONT_SIZE = 14
_MIN_FONT_SIZE = 8
_MAX_FONT_SIZE = 72


def render_scene_graph(
    scene_graph: dict[str, Any],
    *,
    original_size: tuple[int, int] | None = None,
    source_image_bytes: bytes | None = None,
    render_config: dict[str, object] | None = None,
) -> bytes:
    """Render a scene graph to PNG using only PIL primitives."""
    resolved_render_config = _resolve_render_config(render_config)
    working_scene_graph = copy.deepcopy(scene_graph)
    canvas_spec = working_scene_graph.get("canvas", {})
    width = int(canvas_spec.get("width", original_size[0] if original_size else 800))
    height = int(canvas_spec.get("height", original_size[1] if original_size else 600))
    render_scale = _compute_render_scale(working_scene_graph, (width, height), resolved_render_config)
    if render_scale > 1.0:
        working_scene_graph = _scale_scene_graph(working_scene_graph, render_scale)
        canvas_spec = working_scene_graph.get("canvas", {})
        width = int(canvas_spec.get("width", width))
        height = int(canvas_spec.get("height", height))

    _inset_full_canvas_containers(working_scene_graph)

    bg_color = _resolve_canvas_background(scene_graph, source_image_bytes, resolved_render_config)
    image = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(image)

    elements = working_scene_graph.get("elements", [])
    sorted_elements = sorted(elements, key=lambda e: int(e.get("z_index", 0)))

    for element in sorted_elements:
        _render_element(draw, image, element)

    if original_size and render_scale <= 1.0 and (width, height) != original_size:
        image = image.resize(original_size, Image.Resampling.LANCZOS)

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Element renderers
# ---------------------------------------------------------------------------


def _render_element(draw: ImageDraw.ImageDraw, image: Image.Image, element: dict[str, Any]) -> None:
    element_type = element.get("type", "rect")
    renderer = _ELEMENT_RENDERERS.get(element_type, _render_rect)
    renderer(draw, image, element)


def _render_rect(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 0)), int(el.get("height", 0))
    if w <= 0 or h <= 0:
        return
    fill = _safe_fill(el)
    stroke = _safe_stroke(el)
    stroke_w = int(el.get("stroke_width", 1))
    if fill is not None or stroke is not None:
        draw.rectangle([x, y, x + w, y + h], fill=fill, outline=stroke, width=stroke_w)
    _render_text_content(draw, el, x, y, w, h)


def _render_rounded_rect(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 0)), int(el.get("height", 0))
    if w <= 0 or h <= 0:
        return
    fill = _safe_fill(el)
    stroke = _safe_stroke(el)
    stroke_w = int(el.get("stroke_width", 1))
    radius = int(el.get("corner_radius", 8))
    if fill is not None or stroke is not None:
        draw.rounded_rectangle([x, y, x + w, y + h], radius=radius, fill=fill, outline=stroke, width=stroke_w)
    _render_text_content(draw, el, x, y, w, h)


def _render_ellipse(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 0)), int(el.get("height", 0))
    if w <= 0 or h <= 0:
        return
    fill = _safe_fill(el)
    stroke = _safe_stroke(el)
    stroke_w = int(el.get("stroke_width", 1))
    if fill is not None or stroke is not None:
        draw.ellipse([x, y, x + w, y + h], fill=fill, outline=stroke, width=stroke_w)
    _render_text_content(draw, el, x, y, w, h)


def _render_circle(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    _render_ellipse(draw, image, el)


def _render_diamond(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 0)), int(el.get("height", 0))
    if w <= 0 or h <= 0:
        return
    fill = _safe_fill(el)
    stroke = _safe_stroke(el)
    stroke_w = int(el.get("stroke_width", 1))
    cx, cy = x + w // 2, y + h // 2
    points = [(cx, y), (x + w, cy), (cx, y + h), (x, cy)]
    if fill is not None or stroke is not None:
        draw.polygon(points, fill=fill, outline=stroke)
    if stroke_w > 1 and stroke:
        draw.line(points + [points[0]], fill=stroke, width=stroke_w)
    _render_text_content(draw, el, x, y, w, h)


def _render_text(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w = int(el.get("width", 0)) or 9999
    h = int(el.get("height", 0)) or 9999
    _render_text_content(draw, el, x, y, w, h)


def _render_line(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x1 = int(el.get("x1", el.get("x", 0)))
    y1 = int(el.get("y1", el.get("y", 0)))
    x2 = int(el.get("x2", x1))
    y2 = int(el.get("y2", y1))
    stroke = _safe_stroke(el) or "#000000"
    stroke_w = int(el.get("stroke_width", 1))
    draw.line([(x1, y1), (x2, y2)], fill=stroke, width=stroke_w)


def _render_arrow(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x1 = int(el.get("x1", el.get("x", 0)))
    y1 = int(el.get("y1", el.get("y", 0)))
    x2 = int(el.get("x2", x1))
    y2 = int(el.get("y2", y1))
    stroke = _safe_stroke(el) or "#000000"
    stroke_w = int(el.get("stroke_width", 2))
    draw.line([(x1, y1), (x2, y2)], fill=stroke, width=stroke_w)

    marker = el.get("marker_end", "arrowhead")
    if marker == "arrowhead":
        _draw_arrowhead(draw, x1, y1, x2, y2, stroke, stroke_w)


def _render_table(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 0)), int(el.get("height", 0))
    rows = int(el.get("rows", 1))
    cols = int(el.get("cols", 1))
    cells = el.get("cells", [])

    if w <= 0 or h <= 0 or rows <= 0 or cols <= 0:
        return

    if _should_render_styled_matrix(el, w=w, h=h, rows=rows, cols=cols):
        _render_styled_matrix_table(draw, image, el, x=x, y=y, w=w, h=h, rows=rows, cols=cols)
        return

    cell_w = w / cols
    cell_h = h / rows

    stroke = _safe_stroke(el) or "#000000"
    stroke_w = int(el.get("stroke_width", 1))

    draw.rectangle([x, y, x + w, y + h], fill=_safe_fill(el), outline=stroke, width=stroke_w)

    for r in range(1, rows):
        ry = int(y + r * cell_h)
        draw.line([(x, ry), (x + w, ry)], fill=stroke, width=stroke_w)
    for c in range(1, cols):
        cx_pos = int(x + c * cell_w)
        draw.line([(cx_pos, y), (cx_pos, y + h)], fill=stroke, width=stroke_w)

    for cell in cells:
        cr = int(cell.get("row", 0))
        cc = int(cell.get("col", 0))
        cell_x = int(x + cc * cell_w)
        cell_y = int(y + cr * cell_h)
        cw = int(cell_w * int(cell.get("colspan", 1)))
        ch = int(cell_h * int(cell.get("rowspan", 1)))

        cell_fill = cell.get("fill")
        if cell_fill:
            draw.rectangle(
                [cell_x + stroke_w, cell_y + stroke_w, cell_x + cw - stroke_w, cell_y + ch - stroke_w],
                fill=_hex_to_rgba(cell_fill),
            )

        text = str(cell.get("text", "")).strip()
        if not text:
            continue

        explicit_font_size = cell.get("font_size") or el.get("font_size")
        default_font_size = int(ch * 0.32)
        font_size = max(_MIN_FONT_SIZE, min(int(explicit_font_size) if explicit_font_size else default_font_size, _MAX_FONT_SIZE))
        bold = bool(cell.get("bold", False))
        font_family = cell.get("font_family") or el.get("font_family")
        font = _get_font(font_size, bold=bold, family=font_family)
        font_color = _hex_to_rgba(cell.get("font_color") or "#000000") or (0, 0, 0, 255)
        _draw_box_text(
            draw,
            text,
            cell_x + max(2, stroke_w),
            cell_y + max(2, stroke_w),
            max(1, cw - max(4, stroke_w * 2)),
            max(1, ch - max(4, stroke_w * 2)),
            font,
            font_color,
            text_align=str(cell.get("text_align") or el.get("text_align") or "center"),
            family=font_family,
            bold=bold,
        )


def _should_render_styled_matrix(el: dict[str, Any], *, w: int, h: int, rows: int, cols: int) -> bool:
    if rows < 3 or cols < 2 or cols > 4:
        return False
    if min(w, h) < 160:
        return False
    cells = el.get("cells", [])
    if len(cells) < rows * cols * 0.7:
        return False
    non_empty_cells = [cell for cell in cells if str(cell.get("text", "")).strip()]
    if len(non_empty_cells) < rows * max(1, cols - 1):
        return False
    header_cells = [cell for cell in cells if int(cell.get("row", 0)) == 0]
    if len(header_cells) < cols:
        return False
    return True


def _render_styled_matrix_table(
    draw: ImageDraw.ImageDraw,
    image: Image.Image,
    el: dict[str, Any],
    *,
    x: int,
    y: int,
    w: int,
    h: int,
    rows: int,
    cols: int,
) -> None:
    panel_radius = max(12, int(min(w, h) * 0.035))
    panel_fill = _hex_to_rgba("#F6F7FB")
    panel_stroke = _hex_to_rgba("#D8DEE9")
    shadow_fill = (30, 41, 59, 28)
    shadow_offset = max(3, int(min(w, h) * 0.012))
    draw.rounded_rectangle(
        [x + shadow_offset, y + shadow_offset, x + w + shadow_offset, y + h + shadow_offset],
        radius=panel_radius,
        fill=shadow_fill,
    )
    draw.rounded_rectangle([x, y, x + w, y + h], radius=panel_radius, fill=panel_fill, outline=panel_stroke, width=1)

    outer_padding_x = max(10, int(w * 0.03))
    outer_padding_y = max(10, int(h * 0.04))
    col_gap = max(8, int(w * 0.018))
    row_gap = max(8, int(h * 0.022))
    inner_w = max(1, w - outer_padding_x * 2)
    inner_h = max(1, h - outer_padding_y * 2)
    cell_w = (inner_w - col_gap * (cols - 1)) / cols
    cell_h = (inner_h - row_gap * (rows - 1)) / rows
    corner_radius = max(10, int(min(cell_w, cell_h) * 0.16))

    cells_by_position = {
        (int(cell.get("row", 0)), int(cell.get("col", 0))): cell
        for cell in el.get("cells", [])
    }
    column_palette = ["#EEF3FF", "#F7F4EE", "#EEF7F1", "#F6F0FF"]
    header_palette = ["#C9D8F0", "#D8D2C3", "#CFE5D6", "#DDD4F6"]

    for row_index in range(rows):
        for col_index in range(cols):
            cell = cells_by_position.get((row_index, col_index), {})
            cell_x = int(round(x + outer_padding_x + col_index * (cell_w + col_gap)))
            cell_y = int(round(y + outer_padding_y + row_index * (cell_h + row_gap)))
            cw = int(round(cell_w * int(cell.get("colspan", 1)) + col_gap * (int(cell.get("colspan", 1)) - 1)))
            ch = int(round(cell_h * int(cell.get("rowspan", 1)) + row_gap * (int(cell.get("rowspan", 1)) - 1)))

            base_fill = cell.get("fill")
            if not base_fill:
                base_fill = header_palette[col_index % len(header_palette)] if row_index == 0 else column_palette[col_index % len(column_palette)]
            fill_color = _lighten_rgba(_hex_to_rgba(base_fill) or (255, 255, 255, 255), 0.05 if row_index == 0 else 0.16)
            border_color = _mix_rgba(fill_color, (148, 163, 184, 255), 0.45)
            accent_shadow = (*fill_color[:3], 34)

            draw.rounded_rectangle(
                [cell_x, cell_y + 2, cell_x + cw, cell_y + ch + 2],
                radius=corner_radius,
                fill=accent_shadow,
            )
            draw.rounded_rectangle(
                [cell_x, cell_y, cell_x + cw, cell_y + ch],
                radius=corner_radius,
                fill=fill_color,
                outline=border_color,
                width=1,
            )

            text = str(cell.get("text", "")).strip()
            if not text:
                continue
            explicit_font_size = cell.get("font_size") or el.get("font_size")
            default_font_size = int(ch * (0.24 if row_index == 0 else 0.2))
            font_size = max(_MIN_FONT_SIZE, min(int(explicit_font_size) if explicit_font_size else default_font_size, _MAX_FONT_SIZE))
            bold = bool(cell.get("bold", row_index == 0))
            font_family = cell.get("font_family") or el.get("font_family")
            font = _get_font(font_size, bold=bold, family=font_family)
            text_align = str(cell.get("text_align") or ("center" if row_index == 0 or col_index == cols - 1 else "left"))
            font_color = _hex_to_rgba(cell.get("font_color") or ("#203047" if row_index == 0 else "#27364A")) or (39, 54, 74, 255)
            horizontal_padding = max(8, int(cw * 0.08))
            _draw_box_text(
                draw,
                text,
                cell_x + (horizontal_padding if text_align == "left" else 0),
                cell_y + max(4, int(ch * 0.08)),
                cw - (horizontal_padding if text_align == "left" else 0) * 2,
                ch - max(8, int(ch * 0.12)),
                font,
                font_color,
                text_align=text_align,
                family=font_family,
                bold=bold,
            )


def _render_group(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    bg_fill = _safe_fill(el)
    stroke = _safe_stroke(el)
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 0)), int(el.get("height", 0))
    if w > 0 and h > 0 and (bg_fill or stroke):
        stroke_w = int(el.get("stroke_width", 1))
        draw.rectangle([x, y, x + w, y + h], fill=bg_fill, outline=stroke, width=stroke_w)

    children = el.get("children", [])
    sorted_children = sorted(children, key=lambda c: int(c.get("z_index", 0)))
    for child in sorted_children:
        _render_element(draw, image, child)


def _render_icon_placeholder(draw: ImageDraw.ImageDraw, image: Image.Image, el: dict[str, Any]) -> None:
    x, y = int(el.get("x", 0)), int(el.get("y", 0))
    w, h = int(el.get("width", 24)), int(el.get("height", 24))
    if w <= 0 or h <= 0:
        return
    draw.rectangle([x, y, x + w, y + h], fill="#F0F0F0", outline="#CCCCCC", width=1)
    draw.line([(x, y), (x + w, y + h)], fill="#CCCCCC", width=1)
    draw.line([(x + w, y), (x, y + h)], fill="#CCCCCC", width=1)

    desc = el.get("text_content", "")
    if desc:
        font = _get_font(max(_MIN_FONT_SIZE, min(int(h * 0.3), 12)))
        _draw_box_text(draw, desc, x, y, w, h, font, (128, 128, 128, 255))


_ELEMENT_RENDERERS: dict[str, Any] = {
    "rect": _render_rect,
    "rounded_rect": _render_rounded_rect,
    "ellipse": _render_ellipse,
    "circle": _render_circle,
    "diamond": _render_diamond,
    "text": _render_text,
    "line": _render_line,
    "arrow": _render_arrow,
    "table": _render_table,
    "group": _render_group,
    "icon_placeholder": _render_icon_placeholder,
}

# ---------------------------------------------------------------------------
# Text rendering helpers
# ---------------------------------------------------------------------------


def _render_text_content(
    draw: ImageDraw.ImageDraw,
    el: dict[str, Any],
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    text = el.get("text_content")
    if not text:
        return
    font_size = el.get("font_size") or _FALLBACK_FONT_SIZE
    font_size = max(_MIN_FONT_SIZE, min(int(font_size), _MAX_FONT_SIZE))
    bold = el.get("font_weight", "normal") == "bold"
    font_family = el.get("font_family")
    font = _get_font(font_size, bold=bold, family=font_family)
    color = el.get("font_color") or "#000000"
    _draw_box_text(
        draw,
        text,
        x,
        y,
        w,
        h,
        font,
        _hex_to_rgba(color) or (0, 0, 0, 255),
        text_align=str(el.get("text_align", "center")),
        family=font_family,
        bold=bold,
    )


def _draw_box_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    color: tuple[int, ...],
    text_align: str = "center",
    family: str | None = None,
    bold: bool = False,
) -> None:
    if w <= 0 or h <= 0 or not text.strip():
        return

    font_size = getattr(font, "size", _FALLBACK_FONT_SIZE)
    fitted_font = font
    fitted_lines = _wrap_text_lines(draw, text, fitted_font, max(1, w - 4))
    total_height = _measure_wrapped_text_height(draw, fitted_lines, fitted_font)

    while total_height > h and font_size > _MIN_FONT_SIZE:
        font_size -= 1
        fitted_font = _get_font(font_size, bold=bold, family=family)
        fitted_lines = _wrap_text_lines(draw, text, fitted_font, max(1, w - 4))
        total_height = _measure_wrapped_text_height(draw, fitted_lines, fitted_font)

    line_height = _line_height(draw, fitted_font)
    line_spacing = max(2, int(round(line_height * 0.2)))
    current_y = y + max(0, (h - total_height) // 2)
    normalized_align = text_align.lower()
    for line in fitted_lines:
        bbox = draw.textbbox((0, 0), line, font=fitted_font)
        text_width = bbox[2] - bbox[0]
        if normalized_align == "left":
            current_x = x + 2
        elif normalized_align == "right":
            current_x = x + max(0, w - text_width - 2)
        else:
            current_x = x + max(0, (w - text_width) // 2)
        draw.text((current_x, current_y), line, fill=color, font=fitted_font)
        current_y += line_height + line_spacing


@lru_cache(maxsize=128)
def _get_font(size: int, *, bold: bool = False, family: str | None = None) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    for font_path in _build_font_search_paths(family, bold):
        try:
            return ImageFont.truetype(str(font_path), size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _build_font_search_paths(family: str | None, bold: bool) -> list[Path]:
    normalized_family = _normalize_font_family(family)
    search_paths = list(COMMON_SANS_FONTS.get(normalized_family, COMMON_SANS_FONTS[DEFAULT_FONT_FAMILY])[bold])
    if normalized_family != DEFAULT_FONT_FAMILY:
        search_paths.extend(COMMON_SANS_FONTS[DEFAULT_FONT_FAMILY][bold])
    if not bold:
        search_paths.extend(COMMON_SANS_FONTS[DEFAULT_FONT_FAMILY][True])
    return search_paths


def _normalize_font_family(family: str | None) -> str:
    normalized = str(family or "").strip().lower()
    if any(token in normalized for token in {"serif", "times", "georgia"}):
        return "serif"
    if any(token in normalized for token in {"mono", "consol", "courier"}):
        return "mono"
    return DEFAULT_FONT_FAMILY


def _wrap_text_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    wrapped_lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        paragraph = paragraph.strip()
        if not paragraph:
            wrapped_lines.append("")
            continue
        words = paragraph.split()
        if not words:
            wrapped_lines.append(paragraph)
            continue
        current_line = words[0]
        for word in words[1:]:
            candidate = f"{current_line} {word}".strip()
            if _text_width(draw, candidate, font) <= max_width:
                current_line = candidate
                continue
            wrapped_lines.append(current_line)
            current_line = word
        wrapped_lines.append(current_line)
    return wrapped_lines or [text]


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _line_height(draw: ImageDraw.ImageDraw, font: ImageFont.ImageFont | ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    return max(1, bbox[3] - bbox[1])


def _measure_wrapped_text_height(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> int:
    line_height = _line_height(draw, font)
    line_spacing = max(2, int(round(line_height * 0.2)))
    return len(lines) * line_height + max(0, len(lines) - 1) * line_spacing


# ---------------------------------------------------------------------------
# Arrow drawing
# ---------------------------------------------------------------------------


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    color: str | tuple[int, ...],
    stroke_w: int,
) -> None:
    arrow_len = max(8, stroke_w * 4)
    angle = math.atan2(y2 - y1, x2 - x1)
    spread = math.pi / 6

    ax = x2 - int(arrow_len * math.cos(angle - spread))
    ay = y2 - int(arrow_len * math.sin(angle - spread))
    bx = x2 - int(arrow_len * math.cos(angle + spread))
    by = y2 - int(arrow_len * math.sin(angle + spread))

    fill_color = _hex_to_rgba(color) if isinstance(color, str) else color
    draw.polygon([(x2, y2), (ax, ay), (bx, by)], fill=fill_color)


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------


def _hex_to_rgba(color: str | None) -> tuple[int, int, int, int] | None:
    if not color or not isinstance(color, str):
        return None
    color = color.strip()
    if not color.startswith("#") or len(color) < 4:
        return None
    try:
        hex_str = color.lstrip("#")
        if len(hex_str) == 3:
            hex_str = "".join(c * 2 for c in hex_str)
        if len(hex_str) == 6:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            return (r, g, b, 255)
        if len(hex_str) == 8:
            r = int(hex_str[0:2], 16)
            g = int(hex_str[2:4], 16)
            b = int(hex_str[4:6], 16)
            a = int(hex_str[6:8], 16)
            return (r, g, b, a)
    except ValueError:
        pass
    return None


def _safe_fill(el: dict[str, Any]) -> tuple[int, int, int, int] | None:
    opacity = float(el.get("opacity", 1.0))
    rgba = _hex_to_rgba(el.get("fill"))
    if rgba and opacity < 1.0:
        return (rgba[0], rgba[1], rgba[2], int(rgba[3] * opacity))
    return rgba


def _safe_stroke(el: dict[str, Any]) -> str | None:
    stroke = el.get("stroke")
    if stroke and isinstance(stroke, str) and stroke.startswith("#"):
        return stroke
    return None


def _resolve_render_config(render_config: dict[str, object] | None) -> dict[str, float]:
    config = dict(render_config or {})
    return {
        "min_canvas_short_side_px": float(
            max(256, config.get("min_canvas_short_side_px", DEFAULT_RECONSTRUCTION_MIN_CANVAS_SHORT_SIDE_PX))
        ),
        "target_min_font_px": float(
            max(_MIN_FONT_SIZE, config.get("target_min_font_px", DEFAULT_RECONSTRUCTION_TARGET_MIN_FONT_PX))
        ),
        "max_upscale_factor": float(
            max(1.0, config.get("max_upscale_factor", DEFAULT_RECONSTRUCTION_MAX_UPSCALE_FACTOR))
        ),
        "background_sample_ratio": float(
            max(0.01, config.get("background_sample_ratio", DEFAULT_RECONSTRUCTION_BACKGROUND_SAMPLE_RATIO))
        ),
        "background_color_distance_threshold": float(
            max(
                1.0,
                config.get(
                    "background_color_distance_threshold",
                    DEFAULT_RECONSTRUCTION_BACKGROUND_COLOR_DISTANCE_THRESHOLD,
                ),
            )
        ),
        "background_uniformity_threshold": float(
            max(
                0.1,
                config.get(
                    "background_uniformity_threshold",
                    DEFAULT_RECONSTRUCTION_BACKGROUND_UNIFORMITY_THRESHOLD,
                ),
            )
        ),
    }


def _compute_render_scale(
    scene_graph: dict[str, Any],
    canvas_size: tuple[int, int],
    render_config: dict[str, float],
) -> float:
    width, height = canvas_size
    short_side = max(1, min(width, height))
    scale_candidates = [1.0]
    if short_side < render_config["min_canvas_short_side_px"]:
        scale_candidates.append(render_config["min_canvas_short_side_px"] / short_side)

    font_sizes = _collect_font_sizes(scene_graph)
    if font_sizes:
        smallest_font = min(font_sizes)
        if smallest_font < render_config["target_min_font_px"]:
            scale_candidates.append(render_config["target_min_font_px"] / smallest_font)

    return min(render_config["max_upscale_factor"], max(scale_candidates))


def _collect_font_sizes(scene_graph: dict[str, Any]) -> list[int]:
    font_sizes: list[int] = []
    for element in scene_graph.get("elements", []):
        _collect_font_sizes_from_element(element, font_sizes)
    return [size for size in font_sizes if size > 0]


def _collect_font_sizes_from_element(element: dict[str, Any], font_sizes: list[int]) -> None:
    font_size = element.get("font_size")
    if isinstance(font_size, (int, float)):
        font_sizes.append(max(1, int(font_size)))
    for cell in element.get("cells", []):
        cell_font_size = cell.get("font_size")
        if isinstance(cell_font_size, (int, float)):
            font_sizes.append(max(1, int(cell_font_size)))
    for child in element.get("children", []):
        _collect_font_sizes_from_element(child, font_sizes)


def _scale_scene_graph(scene_graph: dict[str, Any], scale: float) -> dict[str, Any]:
    scaled = copy.deepcopy(scene_graph)
    canvas = scaled.get("canvas", {})
    if isinstance(canvas.get("width"), (int, float)):
        canvas["width"] = max(1, int(round(float(canvas["width"]) * scale)))
    if isinstance(canvas.get("height"), (int, float)):
        canvas["height"] = max(1, int(round(float(canvas["height"]) * scale)))
    scaled["elements"] = [_scale_element(element, scale) for element in scaled.get("elements", [])]
    return scaled


def _scale_element(element: dict[str, Any], scale: float) -> dict[str, Any]:
    scaled = copy.deepcopy(element)
    for key in ("x", "y", "width", "height", "x1", "y1", "x2", "y2"):
        if isinstance(scaled.get(key), (int, float)):
            scaled[key] = int(round(float(scaled[key]) * scale))
    for key in ("stroke_width", "corner_radius", "font_size"):
        if isinstance(scaled.get(key), (int, float)):
            scaled[key] = max(1, int(round(float(scaled[key]) * scale)))
    if "children" in scaled:
        scaled["children"] = [_scale_element(child, scale) for child in scaled.get("children", [])]
    if "cells" in scaled:
        scaled["cells"] = [_scale_cell(cell, scale) for cell in scaled.get("cells", [])]
    return scaled


def _scale_cell(cell: dict[str, Any], scale: float) -> dict[str, Any]:
    scaled = copy.deepcopy(cell)
    if isinstance(scaled.get("font_size"), (int, float)):
        scaled["font_size"] = max(1, int(round(float(scaled["font_size"]) * scale)))
    return scaled


def _inset_full_canvas_containers(scene_graph: dict[str, Any]) -> None:
    canvas = scene_graph.get("canvas", {})
    canvas_width = int(canvas.get("width", 0))
    canvas_height = int(canvas.get("height", 0))
    if canvas_width <= 2 or canvas_height <= 2:
        return
    for element in scene_graph.get("elements", []):
        if element.get("type") not in {"table", "rect", "rounded_rect"}:
            continue
        x = int(element.get("x", 0))
        y = int(element.get("y", 0))
        width = int(element.get("width", 0))
        height = int(element.get("height", 0))
        stroke = _safe_stroke(element)
        if not stroke:
            continue
        if x > 0 or y > 0 or x + width < canvas_width or y + height < canvas_height:
            continue
        margin = max(1, int(element.get("stroke_width", 1)))
        if width <= margin * 2 or height <= margin * 2:
            continue
        element["x"] = x + margin
        element["y"] = y + margin
        element["width"] = width - margin * 2
        element["height"] = height - margin * 2


def _resolve_canvas_background(
    scene_graph: dict[str, Any],
    source_image_bytes: bytes | None,
    render_config: dict[str, float],
) -> tuple[int, int, int, int]:
    canvas = scene_graph.get("canvas", {})
    scene_background = _hex_to_rgba(canvas.get("background_color")) or (255, 255, 255, 255)
    if not source_image_bytes:
        return scene_background
    sampled_background, uniformity_score = _sample_source_background(source_image_bytes, render_config["background_sample_ratio"])
    if sampled_background is None:
        return scene_background
    if (
        uniformity_score <= render_config["background_uniformity_threshold"]
        and _rgba_distance(scene_background, sampled_background) >= render_config["background_color_distance_threshold"]
    ):
        return sampled_background
    return scene_background


def _sample_source_background(
    image_bytes: bytes,
    sample_ratio: float,
) -> tuple[tuple[int, int, int, int] | None, float]:
    try:
        with Image.open(BytesIO(image_bytes)) as source_image:
            source_image.load()
            rgb_image = ImageOps.exif_transpose(source_image).convert("RGB")
    except Exception:
        return None, float("inf")

    width, height = rgb_image.size
    sample = max(1, int(round(min(width, height) * sample_ratio)))
    top_strip = _image_rgb_pixels(rgb_image.crop((0, 0, width, sample)))
    bottom_strip = _image_rgb_pixels(rgb_image.crop((0, max(0, height - sample), width, height)))
    left_strip = _image_rgb_pixels(rgb_image.crop((0, 0, sample, height)))
    right_strip = _image_rgb_pixels(rgb_image.crop((max(0, width - sample), 0, width, height)))
    pixels = top_strip + bottom_strip + left_strip + right_strip
    if not pixels:
        return None, float("inf")

    median_color = tuple(sorted(pixel[channel] for pixel in pixels)[len(pixels) // 2] for channel in range(3))
    average_deviation = sum(
        (abs(pixel[0] - median_color[0]) + abs(pixel[1] - median_color[1]) + abs(pixel[2] - median_color[2])) / 3.0
        for pixel in pixels
    ) / len(pixels)
    return (median_color[0], median_color[1], median_color[2], 255), average_deviation


def _image_rgb_pixels(image: Image.Image) -> list[tuple[int, int, int]]:
    image_bytes = image.tobytes()
    return [
        (image_bytes[index], image_bytes[index + 1], image_bytes[index + 2])
        for index in range(0, len(image_bytes), 3)
    ]


def _rgba_distance(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    return math.sqrt(sum((left[index] - right[index]) ** 2 for index in range(3)))


def _lighten_rgba(color: tuple[int, int, int, int], amount: float) -> tuple[int, int, int, int]:
    clamped = max(0.0, min(amount, 1.0))
    return (
        int(round(color[0] + (255 - color[0]) * clamped)),
        int(round(color[1] + (255 - color[1]) * clamped)),
        int(round(color[2] + (255 - color[2]) * clamped)),
        color[3],
    )


def _mix_rgba(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
    weight_right: float,
) -> tuple[int, int, int, int]:
    ratio = max(0.0, min(weight_right, 1.0))
    return (
        int(round(left[0] * (1.0 - ratio) + right[0] * ratio)),
        int(round(left[1] * (1.0 - ratio) + right[1] * ratio)),
        int(round(left[2] * (1.0 - ratio) + right[2] * ratio)),
        int(round(left[3] * (1.0 - ratio) + right[3] * ratio)),
    )


# ---------------------------------------------------------------------------
# Scene graph parsing & validation
# ---------------------------------------------------------------------------


def _parse_scene_graph_json(raw_text: str) -> dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        start = 1
        end = len(lines)
        for i, line in enumerate(lines[1:], start=1):
            if line.strip().startswith("```"):
                end = i
                break
        cleaned = "\n".join(lines[start:end]).strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"VLM вернул невалидный JSON scene graph: {exc}") from exc

    if not isinstance(result, dict):
        raise RuntimeError("VLM scene graph должен быть JSON-объектом.")
    return result


def _validate_scene_graph(scene_graph: dict[str, Any]) -> None:
    canvas = scene_graph.get("canvas")
    if not isinstance(canvas, dict):
        raise RuntimeError("Scene graph должен содержать поле 'canvas'.")
    if not isinstance(canvas.get("width"), (int, float)) or not isinstance(canvas.get("height"), (int, float)):
        raise RuntimeError("Canvas должен содержать width и height.")
    if int(canvas["width"]) <= 0 or int(canvas["height"]) <= 0:
        raise RuntimeError("Canvas width и height должны быть положительными.")

    elements = scene_graph.get("elements")
    if not isinstance(elements, list):
        raise RuntimeError("Scene graph должен содержать массив 'elements'.")


# ---------------------------------------------------------------------------
# VLM response helpers
# ---------------------------------------------------------------------------


def _extract_response_text(response: object) -> str:
    output = getattr(response, "output", None)
    if isinstance(output, list):
        for item in output:
            if getattr(item, "type", None) == "message":
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    for part in content:
                        if getattr(part, "type", None) == "output_text":
                            text = getattr(part, "text", "")
                            if text:
                                return text
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    raise RuntimeError("VLM не вернул текстовый ответ для scene graph extraction.")


def _load_scene_graph_prompt() -> str:
    try:
        text = SCENE_GRAPH_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(f"Не найден prompt для scene graph extraction: {SCENE_GRAPH_PROMPT_PATH}") from exc
    if not text:
        raise RuntimeError(f"Пустой prompt file: {SCENE_GRAPH_PROMPT_PATH}")
    return text


def _image_bytes_to_data_uri(image_bytes: bytes, mime_type: str | None = None) -> str:
    if mime_type is None:
        mime_type = detect_image_mime_type(image_bytes) or "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _detect_mime_type(image_bytes: bytes) -> str | None:
    return detect_image_mime_type(image_bytes)


def _get_image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as img:
        img.load()
        normalized = ImageOps.exif_transpose(img)
        size = normalized.size
        if normalized is not img:
            normalized.close()
        return size
