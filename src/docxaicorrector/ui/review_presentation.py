"""Presentation logic for the formatting-review block (Streamlit-free).

Turns the ``quality_warning`` DATA contract (produced by the pipeline gate) into
a small, testable :class:`ReviewPresentation` value object the result screen
renders. This module holds NO Streamlit import so it is unit-testable in
isolation; the actual widgets live in ``_ui.py``.

Severity keying and per-severity counting mirror the review-text writer
``runtime.artifacts._build_formatting_review_text`` exactly (``aggregate_count``
wins over ``count``), so the notice/counts shown on screen always agree with the
downloadable report.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from docxaicorrector.ui.i18n import t

ReviewLevel = Literal["defect", "fix", "review", "clean"]

# spec 059 FR-B3: the catalog key scheme for one acceptance check name. The names are a
# closed enumeration owned by ``validation/acceptance.py``; this module only turns a name
# into a phrase, so the UI never imports the verdict module and never recomputes a verdict
# (FR-B1). ``tests/test_ui_i18n.py`` enumerates the same names against both catalogs,
# because the regex guard over ``t("literal")`` cannot see a key built with an f-string.
ACCEPTANCE_CHECK_KEY_PREFIX: Final[str] = "result.acceptance_check."

# Max-severity precedence: defect > fix > review > clean.
_SEVERITY_MARKERS = {"fix", "review", "defect"}


@dataclass(frozen=True)
class ReviewPresentation:
    """Rendered facts for the result-screen review block."""

    level: ReviewLevel
    headline: str
    counts: dict[str, int]
    review_available: bool


def _string_sequence(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def build_notice_data_params(notice: Mapping[str, object]) -> dict[str, object]:
    """Turn the LIST data a pipeline notice carries into ``t()`` params.

    The pipeline sends structural identifiers (acceptance check names) and raw anchor texts;
    naming and punctuation are presentation, so they happen here rather than in the pipeline.
    Returns an empty mapping when the notice carries no such data, so every existing notice
    kind renders byte-identically (anti-regression #15).
    """
    params: dict[str, object] = {}
    failed_checks = _string_sequence(notice.get("failed_checks"))
    if failed_checks:
        params["checks"] = ", ".join(
            t(f"{ACCEPTANCE_CHECK_KEY_PREFIX}{name}") for name in failed_checks
        )
    anchors = _string_sequence(notice.get("anchors"))
    if anchors:
        params["anchors"] = "; ".join(f"«{anchor}»" for anchor in anchors)
    return params


def _item_severity(item: Mapping[str, object]) -> str:
    severity = str(item.get("severity") or "review")
    return severity if severity in _SEVERITY_MARKERS else "review"


def _item_count(item: Mapping[str, object]) -> int:
    # Mirror runtime.artifacts._review_item_count: aggregate_count wins over count.
    value = item.get("aggregate_count") if "aggregate_count" in item else item.get("count", 1)
    if not isinstance(value, (int, float, str)):
        return 1
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 1


def build_review_presentation(quality_warning: Mapping[str, object] | None) -> ReviewPresentation:
    """Summarize ``quality_warning`` into a level, headline, and per-severity counts.

    ``clean`` when there is no warning or no counted items. ``review_available``
    is True whenever a warning object is present (even an empty one), because a
    present warning is what makes the review report downloadable.
    """
    counts = {"defect": 0, "fix": 0, "review": 0}
    if quality_warning is not None:
        raw_items = quality_warning.get("formatting_review_items")
        if isinstance(raw_items, (list, tuple)):
            for item in raw_items:
                if isinstance(item, Mapping):
                    counts[_item_severity(item)] += _item_count(item)

    if counts["defect"] > 0:
        level: ReviewLevel = "defect"
    elif counts["fix"] > 0:
        level = "fix"
    elif counts["review"] > 0:
        level = "review"
    else:
        level = "clean"

    if level == "defect":
        headline = t("result.notice_defect", count=counts["defect"])
    elif level == "fix":
        headline = t("result.notice_fix", count=counts["fix"])
    elif level == "review":
        headline = t("result.notice_review", count=counts["review"])
    else:
        headline = t("result.notice_clean")

    return ReviewPresentation(
        level=level,
        headline=headline,
        counts=counts,
        review_available=quality_warning is not None,
    )
