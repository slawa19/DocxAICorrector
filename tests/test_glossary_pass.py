"""Spec 063 P2 — the run glossary: record, render, extraction by form, the call's contract.

Every word in the synthetic documents below is invented ("Zorvane", "quillet bond") so that a
test can never pass because the product happens to know a real book's vocabulary — the product
code holds no term list (Constitution VII), and these tests would catch one that crept in only
if it matched a made-up word, which it cannot.
"""

from __future__ import annotations

import json
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, cast

import pytest

from docxaicorrector.document.segments import (
    GlossaryTerm,
    render_glossary_prompt_section,
)
from docxaicorrector.processing import preparation
from docxaicorrector.text import glossary_pass
from docxaicorrector.text.glossary_pass import (
    GlossaryCandidate,
    GlossaryResponseError,
    GlossarySourceUnit,
    build_glossary_request,
    describe_source_language,
    extract_glossary_candidates,
    missing_required_candidates,
    normalize_glossary_key,
    order_glossary_entries,
    parse_glossary_response,
    select_glossary_source_units,
)


# --- T001: the record and its render -----------------------------------------------------------


def test_glossary_term_new_fields_default_to_a_plain_term():
    term = GlossaryTerm(source_term="quillet bond", target_term="киллетная облигация")

    assert term.kind == "term"
    assert term.note == ""
    assert term.confidence == "medium"


def test_render_line_shapes_name_and_note_and_keeps_the_old_prefix():
    section = render_glossary_prompt_section(
        (
            GlossaryTerm(source_term="quillet bond", target_term="киллетная облигация"),
            GlossaryTerm(source_term="Zorvane", target_term="Зорвейн", kind="name"),
            GlossaryTerm(source_term="marrow", target_term="ядро", note="в значении  ядра системы"),
        ),
        header="H:",
        max_chars=100_000,
    )

    assert section.splitlines() == [
        "H:",
        "- quillet bond -> киллетная облигация",
        "- Zorvane -> Зорвейн (имя)",
        "- marrow -> ядро — в значении ядра системы",
    ]


def test_render_cuts_by_character_budget_and_says_so():
    terms = tuple(GlossaryTerm(source_term=f"term{index}", target_term=f"термин{index}") for index in range(50))
    full = render_glossary_prompt_section(terms, header="H:", max_chars=100_000)
    cut = render_glossary_prompt_section(terms, header="H:", max_chars=120)

    assert full.count("\n") == 50
    assert len(cut) <= 120
    assert cut.endswith("- ...")
    assert cut.splitlines()[1] == "- term0 -> термин0"


def test_render_with_zero_budget_or_no_usable_entries_is_empty():
    terms = (GlossaryTerm(source_term="term", target_term="термин"),)

    assert render_glossary_prompt_section(terms, header="H:", max_chars=0) == ""
    assert (
        render_glossary_prompt_section(
            (GlossaryTerm(source_term="term", target_term=""),), header="H:", max_chars=100_000
        )
        == ""
    )




# --- T004: extraction by form --------------------------------------------------------------------


def _units(paragraphs, *, heading_indexes=()):
    return tuple(
        GlossarySourceUnit(unit_id=f"p{index:04d}", text=text, is_heading=index in heading_indexes)
        for index, text in enumerate(paragraphs)
    )


_FILLER = (
    "The committee met again and the members talked about the weather and the harvest for a while.",
    "It was a long afternoon, and nobody wanted to leave before the rain stopped outside.",
    "This went on for some time, until the last of the visitors had gone home for the night.",
    "There were many questions, and most of them were answered by the people who knew the most.",
)


def _document():
    paragraphs = []
    # Chapter-like stretches: the invented vocabulary recurs across the whole document.
    for round_index in range(6):
        paragraphs.extend(_FILLER)
        paragraphs.append(
            f"In round {round_index} the town of Kelbrook asked Zorvane Pettish about the quillet bond again."
        )
        paragraphs.append(
            "Many people in Kelbrook still preferred the quillet bond to gold, said Zorvane Pettish."
        )
        paragraphs.append("The marrow ledger was opened, and the marrow ledger was closed once more.")
    paragraphs.insert(2, "From here to the last page we will refer to this kind of paper as *quillet bond*.")
    paragraphs.insert(3, "This practice is known as drevage, and drevage is older than any bank.")
    paragraphs.append("Later chapters return to drevage once more, briefly.")
    paragraphs.append("1 This note opens with a capital. 2 There is another note. 3 See the appendix.")
    paragraphs.append("1 This second list of notes repeats the pattern. 2 See also the index.")
    paragraphs.append("Visit www.example.org/Kxqvz for more, or bit.ly/Qzmwt today.")
    paragraphs.append("Visit www.example.org/Kxqvz again, or bit.ly/Qzmwt tomorrow.")
    return paragraphs


def _keys(candidates):
    return {candidate.source_term.lower(): candidate for candidate in candidates}


def test_extraction_finds_names_terms_definitions_and_collocations_by_form():
    candidates = extract_glossary_candidates(_units(_document()))
    keys = _keys(candidates)

    assert "zorvane pettish" in keys and keys["zorvane pettish"].family == "name"
    assert "kelbrook" in keys and keys["kelbrook"].family == "name"
    assert "quillet bond" in keys and keys["quillet bond"].family == "marked"
    assert "defined" in keys["quillet bond"].signals
    assert "drevage" in keys and "defined" in keys["drevage"].signals
    assert "marrow ledger" in keys and keys["marrow ledger"].family == "collocation"


def test_case_test_rejects_capitalised_words_that_open_numbered_notes():
    keys = _keys(extract_glossary_candidates(_units(_document())))

    for function_word in ("this", "there", "see", "the", "it", "in", "many"):
        assert function_word not in keys, function_word


def test_urls_never_become_candidates():
    keys = _keys(extract_glossary_candidates(_units(_document())))

    assert not any("kxqvz" in key or "qzmwt" in key for key in keys)


def test_a_single_occurrence_is_not_a_candidate():
    paragraphs = list(_FILLER) * 3 + ["Only once does Brannoch appear in this text."]
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "brannoch" not in keys


