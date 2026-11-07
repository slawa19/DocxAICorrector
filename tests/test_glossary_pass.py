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
    DEFAULT_GLOSSARY_PROMPT_MAX_CHARS,
    DocumentContextProfile,
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
    domain_glossary_terms,
    extract_glossary_candidates,
    missing_required_candidates,
    normalize_glossary_key,
    order_required_first,
    parse_glossary_response,
    request_candidates,
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

    assert render_glossary_prompt_section(terms, max_chars=0) == ""
    assert render_glossary_prompt_section((GlossaryTerm(source_term="term", target_term=""),)) == ""


def test_profile_slot_is_capped_by_characters_not_by_eight_entries():
    terms = tuple(GlossaryTerm(source_term=f"t{index}", target_term=f"т{index}") for index in range(10))
    prompt = DocumentContextProfile(glossary_terms=terms).to_prompt_text()

    for index in range(10):
        assert f"- t{index} -> т{index}" in prompt
    assert "- ..." not in prompt
    assert DEFAULT_GLOSSARY_PROMPT_MAX_CHARS == 3000


def test_theology_slot_is_unchanged_by_the_shared_helper():
    """FR-016: the domain list is not extended; preparation's output is what it was."""

    source_text = "The Great Tribulation and the rapture, then the Antichrist."
    via_preparation = preparation._build_document_context_glossary_terms(
        translation_domain="theology",
        source_text=source_text,
    )
    via_helper = domain_glossary_terms(source_text=source_text, translation_domain="theology")

    assert via_preparation == via_helper
    assert [term.source_term for term in via_preparation] == ["Great Tribulation", "rapture", "Antichrist"]
    assert via_preparation[0].target_term == "Великая скорбь"
    assert all(term.kind == "term" and term.note == "" for term in via_preparation)
    assert domain_glossary_terms(source_text=source_text, translation_domain="general") == ()


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
    paragraphs.insert(2, "For the rest of the book we will refer to this kind of paper as *quillet bond*.")
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

    assert "worth" in keys and keys["worth"].family == "head"


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


