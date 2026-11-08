"""Spec 065 FR-010 / FR-004: the form-based glossary adherence measurer.

``scripts/measure-glossary-adherence.py`` replaces the 063/064 SC-006 proxy as the measurer of
"does the translation follow its own glossary where a reader looks". Every rule there is a rule of
FORM (Constitution VII): which paragraph is body prose, which entry is a name / multi-word /
capitalised term, how a rendering is found in Russian. These tests pin each rule on invented
terms, so no book's vocabulary is written into the repository.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "measure-glossary-adherence.py"


def _load():
    spec = importlib.util.spec_from_file_location("measure_glossary_adherence", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = _load()


def _pair(idx: int, source: str, target: str | None, **extra: Any) -> dict[str, Any]:
    return {
        "idx": idx,
        "paragraph_id": f"p{idx:04d}",
        "source_text": source,
        "target_text": target,
        "paragraph_status": "accepted",
        "region": "prose",
        "role": "body",
        "structural_role": "body",
        **extra,
    }


def _entry(source: str, target: str, **extra: Any):
    return m.Entry(source_term=source, target_term=target, **extra)


def _row(result: dict[str, Any], source: str) -> dict[str, Any]:
    return next(row for row in result["rows"] if row["source_term"] == source)


# --- scope -------------------------------------------------------------------------------------


def test_only_body_prose_the_model_rendered_is_read():
    term = [_entry("quillet bond", "киллетная облигация")]
    pairs = [
        _pair(1, "The quillet bond was issued.", "Киллетная облигация была выпущена."),
        _pair(2, "A quillet bond kept.", "A quillet bond kept.", paragraph_status="policy_kept_source"),
        _pair(3, "A quillet bond again.", "A quillet bond again.", controlled_fallback=True),
        _pair(4, "Quillet bond, note 4.", "Кильская расписка, примечание 4.", region="back_matter"),
        _pair(5, "The Quillet Bond", "Кильская расписка", role="heading", structural_role="heading"),
        _pair(6, "Quillet bond ... 12", "Кильская расписка ... 12", region="toc", structural_role="toc_entry"),
        _pair(7, "Image", None, missing=True),
    ]
    result = m.measure(pairs, term, min_occurrences=1)

    assert result["scope"] == {
        "measured": 1,
        "status:policy_kept_source": 1,
        "status:controlled_fallback": 1,
        "region:back_matter": 1,
        "role:heading": 1,
        "region:toc": 1,
        "no_target": 1,
    }
    row = _row(result, "quillet bond")
    assert (row["adherent"], row["occurrences"]) == (1, 1)


def test_headings_are_read_when_asked():
    term = [_entry("quillet bond", "киллетная облигация")]
    pairs = [_pair(5, "The Quillet Bond", "Кильская расписка", role="heading", structural_role="heading")]

    assert _row(m.measure(pairs, term, min_occurrences=1), "quillet bond")["occurrences"] == 0
    with_headings = m.measure(pairs, term, include_headings=True, min_occurrences=1)
    assert _row(with_headings, "quillet bond")["occurrences"] == 1


def test_an_occurrence_kept_in_latin_is_not_a_miss():
    """A cited title or a gloss keeps the source term; it is apparatus, not a rendering choice."""
    term = [_entry("quillet bond", "киллетная облигация")]
    pairs = [
        _pair(1, "See *The Quillet Bond Review*.", "См. *The Quillet Bond Review*."),
        _pair(2, "The quillet bond (see *Quillet Bond Review*).", "Киллетная облигация (см. *Quillet Bond Review*)."),
        _pair(3, "The quillet bond and the quillet bond.", "Кильская расписка и quillet bond."),
    ]
    row = _row(m.measure(pairs, term, min_occurrences=1), "quillet bond")

    assert row["kept_in_latin"] == [1]  # every occurrence kept verbatim
    assert row["groups"] == {"glossary": [2], "none": [3]}  # one of two kept: the other is still read


# --- entry selection by form -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "kind", "note", "form"),
    [
        ("Kelbrook", "name", "", "name"),
        ("quillet bond", "term", "", "multi_word"),
        ("post-varrow", "term", "", "hyphenated"),
        ("QVB", "term", "", "capitalised"),
        ("Brennic", "term", "", "capitalised"),
        ("brennic", "term", "смысл: только о займах", "noted"),
        ("brennic", "term", "", "single_lowercase"),
    ],
)
def test_entry_form_decides_the_headline(source, kind, note, form):
    assert m.entry_form(source, kind, note) == form
    assert m.headline_form(form) is (form != "single_lowercase")


def test_single_lowercase_words_and_cut_entries_stay_out_of_the_headline():
    entries = [
        _entry("quillet bond", "киллетная облигация"),
        _entry("brennic", "бренник"),
        _entry("varrow note", "варрова записка", rendered=False),
        _entry("Ostrel", "Острел", kind="name"),
    ]
    pairs = [
        _pair(1, "The quillet bond is brennic.", "Киллетная облигация — бренник."),
        _pair(2, "A quillet bond, a varrow note.", "Киллетная облигация и варровы записки."),
        _pair(3, "Brennic again, and the quillet bond.", "Снова бренник и киллетная облигация."),
        _pair(4, "No terms here but a brennic one.", "Здесь только бренник."),
        _pair(5, "Another varrow note.", "Ещё одна варрова записка."),
        _pair(6, "The last varrow note.", "Последняя расписка."),
    ]
    result = m.measure(pairs, entries)

    assert result["entries_by_bucket"] == {
        "headline": 1,
        "single_lowercase_word": 1,
        "not_in_prompt": 1,
        "no_measured_occurrence": 1,
    }
    assert result["headline"] == {"entries": 1, "occurrences": 3, "adherent": 3, "share": 1.0}
    assert result["single_lowercase_words"]["occurrences"] == 3
    assert result["not_in_prompt"] == {"entries": 1, "occurrences": 3, "adherent": 2, "share": 0.6667}


def test_a_rendering_equal_to_the_source_or_in_latin_is_not_measured():
    assert m.unmeasurable_reason("Ostrel", "Ostrel") == "rendering_equals_source"
    assert m.unmeasurable_reason("Ostrel Group", "Ostrel") == "latin_rendering"
    assert m.unmeasurable_reason("Ostrel", "Острел") is None


# --- source matching ---------------------------------------------------------------------------


def test_a_capitalised_abbreviation_is_matched_case_sensitively():
    """The 063 proxy counted the pronoun *us* as «US»: all 52 such misses of one book were that."""
    term = [_entry("QV", "КВ")]
    pairs = [
        _pair(1, "The QV economy grew.", "Экономика КВ росла."),
        _pair(2, "Let qv go home.", "Давайте пойдём домой."),
        _pair(3, "QV's debt.", "Долг КВ."),
    ]
    row = _row(m.measure(pairs, term, min_occurrences=1), "QV")

    assert (row["adherent"], row["occurrences"]) == (2, 2)


def test_a_rendering_of_short_words_is_matched_whole():
    """``КВ`` would open «квартира» as a prefix; a rendering of 1-2 letter words must equal a word."""
    term = [_entry("QV", "КВ")]
    pairs = [_pair(1, "The QV flat.", "Квартира в центре.")]
    row = _row(m.measure(pairs, term, min_occurrences=1), "QV")

    assert row["groups"] == {"none": [1]}


def test_lowercase_terms_match_any_case_plural_and_possessive_but_not_inside_a_hyphenated_compound():
    term = [_entry("quillet", "киллет")]
    pairs = [
        _pair(1, "Quillets were issued.", "Киллеты были выпущены."),
        _pair(2, "The quillet's value.", "Стоимость киллета."),
        _pair(3, "A quillet-based plan.", "План на основе расписок."),
    ]
    row = _row(m.measure(pairs, term, min_occurrences=1), "quillet")

    assert (row["adherent"], row["occurrences"]) == (2, 2)


def test_an_occurrence_inside_a_longer_rendered_entry_belongs_to_the_longer_entry():
    entries = [_entry("varrow flow", "варров поток"), _entry("varrow flow network", "сеть варровых потоков")]
    pairs = [
        _pair(1, "A varrow flow network.", "Сеть варровых потоков."),
        _pair(2, "A varrow flow.", "Варров поток."),
    ]
    result = m.measure(pairs, entries, min_occurrences=1)

    assert _row(result, "varrow flow")["groups"] == {"glossary": [2]}
    assert _row(result, "varrow flow network")["groups"] == {"glossary": [1]}


# --- target matching ---------------------------------------------------------------------------


def test_a_declined_rendering_counts_and_another_word_does_not():
    term = [_entry("quillet bond", "киллетная облигация")]
    pairs = [
        _pair(1, "Holders of quillet bonds waited.", "Держатели киллетных облигаций ждали."),
        _pair(2, "The quillet bond again.", "Снова кильская расписка."),
        _pair(3, "A *quillet bond*.", "*Киллетная* облигация."),
    ]
    row = _row(m.measure(pairs, term, min_occurrences=1), "quillet bond")

    assert row["groups"] == {"glossary": [1, 3], "none": [2]}
    assert row["reading_list"][0]["idx"] == 2


def test_the_parts_of_a_rendering_must_stand_together():
    """The 063 proxy accepted the two words anywhere in the paragraph; the window does not."""
    term = [_entry("rebound", "стойкость к ударам")]
    far = "Стойкость системы важна. Об этом писали многие авторы много лет подряд. Удары бывают разные."
    pairs = [
        _pair(1, "Its rebound matters.", "Её стойкость к ударам важна."),
        _pair(2, "Its rebound matters.", far),
    ]
    row = _row(m.measure(pairs, term, min_occurrences=1), "rebound")

    assert row["groups"] == {"glossary": [1], "partial: стойкость ударам": [2]}


def test_the_pass_line_needs_five_occurrences_and_a_ninety_percent_glossary_majority():
    term = [_entry("quillet bond", "киллетная облигация")]
    good = [_pair(i, "A quillet bond.", "Киллетная облигация.") for i in range(9)]
    bad = [_pair(9, "A quillet bond.", "Кильская расписка.")]
    row = _row(m.measure(good + bad, term), "quillet bond")
    assert (row["dominant"], row["dominant_share"], row["passes"]) == ("glossary", 0.9, True)

    worse = good[:4] + [_pair(9, "A quillet bond.", "Кильская расписка."), _pair(10, "A quillet bond.", "Кильская расписка.")]
    row = _row(m.measure(worse, term), "quillet bond")
    assert row["passes"] is False

    few = good[:4]
    assert _row(m.measure(few, term), "quillet bond")["passes"] is None


# --- FR-004 contrast pairs ---------------------------------------------------------------------


def test_contrast_pair_counts_distinct_partly_and_collapsed_paragraphs():
    entries = [_entry("durance", "стойкость"), _entry("rebound", "стойкость к ударам")]
    pairs = [
        _pair(1, "Durance needs rebound.", "Стойкости нужна стойкость к ударам."),
        _pair(2, "Rebound is the key to durance.", "Стойкость — ключ к стойкости."),
        _pair(3, "Rebound, rebound and durance.", "Стойкость к ударам, стойкость и снова стойкость."),
        _pair(4, "Only durance here.", "Только стойкость."),
    ]
    rows = m.measure(pairs, entries, min_occurrences=1)["contrast_pairs"]

    assert len(rows) == 1
    row = rows[0]
    assert row["together"] == 3
    assert (row["distinct"], row["collapsed"]) == (1, 1)
    assert row["idx"] == {"distinct": [1], "collapsed": [2], "partly": [3]}


def test_a_word_belongs_to_the_rendering_whose_stem_it_opens_longer():
    """«денежной» opens the stem of деньги too; it is the adjective's word, not a collapse."""
    entries = [_entry("Quill", "деньги"), _entry("quillary", "денежный")]
    pairs = [_pair(1, "Quill and the quillary order.", "Деньги и денежный порядок.")]
    row = m.measure(pairs, entries, min_occurrences=1)["contrast_pairs"][0]

    assert row["idx"] == {"distinct": [1]}