def test_acronym_survives_a_lowercase_homonym():
    paragraphs = []
    for _ in range(5):
        paragraphs.append("The members of GLIMS met, and GLIMS grew.")
        paragraphs.append("He glims at the sky and glims again, then glims once more.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "glims" in keys and keys["glims"].family == "name"


def test_unicode_letters_keep_a_name_whole():
    paragraphs = []
    for _ in range(4):
        paragraphs.append("Later, the chef Andrés Noubrec cooked for the guests.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "andrés noubrec" in keys
    assert not any(key.startswith("andr ") for key in keys)


def test_italic_at_first_use_counts_but_italic_for_stress_later_does_not():
    introduced = ["The *velloran* principle is introduced here.", *_FILLER, *_FILLER, *_FILLER, "The velloran principle returns."]
    stressed = [
        "The harbour was quiet and the harbour was cold.",
        "But the *harbour* was what mattered.",
        *_FILLER,
        *_FILLER,
        "The harbour stayed.",
    ]
    introduced_keys = _keys(extract_glossary_candidates(_units(introduced * 3)))
    stressed_keys = _keys(extract_glossary_candidates(_units(stressed * 3)))

    assert "velloran" in introduced_keys and "emphasis" in introduced_keys["velloran"].signals
    assert "harbour" not in stressed_keys or "emphasis" not in stressed_keys["harbour"].signals


def test_sentence_initial_run_is_taken_whole_only_when_its_first_word_is_a_name():
    paragraphs = []
    for _ in range(5):
        paragraphs.append("QOR Members Union opened a branch. The Tarrow Fund then closed one.")
        paragraphs.append("Everyone knew the QOR Members Union and the Tarrow Fund by now.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "qor members union" in keys
    assert "tarrow fund" in keys
    assert "the tarrow fund" not in keys


def test_headings_do_not_seed_the_name_family():
    paragraphs = ["Grand Title Words Here", *_FILLER, "Grand Title Words Here", *_FILLER]
    keys = _keys(extract_glossary_candidates(_units(paragraphs, heading_indexes={0, 5})))

    assert "grand title words here" not in keys


def test_family_head_collects_a_word_shared_by_several_multiword_candidates():
    paragraphs = []
    for _ in range(6):
        paragraphs.append("The worth creation and the worth extraction were measured.")
        paragraphs.append("Their worth creation exceeded worth extraction, and surplus worth grew.")
        paragraphs.append("Surplus worth and worth creation, again; surplus worth once more.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "worth creation" in keys and "worth extraction" in keys
    # Spec 065 FR-002: a head of collocations none of which the author marked is ONE lowercase
    # word on no form of its own -- not a candidate (the head with marked members: below).
    assert "worth" not in keys


def test_extraction_is_deterministic_and_respects_the_limit():
    units = _units(_document())
    first = extract_glossary_candidates(units)
    second = extract_glossary_candidates(units)

    assert first == second
    assert len(extract_glossary_candidates(units, limit=3)) <= 3
    assert extract_glossary_candidates(units, limit=0) == ()
    assert extract_glossary_candidates((), limit=10) == ()


def test_anti_vacuum_plain_prose_gives_no_function_words():
    keys = _keys(extract_glossary_candidates(_units(list(_FILLER) * 10)))

    assert not any(candidate.family in {"name", "marked"} for candidate in keys.values())


def test_a_defined_term_carries_the_context_where_the_author_introduced_it():
    paragraphs = [
        "People mentioned the varrow scrip in passing, and nobody paid attention.",
        *_FILLER,
        "From now on we will refer to this voucher as *varrow scrip*.",
        *_FILLER,
        "The varrow scrip spread across the valley.",
    ]
    candidate = _keys(extract_glossary_candidates(_units(paragraphs * 2)))["varrow scrip"]

    # The incidental first mention is not where the rendering is decided; the definition is.
    assert candidate.first_unit_id == "p0000"
    assert "refer to this voucher" in candidate.context


def test_candidate_payload_carries_count_and_one_context():
    candidate = _keys(extract_glossary_candidates(_units(_document())))["kelbrook"]
    payload = candidate.to_payload()

    assert payload["term"] == "Kelbrook"
    assert cast(int, payload["count"]) >= 6
    assert "Kelbrook" in str(payload["context"])
    assert len(str(payload["context"])) <= glossary_pass.GLOSSARY_CONTEXT_CHARS


def test_select_units_keeps_prose_and_front_matter_of_model_jobs_only():
    paragraphs = [
        SimpleNamespace(paragraph_id="p1", text="Title page text", role="body"),
        SimpleNamespace(paragraph_id="p2", text="Contents line", role="body"),
        SimpleNamespace(paragraph_id="p3", text="Body text", role="body"),
        SimpleNamespace(paragraph_id="p4", text="A heading", role="heading"),
        SimpleNamespace(paragraph_id="p5", text="Bibliography entry", role="body"),
        SimpleNamespace(paragraph_id="p6", text="[[DOCX_IMAGE_img_001]]", role="image"),
        SimpleNamespace(paragraph_id="p7", text="Passthrough text", role="body"),
    ]
    jobs = [
        {"job_kind": "llm", "paragraph_ids": ["p1", "p2"], "paragraph_regions": ["front_matter", "toc"]},
        {"job_kind": "llm", "paragraph_ids": ["p3", "p4", "p6"], "paragraph_regions": ["prose", "prose", "prose"]},
        {"job_kind": "llm", "paragraph_ids": ["p5"], "paragraph_regions": ["back_matter"]},
        {"job_kind": "passthrough", "paragraph_ids": ["p7"], "paragraph_regions": ["prose"]},
    ]
    units = select_glossary_source_units(jobs, paragraphs)

    assert [unit.unit_id for unit in units] == ["p1", "p3", "p4"]
    assert [unit.is_heading for unit in units] == [False, False, True]


def test_select_units_without_regions_treats_paragraphs_as_prose():
    paragraphs = [SimpleNamespace(paragraph_id="p1", text="Body", role="body")]
    units = select_glossary_source_units([{"job_kind": "llm", "paragraph_ids": ["p1"]}], paragraphs)

    assert [unit.unit_id for unit in units] == ["p1"]


def test_select_units_falls_back_to_job_text_without_source_paragraphs():
    units = select_glossary_source_units([{"job_kind": "llm", "target_text": "Block text"}], None)

    assert [unit.text for unit in units] == ["Block text"]


# --- T006: the call's contract -----------------------------------------------------------------


def _candidate(term, family="name"):
    return GlossaryCandidate(
        source_term=term,
        key=tuple(term.split()),
        family=family,
        signals=("capitalised",),
        occurrence_count=5,
        unit_count=4,
        spread=3,
        first_unit_id="p0001",
        context=f"... {term} ...",
        score=1.0,
    )


def test_request_carries_languages_limit_and_candidates():
    request = build_glossary_request(
        model="model-x",
        candidates=(_candidate("Zorvane Pettish"), _candidate("quillet bond", "marked")),
        source_language="en",
        target_language="ru",
        max_terms=12,
    )

    assert request["model"] == "model-x"
    assert request["temperature"] == 0.2
    request_input = cast(list[dict[str, Any]], request["input"])
    system_text = request_input[0]["content"][0]["text"]
    assert "from en into ru" in system_text
    assert "at most 12 besides the required ones" in system_text
    user_payload = json.loads(request_input[1]["content"][0]["text"])
    assert user_payload["max_terms"] == 12
    assert [item["term"] for item in user_payload["candidates"]] == ["Zorvane Pettish", "quillet bond"]
    assert user_payload["candidates"][0]["signals"] == ["capitalised"]
    assert user_payload["candidates"][0]["context"] == "... Zorvane Pettish ..."
    # Spec 066 T-1: the domain glossary is gone, and with it the request's "fixed_terms" slot.
    assert "fixed_terms" not in user_payload


def test_parse_accepts_only_candidates_and_counts_every_refusal():
    candidates = (_candidate("Zorvane Pettish"), _candidate("quillet bond", "marked"), _candidate("marrow"))
    raw = json.dumps(
        {
            "terms": [
                {"source_term": "quillet bonds", "target_term": "киллетная облигация", "kind": "term"},
                {"source_term": "Zorvane Pettish", "target_term": "Зорвейн Петтиш", "kind": "name"},
                {"source_term": "Invented Thing", "target_term": "выдумка", "kind": "term"},
                {"source_term": "marrow", "target_term": "  ", "kind": "term"},
                {"source_term": "marrow", "target_term": "ядро", "kind": "concept"},
                {"source_term": "marrow", "target_term": "мозг", "kind": "term", "note": "в анатомии"},
                {"source_term": "marrow", "target_term": "костный мозг", "kind": "term", "note": "третий"},
                {"source_term": "Zorvane Pettish", "target_term": "Зорване", "kind": "name"},
                "not an object",
            ]
        },
        ensure_ascii=False,
    )
    result = parse_glossary_response(raw, candidates=candidates, max_terms=10)

    assert [(term.source_term, term.target_term, term.kind, term.note) for term in result.terms] == [
        ("quillet bond", "киллетная облигация", "term", ""),
        ("Zorvane Pettish", "Зорвейн Петтиш", "name", ""),
        ("marrow", "ядро", "term", ""),
        ("marrow", "мозг", "term", "в анатомии"),
    ]
    assert result.rejected_counts == {
        "not_a_candidate": 2,
        "empty_target": 1,
        "duplicate_sense": 2,
        "over_limit": 0,
    }


def test_parse_cuts_at_max_terms_and_reads_fenced_json():
    names = ("Alpha", "Brava", "Corda", "Delta", "Echon")
    candidates = tuple(_candidate(name) for name in names)
    raw = "```json\n" + json.dumps(
        {"terms": [{"source_term": name, "target_term": name.upper()} for name in names]}
    ) + "\n```"
    result = parse_glossary_response(raw, candidates=candidates, max_terms=3)

    assert len(result.terms) == 3
    assert result.rejected_counts["over_limit"] == 2


@pytest.mark.parametrize(
    ("raw", "code"),
    [("", "empty_response"), ("no json here", "no_json"), ("{not json}", "invalid_json"), ('{"x": 1}', "invalid_shape")],
)
def test_parse_raises_a_coded_error_on_unusable_answers(raw, code):
    with pytest.raises(GlossaryResponseError) as raised:
        parse_glossary_response(raw, candidates=(_candidate("Zorvane"),), max_terms=5)

    assert raised.value.code == code


def test_normalized_key_folds_case_plural_and_possessive():
    assert normalize_glossary_key("Harbour Tokens") == normalize_glossary_key("harbour token")
    assert normalize_glossary_key("Zorvane’s") == normalize_glossary_key("zorvane")
    assert normalize_glossary_key("currencies") == ("currency",)
    assert normalize_glossary_key("GLIMS") == ("glims",)


# --- T008: the provider call is booked under its own stage ---------------------------------------


class _ResponsesClient:
    def __init__(self, text: str):
        self.calls: list[dict] = []
        self._text = text
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output_text=self._text,
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300, cost=0.0007),
        )


def test_request_text_completion_books_the_glossary_stage_and_not_the_api_path_counter():
    from docxaicorrector.core import model_accounting
    from docxaicorrector.generation._generation import request_text_completion

    client = _ResponsesClient('{"terms": []}')
    with model_accounting.run_model_accounting_scope(run_id="run-g", source_token="token-g"):
        text = request_text_completion(
            client,
            {"model": "m", "input": [], "temperature": 0.2, "max_output_tokens": 1024},
            usage_stage=model_accounting.STAGE_GLOSSARY_EXTRACTION,
        )
        snapshot = model_accounting.snapshot_run_model_accounting()

    assert text == '{"terms": []}'
    assert len(client.calls) == 1
    stages = cast(dict[str, dict[str, Any]], snapshot["stages"])
    assert set(stages) == {"glossary_extraction"}
    assert stages["glossary_extraction"]["prompt_tokens"] == 1200
    assert stages["glossary_extraction"]["completion_tokens"] == 300
    assert snapshot["api_path_counts"] == {}


def test_request_text_completion_honours_stop_before_paying():
    from docxaicorrector.core import model_accounting
    from docxaicorrector.generation._generation import request_text_completion
    from docxaicorrector.pipeline.contracts import LatePhaseStopped

    client = _ResponsesClient("{}")
    with pytest.raises(LatePhaseStopped):
        request_text_completion(
            client,
            {"model": "m", "input": []},
            usage_stage=model_accounting.STAGE_GLOSSARY_EXTRACTION,
            should_stop=lambda: True,
        )

    assert client.calls == []


# --- T015: the artifact family is bounded ---------------------------------------------------------


def test_run_glossary_artifacts_are_pruned_by_count(tmp_path, monkeypatch):
    from docxaicorrector.core import constants
    from docxaicorrector.pipeline import glossary_phase

    target = tmp_path / "run_glossaries"
    monkeypatch.setattr(constants, "RUN_GLOSSARIES_DIR", target)
    monkeypatch.setattr(glossary_phase, "RUN_GLOSSARIES_MAX_COUNT", 2)

    written = []
    for index in range(4):
        context = SimpleNamespace(run_id=f"run{index}", source_token="")
        written.append(glossary_phase._write_run_glossary_artifact({"index": index}, context=context))

    survivors = sorted(path.name for path in target.glob("*.json"))
    assert len(survivors) == 2
    assert all(name.startswith(("run2_", "run3_")) for name in survivors)
    assert not list(target.glob("*.tmp"))


def test_run_glossary_notice_only_when_there_is_something_to_say():
    from docxaicorrector.pipeline.glossary_phase import build_run_glossary_notice

    assert build_run_glossary_notice(status="built", term_count=5) == {
        "kind": "glossary",
        "level": "info",
        "message_key": "result.run_glossary_built",
        "params": {"count": 5},
    }
    failed_notice = build_run_glossary_notice(status="failed", term_count=0)
    assert failed_notice is not None and failed_notice["level"] == "warning"
    for status in ("not_applicable", "no_candidates", "empty", "stopped"):
        assert build_run_glossary_notice(status=status, term_count=0) is None
    assert build_run_glossary_notice(status="built", term_count=0) is None


def test_glossary_notice_keys_exist_in_both_locales():
    from pathlib import Path

    locales = Path(__file__).resolve().parents[1] / "src" / "docxaicorrector" / "ui" / "locales"
    for language in ("ru", "en"):
        catalog = json.loads((locales / f"{language}.json").read_text(encoding="utf-8"))
        assert "{count}" in catalog["result.run_glossary_built"]
        assert catalog["result.run_glossary_failed"]


# --- T017: the consistency instrument of SC-006 ---------------------------------------------------


def _load_consistency_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "measure-glossary-consistency.py"
    spec = importlib.util.spec_from_file_location("measure_glossary_consistency", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_consistency_script_counts_declined_renderings_and_rejects_other_words():
    script = _load_consistency_script()
    pairs = [
        {"idx": 1, "source_text": "The quillet bond was issued.", "target_text": "Киллетная облигация была выпущена."},
        {"idx": 2, "source_text": "Holders of quillet bonds waited.", "target_text": "Держатели киллетных облигаций ждали."},
        {"idx": 3, "source_text": "A *quillet bond* again.", "target_text": "Снова кильская расписка."},
        {"idx": 4, "source_text": "The quillet bond, once more.", "target_text": "The quillet bond, once more.", "controlled_fallback": True},
        {"idx": 5, "source_text": "Nothing here.", "target_text": "Ничего."},
        {"idx": 6, "source_text": "Image", "target_text": None, "missing": True},
    ]
    rows = script.measure(pairs, [{"source_term": "quillet bond", "target_term": "киллетная облигация", "kind": "term", "note": ""}])

    assert rows[0]["source_pairs"] == 3
    assert rows[0]["adherent_pairs"] == 2
    assert rows[0]["other_idx"] == [3]
    assert rows[0]["controlled_fallback_pairs"] == 1


def test_consistency_script_tells_two_transliterations_apart():
    script = _load_consistency_script()
    pairs = [
        {"idx": 1, "source_text": "In Kelbrook, Vermont.", "target_text": "В Келбруке, Вермонт."},
        {"idx": 2, "source_text": "Kelbrook's bank.", "target_text": "Банк Кельбрука."},
    ]
    rows = script.measure(pairs, [{"source_term": "Kelbrook", "target_term": "Келбрук", "kind": "name", "note": ""}])

    assert rows[0]["adherent_pairs"] == 1
    assert rows[0]["other_idx"] == [2]


# --- inclusion rule (orchestrator decision 2026-11-07): what the author marked is required ----


def test_required_flag_follows_the_authors_marking_not_the_family_score():
    paragraphs = [
        "From now on we will refer to this voucher as *varrow scrip*.",
        "The *brennic* principle is introduced here.",
        "Some people called it “real” money, and others said the “sound note” was better.",
        *_FILLER,
        "The varrow scrip, the brennic principle, the sound note and real money returned.",
        "Once more, Kelbrook and the sound note; the varrow scrip and the brennic principle too.",
        *(_FILLER * 4),
    ]
    keys = _keys(extract_glossary_candidates(_units(paragraphs * 2)))

    assert keys["varrow scrip"].required  # defined
    # Spec 064 FR-009: ONE lowercase word in italics, even at first use and recurring, is a
    # candidate the model may choose, not a term by rule (see the tests below).
    assert "brennic" in keys and not keys["brennic"].required
    assert keys["sound note"].required  # quotes around an expression
    assert "real" not in keys or not keys["real"].required  # quotes around one word: model's choice
    assert not keys["kelbrook"].required  # a name stays at the model's discretion


def test_a_family_of_unmarked_collocations_has_an_optional_head():
    """Anti-vacuum: a head stands only when the author marked its members (spec 065 FR-002)."""
    paragraphs = []
    for _ in range(6):
        paragraphs.append("The worth creation and the worth extraction were measured.")
        paragraphs.append("Their worth creation exceeded worth extraction, and surplus worth grew.")
        paragraphs.append("Surplus worth and worth creation, again; surplus worth once more.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "worth" not in keys
    assert keys["worth creation"].family == "collocation" and not keys["worth creation"].required


def test_a_family_with_an_author_marked_member_has_a_required_head():
    paragraphs = ["This we will call *worth creation* from here on.", "The *surplus worth* is introduced."]
    for _ in range(6):
        paragraphs.append("The worth creation and the worth extraction were measured.")
        paragraphs.append("Their worth creation exceeded worth extraction, and surplus worth grew.")
        paragraphs.append("Surplus worth and worth creation, again; surplus worth once more.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["worth creation"].required
    assert keys["worth"].family == "head" and keys["worth"].required


def test_a_defined_term_is_required_even_when_rare():
    paragraphs = ["We call this *the tallow gap* in our models.", *(_FILLER * 6), "The tallow gap closed."]
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["tallow gap"].occurrence_count == 2
    assert keys["tallow gap"].required


def test_a_term_defined_once_is_required_even_against_a_full_family_quota():
    # Codex acceptance finding 4: the defined term occurs in ONE unit, at the end of a book
    # whose author-marked family is far over its quota. The frequency cut (>= 2 units) and the
    # quota both used to drop it before the "a definition is always required" rule saw it.
    paragraphs: list[str] = []
    for index in range(30):
        paragraphs.append(f"The *brennic {chr(97 + index % 26)}{index} rule* is stressed here.")
        paragraphs.append(f"Again the brennic {chr(97 + index % 26)}{index} rule, and the brennic {chr(97 + index % 26)}{index} rule.")
        paragraphs.extend(_FILLER)
    paragraphs.append("At the very end we call this *the tallow gap* in our models.")
    candidates = extract_glossary_candidates(_units(paragraphs), limit=20)
    keys = _keys(candidates)

    marked = [candidate for candidate in candidates if candidate.family == "marked"]
    # Thirty marked terms compete for a marked quota of four at this limit; the defined one
    # rides over it.
    assert len(marked) == 5
    assert keys["tallow gap"].occurrence_count == 1
    assert keys["tallow gap"].required
    # Only the defined term rides over the limit; the optional candidates still fit it.
    assert sum(1 for candidate in candidates if not candidate.required) <= 20


def test_an_undefined_term_seen_in_one_unit_is_still_not_a_candidate():
    # Anti-vacuum for the bypass above: frequency still cuts what the author did not define.
    paragraphs = ["The *tallow gap* appears once, stressed.", *(_FILLER * 6)]
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "tallow gap" not in keys


def test_a_word_stressed_once_is_not_required():
    """Anti-vacuum: italics once, on a word the text uses anyway, is stress, not a term."""
    paragraphs = []
    for index in range(8):
        paragraphs.append("The harvest was late and the harvest was small, as harvests often are.")
        paragraphs.extend(_FILLER)
        if index == 4:
            paragraphs.append("But the *harvest* mattered more than anything.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "harvest" not in keys or not keys["harvest"].required


def test_an_italic_term_marked_twice_and_recurring_is_required():
    paragraphs = []
    for index in range(8):
        paragraphs.append("Later the brennic rule applied again, as the brennic rule does.")
        paragraphs.extend(_FILLER)
        if index in (2, 5):
            paragraphs.append("Here the *brennic rule* is set out.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["brennic rule"].required


# --- Spec 064 FR-009: what the rule "marked and recurring" requires besides the marking ---------


def _marked_word_document(word: str, *, capitalised: bool = False) -> list[str]:
    """``word`` set in italics where it first appears in two stretches, and used throughout.

    ``capitalised``: the body writes it with a capital in mid-sentence, as a name is written.
    """

    shown = word[:1].upper() + word[1:] if capitalised else word
    paragraphs = []
    for index in range(8):
        paragraphs.append(f"Later the town spoke of {shown} again, as people of {shown} do.")
        paragraphs.extend(_FILLER)
        if index in (2, 5):
            paragraphs.append(f"Here *{shown}* is set out once more.")
    paragraphs.insert(0, f"At first *{shown}* appears in this book.")
    return paragraphs


def test_fr009_one_lowercase_marked_word_is_an_optional_candidate():
    keys = _keys(extract_glossary_candidates(_units(_marked_word_document("brennic"))))

    assert "brennic" in keys
    assert keys["brennic"].family == "marked"
    assert not keys["brennic"].required


def test_fr009_one_capitalised_marked_word_stays_required():
    # ANTI-VACUUM for the test above: the same document, the word written as a name in
    # mid-sentence by the document itself -- the capital is the form that keeps it required.
    keys = _keys(extract_glossary_candidates(_units(_marked_word_document("brennic", capitalised=True))))

    assert keys["brennic"].required


def test_fr009_one_lowercase_defined_word_stays_required():
    paragraphs = _marked_word_document("brennic")
    paragraphs.insert(1, "This old practice is known as *brennic* in the valley.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["brennic"].required
    assert "defined" in keys["brennic"].signals


def test_fr009_two_adjacent_italic_runs_are_one_marked_expression():
    # The importer closes emphasis at a run boundary: "*growth* *hierarchy*" is one term.
    paragraphs = ["The order has been called a *quillet* *ladder* by its critics."]
    for _ in range(6):
        paragraphs.append("The quillet ladder returned, and the quillet ladder grew.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "quillet ladder" in keys and "defined" in keys["quillet ladder"].signals
    assert "quillet" not in keys or "defined" not in keys["quillet"].signals


def test_fr009_a_definition_names_the_marked_term_not_the_object_before_it():
    # "a movement that called itself 'Varrow Economics' (VE)": the verb's object is not the
    # term. The marked span must end the phrase -- "called it 'real' money" (the test above)
    # marks a word inside an expression and defines nothing.
    paragraphs = ["A movement that called itself ‘Varrow Economics’ (VE) was born in the valley."]
    for _ in range(6):
        paragraphs.append("Varrow Economics spread, and itself was a word nobody used as a term.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "varrow economics" in keys and "defined" in keys["varrow economics"].signals
    assert "itself" not in keys or "defined" not in keys["itself"].signals


def test_fr009_a_word_found_by_another_route_still_heads_a_family_with_a_required_member():
    # "worth" is an h2 heading word the body keeps using (heading family, optional) AND the
    # edge of three candidates one of which the author marked: it is required as their head.
    paragraphs: list[tuple[str, int | None]] = [("Book of Things", 1), ("On Worth", 2)]
    paragraphs.append(("This we will call *worth creation* from here on.", None))
    paragraphs.append(("The *surplus worth* is introduced.", None))
    for chapter in range(6):
        paragraphs.append((f"Part {chapter}", 1))
        paragraphs.append(("The worth creation and the worth extraction were measured.", None))
        paragraphs.append(("Their worth creation exceeded worth extraction, and surplus worth grew.", None))
        paragraphs.append(("Surplus worth and worth creation, again; surplus worth once more.", None))
        paragraphs.extend((text, None) for text in _FILLER)
    keys = _keys(extract_glossary_candidates(_heading_units(paragraphs)))

    assert keys["worth"].family == "heading"
    assert "family_head" in keys["worth"].signals
    assert keys["worth"].required


def _heading_units(paragraphs):
    units = []
    for index, (text, level) in enumerate(paragraphs):
        units.append(
            GlossarySourceUnit(unit_id=f"p{index:04d}", text=text, is_heading=level is not None, heading_level=level)
        )
    return tuple(units)


def test_a_heading_word_the_body_keeps_using_is_a_candidate_with_the_heading_as_context():
    paragraphs: list[tuple[str, int | None]] = [("Money and Durable Growth", 1)]
    for chapter in range(4):
        paragraphs.append((f"Chapter {chapter} Notes", 2))
        paragraphs.append(("The question of durable growth returns here, and durable growth matters.", None))
        paragraphs.extend((text, None) for text in _FILLER)
    keys = _keys(extract_glossary_candidates(_heading_units(paragraphs)))
    candidate = keys["durable growth"]

    assert candidate.family == "heading"
    assert candidate.context == "Money and Durable Growth"
    # Fourth pass: an h1 (title, chapter) phrase the body keeps using is required.
    assert candidate.required
    # Spec 065 FR-002: its single words are optional candidates at most -- never required.
    for word in ("durable", "growth"):
        assert word not in keys or not keys[word].required, word


def test_a_heading_phrase_the_body_never_repeats_is_not_a_candidate():
    """Anti-vacuum: a word only in a title is not a subject the book keeps using."""
    paragraphs: list[tuple[str, int | None]] = [("Tidewater Ledger Concerns", 1)]
    for _ in range(4):
        paragraphs.extend((text, None) for text in _FILLER)
    keys = _keys(extract_glossary_candidates(_heading_units(paragraphs)))

    assert "tidewater" not in keys and "ledger" not in keys and "tidewater ledger" not in keys


def test_level_three_headings_are_not_a_candidate_source():
    paragraphs: list[tuple[str, int | None]] = [("Durability Box", 3)]
    for _ in range(4):
        paragraphs.append(("The question of durability returns here, and durability matters.", None))
        paragraphs.extend((text, None) for text in _FILLER)
    keys = _keys(extract_glossary_candidates(_heading_units(paragraphs)))

    assert "durability" not in keys or keys["durability"].family != "heading"


def test_required_candidates_ignore_the_limit_on_the_models_own_choices():
    candidates = (
        replace(_candidate("quillet bond", "marked"), required=True),
        _candidate("Alpha"),
        _candidate("Brava"),
    )
    raw = json.dumps(
        {
            "terms": [
                {"source_term": "Alpha", "target_term": "Альфа"},
                {"source_term": "Brava", "target_term": "Брава"},
                {"source_term": "quillet bond", "target_term": "киллетная облигация"},
            ]
        },
        ensure_ascii=False,
    )
    result = parse_glossary_response(raw, candidates=candidates, max_terms=1)

    assert [term.source_term for term in result.terms] == ["Alpha", "quillet bond"]
    assert result.rejected_counts["over_limit"] == 1
    ordered = order_glossary_entries(candidates, result.terms)
    assert [term.source_term for term in ordered] == ["quillet bond", "Alpha"]
    assert missing_required_candidates(candidates, result.terms) == ()
    assert missing_required_candidates(candidates, result.terms[:1]) == (candidates[0],)


def test_request_marks_required_candidates_for_the_model():
    request = build_glossary_request(
        model="m",
        candidates=(replace(_candidate("quillet bond", "marked"), required=True), _candidate("Alpha")),
        source_language="en",
        target_language="ru",
        max_terms=5,
    )
    request_input = cast(list[dict[str, Any]], request["input"])
    payload = json.loads(request_input[1]["content"][0]["text"])

    assert [item["required"] for item in payload["candidates"]] == [True, False]
    assert "return a rendering for every one of them" in request_input[0]["content"][0]["text"]


def test_role_requests_and_collision_helpers():
    from docxaicorrector.text.glossary_pass import (
        build_distinction_request,
        find_rendering_collisions,
        normalize_rendering,
    )

    required_request = build_glossary_request(
        model="m",
        candidates=(replace(_candidate("quillet bond", "marked"), required=True),),
        source_language="en",
        target_language="ru",
        max_terms=0,
        role="required",
    )
    required_text = cast(list[dict[str, Any]], required_request["input"])[0]["content"][0]["text"]
    assert "Give EVERY candidate one rendering" in required_text
    assert "max_terms" not in json.loads(cast(list[dict[str, Any]], required_request["input"])[1]["content"][0]["text"])

    assert normalize_rendering("Устойчивость") == normalize_rendering("устойчивости")
    assert normalize_rendering("устойчивость") != normalize_rendering("жизнестойкость")
    terms = (
        GlossaryTerm(source_term="durability", target_term="устойчивость"),
        GlossaryTerm(source_term="steadiness", target_term="Устойчивости"),
        GlossaryTerm(source_term="Kelbrook", target_term="Келбрук", kind="name"),
        GlossaryTerm(source_term="durabilities", target_term="устойчивость"),
    )
    groups = find_rendering_collisions(terms)
    # "durabilities" folds to the same source key as "durability": a plural is not a collision.
    assert [[term.source_term for term in group] for group in groups] == [["durability", "steadiness"]]
    request = build_distinction_request(
        model="m",
        groups=groups,
        contexts={("durability",): "ctx one", ("steadiness",): "ctx two"},
        source_language="en",
        target_language="ru",
    )
    payload = json.loads(cast(list[dict[str, Any]], request["input"])[1]["content"][0]["text"])
    assert payload["groups"] == [
        {
            "current_rendering": "устойчивость",
            "terms": [
                {"term": "durability", "count": 0, "keep": True, "context": "ctx one"},
                {"term": "steadiness", "count": 0, "keep": False, "context": "ctx two"},
            ],
        }
    ]


@pytest.mark.parametrize(
    ("setting", "sample", "expected"),
    [
        ("en", "", "en"),
        ("auto", "Plain English prose of the book.", "the source language of the text"),
        ("auto", "", "the source language of the text"),
        ("auto", "Русский текст книги без латиницы.", "ru"),
        ("", "Plain text.", "the source language of the text"),
    ],
)
def test_auto_is_resolved_or_described_never_passed_through(setting, sample, expected):
    assert describe_source_language(setting, sample_text=sample) == expected
    request = build_glossary_request(
        model="m",
        candidates=(_candidate("Alpha"),),
        source_language=setting,
        target_language="ru",
        max_terms=5,
        sample_text=sample,
    )
    request_input = cast(list[dict[str, Any]], request["input"])
    assert f"from {expected} into ru" in request_input[0]["content"][0]["text"]
    assert json.loads(request_input[1]["content"][0]["text"])["source_language"] == expected


def test_parse_reads_the_required_and_other_lists_together():
    candidates = (replace(_candidate("quillet bond", "marked"), required=True), _candidate("Alpha"))
    raw = json.dumps(
        {
            "required_terms": [{"source_term": "quillet bond", "target_term": "Q"}],
            "other_terms": [{"source_term": "Alpha", "target_term": "A", "kind": "name"}],
        }
    )
    result = parse_glossary_response(raw, candidates=candidates, max_terms=5)

    assert [(term.source_term, term.kind) for term in result.terms] == [("quillet bond", "term"), ("Alpha", "name")]


def test_budget_drops_optional_entries_lowest_rank_first_and_never_a_required_one():
    from docxaicorrector.pipeline.glossary_phase import render_run_glossary_section

    required = tuple(replace(_candidate(f"Req{chr(97 + i)}", "marked"), required=True) for i in range(3))
    # Spec 067 FR-008: only single lowercase optional entries are the budget's to cut.
    optional = tuple(_candidate(f"opt{chr(97 + i)}", "marked") for i in range(3))
    terms = tuple(
        GlossaryTerm(source_term=candidate.source_term, target_term="перевод-" + candidate.source_term.lower())
        for candidate in (*required, *optional)
    )
    full = render_run_glossary_section(terms, (*required, *optional), max_chars=100_000)
    tight = render_run_glossary_section(terms, (*required, *optional), max_chars=len(full) - 10)
    tiny = render_run_glossary_section(terms, (*required, *optional), max_chars=10)

    assert "optc" in full and "optc" not in tight and "optb" in tight  # last-ranked optional goes first
    for name in ("Reqa", "Reqb", "Reqc"):
        assert name in tight and name in tiny  # required entries survive any budget
    assert "opta" not in tiny


def _h1_document(title, body_sentence, *, level=1, rounds=4):
    paragraphs: list[tuple[str, int | None]] = [(title, level)]
    for _ in range(rounds):
        paragraphs.append((body_sentence, None))
        paragraphs.extend((text, None) for text in _FILLER)
    return _heading_units(paragraphs)


def test_an_h2_phrase_the_body_keeps_using_stays_optional():
    keys = _keys(
        extract_glossary_candidates(
            _h1_document("Notes on Durable Growth", "The question of durable growth returns here, and durable growth matters.", level=2)
        )
    )

    assert keys["durable growth"].family == "heading"
    assert not keys["durable growth"].required


def test_an_h1_phrase_the_body_never_repeats_is_not_required():
    """Anti-vacuum: the title alone does not make a word a term of the book."""
    keys = _keys(extract_glossary_candidates(_h1_document("Durability Unbound", "Nothing about it here at all, truly.")))

    assert "durability" not in keys and "unbound" not in keys


def test_function_words_and_joiner_edges_of_an_h1_are_not_candidates():
    units = _h1_document(
        "MONEY AND DURABLE GROWTH FOR ALL",
        "Money and durable growth, money and durable growth for all of them, for all.",
    )
    keys = _keys(extract_glossary_candidates(units))

    for phrase in ("and", "for", "all", "money and", "and durable", "growth for", "for all"):
        assert phrase not in keys, phrase
    assert keys["durable growth"].required


def test_a_chapter_number_in_an_h1_is_not_a_candidate():
    units = _h1_document("Chapter VII Durable Growth", "Chapter seven speaks of durable growth, and durable growth again.")
    keys = _keys(extract_glossary_candidates(units))

    assert not any("vii" in key for key in keys)
    assert keys["durable growth"].required


def test_requests_ask_for_standard_transcription_and_the_full_name():
    for role in ("required", "optional"):
        request = build_glossary_request(
            model="m",
            candidates=(_candidate("Zorvane Pettish"),),
            source_language="en",
            target_language="ru",
            max_terms=5,
            role=role,
        )
        text = cast(list[dict[str, Any]], request["input"])[0]["content"][0]["text"]
        assert "standard practical transcription of ru" in text
        assert "first name together with the surname" in text


# --- Codex acceptance finding 5: the measurer's dump reproduces the production decision -----------


def _load_candidates_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "measure-glossary-candidates.py"
    spec = importlib.util.spec_from_file_location("measure_glossary_candidates", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_measurer_dump_round_trip_keeps_heading_levels_and_the_required_set(tmp_path):
    script = _load_candidates_script()
    paragraphs = [SimpleNamespace(paragraph_id="p0000", text="Money and Durable Growth", role="heading", heading_level=1)]
    for chapter in range(4):
        paragraphs.append(
            SimpleNamespace(paragraph_id=f"p1{chapter:03d}", text=f"Chapter {chapter} Notes", role="heading", heading_level=1)
        )
        for line, text in enumerate(
            ("The question of durable growth returns here, and durable growth matters.", *_FILLER)
        ):
            paragraphs.append(
                SimpleNamespace(paragraph_id=f"p2{chapter:02d}{line}", text=text, role="body", heading_level=None)
            )
    jobs = [
        {
            "job_kind": "llm",
            "paragraph_ids": [paragraph.paragraph_id for paragraph in paragraphs],
            "paragraph_regions": ["prose"] * len(paragraphs),
        }
    ]
    produced = extract_glossary_candidates(select_glossary_source_units(jobs, paragraphs))
    assert _keys(produced)["durable growth"].required  # an h1 phrase: the field decides it

    dump = tmp_path / "dump.json"
    script._dump(jobs, paragraphs, dump)
    replayed_jobs, replayed_paragraphs = script._load_dump(dump)
    replayed = extract_glossary_candidates(select_glossary_source_units(replayed_jobs, replayed_paragraphs))

    assert [(c.source_term, c.family, c.required) for c in replayed] == [
        (c.source_term, c.family, c.required) for c in produced
    ]
    assert script._assert_dump_parity(jobs, paragraphs, dump, limit=400) == sum(c.required for c in produced)


# --- Spec 064 FR-009: collisions keep the frequent term's rendering; names keep one form ---------


def _counted(term, count, family="name", required=False):
    return replace(_candidate(term, family), occurrence_count=count, required=required)


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        # Codex review 2026-11-07 (finding 6): two different abbreviations are not one
        # spelling by form -- "US"/"USA" goes to call C like "GDP"/"GDPR".
        ("US", "USA", False),
        ("GDP", "GDPR", False),
        ("U.S.", "US", True),  # periods
        ("TRC", "TRCs", True),  # a plural s
        ("Quillet", "quillets", True),
        ("UN", "UNESCO", False),  # more than one letter longer: another name
        ("BIS", "Bi", False),  # the capital S of an abbreviation is not a plural s
        ("WIR", "Wired", False),  # not two abbreviations
        ("durability", "steadiness", False),
    ],
)
def test_fr009_same_spelling_family_is_decided_by_form(first, second, same):
    assert glossary_pass.same_spelling_family(first, second) is same
    assert glossary_pass.same_spelling_family(second, first) is same


def test_fr009_spellings_of_one_name_sharing_a_rendering_are_not_a_collision():
    terms = (
        GlossaryTerm(source_term="US", target_term="США", kind="name"),
        GlossaryTerm(source_term="U.S.", target_term="США", kind="name"),
    )

    assert glossary_pass.find_rendering_collisions(terms) == []


def test_fr009_a_third_term_on_a_shared_rendering_is_still_a_collision():
    # ANTI-VACUUM: the spelling family is one member of the group, not a pass for the group.
    terms = (
        GlossaryTerm(source_term="US", target_term="США", kind="name"),
        GlossaryTerm(source_term="U.S.", target_term="США", kind="name"),
        GlossaryTerm(source_term="Zorvania", target_term="США", kind="name"),
    )

    groups = glossary_pass.find_rendering_collisions(terms)
    assert [[term.source_term for term in group] for group in groups] == [["US", "U.S.", "Zorvania"]]


def test_fr009_two_names_kept_as_written_do_not_collide_through_the_stem_rule():
    # The stem rule cuts "wired" to "wir"; two names left in their own script are compared whole.
    terms = (
        GlossaryTerm(source_term="QIR", target_term="QIR", kind="name"),
        GlossaryTerm(source_term="Qired", target_term="Qired", kind="name"),
    )

    assert glossary_pass.normalize_rendering("QIR") == glossary_pass.normalize_rendering("Qired")
    assert glossary_pass.find_rendering_collisions(terms) == []


def test_fr009_the_frequent_term_keeps_the_rendering_whatever_order_the_answer_takes():
    from docxaicorrector.pipeline.glossary_phase import _apply_distinction

    rare = GlossaryTerm(source_term="steadiness", target_term="устойчивость")
    frequent = GlossaryTerm(source_term="durability", target_term="устойчивость")
    terms = (rare, frequent)
    counts = {("steadiness",): 18, ("durability",): 144}
    groups = [
        glossary_pass.order_collision_group(group, counts)
        for group in glossary_pass.find_rendering_collisions(terms)
    ]
    assert [term.source_term for term in groups[0]] == ["durability", "steadiness"]

    request = glossary_pass.build_distinction_request(
        model="m", groups=groups, contexts={}, source_language="en", target_language="ru", counts=counts
    )
    payload = json.loads(cast(list[dict[str, Any]], request["input"])[1]["content"][0]["text"])
    assert [(item["term"], item["count"], item["keep"]) for item in payload["groups"][0]["terms"]] == [
        ("durability", 144, True),
        ("steadiness", 18, False),
    ]
    # The model renames the FREQUENT term (what call C did to Money's sustainability): the
    # code keeps the frequent term's rendering and takes only the rare term's new one.
    answer = (
        GlossaryTerm(source_term="steadiness", target_term="стойкость"),
        GlossaryTerm(source_term="durability", target_term="жизнеспособность"),
    )
    result = {term.source_term: term.target_term for term in _apply_distinction(terms, groups, answer)}
    assert result == {"durability": "устойчивость", "steadiness": "стойкость"}


def _name_document(full_names, short, *, ordinary_words=()):
    """A body that uses every full name, the short form alone, and ``ordinary_words`` in lowercase."""

    paragraphs = []
    for index in range(6):
        for full in full_names:
            paragraphs.append(f"In round {index} the council heard {full} speak about the harvest.")
        paragraphs.append(f"The elders said later that {short} was right, and {short} was heard by all.")
        for word in ordinary_words:
            paragraphs.append(f"The {word} road was long, and the {word} gate was shut.")
        paragraphs.extend(_FILLER)
    return paragraphs


def test_fr009_a_surname_belongs_to_the_full_name_by_form():
    keys = _keys(extract_glossary_candidates(_units(_name_document(["Zorvane Pettish"], "Pettish"))))

    assert keys["pettish"].name_head == "Zorvane Pettish"
    assert keys["zorvane pettish"].name_head == ""
    assert keys["pettish"].to_payload()["name_head"] == "Zorvane Pettish"


@pytest.mark.parametrize(
    "full_names",
    [
        ["Adar Quist", "Belo Quist"],  # two people with one surname
        ["Latin Zorvania", "Norrin Zorvania"],  # one word ending two different names
    ],
)
def test_fr009_a_short_form_that_ends_two_different_names_has_no_head(full_names):
    # ANTI-VACUUM: ambiguity is decided by form; the short form is asked for on its own.
    short = full_names[0].split()[-1]
    keys = _keys(extract_glossary_candidates(_units(_name_document(full_names, short))))

    assert keys[short.lower()].name_head == ""


def test_fr009_a_head_that_adds_an_ordinary_word_is_another_entity():
    # "Central Vermont" is not a fuller form of "Vermont": the body writes "central" in lowercase.
    paragraphs = _name_document(["Brisk Zorvania"], "Zorvania", ordinary_words=["brisk"])
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "brisk zorvania" in keys
    assert keys["zorvania"].name_head == ""


def test_fr009_a_surname_is_not_requested_and_inherits_the_full_name():
    candidates = (
        _counted("Zorvane Pettish", 18),
        replace(_counted("Pettish", 32), name_head="Zorvane Pettish"),
        _counted("Kelbrook", 7),
    )

    requested, members = glossary_pass.split_name_families(candidates)

    assert [candidate.source_term for candidate in requested] == ["Zorvane Pettish", "Kelbrook"]
    assert requested[0].occurrence_count == 32  # the head carries the family's standalone uses
    assert [(member.member.source_term, member.head.source_term) for member in members] == [
        ("Pettish", "Zorvane Pettish")
    ]
    terms = (
        GlossaryTerm(source_term="Zorvane Pettish", target_term="Зорвейн Петтиш", kind="name"),
        GlossaryTerm(source_term="Kelbrook", target_term="Келбрук", kind="name"),
    )
    inherited_terms, inherited = glossary_pass.inherit_name_renderings(terms, members)
    assert [(term.source_term, term.target_term) for term in inherited_terms] == [
        ("Zorvane Pettish", "Зорвейн Петтиш"),
        ("Pettish", "Петтиш"),
        ("Kelbrook", "Келбрук"),
    ]
    assert inherited == [{"source_term": "Pettish", "target_term": "Петтиш", "from": "Zorvane Pettish"}]


def test_fr009_a_short_form_never_used_alone_is_neither_sent_nor_inherited():
    # Every "Pettish" is inside "Zorvane Pettish": it is part of the full name, not an entry.
    candidates = (_counted("Zorvane Pettish", 6), replace(_counted("Pettish", 6), name_head="Zorvane Pettish"))

    requested, members = glossary_pass.split_name_families(candidates)

    assert [candidate.source_term for candidate in requested] == ["Zorvane Pettish"]
    assert requested[0].occurrence_count == 6
    assert members == ()


def test_fr009_a_middle_form_and_a_surname_both_inherit_from_the_longest_form():
    paragraphs = _name_document(["Arlo Maynard Quist", "Maynard Quist"], "Quist")
    candidates = extract_glossary_candidates(_units(paragraphs))
    keys = _keys(candidates)
    assert keys["quist"].name_head == "Arlo Maynard Quist"
    assert keys["maynard quist"].name_head == "Arlo Maynard Quist"

    requested, members = glossary_pass.split_name_families(candidates)
    terms, _ = glossary_pass.inherit_name_renderings(
        (GlossaryTerm(source_term="Arlo Maynard Quist", target_term="Арло Мейнард Квист", kind="name"),), members
    )

    assert "Quist" not in [candidate.source_term for candidate in requested]
    assert {term.source_term: term.target_term for term in terms} == {
        "Arlo Maynard Quist": "Арло Мейнард Квист",
        "Maynard Quist": "Мейнард Квист",
        "Quist": "Квист",
    }


@pytest.mark.parametrize("head", ["Bank of Zorvania", "US Zorvania", "Silicon Zorvania’s"])
def test_fr009_only_a_name_shaped_head_takes_a_family(head):
    # A joiner (an institution), an abbreviation, a possessive: not one name of a person or place.
    keys = _keys(extract_glossary_candidates(_units(_name_document([head], "Zorvania"))))

    assert keys["zorvania"].name_head == ""


@pytest.mark.parametrize(
    ("rendering", "expected"),
    [
        ("Сан-Квилло", []),  # another word count: no inherited entry
        ("San Quillo", []),  # kept as written: not a transliteration to share
    ],
)
def test_fr009_a_short_form_inherits_only_a_word_for_word_transliteration(rendering, expected):
    candidates = (_counted("San Quillo", 4), replace(_counted("Quillo", 9), name_head="San Quillo"))
    _, members = glossary_pass.split_name_families(candidates)

    terms, inherited = glossary_pass.inherit_name_renderings(
        (GlossaryTerm(source_term="San Quillo", target_term=rendering, kind="name"),), members
    )

    assert [term.source_term for term in terms] == ["San Quillo"]
    assert inherited == expected


def test_fr009_call_sequence_never_sends_a_surname_and_keeps_the_frequent_rendering():
    from docxaicorrector.pipeline import glossary_phase

    sent = (
        _counted("durability", 144, family="marked", required=True),
        _counted("steadiness", 18, family="marked", required=True),
        _counted("Zorvane Pettish", 18),
        replace(_counted("Pettish", 32), name_head="Zorvane Pettish"),
    )
    answers = [
        {
            "terms": [
                {"source_term": "durability", "target_term": "устойчивость"},
                {"source_term": "steadiness", "target_term": "устойчивость"},
            ]
        },
        {"terms": [{"source_term": "Zorvane Pettish", "target_term": "Зорвейн Петтиш", "kind": "name"}]},
        {
            "terms": [
                {"source_term": "durability", "target_term": "жизнеспособность"},
                {"source_term": "steadiness", "target_term": "стойкость"},
            ]
        },
    ]
    payloads: list[dict[str, Any]] = []

    def fake_request(_client, request, **_kwargs):
        payloads.append(json.loads(request["input"][1]["content"][0]["text"]))
        return json.dumps(answers[len(payloads) - 1], ensure_ascii=False)

    record: dict[str, object] = {}
    status, terms = glossary_phase._call_model(
        context=SimpleNamespace(source_language="en", target_language="ru", runtime=object()),
        dependencies=SimpleNamespace(should_stop_processing=lambda _runtime: False),
        emitters=SimpleNamespace(emit_status=lambda *_args, **_kwargs: None),
        initialization=SimpleNamespace(text_client=object(), job_count=0),
        model="m",
        sent_candidates=sent,
        max_terms=10,
        sample_text="",
        record=record,
        request_text_completion_fn=fake_request,
    )

    assert status == "built"
    sent_terms = [item["term"] for payload in payloads[:2] for item in payload["candidates"]]
    assert "Pettish" not in sent_terms and "Zorvane Pettish" in sent_terms
    rendered = {term.source_term: term.target_term for term in terms}
    assert rendered["durability"] == "устойчивость"
    assert rendered["steadiness"] == "стойкость"
    assert rendered["Pettish"] == "Петтиш"
    assert record["collisions"] == []
    assert record["inherited_name_entries"] == [
        {"source_term": "Pettish", "target_term": "Петтиш", "from": "Zorvane Pettish"}
    ]


def test_fr009_a_renamed_rare_term_changes_only_the_sense_that_collided():
    # Codex acceptance finding 3 under the direction rule: the RARE term is renamed, and of its
    # two senses only the one that shared the frequent term's rendering takes the new one.
    from docxaicorrector.pipeline.glossary_phase import _apply_distinction

    bond = GlossaryTerm(source_term="quillet bond", target_term="киллетная облигация", note="the bond")
    tool = GlossaryTerm(source_term="quillet bond", target_term="квиллет", note="the tool")
    frequent = GlossaryTerm(source_term="Kelbrook", target_term="Квиллет", kind="name")
    terms = (bond, tool, frequent)
    counts = {("quillet", "bond"): 5, ("kelbrook",): 50}
    groups = [
        glossary_pass.order_collision_group(group, counts)
        for group in glossary_pass.find_rendering_collisions(terms)
    ]
    assert [term.source_term for term in groups[0]] == ["Kelbrook", "quillet bond"]
    answer = (
        GlossaryTerm(source_term="Kelbrook", target_term="Келбрук", kind="name"),
        GlossaryTerm(source_term="quillet bond", target_term="квиллетный инструмент", note="the tool"),
    )

    result = [(term.source_term, term.target_term) for term in _apply_distinction(terms, groups, answer)]

    assert result == [
        ("quillet bond", "киллетная облигация"),
        ("quillet bond", "квиллетный инструмент"),
        ("Kelbrook", "Квиллет"),
    ]


# --- Codex acceptance review 2026-11-07: findings 4, 5, 6 --------------------------------------


def test_review6_two_different_abbreviations_on_one_rendering_stay_a_collision():
    terms = (
        GlossaryTerm(source_term="GDP", target_term="ВВП"),
        GlossaryTerm(source_term="GDPR", target_term="ВВП"),
    )

    groups = glossary_pass.find_rendering_collisions(terms)

    assert [[term.source_term for term in group] for group in groups] == [["GDP", "GDPR"]]


def _run_call_sequence(sent, answers):
    from docxaicorrector.pipeline import glossary_phase

    payloads: list[dict[str, Any]] = []

    def fake_request(_client, request, **_kwargs):
        payloads.append(json.loads(request["input"][1]["content"][0]["text"]))
        return json.dumps(answers[len(payloads) - 1], ensure_ascii=False)

    record: dict[str, object] = {}
    status, terms = glossary_phase._call_model(
        context=SimpleNamespace(source_language="en", target_language="ru", runtime=object()),
        dependencies=SimpleNamespace(should_stop_processing=lambda _runtime: False),
        emitters=SimpleNamespace(emit_status=lambda *_args, **_kwargs: None),
        initialization=SimpleNamespace(text_client=object(), job_count=0),
        model="m",
        sent_candidates=tuple(sent),
        max_terms=10,
        sample_text="",
        record=record,
        request_text_completion_fn=fake_request,
    )
    return status, terms, record, payloads


@pytest.mark.parametrize(
    ("note", "resolved"),
    [
        ("the same country written another way", True),
        ("", False),  # ANTI-VACUUM: the same rendering with no note says nothing; still a collision
    ],
)
def test_review6_us_usa_resolved_by_call_c_answering_the_same_with_a_note(note, resolved):
    sent = (_counted("US", 40), _counted("USA", 12))
    answers = [
        {
            "terms": [
                {"source_term": "US", "target_term": "США", "kind": "name"},
                {"source_term": "USA", "target_term": "США", "kind": "name"},
            ]
        },
        {
            "terms": [
                {"source_term": "US", "target_term": "США", "kind": "name"},
                {"source_term": "USA", "target_term": "США", "kind": "name", "note": note},
            ]
        },
    ]

    status, terms, record, payloads = _run_call_sequence(sent, answers)

    assert status == "built"
    assert len(payloads) == 2  # B (the optional names), then C for the collision
    assert [(item["term"], item["keep"]) for item in payloads[1]["groups"][0]["terms"]] == [
        ("US", True),
        ("USA", False),
    ]
    assert {term.source_term: term.target_term for term in terms} == {"US": "США", "USA": "США"}
    assert record["collisions_found"] == 1
    if resolved:
        assert record["collisions"] == []
        assert record["collisions_resolved"] == 1
        assert record["collisions_declared_same"] == [["us", "usa"]]
    else:
        assert record["collisions"] == [{"target_term": "США", "source_terms": ["US", "USA"]}]
        assert record["collisions_resolved"] == 0


def test_review4_lake_geneva_does_not_give_geneva_the_word_lake():
    candidates = (_counted("Lake Geneva", 4), replace(_counted("Geneva", 9), name_head="Lake Geneva"))
    _, members = glossary_pass.split_name_families(candidates)

    terms, inherited = glossary_pass.inherit_name_renderings(
        (GlossaryTerm(source_term="Lake Geneva", target_term="Женевское озеро", kind="name"),), members
    )

    assert inherited == []
    assert "Geneva" not in [term.source_term for term in terms]


def test_review4_a_swapped_name_order_gives_no_inheritance_where_the_script_shows_it():
    candidates = (_counted("Zorvane Pettish", 4), replace(_counted("Pettish", 9), name_head="Zorvane Pettish"))
    _, members = glossary_pass.split_name_families(candidates)

    swapped, swapped_inherited = glossary_pass.inherit_name_renderings(
        (GlossaryTerm(source_term="Zorvane Pettish", target_term="Pettish Zorvane", kind="name"),), members
    )
    in_order, in_order_inherited = glossary_pass.inherit_name_renderings(
        (GlossaryTerm(source_term="Zorvane Pettish", target_term="Zorváne Péttish", kind="name"),), members
    )

    assert swapped_inherited == []
    # ANTI-VACUUM: the same name in order (diacritics are the same letters) is inherited.
    assert in_order_inherited == [{"source_term": "Pettish", "target_term": "Péttish", "from": "Zorvane Pettish"}]


def test_review5_nested_name_forms_count_each_mention_once():
    candidates = (
        _counted("Arlo Maynard Quist", 6),
        replace(_counted("Maynard Quist", 12), name_head="Arlo Maynard Quist"),
        replace(_counted("Quist", 24), name_head="Arlo Maynard Quist"),
    )

    requested, members = glossary_pass.split_name_families(candidates)

    assert [(candidate.source_term, candidate.occurrence_count) for candidate in requested] == [
        ("Arlo Maynard Quist", 24)
    ]
    assert len(members) == 2


def test_review5_the_family_count_does_not_win_a_collision_it_should_lose():
    candidates = (
        _counted("Arlo Maynard Quist", 6),
        replace(_counted("Maynard Quist", 12), name_head="Arlo Maynard Quist"),
        replace(_counted("Quist", 24), name_head="Arlo Maynard Quist"),
        _counted("Quisting", 27),
    )
    requested, _ = glossary_pass.split_name_families(candidates)
    counts = {normalize_glossary_key(candidate.source_term): candidate.occurrence_count for candidate in requested}
    group = [
        GlossaryTerm(source_term="Arlo Maynard Quist", target_term="Квист", kind="name"),
        GlossaryTerm(source_term="Quisting", target_term="Квист"),
    ]

    ordered = glossary_pass.order_collision_group(group, counts)

    # 24 real mentions against 27: the other term keeps the rendering (the old sum, 30, won).
    assert [term.source_term for term in ordered] == ["Quisting", "Arlo Maynard Quist"]


# --- spec 064, 2026-11-08: the completion budget and the recovery of call A ------------------


def test_the_completion_budget_is_the_measured_entry_size_with_headroom():
    """The budget per entry is derived from measurement, not a flat guess of 60.

    Measured on the seven successful glossary stages of the 2026-11-07 runs (19 calls, 1 018
    answer entries; spec 064 Changelog, 2026-11-08): per answer entry p95 38.7 and max 47.3
    tokens, a per-call overhead of 212 tokens by least squares. The failed call (Creating
    Wealth, third run) spent 4 436 tokens on a 74-entry list against a cap of 4 440.
    """

    from docxaicorrector.generation import _generation

    measured_max_per_entry, measured_overhead = 47.3, 212
    assert glossary_pass.GLOSSARY_OUTPUT_TOKENS_PER_ENTRY >= 2 * measured_max_per_entry
    assert glossary_pass.GLOSSARY_OUTPUT_TOKENS_ENVELOPE >= measured_overhead
    # The failed list now has room for the answer it was cut off in, and more.
    assert glossary_pass.glossary_max_output_tokens(74) == 256 + 74 * 96 == 7360
    assert glossary_pass.glossary_max_output_tokens(74) > 4436
    # Every call A of the corpus fits under the budget at the measured max entry size.
    for required_count in (74, 80, 83, 87, 89, 93, 96, 110):
        needed = measured_overhead + measured_max_per_entry * required_count
        assert glossary_pass.glossary_max_output_tokens(required_count) >= 1.5 * needed
    # A floor for a short list and the ceiling every block call already sends this provider.
    assert glossary_pass.glossary_max_output_tokens(1) == 1024
    assert glossary_pass.glossary_max_output_tokens(10_000) == _generation._MODEL_OUTPUT_TOKEN_CEILING
    assert glossary_pass.GLOSSARY_OUTPUT_TOKENS_CEILING == _generation._MODEL_OUTPUT_TOKEN_CEILING


def test_call_a_is_split_in_two_halves_in_request_order():
    five = tuple(_candidate(f"Term{index}") for index in range(5))

    first, second = glossary_pass.split_candidates_in_halves(five)

    assert [candidate.source_term for candidate in first] == ["Term0", "Term1", "Term2"]
    assert [candidate.source_term for candidate in second] == ["Term3", "Term4"]
    assert glossary_pass.split_candidates_in_halves(five[:1]) == (five[:1], ())


def _recovery_sequence(sent, answers):
    """``_call_model`` with scripted answers; an ``Exception`` answer is raised by the provider."""

    from docxaicorrector.pipeline import glossary_phase

    requested: list[list[str]] = []
    events: list[tuple[int, str, dict[str, Any]]] = []

    def fake_request(_client, request, **_kwargs):
        payload = json.loads(request["input"][1]["content"][0]["text"])
        requested.append([item["term"] for item in payload["candidates"]])
        answer = answers[len(requested) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    record: dict[str, object] = {}
    status, terms = glossary_phase._call_model(
        context=SimpleNamespace(source_language="en", target_language="ru", runtime=object()),
        dependencies=SimpleNamespace(
            should_stop_processing=lambda _runtime: False,
            log_event=lambda level, event_id, _message, **context: events.append((level, event_id, context)),
        ),
        emitters=SimpleNamespace(emit_status=lambda *_args, **_kwargs: None),
        initialization=SimpleNamespace(text_client=object(), job_count=0),
        model="m",
        sent_candidates=tuple(sent),
        max_terms=10,
        sample_text="",
        record=record,
        request_text_completion_fn=fake_request,
    )
    return status, terms, record, requested, events


def _answer(*pairs):
    return json.dumps(
        {"terms": [{"source_term": source, "target_term": target} for source, target in pairs]}, ensure_ascii=False
    )


_FOUR_REQUIRED = tuple(
    _counted(term, 5, family="marked", required=True)
    for term in ("quillet bond", "harvest ledger", "council charter", "evening tithe")
)


def test_call_a_answered_with_json_cut_mid_entry_is_asked_again_in_halves():
    import logging

    cut = '{"terms": [{"source_term": "quillet bond", "target_term": "киллетная облига'
    status, terms, record, requested, events = _recovery_sequence(
        _FOUR_REQUIRED,
        [
            cut,
            _answer(("quillet bond", "киллетная облигация"), ("harvest ledger", "урожайная книга")),
            _answer(("council charter", "хартия совета"), ("evening tithe", "вечерняя десятина")),
        ],
    )

    assert status == "built"
    assert requested == [
        ["quillet bond", "harvest ledger", "council charter", "evening tithe"],
        ["quillet bond", "harvest ledger"],
        ["council charter", "evening tithe"],
    ]
    assert len(terms) == 4
    assert record["model_call_count"] == 3
    assert record["unrendered_terms"] == []
    failed_calls = cast(list[dict[str, Any]], record["failed_calls"])
    assert [(call["role"], call["error_code"]) for call in failed_calls] == [("required", "no_json")]
    assert failed_calls[0]["max_output_tokens"] == glossary_pass.glossary_max_output_tokens(4)
    assert [(level, event_id, context["next_step"]) for level, event_id, context in events] == [
        (logging.WARNING, "run_glossary_call_failed", "retry_in_halves")
    ]


def test_a_provider_error_on_call_a_is_not_split_and_call_b_takes_the_required_terms():
    # A transport failure is not a size problem: half the list would fail the same way.
    status, terms, record, requested, events = _recovery_sequence(
        _FOUR_REQUIRED,
        [
            RuntimeError("provider down"),
            _answer(
                ("quillet bond", "киллетная облигация"),
                ("harvest ledger", "урожайная книга"),
                ("council charter", "хартия совета"),
                ("evening tithe", "вечерняя десятина"),
            ),
        ],
    )

    assert status == "built"
    assert len(requested) == 2 and len(requested[1]) == 4
    assert len(terms) == 4
    assert record["reasked_required_count"] == 4
    assert [context["next_step"] for _level, _event_id, context in events] == ["continue_to_call_b"]
    assert cast(list[dict[str, Any]], record["failed_calls"])[0]["error_code"] == "RuntimeError"


def test_anti_vacuum_a_good_call_a_makes_no_extra_call_and_no_warning():
    status, terms, record, requested, events = _recovery_sequence(
        _FOUR_REQUIRED,
        [
            _answer(
                ("quillet bond", "киллетная облигация"),
                ("harvest ledger", "урожайная книга"),
                ("council charter", "хартия совета"),
                ("evening tithe", "вечерняя десятина"),
            ),
        ],
    )

    assert status == "built"
    assert len(requested) == 1 and len(terms) == 4
    assert record["failed_calls"] == []
    assert events == []


# --- Spec 065: the glossary reaches the reader (FR-001 order and budget, FR-002 single words,
# FR-003 phrases above the word). Synthetic text only; no phrase of a corpus book. -------------


def _worth_document(*, public_rounds: int = 4, hyphenated: bool = True) -> list[str]:
    """A head word ("worth") with TWO author-marked members, a "public worth" expression whose
    other word heads a defined term ("public tallow"), and a hyphenated compound."""

    paragraphs = [
        "This we will call *worth creation* from here on.",
        "The *surplus worth* is introduced.",
        "What the town shared we call *public tallow* in this book.",
    ]
    for index in range(6):
        paragraphs.append("The worth creation and the worth extraction were measured.")
        paragraphs.append("Their worth creation exceeded worth extraction, and surplus worth grew.")
        paragraphs.append("Surplus worth and worth creation, again; the public tallow once more.")
        if index < public_rounds:
            paragraphs.append("The public worth of the commons was larger than anyone said.")
        if hyphenated and index < 3:
            paragraphs.append("A worth-based reckoning followed the harvest.")
        paragraphs.extend(_FILLER)
    return paragraphs


def test_fr002_a_neologism_defined_with_quotes_and_recurring_stays_a_required_candidate():
    # Anti-regression 2 of spec 065: a demurrage-like coined word, introduced in quotes by a
    # definition and used again, is the author's term.
    paragraphs = ["A charge on idle notes is technically called a ‘drevage’ fee in the valley."]
    for _ in range(4):
        paragraphs.append("The drevage made people spend, and drevage kept the notes moving.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "drevage" in keys
    assert keys["drevage"].required
    assert "defined" in keys["drevage"].signals


def test_fr002_an_ordinary_word_in_italics_is_never_a_required_entry_and_ranks_last():
    # Anti-regression 2 of spec 065: the ordinary word "harvest", used throughout and set in
    # italics, is not an entry by rule: at most an optional candidate the model may choose,
    # placed after every phrase and name, where the budget cuts first (FR-001).
    paragraphs = []
    for index in range(8):
        paragraphs.append("The harvest was late and the harvest was small, as harvests often are.")
        paragraphs.extend(_FILLER)
        if index in (2, 4):
            paragraphs.append("But the *harvest* mattered more than anything.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "harvest" not in keys or not keys["harvest"].required
    ordered = order_glossary_entries(
        tuple(keys.values()),
        (_entry("harvest", "урожай"), _entry("marrow ledger", "мозговая книга"), _entry("Kelbrook", "Келбрук", kind="name")),
    )
    assert ordered[-1].source_term == "harvest"


def test_fr002_a_word_defined_in_passing_once_is_not_a_candidate_but_three_uses_are():
    once = ["Back then the sailors had called him a quibbler, like most of his crew.", *(_FILLER * 6)]
    recurring = [*once, "The quibbler came back.", "Another quibbler spoke.", *_FILLER]

    assert "quibbler" not in _keys(extract_glossary_candidates(_units(once)))
    # Anti-vacuum: the same definition with the word used three times is a candidate.
    assert "quibbler" in _keys(extract_glossary_candidates(_units(recurring)))


def test_fr002_a_heading_word_alone_is_an_optional_candidate_a_head_of_two_required_members_is_required():
    title_only: list[tuple[str, int | None]] = [("Making Worth", 1)]
    for chapter in range(4):
        title_only.append((f"Part {chapter}", 1))
        title_only.append(("Making things was hard, and making worth was harder still.", None))
        title_only.extend((text, None) for text in _FILLER)
    keys = _keys(extract_glossary_candidates(_heading_units(title_only)))

    # An h1 word the body keeps using: the model may choose it, the rule never forces it.
    assert keys["making"].family == "heading" and not keys["making"].required
    assert keys["worth"].family == "heading" and not keys["worth"].required
    ordered = order_glossary_entries(
        tuple(keys.values()), (_entry("making", "созидание"), _entry("Kelbrook", "Келбрук", kind="name"))
    )
    assert ordered[-1].source_term == "making"  # last: the budget cuts it first

    # Anti-vacuum: "worth" heads two author-marked members here -- it stays, and is required.
    keys = _keys(extract_glossary_candidates(_units(_worth_document())))
    assert keys["worth"].required
    assert "family_head" in keys["worth"].signals


def test_fr002_a_head_with_one_required_member_is_not_a_candidate():
    paragraphs = ["This we will call *worth creation* from here on."]
    for _ in range(6):
        paragraphs.append("The worth creation and the worth extraction were measured.")
        paragraphs.append("Their worth creation exceeded worth extraction, and surplus worth grew.")
        paragraphs.append("Surplus worth and worth creation, again; surplus worth once more.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["worth creation"].required
    assert "worth" not in keys


def test_fr002_an_article_between_the_object_and_the_marked_name_is_not_part_of_the_term():
    paragraphs = ["The old masters called them the ‘tallow class’. Others did not."]
    for _ in range(6):
        paragraphs.append("The tallow class worked, and the tallow class paid them the rent.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "tallow class" in keys and "defined" in keys["tallow class"].signals
    assert "them the" not in keys


def test_fr002_a_quoted_name_inside_a_longer_expression_defines_nothing_before_it():
    # "called it 'real' money": the object before the quotes is not a defined term either.
    paragraphs = ["Some called it ‘quillet’ money, and others did not."]
    for _ in range(6):
        paragraphs.append("It was quillet money, and it was spent; it went around again.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "it" not in keys


def test_fr002_the_tail_of_a_split_word_is_found_by_form():
    plains: list[str] = list(_FILLER * 25)
    for _ in range(4):
        plains.append("Praise for effi ciency and for suffi ciency came from the miller.")
        plains.append("An effi cient mill is a suffi cient mill, said the miller.")
        plains.append("Coal and fossil fuels burned while fossil fuels lasted.")
        plains.append("The town grew and the town paid.")
    tails = glossary_pass._split_word_tails(plains)

    assert "ciency" in tails
    # Anti-vacuum: the second word of a fixed pair follows one word only; whole words are not tails.
    assert "fuels" not in tails
    assert "town" not in tails and "mill" not in tails


def test_fr003_a_phrase_on_a_required_word_is_its_own_required_candidate_before_the_word():
    candidates = extract_glossary_candidates(_units(_worth_document()))
    keys = _keys(candidates)
    order = [candidate.source_term.lower() for candidate in candidates]

    assert keys["public worth"].required and "phrase" in keys["public worth"].signals
    assert keys["worth-based"].required and "phrase" in keys["worth-based"].signals
    assert order.index("public worth") < order.index("worth")
    assert order.index("worth-based") < order.index("worth")


def test_fr003_a_phrase_needs_three_uses_and_a_partner_of_the_books_terms():
    keys = _keys(extract_glossary_candidates(_units(_worth_document(public_rounds=2, hyphenated=False))))

    assert "public worth" not in keys  # twice is not recurring
    assert "worth-based" not in keys
    keys = _keys(extract_glossary_candidates(_units(_worth_document())))
    # "worth extraction": its other word heads no required candidate -- the phrase rule adds
    # nothing; the expression stays whatever the collocation family made of it.
    assert "phrase" not in keys["worth extraction"].signals


def _entry(source, target, *, kind="term", note=""):
    return GlossaryTerm(source_term=source, target_term=target, kind=kind, note=note)


def _counted_candidate(term, count, *, required=False, family="marked"):
    return replace(_candidate(term, family), key=tuple(term.lower().split()), occurrence_count=count, required=required)


def test_fr001_entries_are_ordered_by_tier_then_form_then_use_and_the_budget_cuts_the_tail():
    from docxaicorrector.pipeline.glossary_phase import plan_run_glossary_section

    candidates = (
        _counted_candidate("quillet", 50, required=True),
        _counted_candidate("quillet bond", 10, required=True),
        _counted_candidate("harbour", 90),
        _counted_candidate("Zorvane Pettish", 5, family="name"),
        _counted_candidate("marrow ledger", 40, family="collocation"),
        _counted_candidate("tallow", 3),
    )
    # The model's answer order: single words first, as in the third run.
    terms = (
        _entry("harbour", "гавань"),
        _entry("tallow", "сало"),
        _entry("quillet", "киллет"),
        _entry("Zorvane Pettish", "Зорвейн Петтиш", kind="name"),
        _entry("quillet bond", "киллетная облигация"),
        _entry("marrow ledger", "мозговая книга"),
    )
    ordered = order_glossary_entries(candidates, terms)

    assert [term.source_term for term in ordered] == [
        "quillet bond",  # required, a phrase containing "quillet": moved before it
        "quillet",
        "marrow ledger",  # optional phrases and names by use
        "Zorvane Pettish",
        "harbour",  # optional single words last, by use
        "tallow",
    ]
    full = plan_run_glossary_section(ordered, candidates, max_chars=100_000)
    tight = plan_run_glossary_section(ordered, candidates, max_chars=len(full.text) - 5)
    tiny = plan_run_glossary_section(ordered, candidates, max_chars=10)

    assert full.cut == () and full.unrendered_required == ()
    assert [term.source_term for term in tight.cut] == ["tallow"]
    # Spec 067 FR-008: a phrase and a name extend the budget like a required entry.
    assert [term.source_term for term in tiny.rendered] == ["quillet bond", "quillet", "marrow ledger", "Zorvane Pettish"]
    assert tiny.unrendered_required == ()
    assert [term.source_term for term in tiny.cut] == ["harbour", "tallow"]


def test_fr008_the_budget_cuts_only_optional_single_lowercase_entries():
    # Spec 067 FR-008 (G-1): a fixed budget cut 34 names, phrases and hyphenated entries of The
    # Value of Everything. Every optional entry of a form of its own reaches the section however
    # small the budget; only the optional single lowercase words are left out.
    from docxaicorrector.pipeline.glossary_phase import plan_run_glossary_section

    candidates = (
        _counted_candidate("quillet", 50, required=True),
        _counted_candidate("Zorvane Pettish", 30, family="name"),
        _counted_candidate("marrow ledger", 20, family="collocation"),
        _counted_candidate("short-tallow", 15),
        _counted_candidate("QLB", 12, family="name"),
        _counted_candidate("harbour", 90),
        _counted_candidate("drevage", 60),
        _counted_candidate("tallow", 3),
    )
    terms = (
        _entry("quillet", "киллет"),
        _entry("Zorvane Pettish", "Зорвейн Петтиш", kind="name"),
        _entry("marrow ledger", "мозговая книга"),
        _entry("short-tallow", "краткосальный"),
        _entry("QLB", "КЛБ"),
        _entry("drevage", "древаж", note="the toll on a held coin"),
        _entry("harbour", "гавань"),
        _entry("tallow", "сало"),
    )
    ordered = order_glossary_entries(candidates, terms)
    full = plan_run_glossary_section(ordered, candidates, max_chars=100_000)
    for budget in (10, len(full.text) - 5, len(full.text) // 2):
        plan = plan_run_glossary_section(ordered, candidates, max_chars=budget)
        assert plan.unrendered_required == ()
        assert all(glossary_pass.is_single_lowercase_entry(term) for term in plan.cut), (budget, plan.cut)
        rendered = {term.source_term for term in plan.rendered}
        assert {"quillet", "Zorvane Pettish", "marrow ledger", "short-tallow", "QLB", "drevage"} <= rendered
    tiny = plan_run_glossary_section(ordered, candidates, max_chars=10)
    assert [term.source_term for term in tiny.cut] == ["harbour", "tallow"]
    assert "- drevage -> древаж — the toll on a held coin" in tiny.text and tiny.text.endswith("- ...")
    # Counter-test: with room for everything nothing is cut.
    assert full.cut == () and not full.text.endswith("- ...")


def test_fr008_a_collocation_is_named_as_the_document_writes_it_not_by_its_folded_key():
    # Spec 067 FR-008: a collocation whose last word ends in an "s" that is not a plural was
    # asked for and printed with that "s" cut off -- the surface was built from its folded key.
    # The key stays folded; the name is the written word.
    paragraphs = []
    for _ in range(4):
        paragraphs.append("Clerks tally census from the quillet trade, and they tally census again.")
        paragraphs.extend(_FILLER)
    keys = {candidate.key: candidate for candidate in extract_glossary_candidates(_units(paragraphs))}

    assert ("tally", "censu") in keys
    assert keys[("tally", "censu")].source_term == "tally census"
    assert normalize_glossary_key("tally census") == ("tally", "censu")
    assert not any(word == "censu" for candidate in keys.values() for word in candidate.source_term.split())


def test_fr001_a_noted_or_capitalised_single_word_ranks_with_the_phrases():
    assert glossary_pass.is_single_lowercase_entry(_entry("harbour", "гавань"))
    for entry in (
        _entry("harbour", "гавань", note="the town's own"),
        _entry("Harbour", "Гавань"),
        _entry("worth-based", "основанный на ценности"),
        _entry("Kelbrook", "Келбрук", kind="name"),
        _entry("quillet bond", "киллетная облигация"),
    ):
        assert not glossary_pass.is_single_lowercase_entry(entry), entry


def test_fr003_counter_test_word_and_phrase_both_reach_the_section_the_longer_first():
    from docxaicorrector.core.config import load_system_prompt
    from docxaicorrector.pipeline.glossary_phase import plan_run_glossary_section

    candidates = (_counted_candidate("worth", 90, required=True), _counted_candidate("public worth", 20))
    terms = (
        _entry("worth", "стоимость", note="the sum a thing fetches"),
        _entry("public worth", "общественная ценность"),
    )
    plan = plan_run_glossary_section(order_glossary_entries(candidates, terms), candidates, max_chars=10)

    assert plan.unrendered_required == () and plan.cut == ()
    text = plan.text
    assert "- public worth -> общественная ценность" in text
    assert "- worth -> стоимость — the sum a thing fetches" in text
    assert text.index("- public worth ->") < text.index("- worth ->")
    prompt = load_system_prompt(
        operation="translate", source_language="en", target_language="ru", document_context_prompt=text
    )
    assert text in prompt
    assert "Более длинная запись глоссария имеет приоритет над входящим в неё словом" in prompt
    assert "не распространяйте на словосочетания, которых нет в глоссарии" in prompt
    assert "и в коротких повторных упоминаниях" in prompt  # FR-004


def test_fr003_a_phrase_does_not_displace_a_name():
    # Anti-regression 2 of spec 065: phrases ride over the candidate limit, so the names stay
    # exactly the same whether or not the text carries the phrase.
    paragraphs = _worth_document()
    for _ in range(4):
        paragraphs.append("In those years Zorvane Pettish kept the books of Kelbrook.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))
    without_phrase = _keys(
        extract_glossary_candidates(_units([text for text in paragraphs if "public worth" not in text]))
    )

    assert "zorvane pettish" in keys and "public worth" in keys
    assert {key for key, c in keys.items() if c.family == "name"} == {
        key for key, c in without_phrase.items() if c.family == "name"
    }


def test_fr003_the_glossary_prompts_ask_for_a_note_and_name_the_phrase_signal():
    required = glossary_pass._load_glossary_instructions(glossary_pass.GLOSSARY_ROLE_REQUIRED)
    optional = glossary_pass._load_glossary_instructions(glossary_pass.GLOSSARY_ROLE_OPTIONAL)

    assert 'when a general word is used in a special sense of this book, say that sense in "note"' in required
    assert '"phrase"' in required and '"phrase"' in optional


def test_fr002_a_camelcase_name_the_author_defines_once_stays_a_candidate():
    # Codex acceptance review of spec 065 (P1): "QuillPay" is a name by its inner capital; the
    # case test used to look only for "Quillpay" and "QUILLPAY", call it a lowercase word, and
    # the FR-002 count rule dropped it.
    paragraphs = ["The town built an app for it. This solution, called QuillPay, is free to use.", *(_FILLER * 6)]
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "quillpay" in keys
    assert keys["quillpay"].required and "defined" in keys["quillpay"].signals


def test_fr002_a_case_tie_is_a_capitalised_form_not_a_single_lowercase_word():
    # Spec 065 tie rule: a word the document capitalises mid-sentence as often as it writes it
    # lowercase is not "a word the document writes in lowercase", so the single-word count
    # rule does not apply to it. "Brennaby" -- once "Brennaby", once "brennaby" -- stays.
    paragraphs = [
        "The organisation involved is called Brennaby, as the valley knows.",
        "Later the brennaby site listed its members.",
        *(_FILLER * 6),
    ]
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "brennaby" in keys and keys["brennaby"].required
    # Anti-vacuum: written lowercase twice and capitalised never, the same word defined in
    # passing is a single lowercase word used twice -- not a candidate (FR-002, N = 3).
    lowercase = [
        "The organisation involved is called brennaby, as the valley knows.",
        "Later the brennaby site listed its members.",
        *(_FILLER * 6),
    ]
    assert "brennaby" not in _keys(extract_glossary_candidates(_units(lowercase)))


# --- Spec 067 FR-010: permutations and hyphen variants are one candidate ------------------------


def _ledger_document():
    paragraphs = ["What the town kept we call *tallow* here, and the *tallow ledger* opens the book."]
    for _ in range(6):
        paragraphs.extend(_FILLER)
        paragraphs.append("The tallow ledger grew, and the tallow ledger was read; tallow was weighed.")
        paragraphs.append("Their ledger tallow was counted apart under tallow-ledger rules; the tallow ledger stayed shut.")
    return paragraphs


def test_fr010_word_order_and_hyphen_variants_collapse_into_the_most_used_surface():
    candidates = extract_glossary_candidates(_units(_ledger_document()))
    by_term = {candidate.source_term: candidate for candidate in candidates}

    assert "ledger tallow" not in by_term and "tallow-ledger" not in by_term
    ledger = by_term["tallow ledger"]
    assert set(ledger.spellings) == {"ledger tallow", "tallow-ledger"}
    assert ledger.occurrence_count == 19 + 6 + 6  # every surface's uses
    assert ledger.required
    assert ledger.to_payload()["spellings"] == list(ledger.spellings)
    # The other candidates of the document are untouched.
    assert "tallow" in by_term and by_term["tallow"].spellings == ()
    assert "tallow-ledger rules" in by_term


def test_fr010_an_answer_for_a_spelling_is_not_an_entry_and_the_kept_rendering_stands():
    ledger = replace(
        _candidate("tallow ledger", "marked"), required=True, spellings=("ledger tallow", "tallow-ledger")
    )
    request = build_glossary_request(
        model="m", candidates=(ledger,), source_language="en", target_language="ru", max_terms=5,
        role=glossary_pass.GLOSSARY_ROLE_REQUIRED,
    )
    payload = json.loads(cast(Any, request["input"])[1]["content"][0]["text"])
    assert payload["candidates"][0]["spellings"] == ["ledger tallow", "tallow-ledger"]
    raw = json.dumps(
        {
            "terms": [
                {"source_term": "ledger tallow", "target_term": "прибавочная книга"},
                {"source_term": "tallow ledger", "target_term": "сальная книга"},
                {"source_term": "tallow-ledger", "target_term": "сально-книжный"},
            ]
        }
    )
    result = parse_glossary_response(raw, candidates=(ledger,), max_terms=5)

    assert [(term.source_term, term.target_term) for term in result.terms] == [("tallow ledger", "сальная книга")]
    assert result.rejected_counts["not_a_candidate"] == 2


def test_fr010_the_section_names_the_spellings_on_the_entry_line():
    from docxaicorrector.pipeline.glossary_phase import plan_run_glossary_section

    ledger = replace(_counted_candidate("tallow ledger", 31, required=True), spellings=("ledger tallow", "tallow-ledger"))
    plan = plan_run_glossary_section((_entry("tallow ledger", "сальная книга"),), (ledger,), max_chars=100_000)

    assert plan.text.splitlines()[1] == "- tallow ledger (также: ledger tallow, tallow-ledger) -> сальная книга"
    assert [term.source_term for term in plan.rendered] == ["tallow ledger"]


def test_fr010_names_are_not_collapsed_by_word_order():
    # Anti-regression: a name keeps its case-sensitive identity (spec 064 FR-009 name families).
    paragraphs = list(_document())
    for _ in range(3):
        paragraphs.append("Later Pettish Zorvane wrote back to the town of Kelbrook about it.")
    by_term = {candidate.source_term: candidate for candidate in extract_glossary_candidates(_units(paragraphs))}

    assert "Zorvane Pettish" in by_term and by_term["Zorvane Pettish"].spellings == ()
    assert "Pettish Zorvane" in by_term


def test_fr010_both_glossary_prompts_explain_spellings():
    for role in (glossary_pass.GLOSSARY_ROLE_REQUIRED, glossary_pass.GLOSSARY_ROLE_OPTIONAL):
        text = glossary_pass._load_glossary_instructions(role)
        assert '"spellings", when present, are the same expression written otherwise in the book' in text


# --- Spec 067 FR-009: entries the book sets against each other carry a mutual mark ---------------


def _contrast_document():
    paragraphs = []
    for _ in range(6):
        paragraphs.extend(_FILLER)
        paragraphs.append("The drovish ledgers were kept apart from the brannick ledgers in every town.")
        paragraphs.append("Merchants trusted drovish ledgers more; the clerks preferred drovish ledgers too.")
        paragraphs.append("Brannick ledgers came later, and brannick ledgers are still read.")
        paragraphs.append("The harbour kept salted herring, and salted herring sold well.")
        paragraphs.append("The smoked herring did not sell, though smoked herring was cheap.")
    paragraphs.append("Salted herring and smoked herring met only once, at the fair.")
    return paragraphs


def test_fr009_two_candidates_sharing_the_last_word_side_by_side_are_contrasted():
    by_term = {candidate.source_term: candidate for candidate in extract_glossary_candidates(_units(_contrast_document()))}

    assert by_term["drovish ledgers"].contrasts == ("brannick ledgers",)
    assert by_term["brannick ledgers"].contrasts == ("drovish ledgers",)
    assert by_term["drovish ledgers"].to_payload()["contrasts"] == ["brannick ledgers"]
    # Counter-test: one shared paragraph is not the author setting them against each other.
    assert "salted herring" in by_term and "smoked herring" in by_term
    assert by_term["salted herring"].contrasts == () and by_term["smoked herring"].contrasts == ()


def test_fr009_a_narrower_form_or_an_of_phrase_is_not_a_contrast():
    def candidate(term):
        return replace(_candidate(term, "collocation"), key=normalize_glossary_key(term))

    candidates = (
        candidate("tallow quills"),
        candidate("red tallow quills"),  # ends with "tallow quills": the same thing narrowed
        candidate("theory of quills"),  # a joiner inside: "quills" is not its head
        candidate("brannick quills"),
    )
    shared = {0, 1, 2, 3}
    partners = glossary_pass._contrast_partners(candidates, [set(shared) for _ in candidates])

    assert partners[0] == ("brannick quills",)
    assert partners[1] == ("brannick quills",)
    assert 2 not in partners
    assert set(partners[3]) == {"tallow quills", "red tallow quills"}


def test_fr009_the_section_marks_both_entries_with_the_other_rendering():
    from docxaicorrector.pipeline.glossary_phase import plan_run_glossary_section

    drovish = replace(_counted_candidate("drovish ledgers", 18, required=True), contrasts=("brannick ledgers",))
    brannick = replace(_counted_candidate("brannick ledgers", 12), contrasts=("drovish ledgers",))
    terms = (
        _entry("drovish ledgers", "дровишские книги", note="older, kept by merchants"),
        _entry("brannick ledgers", "бранницкие книги"),
    )
    lines = plan_run_glossary_section(terms, (drovish, brannick), max_chars=10).text.splitlines()

    assert lines[1] == "- drovish ledgers -> дровишские книги ≠ бранницкие книги — older, kept by merchants"
    assert lines[2] == "- brannick ledgers -> бранницкие книги ≠ дровишские книги"
    # Counter-tests: no mark when the partner has no entry, or shares the rendering (a
    # collision -- call C's business, not a contrast to print).
    alone = plan_run_glossary_section(terms[:1], (drovish, brannick), max_chars=10).text
    assert "≠" not in alone
    shared = (terms[0], _entry("brannick ledgers", "дровишские книги"))
    assert "≠" not in plan_run_glossary_section(shared, (drovish, brannick), max_chars=10).text


def test_fr009_the_calls_carry_the_contrast_and_the_prompts_explain_it():
    from docxaicorrector.core.config import load_system_prompt

    drovish = replace(_candidate("drovish ledgers", "marked"), required=True, contrasts=("brannick ledgers",))
    for role in (glossary_pass.GLOSSARY_ROLE_REQUIRED, glossary_pass.GLOSSARY_ROLE_OPTIONAL):
        request = build_glossary_request(
            model="m", candidates=(drovish,), source_language="en", target_language="ru", max_terms=5, role=role
        )
        payload = json.loads(cast(Any, request["input"])[1]["content"][0]["text"])
        assert payload["candidates"][0]["contrast_with"] == ["brannick ledgers"]
        text = glossary_pass._load_glossary_instructions(role)
        assert '"contrast_with"' in text and "contrasted concepts" in text
        assert 'say in "note", in a few words, what sets it apart from them' in text
    prompt = load_system_prompt(
        operation="translate", source_language="en", target_language="ru",
        document_context_prompt="ГЛОССАРИЙ:\n- drovish ledgers -> дровишские книги ≠ бранницкие книги",
    )
    assert "Пометка «≠ …» после передачи называет передачи терминов, которые автор противопоставляет этому" in prompt


# --- Spec 067 FR-011: two form defects of single words -------------------------------------------


def test_fr011_a_paragraph_set_in_capitals_is_no_evidence_of_a_capitalised_form():
    # Rethinking Money, a part title in capitals: a paragraph in capitals gave the word a capital
    # "form" (inner capitals,
    # and a capitalised run), and the marked word became required.
    paragraphs = ["**HARBOURAGE**"]
    for _ in range(4):
        paragraphs.extend(_FILLER)
        paragraphs.append("The harbourage of the town was paid twice, and the harbourage rose.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "harbourage" in keys
    assert not keys["harbourage"].required
    # Counter-test: mixed case is still a name's form (spec 065, Codex finding 2).
    assert glossary_pass._has_inner_capital("QuillPay") and glossary_pass._has_inner_capital("eBay")
    assert not glossary_pass._has_inner_capital("HARBOURAGE")


def _chapter_document(mention):
    paragraphs: list[tuple[str, int | None]] = []
    for number in range(1, 5):
        paragraphs.append((f"PARTITION {number}", 1))
        paragraphs.extend((text, None) for text in _FILLER)
        paragraphs.append((f"As shown in {mention(number)}, this partition matters.", None))
    return _heading_units(paragraphs)


def test_fr011_a_capital_before_a_number_is_a_label_not_the_words_case():
    # Creating Wealth: a word written with a capital before a number 15 times mid-sentence,
    # against 14 lowercase uses, made it a capitalised form, and its all-capitals h1 headings
    # made it required.
    keys = _keys(extract_glossary_candidates(_chapter_document(lambda number: f"Partition {number}")))
    assert "partition" in keys and not keys["partition"].required

    # Counter-test: the same capital NOT before a number is the document's case of the word.
    keys = _keys(extract_glossary_candidates(_chapter_document(lambda number: "the Partition office")))
    assert "partition" in keys and keys["partition"].required


def test_fr011_a_defined_hyphenated_word_split_by_emphasis_is_one_candidate():
    paragraphs = [
        "Its own token is perhaps the guild's oddest habit. The token is called *wink-**nods* or Ws.",
        *(_FILLER * 6),
    ]
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "wink-nods" in keys and "defined" in keys["wink-nods"].signals and keys["wink-nods"].required
    assert "wink" not in keys


def test_fr011_a_defined_expression_the_document_writes_whole_keeps_its_short_first_word():
    # Enough ordinary text that "ebb" is not among the document's 20 commonest words.
    paragraphs = ["The two methods are a tidal scheme known as ebb and flow, and the toll."]
    for round_index in range(12):
        paragraphs.extend(_FILLER)
        if round_index % 3 == 0:
            paragraphs.append("Under ebb and flow the berths are sold, and the flow in berths grows.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert "ebb and flow" in keys and keys["ebb and flow"].required
    assert "flow" not in keys
    # Counter-test: a definition written once is trimmed as before ("called him a lostling").
    once = ["The neighbours called him a lostling, and it stuck.", *(_FILLER * 6)]
    assert "him a lostling" not in _keys(extract_glossary_candidates(_units(once)))


def test_fr010_two_expressions_the_author_defines_each_stay_two_candidates():
    # Codex acceptance review of spec 067 (P0): the author defines both orders as concepts of
    # their own; collapsing them would answer one and reject the other as not_a_candidate.
    paragraphs = [
        "On the river we call this a *house boat*, a home that floats.",
        "On the bank we call that a *boat house*, a shed for the hull.",
    ]
    for _ in range(6):
        paragraphs.extend(_FILLER)
        paragraphs.append("The house boat drifted; the boat house stayed, and the house boat came back.")
    by_term = {candidate.source_term: candidate for candidate in extract_glossary_candidates(_units(paragraphs))}

    assert "house boat" in by_term and "boat house" in by_term
    assert by_term["house boat"].spellings == () and by_term["boat house"].spellings == ()
    assert by_term["house boat"].required and by_term["boat house"].required


def test_fr010_two_place_names_in_either_order_stay_two_candidates():
    # Codex acceptance review of spec 067 (P0): italicised place names are marked drafts with a
    # lowercase key; written capitalised by the document's own count, they are names.
    paragraphs = []
    for _ in range(6):
        paragraphs.extend(_FILLER)
        paragraphs.append("Ships left *North Harbour* at dawn, and later North Harbour was quiet again.")
        paragraphs.append("Boats from *Harbour North* came in, though Harbour North lay further out.")
    by_term = {candidate.source_term: candidate for candidate in extract_glossary_candidates(_units(paragraphs))}

    assert "North Harbour" in by_term and "Harbour North" in by_term
    assert by_term["North Harbour"].spellings == () and by_term["Harbour North"].spellings == ()


# --- Spec 069 WP-2, FR-006: the glossary budget with a model multiplier -----------------------

# entry count -> the budget of today: the floor (0, 1, 8), just past it (9), an ordinary list
# (60, 74), the exact ceiling (168) and past it (169, 10 000).
_SPEC_069_GLOSSARY_BUDGET_OF_TODAY = {
    0: 1024,
    1: 1024,
    8: 1024,
    9: 1120,
    60: 6016,
    74: 7360,
    168: 16384,
    169: 16384,
    10_000: 16384,
}


@pytest.mark.parametrize(("entry_count", "expected"), sorted(_SPEC_069_GLOSSARY_BUDGET_OF_TODAY.items()))
def test_spec_069_glossary_budget_without_a_multiplier_is_the_budget_of_today(entry_count, expected):
    assert glossary_pass.glossary_max_output_tokens(entry_count) == expected
