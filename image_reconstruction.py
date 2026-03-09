"""Deterministic image reconstruction via VLM scene-graph extraction + PIL rendering.

This module replaces hallucination-prone generative redraw with a two-step pipeline:
1. A multimodal VLM extracts a structured JSON scene graph from the source image.
2. PIL renders the scene graph to a pixel-identical PNG — no generative model involved.
"""

from __future__ import annotations

import base64
import json
import logging
import math
from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import get_client
from constants import PROMPTS_DIR
from logger import log_event

SCENE_GRAPH_PROMPT_PATH = PROMPTS_DIR / "scene_graph_extraction.txt"
DEFAULT_RECONSTRUCTION_MODEL = "gpt-4.1"

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def reconstruct_image(
    image_bytes: bytes,
    *,
    model: str = DEFAULT_RECONSTRUCTION_MODEL,
    mime_type: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """End-to-end deterministic reconstruction.

    Returns ``(png_bytes, scene_graph_dict)``.  Raises on unrecoverable
    errors so that callers can fall back to safe mode.
    """
    scene_graph = extract_scene_graph(image_bytes, model=model, mime_type=mime_type)
    original_size = _get_image_size(image_bytes)
    rendered_bytes = render_scene_graph(scene_graph, original_size=original_size)
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
) -> dict[str, Any]:
    """Call a multimodal VLM to extract a structured JSON scene graph."""
    prompt_text = _load_scene_graph_prompt()
    data_uri = _image_bytes_to_data_uri(image_bytes, mime_type)

    client = get_client()
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
) -> bytes:
    """Render a scene graph to PNG using only PIL primitives."""
    canvas_spec = scene_graph.get("canvas", {})
    width = int(canvas_spec.get("width", 800))
    height = int(canvas_spec.get("height", 600))
    bg_color = canvas_spec.get("background_color", "#FFFFFF")

    image = Image.new("RGBA", (width, height), _hex_to_rgba(bg_color) or (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)

    elements = scene_graph.get("elements", [])
    sorted_elements = sorted(elements, key=lambda e: int(e.get("z_index", 0)))

    for element in sorted_elements:
        _render_element(draw, image, element)

    if original_size and (width, height) != original_size:
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

        text = cell.get("text", "")
        if text:
            font_size = max(_MIN_FONT_SIZE, min(int(ch * 0.5), _MAX_FONT_SIZE))
            bold = cell.get("bold", False)
            font = _get_font(font_size, bold=bold)
            font_color = cell.get("font_color") or "#000000"
            _draw_centered_text(draw, text, cell_x, cell_y, cw, ch, font, _hex_to_rgba(font_color))


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
        _draw_centered_text(draw, desc, x, y, w, h, font, (128, 128, 128, 255))


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
    font = _get_font(font_size, bold=bold)
    color = el.get("font_color") or "#000000"
    _draw_centered_text(
        draw,
        text,
        x,
        y,
        w,
        h,
        font,
        _hex_to_rgba(color),
        text_align=str(el.get("text_align", "center")),
    )


def _draw_centered_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    color: tuple[int, ...],
    text_align: str = "center",
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    normalized_align = text_align.lower()
    if normalized_align == "left":
        tx = x
    elif normalized_align == "right":
        tx = x + w - tw
    else:
        tx = x + (w - tw) // 2
    ty = y + (h - th) // 2
    draw.text((tx, ty), text, fill=color, font=font)


def _get_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    font_names = (
        ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
        if bold
        else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for font_path in font_names:
        try:
            return ImageFont.truetype(font_path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


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
        mime_type = _detect_mime_type(image_bytes) or "image/png"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _detect_mime_type(image_bytes: bytes) -> str | None:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if image_bytes.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if image_bytes.startswith(b"BM"):
        return "image/bmp"
    return None


def _get_image_size(image_bytes: bytes) -> tuple[int, int]:
    with Image.open(BytesIO(image_bytes)) as img:
        img.load()
        normalized = ImageOps.exif_transpose(img)
        size = normalized.size
        if normalized is not img:
            normalized.close()
        return size
