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
import hashlib
import json
import os
import re
from pathlib import Path

import pytest
from docx import Document

from docxaicorrector.document.extraction import extract_document_content_from_docx
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


def _stable_perturb_key(source_paragraph) -> int:
    """Stable per-source-paragraph perturbation selector (F16).

    Derives the perturbation bucket from the paragraph's OWN identity — its
    ``paragraph_id`` (falling back to the source text) — instead of its positional
    ``enumerate`` index. This keeps the perturbation of a given source paragraph fixed when
    an UNRELATED paragraph is inserted/removed elsewhere (e.g. a recovered image paragraph,
    F11): only genuinely-adjacent effects (the MERGED next-paragraph fold) move, so the golden
    blesses the actual change instead of a reshuffled delta across every later paragraph.
    """
    identity = str(getattr(source_paragraph, "paragraph_id", "") or "") or str(getattr(source_paragraph, "text", "") or "")
    return int(hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8], 16)


def _build_case(source_paragraphs):
    """Deterministically synthesize (target Document, registry) from source paragraphs.

    Perturbation SELECTION is keyed on a stable per-paragraph identity hash (F16); only the
    positional operations that are genuinely about adjacency/ordering (the MERGED next-source
    fold, the target index a rebuild-key hint points at) still reference the index. The blob
    stays fully reproducible (hash of fixed identities, no RNG / time).
    """
    doc = Document()
    registry: list[dict[str, object]] = []
    n = len(source_paragraphs)
    for i, sp in enumerate(source_paragraphs):
        base = sp.text
        stripped = base.strip()
        words = stripped.split()
        key = _stable_perturb_key(sp)

        # --- target text: mostly identity, ~14% small edit (high ratio -> fuzzy/13
        # accept), ~9% large edit (low ratio -> residual, exercises reject paths).
        ttext = base
        if stripped and key % 7 == 2 and len(words) >= 2:
            ttext = base + " " + words[-1]
        elif stripped and key % 11 == 0 and len(words) >= 4:
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
        if key % 23 == 5:
            # RENAMED: drop the registry entry so this source must be recovered by
            # the exact-text / global-similarity passes instead of a registry pass.
            continue
        entry: dict[str, object] = {"paragraph_id": pid, "text": base}
        if key % 17 == 0 and len(words) >= 3:
            # SPLIT: generated markdown split a heading off the front of the body.
            entry["text"] = "### " + " ".join(words[:2]) + "\n" + " ".join(words[2:])
        elif (
            key % 19 == 0
            and i + 1 < n
            and source_paragraphs[i + 1].paragraph_id
            and source_paragraphs[i + 1].text.strip()
        ):
            # MERGED: generated text folded the next source paragraph in (genuinely
            # positional — the fold target is the immediate document neighbour).
            entry["text"] = base + "\n" + source_paragraphs[i + 1].text
            entry["merged_paragraph_ids"] = [source_paragraphs[i + 1].paragraph_id]
        if key % 31 == 3:
            # Rebuild-key hint (drives the paragraph_id_rebuild_key pass). The hint VALUE is
            # the paragraph's own target index (positional by definition).
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


class _FakeSourceParagraph:
    """Minimal source-paragraph stand-in exposing exactly the attributes _build_case reads."""

    def __init__(self, paragraph_id: str, text: str, role: str = "body", heading_level: int | None = None) -> None:
        self.paragraph_id = paragraph_id
        self.text = text
        self.role = role
        self.heading_level = heading_level


def test_perturbation_selection_is_stable_under_unrelated_insertion() -> None:
    """F16: a source paragraph's perturbation must depend only on its own identity, so
    inserting an unrelated paragraph elsewhere does not reshuffle it.

    Builds the same paragraphs twice — once plain, once with an unrelated paragraph inserted
    at the FRONT (shifting every positional index by one) — and asserts each shared paragraph
    lands the SAME target text. Under the old enumerate-index selection every paragraph after
    the insertion would flip perturbation; under identity-hash selection they are invariant.
    """
    shared = [
        _FakeSourceParagraph(f"p{index:03d}", f"Source paragraph number {index} with several words here.")
        for index in range(40)
    ]
    baseline_doc, _ = _build_case(list(shared))
    inserted = [_FakeSourceParagraph("x_inserted", "An unrelated recovered image paragraph."), *shared]
    inserted_doc, _ = _build_case(inserted)

    baseline_text_by_pid = {sp.paragraph_id: para.text for sp, para in zip(shared, baseline_doc.paragraphs)}
    # The inserted doc has one extra leading paragraph; the rest align to `shared` by offset 1.
    inserted_text_by_pid = {
        sp.paragraph_id: para.text for sp, para in zip(shared, inserted_doc.paragraphs[1:])
    }

    assert baseline_text_by_pid == inserted_text_by_pid
    # Guard against a degenerate all-identity map: the selection must actually perturb some
    # paragraphs, otherwise the invariance above would be vacuous.
    assert any(para.text != sp.text for sp, para in zip(shared, baseline_doc.paragraphs))

    # Stability is per-identity: the key is a pure function of paragraph_id only (text differs).
    assert _stable_perturb_key(shared[5]) == _stable_perturb_key(_FakeSourceParagraph("p005", "different text"))
