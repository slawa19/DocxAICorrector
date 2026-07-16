"""Document-level scan-origin (OCR) provenance classification.

Scanned documents that were OCR'd into DOCX fragment the body into hundreds of
continuous sections, one per detected column region per page, so their
``word/document.xml`` carries a large number of multi-column section definitions
(``<w:cols w:num="N">`` with ``N >= 2``). Authored documents set a column layout
at most a handful of times. This is a structural provenance signal — it does not
look at document text or the filename (Constitution VII: universal, no per-book
literals).

Measured on the reference corpus:

===================  ==============  ================  ==============
Source               tables          w:cols num>=2     media (images)
===================  ==============  ================  ==============
RESISTANCE (scan)    3               129               86
Mazzucato (authored) 3               0                 0
Lietaer (authored)   0               2                 0
===================  ==============  ================  ==============

The threshold below is pinned by those counter-proofs: an absolute floor well
above the authored tail (0-2), plus a density ratio so that a document which is
merely long does not drift over the floor. RESISTANCE clears both bars by a wide
margin; Mazzucato/Lietaer clear neither.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO

# Count only <w:cols> that declare two or more columns. A bare <w:cols> (or
# num="1") is a single-column section and is not a scan signal.
_COLS_NUM_PATTERN = re.compile(r"<w:cols\b[^>]*\bw:num=\"(\d+)\"")
_SECTPR_PATTERN = re.compile(r"<w:sectPr\b")

# Pinned thresholds (see module docstring). RESISTANCE=129 multi-col over 376
# sections (ratio 0.34); authored corpus tops out at 2 multi-col sections.
SCAN_MULTI_COLUMN_ABSOLUTE_MIN = 10
SCAN_MULTI_COLUMN_RATIO_MIN = 0.10


@dataclass(frozen=True)
class ScanOriginClassification:
    is_scan_origin: bool
    multi_column_section_count: int
    total_section_count: int
    multi_column_ratio: float


def classify_document_scan_origin(source_bytes: bytes) -> ScanOriginClassification:
    """Classify a DOCX archive as scan-origin (OCR) or authored from structure."""
    document_xml = _read_document_xml(source_bytes)
    return classify_scan_origin_from_document_xml(document_xml)


def classify_scan_origin_from_document_xml(document_xml: str) -> ScanOriginClassification:
    multi_column_count = sum(1 for value in _COLS_NUM_PATTERN.findall(document_xml) if int(value) >= 2)
    total_sections = len(_SECTPR_PATTERN.findall(document_xml))
    ratio = multi_column_count / total_sections if total_sections else 0.0
    is_scan_origin = (
        multi_column_count >= SCAN_MULTI_COLUMN_ABSOLUTE_MIN
        and ratio >= SCAN_MULTI_COLUMN_RATIO_MIN
    )
    return ScanOriginClassification(
        is_scan_origin=is_scan_origin,
        multi_column_section_count=multi_column_count,
        total_section_count=total_sections,
        multi_column_ratio=round(ratio, 4),
    )


def _read_document_xml(source_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(source_bytes)) as archive:
            return archive.read("word/document.xml").decode("utf-8", "ignore")
    except (KeyError, zipfile.BadZipFile):
        return ""


# --------------------------------------------------------------------------- #
# Per-table authored-signal override for the document-level scan-origin prior. #
# --------------------------------------------------------------------------- #

# Columns whose widths sit within this max/min ratio read as a deliberately laid
# out grid. OCR column-region "tables" carry wildly uneven widths (measured on
# the reference corpus RESISTANCE tables: ratios 2.2-2.5), so a tolerance well
# below that keeps scan tables classified as non-uniform.
_UNIFORM_GRID_MAX_RATIO = 1.5

# OOXML border edge w:val values that mean "no visible border".
_NO_BORDER_VALUES = {"nil", "none"}


def _element_local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def _first_child_by_local_name(element, local_name: str):
    if element is None:
        return None
    for child in element:
        if _element_local_name(child.tag) == local_name:
            return child
    return None


def _attribute_by_local_name(element, local_name: str) -> str | None:
    for key, value in element.attrib.items():
        if _element_local_name(key) == local_name:
            return value
    return None


def _table_has_real_borders(table_element) -> bool:
    table_properties = _first_child_by_local_name(table_element, "tblPr")
    borders = _first_child_by_local_name(table_properties, "tblBorders")
    if borders is None:
        return False
    for edge in borders:
        value = _attribute_by_local_name(edge, "val")
        if value is None:
            continue
        if value.strip().lower() not in _NO_BORDER_VALUES:
            return True
    return False


def _table_has_uniform_grid(table_element) -> bool:
    grid = _first_child_by_local_name(table_element, "tblGrid")
    if grid is None:
        return False
    widths: list[int] = []
    for child in grid:
        if _element_local_name(child.tag) != "gridCol":
            continue
        raw_width = _attribute_by_local_name(child, "w")
        if raw_width is None:
            return False
        try:
            width = int(raw_width)
        except (TypeError, ValueError):
            return False
        if width <= 0:
            return False
        widths.append(width)
    if len(widths) < 2:
        return False
    return (max(widths) / min(widths)) <= _UNIFORM_GRID_MAX_RATIO


def table_has_authored_signals(table_element) -> bool:
    """Return True when a ``w:tbl`` carries strong local authored-table signals.

    The scan-origin (OCR) classification is document-wide, but a genuine authored
    table can appear inside a document that trips the corpus thresholds — and a
    real authored multi-column document can trip them wholesale. Flattening such
    a table destroys real tabular data. This per-table override keeps a table
    when it looks authored: it has real table-level borders (a ``w:tblBorders``
    edge that is not ``nil``/``none``) or a uniform multi-column grid
    (``w:tblGrid`` columns of near-equal width). Borderless, irregular tables —
    the shape produced by OCR column-region detection — carry neither signal and
    are still flattened by the caller.
    """
    if table_element is None:
        return False
    return _table_has_real_borders(table_element) or _table_has_uniform_grid(table_element)
