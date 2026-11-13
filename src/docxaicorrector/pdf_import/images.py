"""Extract reusable image files from PDF text-layer source documents."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from docxaicorrector.core.logger import log_event
from docxaicorrector.pdf_import.paint_evidence import ClipEntry, iter_pages_with_evidence

# Defensive page budget for a *direct* call into this extractor. The primary
# resource budget lives in ``processing.processing_runtime`` and rejects
# over-budget documents before this function runs, but this belt-and-suspenders
# cap keeps a direct caller from iterating an unbounded page tree. Truncation is
# logged (never silent).
_MAX_PDF_IMAGE_SOURCE_PAGES = 2000


@dataclass(frozen=True)
class PdfImageObject:
    page_number: int
    x0: float
    top: float
    x1: float
    bottom: float
    page_height: float | None
    image_bytes: bytes
    mime_type: str | None
    source_index: int
    width_points: float | None = None
    height_points: float | None = None
    # Spec 082: the image's key in the page walk -- ``(page_number, discovery_index)`` names the same
    # object as the ``PdfDiscoveredImage`` of the inventory -- and the family of its PDF colour space.
    discovery_index: int | None = None
    colour_space_family: str | None = None
    # Spec 082 slice A: set only on an image whose bytes were replaced by a render of its own page frame.
    # ``display_*`` is the size the picture is given in the DOCX (the rendered frame, in points), and
    # ``original_*`` keeps the bytes the extractor emitted, so a failed insertion falls back to them.
    display_width_points: float | None = None
    display_height_points: float | None = None
    original_image_bytes: bytes | None = None
    original_mime_type: str | None = None
    # The matrix that placed the image's unit square, in pdfminer's layout space (page rotation
    # included): the ``matrix`` of the ``LTFigure`` pdfminer opens for the image's ``Do``. ``None``
    # when the walk could not see it.
    placement_matrix: tuple[float, float, float, float, float, float] | None = None
    # Spec 082 acceptance round 2. ``frame_box`` is the image's true frame ``(x0, top, x1, bottom)``,
    # top-origin, NOT clamped to the page (``top`` above is clamped to 0 for the ordering key and may
    # understate how far the image reaches past the top edge); ``None`` falls back to the fields above.
    # ``mask`` names what decides where the image is transparent (``SMask``, ``Mask``, ``ImageMask``,
    # ``SMaskInData``, ``ExtGState SMask``) and ``clips`` the clipping paths in force when it is drawn
    # (``paint_evidence.ClipEntry`` with a top-origin box). The defaults mean "none seen"; the extractor
    # always fills them from the page walk.
    frame_box: tuple[float, float, float, float] | None = None
    mask: str | None = None
    clips: tuple[ClipEntry, ...] = ()


@dataclass(frozen=True)
class PdfPaintedRegion:
    """A path or shading painted on a page (spec 082 acceptance round 2): a conservative top-origin box
    ``(x0, top, x1, bottom)``, how far a stroke may reach past it, and whether it is a zero-width stroke."""

    page_number: int
    x0: float
    top: float
    x1: float
    bottom: float
    reach: float
    hairline: bool
    kind: str


# Why a discovered image was not emitted (``PdfDiscoveredImage.skip_reason``).
SKIP_NO_IMAGE_BYTES = "no_image_bytes"
SKIP_UNKNOWN_MIME = "unknown_mime"


@dataclass(frozen=True)
class PdfDiscoveredImage:
    """Every ``LTImage`` the walk met, emitted or not (spec 082 FR-A10)."""

    page_number: int
    discovery_index: int
    x0: float
    top: float
    x1: float
    bottom: float
    colour_space_family: str | None
    skip_reason: str | None
    frame_box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class PdfImageExtraction:
    images: tuple[PdfImageObject, ...]
    discovered: tuple[PdfDiscoveredImage, ...]
    pages_truncated: bool = False
    painted: tuple[PdfPaintedRegion, ...] = ()


def extract_pdf_images_and_inventory(pdf_path: str | Path) -> PdfImageExtraction:
    """Extract embedded PDF images that are already stored as image files, and list every image met.

    Raw bitmap streams that would need raster reconstruction are not emitted; they stay in the
    inventory with their skip reason. Nothing is logged about the outcome here: the summary event is
    written once, after spec 082's frame replacements, by ``log_pdf_image_extraction_outcome``.
    """

    try:
        from pdfminer.layout import LTFigure, LTImage
    except ImportError as exc:  # pragma: no cover - depends on optional env
        raise RuntimeError("optional_dependency_missing:pdfminer.six") from exc

    images: list[PdfImageObject] = []
    discovered: list[PdfDiscoveredImage] = []
    painted: list[PdfPaintedRegion] = []
    pages_truncated = False
    # The same walk as ``pdfminer.high_level.extract_pages``, observed for what the page does to each image
    # besides placing it (``paint_evidence``); the layout is unchanged.
    for page_index, (page_layout, evidence) in enumerate(iter_pages_with_evidence(pdf_path), start=1):
        if page_index > _MAX_PDF_IMAGE_SOURCE_PAGES:
            pages_truncated = True
            log_event(
                logging.WARNING,
                "pdf_image_extraction_page_budget_exceeded",
                "PDF image extraction truncated: page budget exceeded (remaining pages not scanned for images).",
                pdf_path=str(pdf_path),
                max_pages=_MAX_PDF_IMAGE_SOURCE_PAGES,
            )
            break
        page_height = _coerce_optional_float(getattr(page_layout, "height", None))
        for region in evidence.painted:
            x0, top, x1, bottom = _top_origin_box(region.box, page_height)
            painted.append(
                PdfPaintedRegion(
                    page_number=page_index,
                    x0=x0,
                    top=top,
                    x1=x1,
                    bottom=bottom,
                    reach=region.reach,
                    hairline=region.hairline,
                    kind=region.kind,
                )
            )
        for discovery_index, (image, placement_matrix) in enumerate(
            _iter_pdfminer_images_with_placement(page_layout, lt_image_type=LTImage, lt_figure_type=LTFigure)
        ):
            y0 = float(getattr(image, "y0", 0.0) or 0.0)
            y1 = float(getattr(image, "y1", 0.0) or 0.0)
            top, bottom = _pdfminer_top_origin_bounds(y0=y0, y1=y1, page_height=page_height)
            x0 = float(getattr(image, "x0", 0.0) or 0.0)
            x1 = float(getattr(image, "x1", x0) or x0)
            frame_box = _top_origin_box((x0, y0, x1, y1), page_height)
            image_evidence = evidence.for_image(image)
            if image_evidence is None:
                mask, clips = "unknown", ()
            else:
                mask = image_evidence.mask
                clips = tuple(ClipEntry(entry.kind, _top_origin_box(entry.box, page_height)) for entry in image_evidence.clips)
            family = _colour_space_family(image)
            image_bytes = _extract_pdfminer_image_file_bytes(image)
            mime_type = _detect_image_mime_type(image_bytes) if image_bytes else None
            skip_reason = None
            if not image_bytes:
                skip_reason = SKIP_NO_IMAGE_BYTES
            elif mime_type is None:
                skip_reason = SKIP_UNKNOWN_MIME
            discovered.append(
                PdfDiscoveredImage(
                    page_number=page_index,
                    discovery_index=discovery_index,
                    x0=x0,
                    top=top,
                    x1=x1,
                    bottom=bottom,
                    colour_space_family=family,
                    skip_reason=skip_reason,
                    frame_box=frame_box,
                )
            )
            if skip_reason is not None or image_bytes is None:
                continue
            images.append(
                PdfImageObject(
                    page_number=page_index,
                    x0=x0,
                    top=top,
                    x1=x1,
                    bottom=bottom,
                    page_height=page_height,
                    image_bytes=image_bytes,
                    mime_type=mime_type,
                    source_index=max(0, (page_index - 1) * 10000 + int(round(top))),
                    width_points=max(0.0, x1 - x0),
                    height_points=max(0.0, bottom - top),
                    discovery_index=discovery_index,
                    colour_space_family=family,
                    placement_matrix=placement_matrix,
                    frame_box=frame_box,
                    mask=mask,
                    clips=clips,
                )
            )
    return PdfImageExtraction(
        images=tuple(sorted(images, key=lambda item: (item.page_number, item.top, item.x0))),
        discovered=tuple(discovered),
        pages_truncated=pages_truncated,
        painted=tuple(painted),
    )


def log_pdf_image_extraction_outcome(
    extraction: PdfImageExtraction,
    *,
    pdf_path: str | Path,
    frame_render_enabled: bool = True,
    frame_render_checked: int = 0,
    frame_render_replaced: int = 0,
    frame_render_declined: int = 0,
    frame_render_failed: int = 0,
) -> None:
    """The one outcome event of PDF image extraction (spec 082 FR-A10).

    ``discovered`` / ``emitted`` / ``skipped`` keep the meaning they had before spec 082 and are counted
    from the inventory's skip reasons, so they cannot drift from it: an image the extractor does not emit
    is still reported as skipped. The frame-render counters say how many emitted images were compared with
    a render of their page frame, replaced by it, declined, or failed to render; ``frame_render_enabled``
    is false where the step does not run (the OCR branch).
    """

    discovered_count = len(extraction.discovered)
    emitted_count = len(extraction.images)
    skipped_no_image_bytes = sum(1 for item in extraction.discovered if item.skip_reason == SKIP_NO_IMAGE_BYTES)
    skipped_unknown_mime = sum(1 for item in extraction.discovered if item.skip_reason == SKIP_UNKNOWN_MIME)
    skipped_count = skipped_no_image_bytes + skipped_unknown_mime
    frame_counters = {
        "frame_render_enabled": frame_render_enabled,
        "frame_render_checked": frame_render_checked,
        "frame_render_replaced": frame_render_replaced,
        "frame_render_declined": frame_render_declined,
        "frame_render_failed": frame_render_failed,
    }
    if skipped_count > 0:
        # Discovered images that never became emittable objects are a silent
        # image-loss signal; surface it at WARNING so it is observable.
        log_event(
            logging.WARNING,
            "pdf_image_extraction_dropped_images",
            "PDF images were discovered but not emitted; possible silent image loss.",
            pdf_path=str(pdf_path),
            discovered=discovered_count,
            emitted=emitted_count,
            skipped=skipped_count,
            skipped_no_image_bytes=skipped_no_image_bytes,
            skipped_unknown_mime=skipped_unknown_mime,
            pages_truncated=extraction.pages_truncated,
            **frame_counters,
        )
    else:
        log_event(
            logging.INFO,
            "pdf_image_extraction_summary",
            "PDF image extraction completed.",
            pdf_path=str(pdf_path),
            discovered=discovered_count,
            emitted=emitted_count,
            pages_truncated=extraction.pages_truncated,
            **frame_counters,
        )


def _colour_space_family(image: object) -> str | None:
    """The family of the image's PDF colour space: the name itself, or the first element of an array
    (``[/Separation /Black ...]`` -> ``Separation``). ``None`` when the stream carries none (an image mask)."""

    attrs = getattr(getattr(image, "stream", None), "attrs", None)
    if not isinstance(attrs, dict):
        return None
    value = attrs.get("ColorSpace", attrs.get("CS"))
    if value is None:
        return None
    try:
        from pdfminer.pdftypes import resolve1
    except ImportError:  # pragma: no cover - depends on optional env
        return None
    try:
        value = resolve1(value)
        if isinstance(value, list):
            if not value:
                return None
            value = resolve1(value[0])
    except Exception:
        return None
    name = getattr(value, "name", value)
    if isinstance(name, bytes):
        name = name.decode("latin-1", errors="replace")
    return name if isinstance(name, str) and name else None


def _iter_pdfminer_images_with_placement(
    element,
    *,
    lt_image_type: type,
    lt_figure_type: type,
    placement: tuple[float, float, float, float, float, float] | None = None,
) -> Iterable[tuple[object, tuple[float, float, float, float, float, float] | None]]:
    """Each ``LTImage`` with the matrix of the nearest enclosing ``LTFigure`` -- pdfminer wraps every
    image ``Do`` in a figure whose matrix is the CTM at the ``Do`` (``PDFPageInterpreter.do_Do``)."""

    if isinstance(element, lt_image_type):
        yield element, placement
        return
    if isinstance(element, lt_figure_type) or hasattr(element, "__iter__"):
        if isinstance(element, lt_figure_type):
            placement = _coerce_matrix(getattr(element, "matrix", None))
        try:
            children = list(element)
        except TypeError:
            return
        for child in children:
            yield from _iter_pdfminer_images_with_placement(
                child,
                lt_image_type=lt_image_type,
                lt_figure_type=lt_figure_type,
                placement=placement,
            )


def _coerce_matrix(value: object) -> tuple[float, float, float, float, float, float] | None:
    if value is None:
        return None
    try:
        numbers = [float(v) for v in value]  # type: ignore[union-attr]
    except (TypeError, ValueError):
        return None
    if len(numbers) != 6:
        return None
    return (numbers[0], numbers[1], numbers[2], numbers[3], numbers[4], numbers[5])


def _extract_pdfminer_image_file_bytes(image: object) -> bytes | None:
    stream = getattr(image, "stream", None)
    if stream is None:
        return None
    for method_name in ("get_rawdata", "get_data"):
        method = getattr(stream, method_name, None)
        if method is None:
            continue
        try:
            data = method()
        except Exception:
            continue
        if isinstance(data, bytes) and data:
            return data
    return None


def _detect_image_mime_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    return None


def _pdfminer_top_origin_bounds(
    *,
    y0: float,
    y1: float,
    page_height: float | None,
) -> tuple[float, float]:
    if not page_height or page_height <= 0:
        return float(y1), float(y0)
    top = max(0.0, page_height - float(y1))
    bottom = max(top, page_height - float(y0))
    return top, bottom


def _top_origin_box(box: tuple[float, float, float, float], page_height: float | None) -> tuple[float, float, float, float]:
    """A layout box ``(x0, y0, x1, y1)`` (origin bottom-left) as ``(x0, top, x1, bottom)``, NOT clamped to
    the page: the admission checks of spec 082 need to see how far a frame reaches past an edge."""

    x0, y0, x1, y1 = (float(v) for v in box)
    if not page_height or page_height <= 0:
        return (x0, y1, x1, y0)
    return (x0, page_height - y1, x1, page_height - y0)


def _coerce_optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
