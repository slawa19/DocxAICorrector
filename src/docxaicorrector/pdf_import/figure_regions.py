"""Spec 082 slice B: a composite figure becomes ONE picture -- a render of its region of the page.

A page qualifies only when the import's inventory lists an image the extractor cannot emit as a file (the
seed). On such a page the graphics -- images and vector paths, read by a separate pdfminer pass that never
touches the extracted images -- are grouped: two graphics belong together when the gap between their boxes is
at most the page's median text-line height. A group holding a seed starts a region; the region absorbs every
group that touches it and every text line set smaller than body that crosses the edge of its graphics (so the
picture does not cut a label in half), until nothing changes. Text is never removed, filtered or marked: the
emitted pictures inside the region are replaced by one render, and every line stays a paragraph.

Every doubt declines the whole page (it stays exactly as without this step):

- a graphic whose box contains more than half of the page's text lines -- an image of that kind is a scan or a
  background under the text (decline); a path of that kind is the frame of the text block (left out of growth);
- the importer's body typography is unknown (T1); the page's running-text lines outside the region (lines of
  at least as many words as the importer's own body-line test) exist and none is set at body size -- the
  profile does not describe this page (T2); more than half of the lines in the region are running text -- a
  text block with graphics, not a figure with labels (T3);
- a line at body size or larger with a letter or digit overlaps the region (G1); a line with a letter at least
  ``_FULL_LINE_FILL_RATIO`` of the body column wide overlaps it (G2);
- an emitted picture of the region does not lie entirely inside the region clipped to the CropBox; the pass's
  images disagree with the inventory; the page geometry, the pixel density or the pixel budget forbid a render.

The render's pixel density is the highest of the emitted members' own densities (as slice A delivered them --
no correct picture loses pixels) and the area-weighted median of the seeds' densities. Measured on the four
corpus PDFs (spec 082 research R30-R37, 2026-11-13): only Rethinking Money p151 qualifies and is accepted.

The step runs after slice A, on its output, and is contained: a failure at any stage leaves the page (or every
page, for a document-level stage) as slice A delivered it and logs an ERROR.
"""

from __future__ import annotations

import io
import logging
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from docxaicorrector.core.logger import log_event
from docxaicorrector.pdf_import.images import PdfImageExtraction, PdfImageObject

Box = tuple[float, float, float, float]
Key = tuple[int, int]

DECLINE_IMAGE_ENCLOSES_TEXT = "image_encloses_page_text"
DECLINE_TYPOGRAPHY_UNKNOWN = "typography_unknown"
DECLINE_TYPOGRAPHY_DISAGREES = "typography_disagrees"
DECLINE_TEXT_BLOCK = "text_block_inside"
DECLINE_RUNNING_TEXT = "running_text_inside"
DECLINE_FULL_LINE = "full_line_inside"
DECLINE_MEMBER_OUTSIDE = "member_outside_crop_box"
DECLINE_OUTSIDE_CROP_BOX = "outside_crop_box"
DECLINE_INVENTORY_MISMATCH = "inventory_mismatch"
DECLINE_UNKNOWN_DENSITY = "unknown_density"
DECLINE_EXCEEDS_PIXEL_BUDGET = "exceeds_pixel_budget"
DECLINE_USER_UNIT = "user_unit"
DECLINE_PAGE_GEOMETRY_DISAGREES = "page_geometry_disagrees"
DECLINE_PAGE_ATOMIC = "page_atomic"
DECLINE_IMAGE_COUNT_CAP = "image_count_cap"

_PREVIEW_CHARS = 120
# The pass and the inventory are the same pdfminer arithmetic on the same file; this only absorbs float noise.
_INVENTORY_TOLERANCE_PT = 1e-6


@dataclass(frozen=True)
class PageGraphic:
    box: Box
    kind: str  # "image" | "path"
    discovery_index: int | None = None
    source_px: tuple[int, int] | None = None


@dataclass(frozen=True)
class PageGraphics:
    page_number: int
    graphics: tuple[PageGraphic, ...]


@dataclass(frozen=True)
class FigureRegion:
    page_number: int
    box: Box
    member_keys: tuple[Key, ...]
    seed_count: int
    image_count: int
    path_count: int
    grown_line_count: int
    seed_density: float | None  # pixels per point


