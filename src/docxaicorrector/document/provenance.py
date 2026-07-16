"""Document-level scan-origin (OCR) provenance classification.

Scanned documents that were OCR'd into DOCX fragment the body into hundreds of
continuous sections — one per detected column region per page — so their
``word/document.xml`` carries a large number of multi-column section
definitions (``<w:cols w:num="N">`` with ``N >= 2``). Authored documents set a
column layout at most a handful of times. This is a purely STRUCTURAL
provenance signal: it inspects section geometry only, never the document text or
the filename, so it stays language- and title-agnostic (Constitution VII:
universal, no per-document literals).

The thresholds below are GENERAL heuristics with deliberately CONSERVATIVE
defaults — not values fitted to any one document. They encode two properties
that hold for OCR column-region fragmentation in general:

* an absolute floor on multi-column sections, set well above the small tail a
  normal authored document may legitimately carry (a magazine spread, a
  two-column reference page), so occasional authored multi-column layout never
  trips it; and
* a density ratio, so that a merely LONG authored document does not drift over
  the floor on section volume alone.

Anti-vacuum / generality note: both bars must be cleared, and the bias is
toward classifying a document as AUTHORED. A borderline document is left
authored (its tables preserved) rather than flattened, because destroying real
tabular data is the costly error. The defaults are overridable via ``app_config``
(see :func:`resolve_scan_origin_config`) so a deployment can tune them without
editing code; nothing here is calibrated to a specific corpus.

Residual-heuristic honesty: structural provenance detection inherently needs a
calibrated signal — there is no single threshold that is at once corpus-free
and perfectly separating. What this module guarantees is that the calibration
lives in NAMED, documented, config-overridable constants with conservative,
general defaults, rather than in per-document literals or text/filename
matching. A fully calibration-free provenance detector remains future work.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Mapping

# Count only <w:cols> that declare two or more columns. A bare <w:cols> (or
# num="1") is a single-column section and is not a scan signal.
_COLS_NUM_PATTERN = re.compile(r"<w:cols\b[^>]*\bw:num=\"(\d+)\"")
_SECTPR_PATTERN = re.compile(r"<w:sectPr\b")

# --------------------------------------------------------------------------- #
# General heuristic defaults (conservative, config-overridable — NOT per-book) #
# --------------------------------------------------------------------------- #

# Minimum count of multi-column sections before a document can read as OCR
# column-region fragmentation. Set well above the small multi-column tail that
# an authored document may legitimately carry.
DEFAULT_SCAN_MULTI_COLUMN_ABSOLUTE_MIN = 10
# Minimum share of sections that must be multi-column, so a merely long authored
# document does not clear the absolute floor on section volume alone.
DEFAULT_SCAN_MULTI_COLUMN_RATIO_MIN = 0.10
# Columns whose widths sit within this max/min ratio read as a deliberately laid
# out grid. OCR column-region "tables" carry wildly uneven widths, so a
# tolerance comfortably below typical OCR width spread keeps scan tables
# classified as non-uniform. General default, not fitted to any document.
DEFAULT_AUTHORED_UNIFORM_GRID_MAX_RATIO = 1.5

# app_config keys that override the defaults above (see resolve_scan_origin_config).
_MULTI_COLUMN_ABSOLUTE_MIN_KEY = "scan_origin_multi_column_absolute_min"
_MULTI_COLUMN_RATIO_MIN_KEY = "scan_origin_multi_column_ratio_min"
_UNIFORM_GRID_MAX_RATIO_KEY = "authored_table_uniform_grid_max_ratio"

# OOXML border edge w:val values that mean "no visible border".
_NO_BORDER_VALUES = {"nil", "none"}


@dataclass(frozen=True)
class ScanOriginConfig:
    """Tunable, config-overridable thresholds for scan-origin provenance.

    All fields default to the general, conservative module constants. They are
    heuristics, not per-corpus literals; a deployment may override them through
    ``app_config`` without changing the defaults or editing code.
    """

    multi_column_absolute_min: int = DEFAULT_SCAN_MULTI_COLUMN_ABSOLUTE_MIN
    multi_column_ratio_min: float = DEFAULT_SCAN_MULTI_COLUMN_RATIO_MIN
    authored_uniform_grid_max_ratio: float = DEFAULT_AUTHORED_UNIFORM_GRID_MAX_RATIO


DEFAULT_SCAN_ORIGIN_CONFIG = ScanOriginConfig()


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def resolve_scan_origin_config(app_config: Mapping[str, object] | None) -> ScanOriginConfig:
    """Build a :class:`ScanOriginConfig` from ``app_config`` overrides.

    Missing/invalid keys fall back to the general conservative defaults, so the
    numeric behaviour is unchanged unless a deployment deliberately tunes it.
    """
    if not app_config:
        return DEFAULT_SCAN_ORIGIN_CONFIG
    return ScanOriginConfig(
        multi_column_absolute_min=_coerce_int(
            app_config.get(_MULTI_COLUMN_ABSOLUTE_MIN_KEY, DEFAULT_SCAN_MULTI_COLUMN_ABSOLUTE_MIN),
            DEFAULT_SCAN_MULTI_COLUMN_ABSOLUTE_MIN,
        ),
        multi_column_ratio_min=_coerce_float(
            app_config.get(_MULTI_COLUMN_RATIO_MIN_KEY, DEFAULT_SCAN_MULTI_COLUMN_RATIO_MIN),
            DEFAULT_SCAN_MULTI_COLUMN_RATIO_MIN,
        ),
        authored_uniform_grid_max_ratio=_coerce_float(
            app_config.get(_UNIFORM_GRID_MAX_RATIO_KEY, DEFAULT_AUTHORED_UNIFORM_GRID_MAX_RATIO),
            DEFAULT_AUTHORED_UNIFORM_GRID_MAX_RATIO,
        ),
    )


@dataclass(frozen=True)
class ScanOriginClassification:
    is_scan_origin: bool
    multi_column_section_count: int
    total_section_count: int
    multi_column_ratio: float


def classify_document_scan_origin(
    source_bytes: bytes, *, config: ScanOriginConfig | None = None
) -> ScanOriginClassification:
    """Classify a DOCX archive as scan-origin (OCR) or authored from structure."""
    document_xml = _read_document_xml(source_bytes)
    return classify_scan_origin_from_document_xml(document_xml, config=config)


def classify_scan_origin_from_document_xml(
    document_xml: str, *, config: ScanOriginConfig | None = None
) -> ScanOriginClassification:
    config = config or DEFAULT_SCAN_ORIGIN_CONFIG
    multi_column_count = sum(1 for value in _COLS_NUM_PATTERN.findall(document_xml) if int(value) >= 2)
    total_sections = len(_SECTPR_PATTERN.findall(document_xml))
    ratio = multi_column_count / total_sections if total_sections else 0.0
    is_scan_origin = (
        multi_column_count >= config.multi_column_absolute_min
        and ratio >= config.multi_column_ratio_min
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


def _table_has_uniform_grid(table_element, *, max_ratio: float) -> bool:
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
    return (max(widths) / min(widths)) <= max_ratio


def table_has_authored_signals(
    table_element, *, uniform_grid_max_ratio: float = DEFAULT_AUTHORED_UNIFORM_GRID_MAX_RATIO
) -> bool:
    """Return True when a ``w:tbl`` carries strong local authored-table signals.

    The scan-origin (OCR) classification is document-wide, but a genuine authored
    table can appear inside a document that trips the general thresholds — and a
    real authored multi-column document can trip them wholesale. Flattening such
    a table destroys real tabular data. This per-table override keeps a table
    when it looks authored: it has real table-level borders (a ``w:tblBorders``
    edge that is not ``nil``/``none``) or a uniform multi-column grid
    (``w:tblGrid`` columns of near-equal width, within ``uniform_grid_max_ratio``).
    Borderless, irregular tables — the shape produced by OCR column-region
    detection — carry neither signal and are still flattened by the caller.

    ``uniform_grid_max_ratio`` is a general, config-overridable heuristic (see
    :class:`ScanOriginConfig`), not a value fitted to a specific document.
    """
    if table_element is None:
        return False
    return _table_has_real_borders(table_element) or _table_has_uniform_grid(
        table_element, max_ratio=uniform_grid_max_ratio
    )
