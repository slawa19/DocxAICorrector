"""Spec 070 T-H4: ``scripts/measure-narration-exclusion.py --per-paragraph`` lists the audiobook's
per-paragraph exclusions with their addresses and reasons, and makes no model call.

The document is invented; it carries the SHAPE of the real cases (prose, a heading, a run of
punctuation with no connected text).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from docx import Document

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "measure-narration-exclusion.py"

_PROSE_A = (
    "A harbour is not a place but an arrangement among its pilots to treat one stretch of water "
    "as a shelter from the storm, and that arrangement is what this chapter is about."
)
_PROSE_B = "The tide returned at dusk and the pilots, who had waited all afternoon, rowed out to meet the first ship."
_FRAGMENT = "* * * * *"


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_narration_exclusion_script", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fictional_docx(tmp_path: Path, paragraphs: list[str]) -> Path:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    path = tmp_path / "fictional.docx"
    document.save(str(path))
    return path


def test_per_paragraph_mode_names_the_excluded_paragraph_its_reason_and_its_address(tmp_path: Path) -> None:
    script = _load_script()
    source = _fictional_docx(tmp_path, [_PROSE_A, _FRAGMENT, _PROSE_B])

    result = script.measure_per_paragraph(source, chunk_size=3000)

    assert result["excluded_count"] == 1
    assert result["excluded_by_reason"] == {"fragment": 1}
    (entry,) = result["exclusions"]
    assert entry["reason"] == "fragment"
    assert entry["sample"] == _FRAGMENT
    assert entry["paragraph_id"]
    assert result["excluded_paragraph_ids_by_reason"] == {"fragment": [entry["paragraph_id"]]}
    # The denominator is the narrated paragraphs: the two prose paragraphs, not the fragment.
    assert result["expected_paragraph_count"] == 2
    assert entry["paragraph_id"] not in str(result["expected_paragraph_count"])


def test_a_document_of_prose_only_excludes_nothing(tmp_path: Path) -> None:
    """The counter-proof of the above: the reason comes from the paragraph, not from the mode."""
    script = _load_script()
    source = _fictional_docx(tmp_path, [_PROSE_A, _PROSE_B])

    result = script.measure_per_paragraph(source, chunk_size=3000)

    assert result["excluded_count"] == 0
    assert result["exclusions"] == []
    assert result["expected_paragraph_count"] == 2


def test_the_per_paragraph_mode_never_asks_for_a_model_client(tmp_path: Path) -> None:
    script = _load_script()
    # The module's offline contract: its client factory raises if preparation ever reaches for one.
    with pytest.raises(AssertionError, match="offline by contract"):
        script._no_llm_client()
    source = _fictional_docx(tmp_path, [_PROSE_A, _FRAGMENT])

    assert script.measure_per_paragraph(source, chunk_size=3000)["excluded_count"] == 1


def test_command_line_prints_one_address_line_per_exclusion(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script = _load_script()
    source = _fictional_docx(tmp_path, [_PROSE_A, _FRAGMENT, _PROSE_B])

    assert script.main([str(source), "--operation", "audiobook", "--per-paragraph"]) == 0

    out = capsys.readouterr().out
    assert "excluded=1" in out
    assert f"fragment\t{_FRAGMENT}" in out
