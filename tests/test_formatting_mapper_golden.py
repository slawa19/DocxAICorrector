"""Full-blob characterization gate for the formatting-transfer mapper (spec 029).

This test snapshots the ENTIRE output of ``_map_source_target_paragraphs`` — the
``mapping_pairs`` (serialized as ``[paragraph_id, target_index]``) PLUS the complete
``diagnostics`` dict — to canonical sorted JSON, and asserts byte-for-byte equality
against a committed golden fixture.

It is the correctness gate for the spec-029 performance refactor: every optimization
lever (E/A/B/C) MUST leave this blob byte-identical. Inputs are built fully offline
(no LLM/API): the four books under ``tests/sources/book`` are extracted, a realistic
identity target ``Document`` is synthesized (headings styled ``Heading N``, everything
else ``Normal``), deterministic target perturbations force residuals into the fuzzy
passes (9/10/11) and the global similarity pass (13), and a synthesized
``generated_paragraph_registry`` carries deliberate SPLIT / MERGED / RENAMED / rebuild-key
entries so the registry-driven passes are exercised too.

Determinism is guaranteed by index arithmetic only (no RNG / time). To regenerate the
fixtures after an intentional, reviewed behavior change, run::

    UPDATE_FORMATTING_MAPPER_GOLDEN=1 <run this test>
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import pytest
from docx import Document

from docxaicorrector.document._document import extract_document_content_from_docx
from docxaicorrector.generation.formatting_transfer import _map_source_target_paragraphs

# Cap paragraphs per book: the gate exercises every pass at this size (11 distinct
# strategies fire) while staying a few seconds per book. Full-book scaling is the
# job of the offline profiling harness, not this correctness gate.
_PARAGRAPH_CAP = 500

# Loads the real book fixtures under tests/sources/book/ (offline, no API) — an
# integration-grade characterization gate, not a fast unit test.
pytestmark = pytest.mark.integration_local

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BOOK_GLOB = str(_REPO_ROOT / "tests" / "sources" / "book" / "*.docx")
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "formatting_mapper_golden"


def _slug(path: str) -> str:
    stem = Path(path).stem
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def _build_case(source_paragraphs):
    """Deterministically synthesize (target Document, registry) from source paragraphs.

    All perturbation is pure index arithmetic so the blob is reproducible.
    """
    doc = Document()
    registry: list[dict[str, object]] = []
    n = len(source_paragraphs)
    for i, sp in enumerate(source_paragraphs):
        base = sp.text
        stripped = base.strip()
        words = stripped.split()

        # --- target text: mostly identity, ~14% small edit (high ratio -> fuzzy/13
        # accept), ~9% large edit (low ratio -> residual, exercises reject paths).
        ttext = base
        if stripped and i % 7 == 2 and len(words) >= 2:
            ttext = base + " " + words[-1]
        elif stripped and i % 11 == 0 and len(words) >= 4:
            ttext = " ".join(words[: max(1, len(words) // 2)])

        # Realistic styling so role resolution mirrors a real generated docx.
        if sp.role == "heading":
            level = min(max(sp.heading_level or 1, 1), 6)
            doc.add_paragraph(ttext, style=f"Heading {level}")
        else:
            doc.add_paragraph(ttext, style="Normal")

        # --- registry entry (the "generated" text the model produced).
        pid = sp.paragraph_id
        if not pid:
            continue
        if i % 23 == 5:
            # RENAMED: drop the registry entry so this source must be recovered by
            # the exact-text / global-similarity passes instead of a registry pass.
            continue
        entry: dict[str, object] = {"paragraph_id": pid, "text": base}
        if i % 17 == 0 and len(words) >= 3:
            # SPLIT: generated markdown split a heading off the front of the body.
            entry["text"] = "### " + " ".join(words[:2]) + "\n" + " ".join(words[2:])
        elif (
            i % 19 == 0
            and i + 1 < n
            and source_paragraphs[i + 1].paragraph_id
            and source_paragraphs[i + 1].text.strip()
        ):
            # MERGED: generated text folded the next source paragraph in.
            entry["text"] = base + "\n" + source_paragraphs[i + 1].text
            entry["merged_paragraph_ids"] = [source_paragraphs[i + 1].paragraph_id]
        if i % 31 == 3:
            # Rebuild-key hint (drives the paragraph_id_rebuild_key pass).
            entry["target_paragraph_indexes"] = [i]
        registry.append(entry)
    return doc, registry


def _serialize(mapping_pairs, diagnostics, target_paragraphs) -> str:
    index_by_target = {id(paragraph): index for index, paragraph in enumerate(target_paragraphs)}
    pairs = [
        [source_paragraph.paragraph_id, index_by_target[id(target_paragraph)]]
        for source_paragraph, target_paragraph in mapping_pairs
    ]
    blob = {"mapping_pairs": pairs, "diagnostics": diagnostics}
    return json.dumps(blob, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _compute_blob(book_path: str) -> str:
    with open(book_path, "rb") as handle:
        source_paragraphs, _ = extract_document_content_from_docx(handle)
    source_paragraphs = source_paragraphs[:_PARAGRAPH_CAP]
    document, registry = _build_case(source_paragraphs)
    target_paragraphs = document.paragraphs
    mapping_pairs, diagnostics = _map_source_target_paragraphs(
        source_paragraphs,
        target_paragraphs,
        generated_paragraph_registry=registry,
    )
    return _serialize(mapping_pairs, diagnostics, target_paragraphs)


_BOOKS = sorted(glob.glob(_BOOK_GLOB))


@pytest.mark.parametrize("book_path", _BOOKS, ids=[_slug(book) for book in _BOOKS])
def test_formatting_mapper_output_matches_golden(book_path: str) -> None:
    assert _BOOKS, f"no book fixtures found under {_BOOK_GLOB}"
    blob = _compute_blob(book_path)
    fixture_path = _FIXTURE_DIR / f"{_slug(book_path)}.json"

    if os.environ.get("UPDATE_FORMATTING_MAPPER_GOLDEN"):
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(blob, encoding="utf-8")
        pytest.skip(f"regenerated golden fixture: {fixture_path.name}")

    assert fixture_path.exists(), (
        f"missing golden fixture {fixture_path}; regenerate with "
        f"UPDATE_FORMATTING_MAPPER_GOLDEN=1"
    )
    expected = fixture_path.read_text(encoding="utf-8")
    assert blob == expected, (
        f"formatting mapper output diverged from golden for {Path(book_path).name}; "
        f"a spec-029 lever must be byte-identical"
    )
