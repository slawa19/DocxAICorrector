"""TOC-region detectors from ``validation/structural.py`` (spec 034, Step 3, Cluster D).

Pure leaf helpers over paragraph objects. Depend only on stdlib / typing -- never on the
``structural`` orchestration module -- so no import cycle is introduced; ``structural``
re-exports them so the qualified names keep resolving.

The structure-recognition TOC detectors that used to live here were removed by spec 066
(C-2): nothing produces their inputs any more, so the TOC/body-concat gate is the markdown
signal alone.
"""

from __future__ import annotations

from collections.abc import Sequence


def _count_effective_toc_regions_from_source(paragraphs: Sequence[object]) -> int:
    count = 0
    index = 0
    paragraph_units = list(paragraphs)
    while index < len(paragraph_units):
        structural_role = _normalized_structural_role(paragraph_units[index])
        if structural_role != "toc_header":
            index += 1
            continue
        look_ahead = index + 1
        while look_ahead < len(paragraph_units) and _normalized_structural_role(paragraph_units[look_ahead]) == "toc_entry":
            look_ahead += 1
        if look_ahead - index >= 3:
            count += 1
            index = look_ahead
            continue
        index += 1
    return count


def _normalized_structural_role(paragraph: object) -> str:
    return str(getattr(paragraph, "structural_role", "") or "").strip().lower()


def _derive_toc_body_concat_gate_fields(*, markdown_detected: bool) -> dict[str, object]:
    return {
        "toc_body_concat_detected": bool(markdown_detected),
        "toc_body_concat_markdown_detected": bool(markdown_detected),
    }
