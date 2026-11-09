"""The document quality-gate hygiene channel is emitted for EVERY operation.

Defect this pins (measured 2026-08-09 over the eight delivered spec-059 runs): the whole
hygiene channel of ``_build_translation_quality_report`` lived inside a
``processing_operation == "translate"`` block. Its COUNTERS were computed above the block
and serialized unconditionally, but ``gate_reasons`` and ``formatting_review_items`` were
born inside it — so an audiobook run showed the user an empty review panel
(``formatting_review_items`` 0/0/0/0) while the very same detectors in the very same
report counted 11/9/15/48 untranslated paragraphs, and the acceptance verdict rejected the
run. The panel said "clean" about a run that did not pass.

Two axes are pinned here, and they are NOT the same axis:

* language-INDEPENDENT hygiene (heading demotion, bullet-marker heading, TOC/body concat,
  false fragment, residual bullet glyph, list-fragment regression, unmapped source/target
  coverage, mapping text quality) — emitted for every operation;
* language-KEYED detectors (mixed_script, untranslated_structural, untranslated_body) —
  emitted only for ``core.models.LANGUAGE_CHANGING_OPERATIONS``.

Plus the safety boundary that must never be relaxed: the FATAL escalation
``untranslated_body_text_above_threshold`` stays reachable ONLY on ``translate``.
"""

import json

import pytest

from docxaicorrector.core.models import LANGUAGE_CHANGING_OPERATIONS
from docxaicorrector.pipeline import output_validation
from docxaicorrector.pipeline import quality_gate


class _Context:
    def __init__(self, operation: str, *, policy: str = "advisory") -> None:
        self.processing_operation = operation
        self.uploaded_filename = "book.docx"
        self.app_config = {"translation_output_quality_gate_policy": policy}


# A paragraph that stayed in the source language: no Cyrillic, >= 280 chars,
# >= 30 latin words, and not bibliography/URL dominant.
_ENGLISH_BODY = (
    "The company kept the same policy for another year and nobody in the office was willing "
    "to explain why the numbers had moved so far away from the plan that everyone had signed "
    "in the spring, so the meeting ended without a decision and the team went back to work on "
    "the parts of the product that were still moving forward without any argument at all."
)
# Same shape, long enough that a single paragraph clears the catastrophic threshold
# (>= 2000 chars) and, being nearly the whole document, also the 2% ratio.
_LONG_ENGLISH_BODY = " ".join([_ENGLISH_BODY] * 7)


def _entry(text: str, index: int, *, role: str = "body", heading_level: int | None = None):
    return output_validation.FinalAssemblyEntry(
        text=text,
        block_index=1,
        paragraph_id=f"p{index}",
        source_index=index,
        role=role,
        structural_role=role,
        heading_level=heading_level,
        from_registry=True,
    )


def _assembly(*texts_and_roles):
    entries = tuple(
        _entry(text, index, role=role, heading_level=2 if role == "heading" else None)
        for index, (text, role) in enumerate(texts_and_roles)
    )
    return output_validation.FinalMarkdownAssemblyResult(
        final_markdown="\n\n".join(entry.text for entry in entries),
        entries=entries,
        diagnostics=output_validation.FinalAssemblyDiagnostics(),
    )


def _hygiene_document():
    """A delivered document carrying language-INDEPENDENT hygiene defects only.

    ``## ●`` is a bullet-marker heading and ``• остаток`` a residual bullet glyph; both are
    pure formatting damage that says nothing about which language the text is in.
    """
    return _assembly(
        ("## ●", "heading"),
        ("• остаток списка после сборки", "body"),
        ("Обычный переведённый абзац без замечаний.", "body"),
    )


def _language_document(body_text: str = _ENGLISH_BODY):
    return _assembly(
        ("## The Lanternkeeper Guild", "heading"),
        (body_text, "body"),
    )


def _report(operation: str, assembly, *, policy: str = "advisory") -> dict:
    return quality_gate._build_translation_quality_report(
        context=_Context(operation, policy=policy),
        final_markdown=assembly.final_markdown,
        formatting_diagnostics_artifacts=[],
        assembly_result=assembly,
        runtime_display_markdown=assembly.final_markdown,
    )


_LANGUAGE_REASONS = {
    "mixed_script_terms_review_required",
    "mixed_script_terms_present",
    "untranslated_structural_text_review_required",
    "untranslated_body_text_review_required",
    "untranslated_body_text_above_threshold",
}


# --------------------------------------------------------------------------- #
# 1. The hygiene channel reaches the audiobook path at all.
# --------------------------------------------------------------------------- #


def test_audiobook_run_emits_hygiene_gate_reasons_and_review_items():
    report = _report("audiobook", _hygiene_document())

    assert report["gate_reasons"], "audiobook run reported no gate_reasons at all"
    assert report["formatting_review_items"], "audiobook run showed the user an empty review panel"
    assert "bullet_marker_headings_review_required" in report["gate_reasons"]
    assert "residual_bullet_glyphs_review_required" in report["gate_reasons"]
    # The counters were ALWAYS serialized; the defect was that nothing was emitted from them.
    assert report["bullet_heading_count"] == 1
    assert report["residual_bullet_glyph_count"] == 1
    # Reporting is not gating: the run is still delivered.
    assert report["quality_status"] == "warn"


