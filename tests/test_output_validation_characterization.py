"""Characterization safety net for ``pipeline/output_validation.py`` (spec 035, Step 0).

This module is core-dominated: a tightly-recursive final-markdown assembly engine
plus the ``collect_*`` / ``normalize_*`` families and two thin satellites
(paragraph-break detection, TOC-block validation). Spec 035 extracts ONLY the two
clean satellites and pins the interwoven core behind the goldens snapshotted here.
These goldens MUST stay byte-identical across every behaviour-preserving step of the
decomposition (satellite extraction and any follow-up).

Inputs are built fully offline with no fixtures: every function under test is a pure
CPU transform over in-memory strings / mappings / lightweight paragraph stubs.

To regenerate the goldens after an intentional, reviewed behaviour change, run::

    UPDATE_OUTPUT_VALIDATION_GOLDEN=1 <run this test>
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from types import SimpleNamespace

import docxaicorrector.pipeline.output_validation as ov

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "output_validation_characterization"
_UPDATE = os.environ.get("UPDATE_OUTPUT_VALIDATION_GOLDEN") == "1"


def _jsonable(obj: object) -> object:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {key: _jsonable(value) for key, value in dataclasses.asdict(obj).items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _jsonable(value) for key, value in obj.items()}
    return obj


def _canonical(obj: object) -> str:
    return json.dumps(_jsonable(obj), ensure_ascii=False, indent=2, sort_keys=True)


def _assert_golden(name: str, obj: object) -> None:
    path = _FIXTURE_DIR / f"{name}.json"
    serialized = _canonical(obj)
    if _UPDATE:
        _FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized + "\n", encoding="utf-8")
        return
    assert path.exists(), f"missing golden fixture: {path} (run UPDATE_OUTPUT_VALIDATION_GOLDEN=1)"
    expected = path.read_text(encoding="utf-8")
    assert serialized + "\n" == expected, f"golden diff for {name}"


def _para(
    paragraph_id: str,
    source_index: int,
    *,
    role: str = "body",
    structural_role: str = "body",
    heading_level=None,
    list_kind=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        paragraph_id=paragraph_id,
        source_index=source_index,
        role=role,
        structural_role=structural_role,
        heading_level=heading_level,
        list_kind=list_kind,
        boundary_source="raw",
        boundary_confidence="explicit",
    )


# ---------------------------------------------------------------------------
# assemble_final_markdown — full FinalMarkdownAssemblyResult over 4 triples
# ---------------------------------------------------------------------------

def test_assemble_final_markdown_golden() -> None:
    triples = {
        "partial_registry_uncovered": dict(
            processed_chunks=[
                "Первый абзац исходного блока.\n\nВторой абзац исходного блока.",
                "Passthrough блок без registry.\n\nСохранить как есть.",
            ],
            generated_paragraph_registry=[
                {"block_index": 1, "paragraph_id": "p1", "text": "Первый абзац исходного блока."},
                {"block_index": 1, "paragraph_id": "p2", "text": "Второй абзац исходного блока."},
            ],
            source_paragraphs=[_para("p1", 0), _para("p2", 1)],
        ),
        "inconsistent_registry_fallback": dict(
            processed_chunks=["Первый абзац.\n\nВторой абзац."],
            generated_paragraph_registry=[
                {"block_index": 1, "paragraph_id": "p1", "text": "Первый абзац."},
            ],
            source_paragraphs=[_para("p1", 0)],
        ),
        "toc_backed_heading_boundary": dict(
            processed_chunks=["## Введение\n\nОсновной текст раздела."],
            generated_paragraph_registry=[
                {"block_index": 1, "paragraph_id": "toc-heading", "text": "## Введение"},
                {"block_index": 1, "paragraph_id": "body-1", "text": "Основной текст раздела."},
            ],
            source_paragraphs=[
                _para("toc-heading", 0, role="heading", structural_role="heading", heading_level=2),
                _para("body-1", 1),
            ],
        ),
        "adjacent_body_fragment_merge": dict(
            processed_chunks=[
                "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить\n\nВеликую скорбь",
            ],
            generated_paragraph_registry=[
                {
                    "block_index": 1,
                    "paragraph_id": "body-left",
                    "text": "Для христиан жизненно важно помнить знамения, чтобы, если им будет даровано пережить",
                },
                {"block_index": 1, "paragraph_id": "body-right", "text": "Великую скорбь"},
            ],
            source_paragraphs=[_para("body-left", 0), _para("body-right", 1)],
        ),
    }
    result = {name: ov.assemble_final_markdown(**kwargs) for name, kwargs in triples.items()}
    _assert_golden("assemble_final_markdown", result)


# ---------------------------------------------------------------------------
# collect_* — all 9 sample collectors (one input each)
# ---------------------------------------------------------------------------

def test_collect_samples_golden() -> None:
    entries = (
        ov.FinalAssemblyEntry(text="### (Откровение 1:1)", block_index=1),
        ov.FinalAssemblyEntry(text="Основной текст раздела продолжается здесь.", block_index=1),
        ov.FinalAssemblyEntry(text="## (заметка в скобках)", block_index=2),
    )
    paragraph_break_registry = [
        {
            "source_index": 219,
            "origin_raw_indexes": [220],
            "text_preview": "this scenario has been repeated for every one of the large-scale banking crises and monetary",
            "role": "body",
            "structural_role": "toc_entry",
            "heading_level": None,
            "list_kind": None,
        },
        {
            "source_index": 219,
            "origin_raw_indexes": [220],
            "text_preview": "meltdowns of our times.",
            "role": "body",
            "structural_role": "toc_entry",
            "heading_level": None,
            "list_kind": None,
        },
    ]
    result = {
        "collect_bullet_heading_samples": ov.collect_bullet_heading_samples("## •\n\nОбычный текст."),
        "collect_page_placeholder_heading_concat_samples": ov.collect_page_placeholder_heading_concat_samples(
            "This page intentionally left blank Chapter 1"
        ),
        "collect_false_fragment_heading_samples_from_entries": ov.collect_false_fragment_heading_samples_from_entries(entries),
        "collect_false_fragment_heading_samples": ov.collect_false_fragment_heading_samples(
            "### (Откровение 1:1)\n\nОбычный текст раздела здесь идёт."
        ),
        "collect_residual_bullet_glyph_samples": ov.collect_residual_bullet_glyph_samples("Текст ● ещё текста здесь."),
        "collect_list_fragment_regression_samples": ov.collect_list_fragment_regression_samples(
            "Это связано с Седьмой\n- Судной печатью № 1"
        ),
        "collect_mixed_script_samples": ov.collect_mixed_script_samples("Это meханизм работает."),
        "collect_theology_style_issue_samples": ov.collect_theology_style_issue_samples("imago dei в исходном тексте."),
        "collect_paragraph_break_samples": ov.collect_paragraph_break_samples(paragraph_break_registry),
    }
    _assert_golden("collect_samples", result)


# ---------------------------------------------------------------------------
# normalize_* — all 7 normalizers (incl. the protected_heading_texts branch)
# ---------------------------------------------------------------------------

def test_normalize_golden() -> None:
    false_fragment_input = "Это предложение продолжается,\n\n## словом\n\nи далее по тексту."
    result = {
        "normalize_heading_match_text": ov.normalize_heading_match_text("## Пример: Heading!"),
        "normalize_page_placeholder_heading_concats_markdown": ov.normalize_page_placeholder_heading_concats_markdown(
            "This page intentionally left blank Chapter 1"
        ),
        "normalize_false_fragment_headings_markdown__unprotected": ov.normalize_false_fragment_headings_markdown(
            false_fragment_input
        ),
        "normalize_false_fragment_headings_markdown__protected": ov.normalize_false_fragment_headings_markdown(
            false_fragment_input, protected_heading_texts=["словом"]
        ),
        "normalize_inline_fragment_paragraphs_markdown": ov.normalize_inline_fragment_paragraphs_markdown(
            "Предложение не закончено,\n\nмаленький фрагмент"
        ),
        "normalize_residual_bullet_glyphs_markdown": ov.normalize_residual_bullet_glyphs_markdown(
            "Текст ● ещё\n● Пункт списка"
        ),
        "normalize_list_fragment_regressions_markdown": ov.normalize_list_fragment_regressions_markdown(
            "Введение: 1.\nПервая глава"
        ),
        "normalize_mixed_script_markdown": ov.normalize_mixed_script_markdown("Это meханизм работает."),
    }
    _assert_golden("normalize", result)


# ---------------------------------------------------------------------------
# validate_translated_toc_block — one case per TocValidationResult reason
# ---------------------------------------------------------------------------

def test_validate_translated_toc_block_golden() -> None:
    cases = {
        "same_language_valid": dict(
            source_text="Содержание",
            processed_chunk="Содержание",
            structural_roles=["toc_header"],
            source_language="ru",
            target_language="RU",
        ),
        "empty_toc_block": dict(
            source_text="",
            processed_chunk="Contents",
            structural_roles=None,
            source_language="ru",
            target_language="en",
        ),
        "toc_paragraph_count_drift": dict(
            source_text="Глава Один\n\nГлава Два",
            processed_chunk="Chapter One",
            structural_roles=["toc_entry", "toc_entry"],
            source_language="ru",
            target_language="en",
        ),
        "unchanged_toc_header": dict(
            source_text="Содержание",
            processed_chunk="Содержание",
            structural_roles=["toc_header"],
            source_language="ru",
            target_language="en",
        ),
        "too_many_unchanged_toc_entries": dict(
            source_text="Глава Один\n\nГлава Два\n\nГлава Три",
            processed_chunk="Глава Один\n\nГлава Два\n\nГлава Три",
            structural_roles=["toc_entry", "toc_entry", "toc_entry"],
            source_language="ru",
            target_language="en",
        ),
        "lost_toc_page_markers": dict(
            source_text="Глава Один...... 5\n\nГлава Два...... 12",
            processed_chunk="Chapter One\n\nChapter Two",
            structural_roles=["toc_entry", "toc_entry"],
            source_language="ru",
            target_language="en",
        ),
        "cross_language_valid": dict(
            source_text="Глава Один",
            processed_chunk="Chapter One",
            structural_roles=["toc_entry"],
            source_language="ru",
            target_language="en",
        ),
    }
    result = {name: ov.validate_translated_toc_block(**kwargs) for name, kwargs in cases.items()}
    _assert_golden("validate_translated_toc_block", result)


# ---------------------------------------------------------------------------
# classify_processed_block — one case per ProcessedBlockStatus
# ---------------------------------------------------------------------------

def test_classify_processed_block_golden() -> None:
    english_fallback = (
        "This entire paragraph remained in the original English language without any "
        "translation applied to it whatsoever across every single sentence here."
    )
    cases = {
        "empty": dict(target_text="нечто", processed_chunk="   "),
        "source_text_fallback": dict(target_text=english_fallback, processed_chunk=english_fallback),
        "bullet_heading_output": dict(target_text="нечто", processed_chunk="## •"),
        "heading_only_output": dict(
            target_text="Это тело абзаца, содержащее знаки препинания и несколько слов.",
            processed_chunk="# Заголовок",
        ),
        "toc_body_concat": dict(target_text="Contents", processed_chunk="Введение....5 Начало"),
        "english_residual_output": dict(target_text="нечто", processed_chunk="Русский текст chapter здесь."),
        "valid": dict(target_text="нечто", processed_chunk="Просто нормальный русский текст без проблем."),
    }
    result = {name: ov.classify_processed_block(**kwargs) for name, kwargs in cases.items()}
    _assert_golden("classify_processed_block", result)


# ---------------------------------------------------------------------------
# The 4 private-via-alias TOC names remain callable with current values.
# ---------------------------------------------------------------------------

def test_private_toc_aliases_callable() -> None:
    assert ov._is_page_reference_like("42") is True
    assert ov._is_page_reference_like("Глава") is False
    assert ov._has_page_reference_suffix("Глава Один...... 5") is True
    assert ov._has_page_reference_suffix("Глава Один") is False
    assert ov._is_substantive_toc_line("Глава Один") is True
    assert ov._is_substantive_toc_line("42") is False
    assert ov._is_allowlisted_unchanged_toc_line("42", "42") is True
    assert ov._is_allowlisted_unchanged_toc_line("Глава Один", "Глава Один") is False