@dataclass(frozen=True)
class RegionDecline:
    page_number: int
    reason: str
    detail: str = ""
    box: Box | None = None
    seed_count: int = 0


@dataclass(frozen=True)
class FigureRegionPlan:
    seed_pages: tuple[int, ...]
    regions: tuple[FigureRegion, ...]
    declines: tuple[RegionDecline, ...]


@dataclass(frozen=True)
class FigureRegionOutcome:
    images: tuple[PdfImageObject, ...]
    seed_pages: int = 0
    rendered: int = 0
    declined: int = 0
    failed: int = 0
    images_absorbed: int = 0
    absorbed_frame_renders: int = 0


@dataclass
class _Line:
    box: Box
    size: float | None
    text: str
    words: int = field(init=False)

    def __post_init__(self) -> None:
        self.words = len(self.text.split())


# ----------------------------------------------------------------------------------------------- geometry


def _gap(a: Box, b: Box) -> float:
    return max(0.0, a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3])


def _union(boxes: Iterable[Box]) -> Box:
    boxes = list(boxes)
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _meets(a: Box, b: Box) -> bool:
    """Closed boxes: touching counts."""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _overlaps(a: Box, b: Box) -> bool:
    """Positive area, as slice A's ``text_over_frame``."""
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _contains(outer: Box, inner: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _intersection(a: Box, b: Box) -> Box | None:
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    return box


def _components(boxes: Sequence[Box], tolerance: float) -> list[list[int]]:
    parent = list(range(len(boxes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    order = sorted(range(len(boxes)), key=lambda i: boxes[i][0])
    for position, i in enumerate(order):
        for j in order[position + 1 :]:
            if boxes[j][0] > boxes[i][2] + tolerance:
                break
            if _gap(boxes[i], boxes[j]) <= tolerance:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float | None:
    pairs = sorted((v, w) for v, w in zip(values, weights) if w > 0)
    if not pairs:
        return None
    half = sum(w for _v, w in pairs) / 2.0
    running = 0.0
    for value, weight in pairs:
        running += weight
        if running >= half:
            return value
    return pairs[-1][0]


# ----------------------------------------------------------------------------------------------- inventory


def seed_pages(extraction: PdfImageExtraction) -> tuple[int, ...]:
    """Pages holding an image the extractor could not emit -- the only pages the step reads."""

    return tuple(sorted({item.page_number for item in extraction.discovered if item.skip_reason is not None}))


def _path_box(curve, height: float) -> Box:
    """The box over EVERY operand of the path (end and control points): a Bezier curve lies in the convex hull of
    its control points, so this box contains the drawn geometry (stroke width aside)."""

    xs: list[float] = []
    ys: list[float] = []
    for segment in getattr(curve, "original_path", None) or ():
        for point in segment[1:]:
            try:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
            except (TypeError, ValueError, IndexError):
                continue
    if not xs:
        xs = [float(curve.x0), float(curve.x1)]
        ys = [float(curve.y0), float(curve.y1)]
    return (min(xs), height - max(ys), max(xs), height - min(ys))


def _walk(element, lt_image, lt_curve, lt_figure):
    """Images in the extractor's walk order (``images._iter_pdfminer_images_with_placement``) and paths."""

    if isinstance(element, lt_image):
        yield element
        return
    if isinstance(element, lt_curve):
        yield element
        return
    if isinstance(element, lt_figure) or hasattr(element, "__iter__"):
        try:
            children = list(element)
        except TypeError:
            return
        for child in children:
            yield from _walk(child, lt_image, lt_curve, lt_figure)


def read_page_graphics(pdf_path: str | Path, page_numbers: Iterable[int]) -> dict[int, PageGraphics]:
    """A separate pdfminer layout pass over ``page_numbers`` (1-based) only: image boxes with their pixel size and
    path boxes, top-origin. It runs after image extraction returned and never sees the extracted images."""

    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTCurve, LTFigure, LTImage

    wanted = sorted(set(page_numbers))
    result: dict[int, PageGraphics] = {}
    if not wanted:
        return result
    for index, layout in enumerate(extract_pages(str(pdf_path), page_numbers=[number - 1 for number in wanted])):
        page_number = wanted[index]
        height = float(layout.height)
        graphics: list[PageGraphic] = []
        image_index = 0
        for element in _walk(layout, LTImage, LTCurve, LTFigure):
            if isinstance(element, LTImage):
                size = getattr(element, "srcsize", None)
                source_px = None
                try:
                    if size and int(size[0]) > 0 and int(size[1]) > 0:
                        source_px = (int(size[0]), int(size[1]))
                except (TypeError, ValueError):
                    source_px = None
                box = (float(element.x0), height - float(element.y1), float(element.x1), height - float(element.y0))
                graphics.append(PageGraphic(box=box, kind="image", discovery_index=image_index, source_px=source_px))
                image_index += 1
            else:
                graphics.append(PageGraphic(box=_path_box(element, height), kind="path"))
        result[page_number] = PageGraphics(page_number=page_number, graphics=tuple(graphics))
    return result


# ----------------------------------------------------------------------------------------------- the rule


def _font_sizes_match(first: float | None, second: float | None) -> bool:
    from docxaicorrector.pdf_import.logical_import import _font_sizes_match as importer_match

    return importer_match(first, second)


def _body_or_larger(size: float | None, body: float) -> bool:
    return bool(size) and (float(size or 0.0) >= body or _font_sizes_match(size, body))


def _has_letter(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def _has_letter_or_digit(text: str) -> bool:
    return any(ch.isalpha() or ch.isdigit() for ch in text)


def _member_box(image: PdfImageObject) -> Box:
    frame = image.frame_box
    if frame is not None:
        return (float(frame[0]), float(frame[1]), float(frame[2]), float(frame[3]))
    return (float(image.x0), float(image.top), float(image.x1), float(image.bottom))


def _source_density(graphic: PageGraphic) -> float | None:
    if graphic.source_px is None:
        return None
    width = graphic.box[2] - graphic.box[0]
    height = graphic.box[3] - graphic.box[1]
    if width <= 0 or height <= 0:
        return None
    return max(graphic.source_px[0] / width, graphic.source_px[1] / height)


def plan_figure_regions(
    extraction: PdfImageExtraction,
    spans: Sequence[object],
    graphics: Mapping[int, PageGraphics],
    typography,
    crop_boxes: Mapping[int, Box],
) -> FigureRegionPlan:
    """Which regions are rendered, page by page. Pure: reads the inventory, the spans, the pass and the boxes."""

    from docxaicorrector.pdf_import.logical_import import _BODY_LINE_MIN_WORDS, _FULL_LINE_FILL_RATIO

    pages = seed_pages(extraction)
    regions: list[FigureRegion] = []
    declines: list[RegionDecline] = []
    body = getattr(typography, "body_font_size", None)
    left = getattr(typography, "body_left_x0", None)
    right = getattr(typography, "body_right_x1", None)
    column = (float(right) - float(left)) if left is not None and right is not None else None
    if not body or column is None or column <= 0:
        return FigureRegionPlan(pages, (), tuple(RegionDecline(page, DECLINE_TYPOGRAPHY_UNKNOWN) for page in pages))
    body = float(body)

    lines_by_page: dict[int, list[_Line]] = {}
    for span in spans:
        text = str(getattr(span, "text", "") or "").strip()
        if not text:
            continue
        box = (float(getattr(span, "x0")), float(getattr(span, "top")), float(getattr(span, "x1")), float(getattr(span, "bottom")))
        size = getattr(span, "font_size", None)
        lines_by_page.setdefault(int(getattr(span, "page_number")), []).append(
            _Line(box=box, size=float(size) if isinstance(size, (int, float)) else None, text=text)
        )
    heights = [line.box[3] - line.box[1] for lines in lines_by_page.values() for line in lines if line.box[3] > line.box[1]]
    book_line_height = statistics.median(heights) if heights else 0.0
    discovered = {(item.page_number, item.discovery_index): item for item in extraction.discovered}
    emitted = {(image.page_number, image.discovery_index): image for image in extraction.images if image.discovery_index is not None}

    for page in pages:
        page_regions, page_declines = _plan_page(
            page,
            graphics.get(page),
            lines_by_page.get(page, []),
            book_line_height,
            discovered,
            emitted,
            crop_boxes.get(page),
            body=body,
            column=column,
            min_words=_BODY_LINE_MIN_WORDS,
            full_line_ratio=_FULL_LINE_FILL_RATIO,
        )
        if page_declines:
            declines.extend(page_declines)
            declines.extend(
                RegionDecline(page, DECLINE_PAGE_ATOMIC, "another region of the page was declined", region.box, region.seed_count)
                for region in page_regions
            )
            continue
        regions.extend(page_regions)
    return FigureRegionPlan(pages, tuple(regions), tuple(declines))


def _plan_page(
    page: int,
    page_graphics: PageGraphics | None,
    lines: list[_Line],
    book_line_height: float,
    discovered,
    emitted,
    crop: Box | None,
    *,
    body: float,
    column: float,
    min_words: int,
    full_line_ratio: float,
) -> tuple[list[FigureRegion], list[RegionDecline]]:
    if crop is None:
        return [], [RegionDecline(page, DECLINE_PAGE_GEOMETRY_DISAGREES, "no page geometry")]
    if page_graphics is None:
        return [], [RegionDecline(page, DECLINE_INVENTORY_MISMATCH, "the pass did not read the page")]
    images = [g for g in page_graphics.graphics if g.kind == "image"]
    inventory = sorted((item for key, item in discovered.items() if key[0] == page), key=lambda item: item.discovery_index)
    if len(images) != len(inventory):
        return [], [RegionDecline(page, DECLINE_INVENTORY_MISMATCH, f"{len(images)} images in the pass, {len(inventory)} in the inventory")]
    for graphic, item in zip(images, inventory):
        frame = item.frame_box or (item.x0, item.top, item.x1, item.bottom)
        if graphic.discovery_index != item.discovery_index or any(
            abs(float(a) - float(b)) > _INVENTORY_TOLERANCE_PT for a, b in zip(graphic.box, frame)
        ):
            return [], [RegionDecline(page, DECLINE_INVENTORY_MISMATCH, f"image {item.discovery_index}")]

    # Graphics that hold most of the page's text: a scan or a background under the text (image), the frame of the
    # text block (path).
    nodes: list[PageGraphic] = []
    for graphic in page_graphics.graphics:
        held = sum(1 for line in lines if _contains(graphic.box, line.box))
        if lines and held * 2 > len(lines):
            if graphic.kind == "image":
                return [], [RegionDecline(page, DECLINE_IMAGE_ENCLOSES_TEXT, f"image {graphic.discovery_index} holds {held} of {len(lines)} lines")]
            continue
        nodes.append(graphic)

    heights = [line.box[3] - line.box[1] for line in lines if line.box[3] > line.box[1]]
    tolerance = statistics.median(heights) if heights else book_line_height
    boxes = [node.box for node in nodes]
    groups = _components(boxes, tolerance)
    group_boxes = [_union(boxes[i] for i in group) for group in groups]

    def is_seed(node: PageGraphic) -> bool:
        item = discovered.get((page, node.discovery_index)) if node.kind == "image" else None
        return item is not None and item.skip_reason is not None

    state = [
        {"groups": {k}, "hull": group_boxes[k], "box": group_boxes[k], "lines": []}
        for k, group in enumerate(groups)
        if any(is_seed(nodes[i]) for i in group)
    ]
    changed = True
    while changed:
        changed = False
        for region in state:
            hull = region["hull"]
            grown = [
                index
                for index, line in enumerate(lines)
                if _overlaps(hull, line.box)
                and not _contains(hull, line.box)
                and line.size is not None
                and not _body_or_larger(line.size, body)
            ]
            region["lines"] = grown
            region["box"] = _union([hull] + [lines[i].box for i in grown])
            for k, box in enumerate(group_boxes):
                if k not in region["groups"] and _meets(region["box"], box):
                    region["groups"].add(k)
                    region["hull"] = _union([region["hull"], box])
                    changed = True
        merged: list[dict] = []
        for region in state:
            target = next((m for m in merged if _meets(m["box"], region["box"])), None)
            if target is None:
                merged.append(region)
                continue
            target["groups"] |= region["groups"]
            target["hull"] = _union([target["hull"], region["hull"]])
            target["box"] = _union([target["box"], region["box"]])
            changed = True
        state = merged

    planned: list[FigureRegion] = []
    declines: list[RegionDecline] = []
    for region in state:
        members = [nodes[i] for k in sorted(region["groups"]) for i in groups[k]]
        seeds = [node for node in members if is_seed(node)]
        clipped = _intersection(region["box"], crop)
        if clipped is None:
            declines.append(RegionDecline(page, DECLINE_OUTSIDE_CROP_BOX, "", region["box"], len(seeds)))
            continue
        decline = _guard(
            clipped, lines, body=body, column=column, min_words=min_words, full_line_ratio=full_line_ratio
        )
        if decline is not None:
            declines.append(RegionDecline(page, decline[0], decline[1], clipped, len(seeds)))
            continue
        member_keys = tuple(
            sorted((page, int(node.discovery_index)) for node in members if node.kind == "image" and (page, node.discovery_index) in emitted)
        )
        outside = next((key for key in member_keys if not _contains(clipped, _member_box(emitted[key]))), None)
        if outside is not None:
            declines.append(RegionDecline(page, DECLINE_MEMBER_OUTSIDE, f"image {outside[1]}", clipped, len(seeds)))
            continue
        densities = [(d, (s.box[2] - s.box[0]) * (s.box[3] - s.box[1])) for s in seeds if (d := _source_density(s)) is not None]
        planned.append(
            FigureRegion(
                page_number=page,
                box=clipped,
                member_keys=member_keys,
                seed_count=len(seeds),
                image_count=sum(1 for node in members if node.kind == "image"),
                path_count=sum(1 for node in members if node.kind == "path"),
                grown_line_count=len(region["lines"]),
                seed_density=_weighted_median([d for d, _a in densities], [a for _d, a in densities]),
            )
        )
    return planned, declines


def _guard(box: Box, lines: list[_Line], *, body: float, column: float, min_words: int, full_line_ratio: float) -> tuple[str, str] | None:
    inside = [line for line in lines if _overlaps(box, line.box)]
    outside = [line for line in lines if not _overlaps(box, line.box)]
    running_outside = [line for line in outside if line.words >= min_words]
    if running_outside and not any(_font_sizes_match(line.size, body) for line in running_outside):
        return DECLINE_TYPOGRAPHY_DISAGREES, running_outside[0].text[:_PREVIEW_CHARS]
    running_inside = [line for line in inside if line.words >= min_words]
    if inside and len(running_inside) * 2 > len(inside):
        return DECLINE_TEXT_BLOCK, f"{len(running_inside)} of {len(inside)} lines"
    for line in inside:
        if _body_or_larger(line.size, body) and _has_letter_or_digit(line.text):
            return DECLINE_RUNNING_TEXT, line.text[:_PREVIEW_CHARS]
    for line in inside:
        if _has_letter(line.text) and (line.box[2] - line.box[0]) >= full_line_ratio * column:
            return DECLINE_FULL_LINE, line.text[:_PREVIEW_CHARS]
    return None


# ----------------------------------------------------------------------------------------------- applying it


def _picture_density(image: PdfImageObject) -> float | None:
    """Pixels per point of an emitted picture as slice A delivered it (a frame render: its PNG over its explicit
    size; otherwise the file over its frame). ``None`` when the file header cannot be read."""

    try:
        from PIL import Image

        with Image.open(io.BytesIO(image.image_bytes)) as opened:
            width_px, height_px = opened.size
    except Exception:  # noqa: BLE001 - the region is then declined
        return None
    if image.display_width_points and image.display_height_points:
        width, height = float(image.display_width_points), float(image.display_height_points)
    else:
        box = _member_box(image)
        width, height = box[2] - box[0], box[3] - box[1]
    if width <= 0 or height <= 0 or width_px <= 0 or height_px <= 0:
        return None
    return max(width_px / width, height_px / height)


def _key(image: PdfImageObject) -> Key | None:
    if image.discovery_index is None:
        return None
    return (image.page_number, int(image.discovery_index))


class _Declined(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


def replace_composite_figures(
    pdf_path: str | Path,
    extraction: PdfImageExtraction,
    images_a: Sequence[PdfImageObject],
    spans: Sequence[object],
    *,
    max_image_count: int | None = None,
) -> FigureRegionOutcome:
    """Slice B on slice A's output. Never raises: a failure keeps slice A's pictures (page or document) and logs."""

    from docxaicorrector.pdf_import.image_frames import _within_pixel_budget
    from docxaicorrector.pdf_import.logical_import import pdf_body_typography
    from docxaicorrector.pdf_import.page_render import (
        PageGeometryMismatch,
        encode_frame_png,
        frame_geometry,
        open_pdf_for_rendering,
        read_page_geometry,
        render_frame,
    )

    unchanged = FigureRegionOutcome(images=tuple(images_a))
    pages = seed_pages(extraction)
    if not pages:
        return unchanged
    stage = "inventory"
    try:
        graphics = read_page_graphics(pdf_path, pages)
        stage = "typography"
        typography = pdf_body_typography(list(spans))  # type: ignore[arg-type]
        stage = "page_geometry"
        geometries = read_page_geometry(pdf_path, pages)
        stage = "plan"
        plan = plan_figure_regions(
            extraction, spans, graphics, typography, {page: geometry.layout_cropbox for page, geometry in geometries.items()}
        )
    except Exception as exc:  # noqa: BLE001 - every page stays as slice A delivered it
        for page in pages:
            _log_failed(pdf_path, page, stage, exc)
        return FigureRegionOutcome(images=tuple(images_a), seed_pages=len(pages), failed=len(pages))

    declines = list(plan.declines)
    by_key = {key: image for image in images_a if (key := _key(image)) is not None}
    regions_by_page: dict[int, list[FigureRegion]] = {}
    for region in plan.regions:
        regions_by_page.setdefault(region.page_number, []).append(region)
    rendered: dict[int, list[tuple[FigureRegion, PdfImageObject, dict]]] = {}
    failed = 0
    if regions_by_page:
        try:
            with open_pdf_for_rendering(pdf_path) as document:
                for page, page_regions in regions_by_page.items():
                    stage = "render"
                    built: list[tuple[FigureRegion, PdfImageObject, dict]] = []
                    try:
                        geometry_of_page = geometries[page]
                        if geometry_of_page.user_unit != 1.0:
                            raise _Declined(DECLINE_USER_UNIT)
                        for region in page_regions:
                            members = tuple(by_key[key] for key in region.member_keys)
                            member_densities = [_picture_density(member) for member in members]
                            if any(density is None for density in member_densities):
                                raise _Declined(DECLINE_UNKNOWN_DENSITY, "an emitted member has no readable size")
                            candidates = [d for d in member_densities if d is not None]
                            member_scale = max(candidates) if candidates else None
                            scale = max(v for v in (member_scale, region.seed_density) if v is not None) if (
                                member_scale is not None or region.seed_density is not None
                            ) else None
                            if not scale or scale <= 0:
                                raise _Declined(DECLINE_UNKNOWN_DENSITY)
                            stage = "render"
                            geometry = frame_geometry(region.box, crop=geometry_of_page.layout_cropbox, scale=scale)
                            if geometry is None:
                                raise _Declined(DECLINE_OUTSIDE_CROP_BOX)
                            if not _within_pixel_budget(geometry):
                                raise _Declined(DECLINE_EXCEEDS_PIXEL_BUDGET, f"{geometry.width_px}x{geometry.height_px}")
                            try:
                                picture = render_frame(document, page_number=page, page_geometry=geometry_of_page, geometry=geometry)
                            except PageGeometryMismatch as exc:
                                raise _Declined(DECLINE_PAGE_GEOMETRY_DISAGREES, str(exc)) from exc
                            stage = "encode"
                            encoded = encode_frame_png(picture, geometry)
                            top = max(0.0, region.box[1])
                            image = PdfImageObject(
                                page_number=page,
                                x0=region.box[0],
                                top=top,
                                x1=region.box[2],
                                bottom=max(top, region.box[3]),
                                page_height=members[0].page_height if members else None,
                                image_bytes=encoded.png_bytes,
                                mime_type="image/png",
                                source_index=max(0, (page - 1) * 10000 + int(round(top))),
                                width_points=region.box[2] - region.box[0],
                                height_points=region.box[3] - region.box[1],
                                display_width_points=geometry.frame_width_points,
                                display_height_points=geometry.frame_height_points,
                                frame_box=region.box,
                                region_members=members,
                            )
                            built.append(
                                (
                                    region,
                                    image,
                                    {
                                        "scale_dpi": round(scale * 72.0, 2),
                                        "scale_source": "member" if member_scale is not None and member_scale >= (region.seed_density or 0.0) else "seeds",
                                        "width_px": geometry.width_px,
                                        "height_px": geometry.height_px,
                                        "bytes": len(encoded.png_bytes),
                                        "grayscale": encoded.grayscale,
                                    },
                                )
                            )
                    except _Declined as declined:
                        declines.extend(
                            RegionDecline(page, declined.reason, declined.detail, region.box, region.seed_count) for region in page_regions
                        )
                        continue
                    except Exception as exc:  # noqa: BLE001 - this page stays as slice A delivered it
                        failed += 1
                        _log_failed(pdf_path, page, stage, exc)
                        continue
                    rendered[page] = built
        except Exception as exc:  # noqa: BLE001 - the renderer could not open the document
            for page in regions_by_page:
                if page not in rendered:
                    failed += 1
                    _log_failed(pdf_path, page, "render", exc)

    absorbed = {key for built in rendered.values() for region, _image, _info in built for key in region.member_keys}
    region_images = [image for built in rendered.values() for _region, image, _info in built]
    images = [image for image in images_a if _key(image) not in absorbed] + region_images
    images.sort(key=lambda image: (image.page_number, image.top, image.x0))
    if max_image_count is not None and len(images) > max_image_count:
        for page, built in rendered.items():
            declines.extend(
                RegionDecline(page, DECLINE_IMAGE_COUNT_CAP, f"{len(images)} > {max_image_count}", region.box, region.seed_count)
                for region, _image, _info in built
            )
        _log_declines(pdf_path, declines)
        return FigureRegionOutcome(images=tuple(images_a), seed_pages=len(pages), declined=len(declines), failed=failed)

    _log_declines(pdf_path, declines)
    absorbed_frame_renders = 0
    for page, built in rendered.items():
        for region, image, info in built:
            members = image.region_members or ()
            renders = sum(1 for member in members if member.original_image_bytes is not None)
            absorbed_frame_renders += renders
            log_event(
                logging.INFO,
                "pdf_figure_region_rendered",
                "A composite figure was rendered as one picture of its page region; its text stays as paragraphs.",
                pdf_path=str(pdf_path),
                page_number=page,
                box=[round(value, 1) for value in region.box],
                seed_count=region.seed_count,
                image_count=region.image_count,
                path_count=region.path_count,
                members_emitted=len(members),
                member_keys=[list(key) for key in region.member_keys],
                absorbed_frame_renders=renders,
                grown_line_count=region.grown_line_count,
                **info,
            )
    return FigureRegionOutcome(
        images=tuple(images),
        seed_pages=len(pages),
        rendered=len(region_images),
        declined=len(declines),
        failed=failed,
        images_absorbed=len(absorbed),
        absorbed_frame_renders=absorbed_frame_renders,
    )


def _log_declines(pdf_path: str | Path, declines: Sequence[RegionDecline]) -> None:
    for decline in declines:
        log_event(
            logging.INFO,
            "pdf_figure_region_declined",
            "A composite-figure region was not rendered; its page stays as it is imported without the step.",
            pdf_path=str(pdf_path),
            page_number=decline.page_number,
            box=None if decline.box is None else [round(value, 1) for value in decline.box],
            seed_count=decline.seed_count,
            reason=decline.reason,
            detail=decline.detail[:_PREVIEW_CHARS],
        )


def _log_failed(pdf_path: str | Path, page: int | None, stage: str, exc: BaseException) -> None:
    log_event(
        logging.ERROR,
        "pdf_figure_region_failed",
        "Rendering a composite-figure region failed; the page keeps the pictures it is imported with without the step.",
        pdf_path=str(pdf_path),
        page_number=page,
        stage=stage,
        error_type=exc.__class__.__name__,
        error_message=str(exc)[:_PREVIEW_CHARS],
    )