def test_audiobook_hygiene_matches_translate_hygiene_reason_for_reason():
    """The hygiene half is language-independent, so both operations must say the same thing."""
    audiobook = _report("audiobook", _hygiene_document())
    translate = _report("translate", _hygiene_document())

    assert audiobook["gate_reasons"] == translate["gate_reasons"]
    assert json.dumps(audiobook["formatting_review_items"], sort_keys=True, ensure_ascii=False) == json.dumps(
        translate["formatting_review_items"], sort_keys=True, ensure_ascii=False
    )


def test_audiobook_run_emits_no_language_keyed_reasons_because_it_has_no_language_pair():
    # Spec 070 FR-001: ``audiobook`` left LANGUAGE_CHANGING_OPERATIONS -- its input is already in
    # its final language, so "still in the source language" is not a statement it may make.
    audiobook = _report("audiobook", _language_document())
    translate = _report("translate", _language_document())

    assert "audiobook" not in LANGUAGE_CHANGING_OPERATIONS
    assert not (set(audiobook["gate_reasons"]) & _LANGUAGE_REASONS)
    assert not any(item["reason"] in _LANGUAGE_REASONS for item in audiobook["formatting_review_items"])
    # Counter-proof: the same document on ``translate`` still emits them.
    assert "untranslated_body_text_review_required" in translate["gate_reasons"]
    # The measurement itself is operation-independent.
    assert audiobook["untranslated_body_text_count"] == translate["untranslated_body_text_count"] == 1


# --------------------------------------------------------------------------- #
# 2. Safety boundary: the FATAL escalation is reachable only on ``translate``.
#    A paid audiobook must never be destroyed by this detector.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("operation", ["audiobook", "edit"])
def test_untranslated_body_above_both_thresholds_never_fails_outside_translate(operation):
    assembly = _language_document(_LONG_ENGLISH_BODY)
    report = _report(operation, assembly)

    # Precondition: this input really does cross BOTH catastrophic thresholds, so the test
    # is proving the operation guard and not a too-small fixture.
    assert report["untranslated_body_text_chars"] >= quality_gate._UNTRANSLATED_BODY_FAIL_MIN_CHARS
    assert report["untranslated_body_text_ratio"] >= quality_gate._UNTRANSLATED_BODY_FAIL_RATIO

    assert "untranslated_body_text_above_threshold" not in report["gate_reasons"]
    assert report["quality_status"] != "fail"
    assert not (set(report["gate_reasons"]) & quality_gate._FATAL_DOCUMENT_GATE_REASONS)


def test_untranslated_body_above_both_thresholds_still_fails_on_translate():
    """Anti-vacuum counter-proof for the guard above: it withholds the escalation, it does
    not delete it. The identical document on ``translate`` still hard-fails."""
    report = _report("translate", _language_document(_LONG_ENGLISH_BODY))

    assert "untranslated_body_text_above_threshold" in report["gate_reasons"]
    assert report["quality_status"] == "fail"


def test_untranslated_body_outside_translate_is_still_counted_and_reported():
    """Anti-vacuum counter-proof #2: withholding the FATAL token must not withhold the
    MEASUREMENT. The audiobook run reports exactly the same characters as the translate
    run, at review severity, with the samples the reviewer needs."""
    assembly = _language_document(_LONG_ENGLISH_BODY)
    audiobook = _report("audiobook", assembly)
    translate = _report("translate", assembly)

    assert audiobook["untranslated_body_text_count"] == translate["untranslated_body_text_count"] == 1
    assert audiobook["untranslated_body_text_chars"] == translate["untranslated_body_text_chars"]
    assert audiobook["untranslated_body_text_samples"] == translate["untranslated_body_text_samples"]
    # Spec 070: the review item is a language statement, which audiobook no longer makes; the
    # translate run keeps its language-keyed reason (this document is above both thresholds, so it is the
    # hard-fail token, not the review one; counter-proof: the rule is gone for audiobook only).
    assert "untranslated_body_text_review_required" not in audiobook["gate_reasons"]
    assert "untranslated_body_text_above_threshold" in translate["gate_reasons"]


# --------------------------------------------------------------------------- #
# 3. ``edit`` gets the hygiene channel and no language-keyed reason.
# --------------------------------------------------------------------------- #


def test_edit_run_gets_hygiene_reasons():
    report = _report("edit", _hygiene_document())

    assert "edit" not in LANGUAGE_CHANGING_OPERATIONS
    assert "bullet_marker_headings_review_required" in report["gate_reasons"]
    assert "residual_bullet_glyphs_review_required" in report["gate_reasons"]
    assert report["formatting_review_items"]


def test_edit_run_gets_no_language_keyed_reasons():
    """``edit`` never changes the language, so "this is still in the source language" is not
    a statement it is entitled to make — even though the detectors still COUNT it."""
    report = _report("edit", _language_document())

    assert not (set(report["gate_reasons"]) & _LANGUAGE_REASONS)
    assert not [
        item for item in report["formatting_review_items"] if item["reason"] in _LANGUAGE_REASONS
    ]
    # Anti-vacuum: the measurement itself is untouched — the counters still describe reality,
    # the operation only decides whether a REASON is emitted from them.
    assert report["untranslated_body_text_count"] == 1
    assert report["untranslated_structural_text_count"] == 1


def test_edit_run_hygiene_is_identical_to_translate_hygiene():
    edit = _report("edit", _hygiene_document())
    translate = _report("translate", _hygiene_document())

    assert edit["gate_reasons"] == translate["gate_reasons"]
    assert edit["formatting_review_items"] == translate["formatting_review_items"]
