"""Spec 082 slice A, acceptance round 2: what the page does to an image besides placing it.

The frame-render replacement compares a stored image with the render of its frame. That comparison says
something about the IMAGE only when the image alone decides what the frame shows. pdfminer's layout does not
say whether it does: its interpreter ignores clipping (``W``, ``W*``), graphics-state dictionaries (``gs``,
where a soft mask lives) and shadings (``sh``), and its path objects keep only end points (a Bezier curve's
bulge is outside its box). This module runs the same interpretation pdfminer runs for the layout -- the same
resource manager, aggregator and ``LAParams`` as ``pdfminer.high_level.extract_pages`` -- through subclasses
that OBSERVE it, and records:

- every painted path and shading as a conservative box: all path points including Bezier control points
  (a curve lies in the convex hull of its control points), widened by how far a stroke can reach past them;
  a shading paints its whole clip, or the whole page when nothing clips it;
- for every image: whether a mask decides where it is transparent (its own ``/SMask``, ``/Mask``,
  ``/ImageMask``, ``/SMaskInData``, or a soft mask in the graphics state it is drawn with), and the clipping
  paths in force when it is drawn, a form's ``/BBox`` included.

The layout itself is unchanged: every overridden method calls pdfminer's own first, and nothing here alters
the interpreter's graphics state. Coordinates are pdfminer's layout space (origin bottom-left).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Box = tuple[float, float, float, float]

CLIP_RECTANGLE = "rectangle"
CLIP_OTHER = "other"

_WHOLE_PAGE: Box = (-math.inf, -math.inf, math.inf, math.inf)


@dataclass(frozen=True)
class PaintedRegion:
    """A conservative box around what one path or shading painted (layout space, origin bottom-left).

    ``reach`` is how far paint may extend past the box (a stroke's half width with its joins and caps);
    ``hairline`` marks a stroke of width 0, which PDF draws one device pixel wide."""

    box: Box
    reach: float
    hairline: bool
    kind: str


@dataclass(frozen=True)
class ClipEntry:
    """One clipping path in force: an axis-aligned rectangle, or any other shape (``CLIP_OTHER``), with its
    conservative box."""

    kind: str
    box: Box


@dataclass(frozen=True)
class ImagePaintEvidence:
    mask: str | None
    clips: tuple[ClipEntry, ...]


@dataclass
class PageEvidence:
    painted: list[PaintedRegion]
    images: dict[int, tuple[object, ImagePaintEvidence]]

    def for_image(self, item: object) -> ImagePaintEvidence | None:
        found = self.images.get(id(item))
        if found is None or found[0] is not item:
            return None
        return found[1]


def _apply(ctm, x: float, y: float) -> tuple[float, float]:
    a, b, c, d, e, f = ctm
    return (a * x + c * y + e, b * x + d * y + f)


def _matrix_norm(ctm) -> float:
    """The largest factor by which ``ctm`` stretches a length (its spectral norm)."""

    a, b, c, d = (float(v) for v in ctm[:4])
    s = a * a + b * b + c * c + d * d
    det = a * d - b * c
    return math.sqrt(max(0.0, (s + math.sqrt(max(0.0, s * s - 4.0 * det * det))) / 2.0))


def _segment_points(path) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for segment in path:
        values = segment[1:]
        for index in range(0, len(values) - 1, 2):
            try:
                points.append((float(values[index]), float(values[index + 1])))
            except (TypeError, ValueError):
                continue
    return points


def _bounds(points: list[tuple[float, float]]) -> Box | None:
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _subpaths(path) -> list[list[tuple[str, list[tuple[float, float]]]]]:
    subpaths: list[list[tuple[str, list[tuple[float, float]]]]] = []
    for segment in path:
        operator = str(segment[0])
        if operator == "m" or not subpaths:
            subpaths.append([])
        subpaths[-1].append((operator, _segment_points([segment])))
    return subpaths


def clip_entry(path, ctm) -> ClipEntry:
    """Classify a clipping path. It is a rectangle when, after dropping subpaths that enclose no area (a lone
    ``m``, as InDesign writes after a ``re``), exactly one subpath remains, it is made of straight segments
    only, and its corners -- repeated points and a closing point equal to the start removed -- are the four
    corners of an axis-aligned box. Anything else (curves, slanted edges, several subpaths, an empty path) is
    ``CLIP_OTHER``: its shape is not followed further. A clip is implicitly closed (PDF 32000-1 8.5.4)."""

    device = [_apply(ctm, x, y) for x, y in _segment_points(path)]
    box = _bounds(device)
    if box is None:
        return ClipEntry(CLIP_OTHER, _WHOLE_PAGE)
    drawn = [subpath for subpath in _subpaths(path) if any(operator not in {"m", "h"} for operator, _points in subpath)]
    if len(drawn) != 1 or any(operator not in {"m", "l", "h"} for operator, _points in drawn[0]):
        return ClipEntry(CLIP_OTHER, box)
    corners: list[tuple[float, float]] = []
    for _operator, points in drawn[0]:
        for x, y in points:
            point = _apply(ctm, x, y)
            if not corners or corners[-1] != point:
                corners.append(point)
    if len(corners) > 1 and corners[-1] == corners[0]:
        corners.pop()
    corner_box = _bounds(corners)
    if (
        len(corners) == 4
        and len(set(corners)) == 4
        and corner_box is not None
        and corner_box[2] > corner_box[0]
        and corner_box[3] > corner_box[1]
    ):
        edges = list(zip(corners, corners[1:] + corners[:1]))
        if all(p[0] == q[0] or p[1] == q[1] for p, q in edges) and all(
            p[0] in (corner_box[0], corner_box[2]) and p[1] in (corner_box[1], corner_box[3]) for p in corners
        ):
            return ClipEntry(CLIP_RECTANGLE, corner_box)
    return ClipEntry(CLIP_OTHER, box)


def _intersection(entries: tuple[ClipEntry, ...]) -> Box:
    box = _WHOLE_PAGE
    for entry in entries:
        box = (max(box[0], entry.box[0]), max(box[1], entry.box[1]), min(box[2], entry.box[2]), min(box[3], entry.box[3]))
    return box


def _image_mask(stream) -> str | None:
    get = getattr(stream, "get_any", None)
    if get is None:
        return None
    if get(("SMask",)) is not None:
        return "SMask"
    if get(("Mask",)) is not None:
        return "Mask"
    if _truthy(get(("IM", "ImageMask"))):
        return "ImageMask"
    if _truthy(get(("SMaskInData",))):
        return "SMaskInData"
    return None


def _truthy(value) -> bool:
    try:
        from pdfminer.pdftypes import resolve1

        value = resolve1(value)
    except Exception:  # noqa: BLE001 - an unresolvable flag counts as set: the check is conservative
        return value is not None
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return True


def iter_pages_with_evidence(pdf_path: str | Path) -> Iterator[tuple[Any, PageEvidence]]:
    """``pdfminer.high_level.extract_pages`` with the paint evidence of each page."""

    from pdfminer.converter import PDFPageAggregator
    from pdfminer.layout import LAParams
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdftypes import dict_value, list_value, resolve1, stream_value
    from pdfminer.psparser import literal_name
    from pdfminer.utils import mult_matrix

    class _Aggregator(PDFPageAggregator):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.evidence = PageEvidence(painted=[], images={})
            self.observer: Any = None
            self.painting = False

        def begin_page(self, page, ctm) -> None:
            self.evidence = PageEvidence(painted=[], images={})
            super().begin_page(page, ctm)

        def paint_path(self, gstate, stroke, fill, evenodd, path) -> None:
            # pdfminer re-enters paint_path once per subpath; the whole path is recorded once.
            if self.painting:
                super().paint_path(gstate, stroke, fill, evenodd, path)
                return
            self.painting = True
            try:
                super().paint_path(gstate, stroke, fill, evenodd, path)
            finally:
                self.painting = False
            box = _bounds([_apply(self.ctm, x, y) for x, y in _segment_points(path)])
            if box is None:
                return
            reach = 0.0
            hairline = False
            if stroke:
                width = float(getattr(self.observer, "line_width", 1.0)) if self.observer is not None else 1.0
                if width <= 0:
                    hairline = True
                else:
                    reach = width / 2.0 * _matrix_norm(self.ctm) * _join_factor(gstate)
            self.evidence.painted.append(PaintedRegion(box=box, reach=reach, hairline=hairline, kind="path"))

        def render_image(self, name, stream) -> None:
            super().render_image(name, stream)
            item = self.cur_item._objs[-1]
            observer = self.observer
            mask = _image_mask(stream)
            if mask is None and observer is not None and observer.soft_mask:
                mask = "ExtGState SMask"
            clips = tuple(observer.clips) if observer is not None else ()
            self.evidence.images[id(item)] = (item, ImagePaintEvidence(mask=mask, clips=clips))

    class _Interpreter(PDFPageInterpreter):
        def __init__(self, rsrcmgr, device) -> None:
            super().__init__(rsrcmgr, device)
            self.inherited: tuple[tuple[ClipEntry, ...], bool, float] = ((), False, 1.0)
            self.pending_form_clip: ClipEntry | None = None

        def dup(self):
            child = super().dup()
            clips = self.clips + ((self.pending_form_clip,) if self.pending_form_clip is not None else ())
            child.inherited = (clips, self.soft_mask, self.line_width)  # type: ignore[attr-defined]
            return child

        def init_resources(self, resources) -> None:
            super().init_resources(resources)
            self.extgstates: dict[object, object] = {}
            try:
                found = dict_value(resources).get("ExtGState") if resources else None
                self.extgstates = dict(dict_value(found)) if found is not None else {}
            except Exception:  # noqa: BLE001 - unreadable resources: every gs then counts as a soft mask
                self.extgstates = {}

        def init_state(self, ctm) -> None:
            super().init_state(ctm)
            self.clips, self.soft_mask, self.line_width = self.inherited
            self.evidence_stack: list[tuple[tuple[ClipEntry, ...], bool, float]] = []

        def render_contents(self, resources, streams, ctm=(1, 0, 0, 1, 0, 0)) -> None:
            previous = device.observer
            device.observer = self
            try:
                super().render_contents(resources, streams, ctm=ctm)
            finally:
                device.observer = previous

        def do_q(self) -> None:
            self.evidence_stack.append((self.clips, self.soft_mask, self.line_width))
            super().do_q()

        def do_Q(self) -> None:
            if self.evidence_stack:
                self.clips, self.soft_mask, self.line_width = self.evidence_stack.pop()
            super().do_Q()

        def do_w(self, linewidth) -> None:
            super().do_w(linewidth)
            try:
                self.line_width = float(resolve1(linewidth))
            except (TypeError, ValueError):
                pass

        def do_W(self) -> None:
            super().do_W()
            self.clips = self.clips + (clip_entry(self.curpath, self.ctm),)

        def do_W_a(self) -> None:
            super().do_W_a()
            self.clips = self.clips + (clip_entry(self.curpath, self.ctm),)

        def do_gs(self, name) -> None:
            super().do_gs(name)
            try:
                state = dict_value(self.extgstates.get(literal_name(name)))
            except Exception:  # noqa: BLE001 - a state that cannot be read may hold a soft mask
                self.soft_mask = True
                return
            if "SMask" in state:
                value = resolve1(state["SMask"])
                self.soft_mask = not (hasattr(value, "name") and literal_name(value) == "None")

        def do_sh(self, name) -> None:
            super().do_sh(name)
            device.evidence.painted.append(PaintedRegion(box=_intersection(self.clips), reach=0.0, hairline=False, kind="shading"))

        def do_Do(self, xobjid_arg) -> None:
            self.pending_form_clip = None
            try:
                xobj = stream_value(self.xobjmap[literal_name(xobjid_arg)])
                if xobj.get("Subtype") is not None and literal_name(xobj.get("Subtype")) == "Form" and "BBox" in xobj:
                    bbox = [float(v) for v in list_value(xobj["BBox"])]
                    matrix = list_value(xobj.get("Matrix", (1, 0, 0, 1, 0, 0)))
                    form_ctm = mult_matrix(tuple(float(v) for v in matrix), self.ctm)  # type: ignore[arg-type]
                    outline = [("m", bbox[0], bbox[1]), ("l", bbox[2], bbox[1]), ("l", bbox[2], bbox[3]), ("l", bbox[0], bbox[3]), ("h",)]
                    self.pending_form_clip = clip_entry(outline, form_ctm)
            except Exception:  # noqa: BLE001 - pdfminer's own do_Do decides what to do with a broken XObject
                self.pending_form_clip = None
            try:
                super().do_Do(xobjid_arg)
            finally:
                self.pending_form_clip = None

    with open(pdf_path, "rb") as handle:
        manager = PDFResourceManager(caching=True)
        device = _Aggregator(manager, laparams=LAParams())
        interpreter = _Interpreter(manager, device)
        for page in PDFPage.get_pages(handle, None, maxpages=0, password="", caching=True):
            interpreter.process_page(page)
            yield device.get_result(), device.evidence


def _join_factor(gstate) -> float:
    """How far a stroke may reach past its path, in half line widths: a square cap reaches sqrt(2) at a
    corner; a miter join reaches up to the miter limit (PDF 32000-1 8.4.3.5, default 10)."""

    join = _number(getattr(gstate, "linejoin", None), 0.0)
    if join == 0.0:
        return max(math.sqrt(2.0), _number(getattr(gstate, "miterlimit", None), 10.0))
    return math.sqrt(2.0)


def _number(value, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default