def test_compositions_and_renderings_without_a_common_stem_are_not_contrast_pairs():
    entries = [
        _entry("worth", "стоимость"),
        _entry("create worth", "создавать стоимость"),
        _entry("quillet", "киллет"),
    ]
    pairs = [_pair(1, "To create worth, add worth and a quillet.", "Создавать стоимость, добавлять стоимость и киллет.")]

    assert m.measure(pairs, entries, min_occurrences=1)["contrast_pairs"] == []


# --- inputs and coverage -----------------------------------------------------------------------


def _write(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
    return path


def test_region_comes_from_side_paragraphs_by_text_then_from_agreeing_neighbours(tmp_path):
    pairs = [
        {"idx": 0, "paragraph_id": "a", "source_text": "First body line.", "target_text": "x"},
        {"idx": 1, "paragraph_id": "b", "source_text": "A re-cut line.", "target_text": "x"},
        {"idx": 2, "paragraph_id": "c", "source_text": "Second *body* line.", "target_text": "x"},
        {"idx": 3, "paragraph_id": "d", "source_text": "1. Note one.", "target_text": "x"},
    ]
    side = [
        {"paragraph_id": "zz", "source_text": "First body line.", "region": "prose"},
        {"paragraph_id": "c", "source_text": "Second body line.", "region": "prose"},
        {"paragraph_id": "d", "source_text": "Something else entirely.", "region": "prose"},
        {"paragraph_id": "q", "source_text": "1. Note one.", "region": "back_matter"},
    ]
    loaded, filled = m.load_pairs(_write_jsonl(tmp_path / "pairs.jsonl", pairs), _write_jsonl(tmp_path / "side.jsonl", side))

    assert [pair.get("region") for pair in loaded] == ["prose", "prose", "prose", "back_matter"]
    assert filled == {"region_by_text": 2, "region_by_paragraph_id": 1, "region_by_neighbours": 1}


def test_report_fills_a_missing_status_from_the_final_registry(tmp_path):
    pairs = [{"idx": 0, "paragraph_id": "p1", "source_text": "s", "target_text": "s"}]
    report = {
        "runtime": {
            "state": {
                "final_generated_paragraph_registry": [
                    {"paragraph_id": "p0", "merged_paragraph_ids": ["p1"], "paragraph_status": "policy_kept_source"}
                ]
            }
        }
    }
    loaded, _ = m.load_pairs(_write_jsonl(tmp_path / "pairs.jsonl", pairs), None, _write(tmp_path / "report.json", report))

    assert m.scope_reason(loaded[0]) == "status:policy_kept_source"


def test_coverage_reads_the_section_from_rendered_terms_when_the_artifact_has_it(tmp_path):
    glossary = {
        "status": "built",
        "terms": [
            {"source_term": "quillet bond", "target_term": "киллетная облигация", "kind": "term"},
            {"source_term": "varrow note", "target_term": "варрова записка", "kind": "term"},
            {"source_term": "brennic", "target_term": "бренник", "kind": "term"},
        ],
        "candidates": [{"term": "varrow note", "required": True}, {"term": "brennic", "required": False}],
        "rendered_term_count": 2,
        "unrendered_terms": ["sound note"],
    }
    entries, info = m.load_entries(_write(tmp_path / "g.json", glossary))
    assert [entry.rendered for entry in entries] == [True, True, False]  # stored-order prefix

    glossary["rendered_terms"] = ["quillet bond", "brennic"]
    glossary["unrendered_required"] = ["varrow note"]
    entries, info = m.load_entries(_write(tmp_path / "g.json", glossary))
    assert [entry.rendered for entry in entries] == [True, False, True]
    result = m.measure([], entries)
    coverage = m.coverage(result["rows"], info)
    assert [row["source_term"] for row in coverage["required_cut"]] == ["varrow note"]
    assert coverage["required_absent_from_glossary"] == ["sound note"]
    assert coverage["unrendered_required_from_artifact"] == ["varrow note"]


def test_cli_writes_json_and_prints_the_headline(tmp_path, capsys):
    pairs = _write_jsonl(
        tmp_path / "pairs.jsonl",
        [
            _pair(1, "The quillet bond rose.", "Киллетная облигация выросла."),
            _pair(2, "Quillet bonds fell.", "Киллетные облигации упали."),
            _pair(3, "A quillet bond.", "Кильская расписка."),
        ],
    )
    glossary = _write(
        tmp_path / "g.json",
        {"terms": [{"source_term": "quillet bond", "target_term": "киллетная облигация", "kind": "term"}], "rendered_term_count": 1},
    )
    out = tmp_path / "out.json"

    assert m.main(["--pairs", str(pairs), "--glossary", str(glossary), "--json", str(out), "--show", "2"]) == 0
    printed = capsys.readouterr().out
    assert "HEADLINE 66.7% = 2/3 occurrences over 1 entries" in printed
    assert "3 [none] EN:" in printed
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["headline"]["occurrences"] == 3


def test_cli_reports_an_empty_glossary_instead_of_failing(tmp_path, capsys):
    pairs = _write_jsonl(tmp_path / "pairs.jsonl", [_pair(1, "x", "y")])
    glossary = _write(tmp_path / "g.json", {"status": "failed", "terms": []})

    assert m.main(["--pairs", str(pairs), "--glossary", str(glossary)]) == 0
    assert "glossary has no entries (status failed)" in capsys.readouterr().out


def test_the_script_stays_standard_library_only():
    """It is run with ``python3 -I`` on recorded runs; a repository import would break that."""
    text = SCRIPT.read_text(encoding="utf-8")

    assert "docxaicorrector" not in text.split('"""', 2)[2]
    assert "sys.path" not in text