def test_request_carries_languages_limit_candidates_and_fixed_terms():
    request = build_glossary_request(
        model="model-x",
        candidates=(_candidate("Zorvane Pettish"), _candidate("quillet bond", "marked")),
        fixed_terms=(GlossaryTerm(source_term="Great Tribulation", target_term="Великая скорбь"),),
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
    assert user_payload["fixed_terms"] == [{"source_term": "Great Tribulation", "target_term": "Великая скорбь"}]


def test_fixed_domain_terms_are_taken_out_of_the_request():
    left = request_candidates(
        (_candidate("Great Tribulations"), _candidate("Zorvane")),
        (GlossaryTerm(source_term="Great Tribulation", target_term="Великая скорбь"),),
    )

    assert [candidate.source_term for candidate in left] == ["Zorvane"]


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
    assert normalize_glossary_key("Wellness Tokens") == normalize_glossary_key("wellness token")
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
    assert keys["brennic"].required  # italics at first use
    assert keys["sound note"].required  # quotes around an expression
    assert "real" not in keys or not keys["real"].required  # quotes around one word: model's choice
    assert not keys["kelbrook"].required  # a name stays at the model's discretion


def test_a_family_of_unmarked_collocations_has_an_optional_head():
    """Anti-vacuum: a head is required only when the author marked one of its members."""
    paragraphs = []
    for _ in range(6):
        paragraphs.append("The worth creation and the worth extraction were measured.")
        paragraphs.append("Their worth creation exceeded worth extraction, and surplus worth grew.")
        paragraphs.append("Surplus worth and worth creation, again; surplus worth once more.")
        paragraphs.extend(_FILLER)
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["worth"].family == "head" and not keys["worth"].required
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
            paragraphs.append("Here the *brennic* rule is set out.")
    keys = _keys(extract_glossary_candidates(_units(paragraphs)))

    assert keys["brennic"].required


def _heading_units(paragraphs):
    units = []
    for index, (text, level) in enumerate(paragraphs):
        units.append(
            GlossarySourceUnit(unit_id=f"p{index:04d}", text=text, is_heading=level is not None, heading_level=level)
        )
    return tuple(units)


def test_a_heading_word_the_body_keeps_using_is_a_candidate_with_the_heading_as_context():
    paragraphs: list[tuple[str, int | None]] = [("Money and Durability", 1)]
    for chapter in range(4):
        paragraphs.append((f"Chapter {chapter} Notes", 2))
        paragraphs.append(("The question of durability returns here, and durability matters.", None))
        paragraphs.extend((text, None) for text in _FILLER)
    candidate = _keys(extract_glossary_candidates(_heading_units(paragraphs)))["durability"]

    assert candidate.family == "heading"
    assert candidate.context == "Money and Durability"
    # Fourth pass: an h1 (title, chapter) phrase the body keeps using is required.
    assert candidate.required


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
    ordered = order_required_first(candidates, result.terms)
    assert [term.source_term for term in ordered] == ["quillet bond", "Alpha"]
    assert missing_required_candidates(candidates, result.terms) == ()
    assert missing_required_candidates(candidates, result.terms[:1]) == (candidates[0],)


def test_request_marks_required_candidates_for_the_model():
    request = build_glossary_request(
        model="m",
        candidates=(replace(_candidate("quillet bond", "marked"), required=True), _candidate("Alpha")),
        fixed_terms=(),
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
        fixed_terms=(),
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
            "terms": [{"term": "durability", "context": "ctx one"}, {"term": "steadiness", "context": "ctx two"}],
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
        fixed_terms=(),
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
    optional = tuple(_candidate(f"Opt{chr(97 + i)}") for i in range(3))
    terms = tuple(
        GlossaryTerm(source_term=candidate.source_term, target_term="перевод-" + candidate.source_term.lower())
        for candidate in (*required, *optional)
    )
    full = render_run_glossary_section(terms, (*required, *optional), max_chars=100_000)
    tight = render_run_glossary_section(terms, (*required, *optional), max_chars=len(full) - 10)
    tiny = render_run_glossary_section(terms, (*required, *optional), max_chars=10)

    assert "Optc" in full and "Optc" not in tight and "Optb" in tight  # last-ranked optional goes first
    for name in ("Reqa", "Reqb", "Reqc"):
        assert name in tight and name in tiny  # required entries survive any budget
    assert "Opta" not in tiny


def _h1_document(title, body_sentence, *, level=1, rounds=4):
    paragraphs: list[tuple[str, int | None]] = [(title, level)]
    for _ in range(rounds):
        paragraphs.append((body_sentence, None))
        paragraphs.extend((text, None) for text in _FILLER)
    return _heading_units(paragraphs)


def test_an_h2_phrase_the_body_keeps_using_stays_optional():
    keys = _keys(
        extract_glossary_candidates(
            _h1_document("Notes on Durability", "The question of durability returns here, and durability matters.", level=2)
        )
    )

    assert keys["durability"].family == "heading"
    assert not keys["durability"].required


def test_an_h1_phrase_the_body_never_repeats_is_not_required():
    """Anti-vacuum: the title alone does not make a word a term of the book."""
    keys = _keys(extract_glossary_candidates(_h1_document("Durability Unbound", "Nothing about it here at all, truly.")))

    assert "durability" not in keys and "unbound" not in keys


def test_function_words_and_joiner_edges_of_an_h1_are_not_candidates():
    units = _h1_document(
        "MONEY AND DURABILITY FOR ALL",
        "Money and durability, money and durability for all of them, for all.",
    )
    keys = _keys(extract_glossary_candidates(units))

    for phrase in ("and", "for", "all", "money and", "and durability", "durability for", "for all"):
        assert phrase not in keys, phrase
    assert keys["durability"].required


def test_a_chapter_number_in_an_h1_is_not_a_candidate():
    units = _h1_document("Chapter VII Durability", "Chapter seven speaks of durability, and durability again.")
    keys = _keys(extract_glossary_candidates(units))

    assert not any("vii" in key for key in keys)
    assert keys["durability"].required


def test_requests_ask_for_standard_transcription_and_the_full_name():
    for role in ("required", "optional"):
        request = build_glossary_request(
            model="m",
            candidates=(_candidate("Zorvane Pettish"),),
            fixed_terms=(),
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
    paragraphs = [SimpleNamespace(paragraph_id="p0000", text="Money and Durability", role="heading", heading_level=1)]
    for chapter in range(4):
        paragraphs.append(
            SimpleNamespace(paragraph_id=f"p1{chapter:03d}", text=f"Chapter {chapter} Notes", role="heading", heading_level=1)
        )
        for line, text in enumerate(
            ("The question of durability returns here, and durability matters.", *_FILLER)
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
    assert _keys(produced)["durability"].required  # an h1 phrase: the field decides it

    dump = tmp_path / "dump.json"
    script._dump(jobs, paragraphs, dump)
    replayed_jobs, replayed_paragraphs = script._load_dump(dump)
    replayed = extract_glossary_candidates(select_glossary_source_units(replayed_jobs, replayed_paragraphs))

    assert [(c.source_term, c.family, c.required) for c in replayed] == [
        (c.source_term, c.family, c.required) for c in produced
    ]
    assert script._assert_dump_parity(jobs, paragraphs, dump, limit=400) == sum(c.required for c in produced)
