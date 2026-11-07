"""Spec 063 FR-011 / FR-012 under owner decision D1 (2026-11-07).

D1: entries of a bibliography and references stay in the SOURCE language, the commentary of
notes is translated, one policy per book -- keyed on the back-matter REGION and the section
that region opens with, never on the shape of an entry (Constitution VII).

* FR-011: a block made only of reference-list entries is delivered as its own source with NO
  model call, under the per-paragraph status ``policy_kept_source``; a block that mixes entries
  with anything else goes to the model with the D1 rule naming its back-matter paragraphs.
* FR-012: how the back matter reached the reader is published as run data -- source against
  translated paragraphs per section, blocks kept by policy (= calls saved), and the
  ``needs_review`` count of reference-list blocks whose entries came out mixed.

Anti-vacuum, by the spec's anti-regression 1 and 7: a prose paragraph is never kept, a block
carrying one still goes to the model, and if it then ships as its own source the 059/061
invariant still announces it.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.core import model_accounting
from docxaicorrector.core.models import (
    BACK_MATTER_SECTION_INDEX,
    BACK_MATTER_SECTION_NOTES,
    BACK_MATTER_SECTION_REFERENCES,
    BACK_MATTER_SECTION_VALUES,
    PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
    DocumentBlock,
    ParagraphUnit,
)
from docxaicorrector.document import semantic_blocks
from docxaicorrector.generation._generation import (
    PARAGRAPH_STATUS_ACCEPTED,
    MarkerPreservedBlockText,
    ParagraphDisposition,
)
from docxaicorrector.pipeline import narration_postprocess, quality_gate
from docxaicorrector.pipeline.contracts import BlockExecutionPayload
from docxaicorrector.pipeline.job_parsing import parse_processing_job
from docxaicorrector.validation.formatting_coverage import _BACKMATTER_SECTION_TITLES

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENTRY_A = "Aghion, P. and Howitt, P., *Endogenous Growth Theory* (Cambridge, MA: MIT Press, 1998)."
_ENTRY_B = "Akerlof, G. A., 'The market for lemons', *Quarterly Journal of Economics* 84(3), 1970, pp. 488-500."
_PROSE = (
    "Money is not a thing but an agreement within a community to use something standardised "
    "as a means of payment, and that agreement is what this chapter is about."
)


# --- the document layer: which back-matter SECTION a block belongs to ------------------------


def test_the_section_partition_covers_the_blessed_anchor_lexicon_exactly() -> None:
    """No title is invented and none is left without a kind: the partition IS the lexicon."""
    assert frozenset(semantic_blocks._BACK_MATTER_SECTION_KIND_BY_TITLE) == frozenset(_BACKMATTER_SECTION_TITLES)
    assert set(semantic_blocks._BACK_MATTER_SECTION_KIND_BY_TITLE.values()) == set(BACK_MATTER_SECTION_VALUES)


def _book_with_back_matter() -> list[DocumentBlock]:
    def unit(text: str, pid: str, *, role: str = "body", level: int | None = None) -> ParagraphUnit:
        return ParagraphUnit(text=text, role=role, paragraph_id=pid, heading_level=level, structural_role=role)

    return [
        DocumentBlock(paragraphs=[unit("Chapter One", "p0000", role="heading", level=1), unit(_PROSE, "p0001")]),
        DocumentBlock(paragraphs=[unit("Notes", "p0002", role="heading", level=1), unit("1. Ibid., p. 4.", "p0003")]),
        DocumentBlock(paragraphs=[unit("2. Smith argues the opposite; see Akerlof 1970.", "p0004")]),
        DocumentBlock(paragraphs=[unit("Bibliography", "p0005", role="heading", level=1), unit(_ENTRY_A, "p0006")]),
        DocumentBlock(paragraphs=[unit(_ENTRY_A, "p0007"), unit(_ENTRY_B, "p0008", role="list")]),
        DocumentBlock(paragraphs=[unit("Index", "p0009", role="heading", level=1), unit("barter, 12, 45", "p0010")]),
    ]


def test_editing_jobs_name_the_back_matter_section_of_every_back_matter_block() -> None:
    jobs = semantic_blocks.build_editing_jobs(_book_with_back_matter(), max_chars=3000, processing_operation="translate")

    assert [job["back_matter_section"] for job in jobs] == [
        None,
        BACK_MATTER_SECTION_NOTES,
        BACK_MATTER_SECTION_NOTES,
        BACK_MATTER_SECTION_REFERENCES,
        BACK_MATTER_SECTION_REFERENCES,
        BACK_MATTER_SECTION_INDEX,
    ]
    # The section qualifies the region and never disagrees with it about WHICH blocks are
    # back matter.
    for job in jobs:
        in_region = set(cast(list[str], job["paragraph_regions"])) == {"back_matter"}
        assert in_region == (job["back_matter_section"] is not None)


def test_the_section_reaches_the_payload_and_an_unknown_name_is_refused() -> None:
    job = {
        "job_kind": "llm",
        "target_text": "x",
        "context_before": "",
        "context_after": "",
        "target_chars": 1,
        "context_chars": 0,
        "paragraph_ids": ["p0001"],
        "paragraph_regions": ["back_matter"],
        "back_matter_section": "references",
    }
    assert parse_processing_job(job=job, payload_factory=BlockExecutionPayload).back_matter_section == "references"
    assert parse_processing_job(job={**job, "back_matter_section": None}, payload_factory=BlockExecutionPayload).back_matter_section is None
    with pytest.raises(ValueError, match="unknown section name"):
        parse_processing_job(job={**job, "back_matter_section": "bibliography"}, payload_factory=BlockExecutionPayload)


# --- FR-011: which block is kept without a model call ------------------------------------------


def _marked(paragraph_ids: list[str], texts: list[str]) -> str:
    return "\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(paragraph_ids, texts))


def _payload(
    *,
    texts: list[str] | None = None,
    regions: list[str] | None = None,
    roles: list[str] | None = None,
    section: str | None = BACK_MATTER_SECTION_REFERENCES,
    job_kind: str = "llm",
    toc_dominant: bool = False,
) -> SimpleNamespace:
    texts = texts if texts is not None else [_ENTRY_A, _ENTRY_B]
    paragraph_ids = [f"p{index:04d}" for index in range(len(texts))]
    target_text = "\n\n".join(texts)
    return SimpleNamespace(
        job_kind=job_kind,
        toc_dominant=toc_dominant,
        target_text=target_text,
        target_text_with_markers=_marked(paragraph_ids, texts),
        paragraph_ids=paragraph_ids,
        structural_roles=roles if roles is not None else ["body", "list"][: len(texts)] + ["body"] * max(0, len(texts) - 2),
        paragraph_regions=regions if regions is not None else ["back_matter"] * len(texts),
        back_matter_section=section,
        narration_include=False,
        target_chars=len(target_text),
        context_chars=0,
        context_before="",
        context_after="",
    )


_TRANSLATE = SimpleNamespace(processing_operation="translate")


def test_a_block_of_reference_list_entries_is_kept() -> None:
    assert block_execution.reference_list_block_keeps_source(context=_TRANSLATE, payload=_payload()) is True


@pytest.mark.parametrize(
    "override",
    [
        pytest.param({"regions": ["back_matter", "prose"]}, id="a-prose-paragraph-anti-vacuum"),
        pytest.param({"roles": ["heading", "body"]}, id="a-heading-is-translated"),
        pytest.param({"roles": ["body", "caption"]}, id="an-unknown-role-goes-to-the-model"),
        pytest.param({"section": BACK_MATTER_SECTION_NOTES}, id="notes-translate-their-commentary"),
        pytest.param({"section": BACK_MATTER_SECTION_INDEX}, id="the-index-is-not-covered-by-D1"),
        pytest.param({"section": None}, id="outside-the-back-matter"),
        pytest.param({"toc_dominant": True}, id="toc-routed"),
        pytest.param({"job_kind": "passthrough"}, id="already-passthrough"),
        pytest.param({"regions": ["back_matter"]}, id="regions-out-of-step"),
    ],
)
def test_anything_but_a_pure_reference_list_block_goes_to_the_model(override: dict[str, Any]) -> None:
    assert block_execution.reference_list_block_keeps_source(context=_TRANSLATE, payload=_payload(**override)) is False


@pytest.mark.parametrize("operation", ["edit", "audiobook", ""])
def test_the_policy_is_a_translation_policy(operation: str) -> None:
    context = SimpleNamespace(processing_operation=operation)
    assert block_execution.reference_list_block_keeps_source(context=context, payload=_payload()) is False


def test_the_kept_block_is_its_source_to_the_character_with_a_per_paragraph_status() -> None:
    payload = _payload()
    chunk = block_execution.policy_kept_source_chunk(context=_TRANSLATE, payload=payload, marker_mode_enabled=True)

    assert chunk is not None
    assert chunk == payload.target_text
    dispositions = block_execution.marker_paragraph_dispositions(chunk)
    assert dispositions is not None
    assert [(d.paragraph_id, d.text, d.status) for d in dispositions] == [
        ("p0000", _ENTRY_A, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE),
        ("p0001", _ENTRY_B, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE),
    ]
    registry = block_execution.build_processed_paragraph_registry_entries(
        block_index=7, paragraph_ids=payload.paragraph_ids, processed_chunk=chunk
    )
    assert [entry["paragraph_status"] for entry in registry] == [PARAGRAPH_STATUS_POLICY_KEPT_SOURCE] * 2
    # Without markers there is no registry to carry a status, and the source ships as is.
    assert block_execution.policy_kept_source_chunk(context=_TRANSLATE, payload=payload, marker_mode_enabled=False) == payload.target_text


def test_an_unaddressable_source_falls_back_to_the_model_rather_than_being_guessed() -> None:
    payload = _payload()
    payload.target_text_with_markers = payload.target_text  # no markers at all
    assert block_execution.policy_kept_source_chunk(context=_TRANSLATE, payload=payload, marker_mode_enabled=True) is None


# --- FR-011 end to end through ``process_single_block`` ---------------------------------------


def _harness():
    events: list[tuple[str, dict[str, object]]] = []
    dependencies = SimpleNamespace(log_event=lambda _level, event, _message, **context: events.append((event, context)))
    emitters = SimpleNamespace(
        emit_state=lambda _runtime, **_kwargs: None,
        emit_status=lambda _runtime, **_kwargs: None,
        emit_log=lambda _runtime, **_kwargs: None,
    )
    return dependencies, emitters, events


def _run(payload: SimpleNamespace, *, model_answer: str | None = None, classification: str = "valid", marker_mode: bool = True):
    dependencies, emitters, events = _harness()
    state = SimpleNamespace(
        processed_chunks=[],
        narration_chunks=[],
        excluded_narration_block_count=0,
        narration_excluded_source_fallback_block_count=0,
        narration_excluded_source_fallback_chars=0,
        narration_excluded_source_fallback_paragraphs=[],
        narration_excluded_omitted_paragraph_count=0,
        narration_excluded_omitted_chars=0,
        narration_excluded_omitted_paragraphs=[],
        untranslated_prose_delivered_paragraphs=[],
        generated_paragraph_registry=[],
        started_at=0.0,
    )
    model_calls: list[object] = []
    classifier_calls: list[object] = []

    def execute_processing_block_fn(**_kwargs: object) -> tuple[str, bool]:
        model_calls.append(_kwargs)
        return (model_answer if model_answer is not None else payload.target_text), marker_mode

    def classify(target_text: str, chunk: str, **_kwargs: object) -> str:
        classifier_calls.append((target_text, chunk))
        return classification

    def append_registry(**kwargs: object) -> None:
        state.generated_paragraph_registry.extend(
            block_execution.build_processed_paragraph_registry_entries(
                block_index=1, paragraph_ids=payload.paragraph_ids, processed_chunk=cast(str, kwargs["processed_chunk"])
            )
        )

    context = SimpleNamespace(
        processing_operation="translate",
        source_language="en",
        target_language="ru",
        uploaded_filename="book.pdf",
        runtime=object(),
        on_progress=lambda **_kwargs: None,
    )
    with model_accounting.run_model_accounting_scope(run_id="run-063", source_token="token-063") as ledger:
        outcome = block_execution.process_single_block(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=SimpleNamespace(job_count=1),
            index=1,
            job=object(),
            parse_processing_job_fn=lambda *, job: payload,
            handle_invalid_processing_job_fn=lambda **_kwargs: "failed",
            emit_block_started_fn=lambda **_kwargs: None,
            is_marker_mode_enabled_fn=lambda _context, _payload: marker_mode,
            execute_processing_block_fn=execute_processing_block_fn,
            handle_block_generation_failure_fn=lambda **_kwargs: "failed",
            classify_processed_block_fn=classify,
            handle_processed_block_rejection_fn=lambda **_kwargs: "failed",
            append_marker_registry_entries_fn=append_registry,
            handle_marker_registry_failure_fn=lambda **_kwargs: "failed",
            emit_block_completed_fn=lambda **_kwargs: None,
        )
        snapshot = ledger.snapshot()
    return SimpleNamespace(
        outcome=outcome,
        state=state,
        events=events,
        model_calls=model_calls,
        classifier_calls=classifier_calls,
        snapshot=snapshot,
    )


def test_a_reference_list_block_costs_no_model_call_and_is_no_fallback(monkeypatch) -> None:
    """The FR-011 test the spec names: zero model calls, the source text, zero fallback events."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    payload = _payload()

    run = _run(payload)

    assert run.outcome is None
    assert run.model_calls == []
    assert run.classifier_calls == []  # nothing to classify: the model was never asked
    assert run.state.processed_chunks == [payload.target_text]
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [
        PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
    ] * 2
    assert [event for event, _ in run.events].count("block_controlled_fallback") == 0
    assert [event for event, _ in run.events].count("block_apparatus_policy_kept_source") == 1
    assert run.snapshot["controlled_block_fallback_block_count"] == 0
    assert run.snapshot["untranslated_prose_block_delivery_count"] == 0
    assert run.snapshot["back_matter_policy_kept_block_count"] == 1
    assert run.snapshot["back_matter_policy_kept_paragraph_count"] == 2
    assert run.snapshot["back_matter_policy_kept_chars"] == len(payload.target_text)
    assert run.snapshot["back_matter_source_paragraph_counts"] == {"references": 2}
    assert run.snapshot["back_matter_translated_paragraph_counts"] == {}
    assert run.snapshot["back_matter_mixed_block_count"] == 0
    # The back matter is outside the narration by the document layer (spec 054), as before.
    assert run.state.narration_chunks == []
    assert run.state.excluded_narration_block_count == 1


def test_anti_vacuum_a_prose_paragraph_sends_the_block_to_the_model_and_its_loss_is_announced(monkeypatch) -> None:
    """Anti-regression 1: the block carries prose, so it is translated -- and when the model
    returns it untranslated, the 059 invariant still counts it, as on RM 2026-11-07."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    payload = _payload(texts=[_ENTRY_A, _PROSE], regions=["back_matter", "prose"])
    payload.narration_include = True

    run = _run(payload, model_answer=payload.target_text, classification="source_text_fallback", marker_mode=False)

    assert len(run.model_calls) == 1
    assert run.snapshot["back_matter_policy_kept_block_count"] == 0
    assert run.snapshot["untranslated_prose_block_delivery_count"] == 1
    assert [event for event, _ in run.events].count("block_untranslated_prose_delivered") == 1


def test_a_notes_block_goes_to_the_model_and_its_mix_is_not_a_finding(monkeypatch) -> None:
    """Notes translate their commentary and keep their references: a note that is a bare
    reference beside a translated comment is the policy working, not a mixed block."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    note_reference = "1. Ibid., p. 4."
    note_comment = "2. Smith argues the opposite."
    payload = _payload(texts=[note_reference, note_comment], roles=["list", "list"], section=BACK_MATTER_SECTION_NOTES)
    answer = MarkerPreservedBlockText(
        "\n\n".join([note_reference, "2. Смит утверждает обратное."]),
        (
            ParagraphDisposition("p0000", note_reference, PARAGRAPH_STATUS_ACCEPTED),
            ParagraphDisposition("p0001", "2. Смит утверждает обратное.", PARAGRAPH_STATUS_ACCEPTED),
        ),
    )

    run = _run(payload, model_answer=answer)

    assert len(run.model_calls) == 1
    assert run.snapshot["back_matter_source_paragraph_counts"] == {"notes": 1}
    assert run.snapshot["back_matter_translated_paragraph_counts"] == {"notes": 1}
    assert run.snapshot["back_matter_mixed_block_count"] == 0


def test_a_reference_list_block_whose_entries_came_out_mixed_needs_review(monkeypatch) -> None:
    """FR-012 / SC-005: the inconsistency the review found inside one book is counted and
    logged for review, never gated."""
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)
    texts = ["Bibliography", _ENTRY_A, _ENTRY_B]
    payload = _payload(texts=texts, roles=["heading", "body", "body"])
    translated_entry = "Акерлоф Дж., «Рынок лимонов», 1970."
    answer = MarkerPreservedBlockText(
        "\n\n".join(["Библиография", _ENTRY_A, translated_entry]),
        (
            ParagraphDisposition("p0000", "Библиография", PARAGRAPH_STATUS_ACCEPTED),
            ParagraphDisposition("p0001", _ENTRY_A, PARAGRAPH_STATUS_ACCEPTED),
            ParagraphDisposition("p0002", translated_entry, PARAGRAPH_STATUS_ACCEPTED),
        ),
    )

    run = _run(payload, model_answer=answer)

    assert len(run.model_calls) == 1  # the heading makes it a mixed block: it goes to the model
    assert run.outcome is None
    assert run.snapshot["back_matter_mixed_block_count"] == 1
    review = [context for event, context in run.events if event == "back_matter_policy_mixed_block"]
    assert len(review) == 1
    assert review[0]["needs_review"] is True
    assert review[0]["source_paragraph_ids"] == ["p0001"]
    assert review[0]["translated_paragraph_ids"] == ["p0002"]


# --- the per-block prompt ----------------------------------------------------------------------


def _capture_block_prompt(payload: SimpleNamespace, *, operation: str = "translate") -> str:
    captured: dict[str, object] = {}
    context = SimpleNamespace(
        processing_operation=operation,
        model_id="model",
        model="model",
        max_retries=1,
        runtime=None,
        document_segments=(),
    )
    block_execution._generate_block_chunk(
        context=context,
        dependencies=SimpleNamespace(
            generate_markdown_block=lambda **kwargs: captured.update(kwargs) or "ok",
            should_stop_processing=lambda _runtime: False,
        ),
        state=SimpleNamespace(completed_segment_ids=set(), segment_outputs={}),
        initialization=SimpleNamespace(text_client=None, client=object(), text_model_id="model", segment_ids_by_job=()),
        index=1,
        payload=payload,
        marker_mode_enabled=True,
        system_prompt="SYSTEM",
    )
    return str(captured["system_prompt"])


def test_a_notes_block_carries_the_d1_rule_in_its_prompt() -> None:
    prompt = _capture_block_prompt(_payload(section=BACK_MATTER_SECTION_NOTES))

    assert prompt.startswith("SYSTEM\n\n")
    assert block_execution._APPARATUS_PROMPT_HEADER in prompt
    assert "- Раздел: примечания" in prompt
    assert "- Абзацы: все абзацы блока" in prompt
    assert "Переводите только авторский комментарий." in prompt


def test_a_mixed_block_names_its_back_matter_paragraphs_by_marker() -> None:
    prompt = _capture_block_prompt(_payload(regions=["prose", "back_matter"], texts=[_PROSE, _ENTRY_A]))

    assert "- Раздел: список литературы" in prompt
    assert "- Абзацы: [[DOCX_PARA_p0001]]" in prompt
    assert "[[DOCX_PARA_p0000]]" not in prompt


@pytest.mark.parametrize(
    ("operation", "section"),
    [
        ("translate", BACK_MATTER_SECTION_INDEX),
        ("translate", None),
        ("edit", BACK_MATTER_SECTION_NOTES),
    ],
)
def test_no_rule_outside_the_sections_and_operation_d1_speaks_about(operation: str, section: str | None) -> None:
    prompt = _capture_block_prompt(_payload(section=section), operation=operation)
    assert block_execution._APPARATUS_PROMPT_HEADER not in prompt


def test_the_translate_prompt_points_at_the_block_section_by_its_exact_header() -> None:
    prompt = (_REPO_ROOT / "src" / "docxaicorrector" / "resources" / "prompts" / "operation_translate.txt").read_text(
        encoding="utf-8"
    )
    header = block_execution._APPARATUS_PROMPT_HEADER.rstrip(":")
    assert f"«{header}»" in prompt
    assert "записи библиографии и ссылки на источники оставляйте как есть" in prompt


# --- how the 059/061 invariants and the narration read the new status --------------------------


def _kept_chunk() -> MarkerPreservedBlockText:
    return MarkerPreservedBlockText(
        "\n\n".join([_ENTRY_A, _ENTRY_B]),
        (
            ParagraphDisposition("p0000", _ENTRY_A, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE),
            ParagraphDisposition("p0001", _ENTRY_B, PARAGRAPH_STATUS_POLICY_KEPT_SOURCE),
        ),
    )


def test_the_source_text_delivery_channel_does_not_count_a_policy_kept_entry() -> None:
    facts = quality_gate.build_source_text_delivery_facts([_kept_chunk()])
    assert facts["block_count"] == 0
    status_counts = cast(dict[str, int], facts["status_counts"])
    assert "policy_kept_source" not in status_counts
    assert sum(status_counts.values()) == 0


def test_the_standalone_narration_projection_neither_speaks_nor_books_it_as_a_loss() -> None:
    text, withheld = block_execution.narration_projection_for_processed_block(
        _kept_chunk(), processing_operation="translate"
    )
    assert text == ""
    assert withheld == []


def test_the_cleanup_narration_projection_skips_it_too() -> None:
    context = SimpleNamespace(processing_operation="translate", jobs=[{"narration_include": True}])
    registry = [
        {"block_index": 1, "paragraph_id": "p0000", "text": _ENTRY_A, "paragraph_status": PARAGRAPH_STATUS_POLICY_KEPT_SOURCE},
        {"block_index": 1, "paragraph_id": "p0001", "text": "Перевод.", "paragraph_status": PARAGRAPH_STATUS_ACCEPTED},
    ]
    projected = narration_postprocess._project_final_cleanup_narration_chunks(
        context=context, final_generated_paragraph_registry=registry
    )
    assert projected == ["Перевод."]


# --- replay over the recorded 2026-11-07 runs (opt-in evidence, not a CI test) -----------------
#
# Same opt-in as the P0 replay in ``test_document_pipeline_output_validation.py``: point
# ``DOCXAI_TRANSLATE_REPLAY_ROOT`` at the directory holding ``<book>/<report>.json``,
# ``<book>/pairs.jsonl`` and ``<book>/source_paragraphs.json``; without it, or with a book
# missing, the test skips. The run's own block boundaries are read off its registry (the
# reconstructed job count equals the run's on all four books), the PRODUCTION
# ``build_editing_jobs`` resolves regions and sections on them, and the PRODUCTION predicate
# decides which blocks the policy keeps.
_REPLAY_ROOT_ENV = "DOCXAI_TRANSLATE_REPLAY_ROOT"
_REPLAY_ROOT = os.environ.get(_REPLAY_ROOT_ENV, "").strip()
# (book, report, kept blocks = model calls saved, kept paragraphs) measured 2026-11-07.
_REPLAY_BOOKS = [
    ("money_sustainability", "money_sustainability_pdf_full_heldout_report.json", 7, 25),
    ("creating_wealth", "creatingwealth_pdf_full_benchmark_report.json", 0, 0),
    ("rethinking_money", "lietaer_pdf_full_benchmark_report.json", 5, 177),
    ("value_of_everything", "mazzucato_pdf_full_benchmark_report.json", 45, 307),
]


@pytest.mark.skipif(not _REPLAY_ROOT, reason=f"Set {_REPLAY_ROOT_ENV} to the recorded translate-run directory.")
@pytest.mark.parametrize(
    ("book", "report_name", "kept_blocks", "kept_paragraphs"),
    _REPLAY_BOOKS,
    ids=[book[0] for book in _REPLAY_BOOKS],
)
def test_apparatus_policy_replay_on_recorded_translate_runs(book, report_name, kept_blocks, kept_paragraphs) -> None:
    book_dir = Path(_REPLAY_ROOT) / book
    report_path = book_dir / report_name
    source_path = book_dir / "source_paragraphs.json"
    pairs_path = book_dir / "pairs.jsonl"
    if not report_path.is_file() or not source_path.is_file() or not pairs_path.is_file():
        pytest.skip(f"recorded run for {book} is absent under {book_dir}")

    with report_path.open(encoding="utf-8") as handle:
        state = json.load(handle)["runtime"]["state"]
    block_by_id = {entry["paragraph_id"]: entry["block_index"] for entry in state["processed_paragraph_registry"]}
    run_job_count = len(state["processed_block_markdowns"])
    del state
    with source_path.open(encoding="utf-8") as handle:
        records = json.load(handle)["paragraphs"]
    with pairs_path.open(encoding="utf-8") as handle:
        pair_by_id = {pair["paragraph_id"]: pair for pair in map(json.loads, handle)}

    blocks: list[DocumentBlock] = []
    current: object = object()
    for record in records:
        unit = ParagraphUnit(
            text=record["text"],
            role=record["role"],
            asset_id=record.get("asset_id"),
            heading_level=record.get("heading_level"),
            list_kind=record.get("list_kind"),
            paragraph_id=record["paragraph_id"],
            source_index=record["source_index"],
            structural_role=record.get("structural_role") or "body",
        )
        key = block_by_id.get(record["paragraph_id"])
        if key is None or key != current:
            blocks.append(DocumentBlock(paragraphs=[unit]))
            current = key if key is not None else object()
        else:
            blocks[-1].paragraphs.append(unit)

    jobs = semantic_blocks.build_editing_jobs(blocks, max_chars=6000, processing_operation="translate")
    assert len(jobs) == run_job_count  # the replay sees the run's own blocks

    kept_ids: list[str] = []
    kept_block_count = 0
    regions_of_kept: Counter[str] = Counter()
    roles_of_kept: Counter[str] = Counter()
    sections: Counter[str] = Counter()
    for job in jobs:
        payload = parse_processing_job(job=job, payload_factory=BlockExecutionPayload)
        if payload.back_matter_section:
            sections[payload.back_matter_section] += len(payload.paragraph_ids or ())
        if block_execution.reference_list_block_keeps_source(context=_TRANSLATE, payload=payload):
            kept_block_count += 1
            kept_ids.extend(payload.paragraph_ids or ())
            regions_of_kept.update(payload.paragraph_regions or ())
            roles_of_kept.update(payload.structural_roles or ())

    kept_pairs = [pair_by_id[paragraph_id] for paragraph_id in kept_ids if paragraph_id in pair_by_id]
    print(
        json.dumps(
            {
                "book": book,
                "back_matter_paragraphs_by_section": dict(sections),
                "kept_blocks_model_calls_saved": kept_block_count,
                "kept_paragraphs": len(kept_ids),
                "kept_pairs_delivered_changed_in_run": sum(
                    1 for pair in kept_pairs if (pair.get("target_text") or "").strip() != (pair["source_text"] or "").strip()
                ),
                "kept_pairs_controlled_fallback_in_run": sum(1 for pair in kept_pairs if pair.get("controlled_fallback")),
            },
            ensure_ascii=False,
        )
    )
    assert kept_block_count == kept_blocks
    assert len(kept_ids) == kept_paragraphs
    # Zero prose affected: nothing outside the back-matter region, and no heading, is kept.
    assert set(regions_of_kept) <= {"back_matter"}
    assert set(roles_of_kept) <= set(block_execution.REFERENCE_ENTRY_STRUCTURAL_ROLES)


def test_the_run_summary_prints_the_back_matter_policy_counters() -> None:
    """FR-012 reaches the run summary, where the 2026-11-07 review had to re-derive it."""
    import importlib.util

    harness_path = _REPO_ROOT / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    spec = importlib.util.spec_from_file_location("run_lietaer_validation_back_matter_probe", harness_path)
    assert spec is not None and spec.loader is not None
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    lines = harness._build_model_accounting_summary_lines(
        {
            "back_matter_policy_kept_block_count": 45,
            "back_matter_policy_kept_paragraph_count": 307,
            "back_matter_policy_kept_chars": 41000,
            "back_matter_mixed_block_count": 0,
            "back_matter_source_paragraph_counts": {"references": 310, "notes": 120},
            "back_matter_translated_paragraph_counts": {"notes": 567},
        }
    )

    assert "model_accounting_back_matter_policy_kept_block_count=45" in lines
    assert "model_accounting_back_matter_policy_kept_paragraph_count=307" in lines
    assert "model_accounting_back_matter_mixed_block_count=0" in lines
    assert 'model_accounting_back_matter_source_paragraph_counts={"notes": 120, "references": 310}' in lines
    assert 'model_accounting_back_matter_translated_paragraph_counts={"notes": 567}' in lines


# --- spec 064 FR-006: a reference the MODEL kept under rule 12 is apparatus, not a fallback ----
#
# On the 2026-11-07 rerun The Value of Everything filed 209 blocks / 312 paragraphs of its notes
# as controlled ``source_text_fallback``: the model kept citation-only notes and URLs as prompt
# rule 12 told it to, and the pair rule of spec 059 read the unchanged answer as a failure. The
# predicate is untouched (``delivered_text_equals_source`` stays the only comparison); what
# changes is the DISPOSITION of such a paragraph in a ``notes``/``references`` section.

_NOTE_URL = "3. https://www.ft.com/content/cc58c190-6ec3-11e6-a0c9-1365ce54b926"
_NOTE_REPORT = "2. Goldman Sachs Annual Report, 2010."
_NOTE_ARTICLE = (
    "7. W. Lazonick, M. Mazzucato and Ö. Tulum, ‘Apple’s changing business model: What should "
    "the world’s richest company do with its profits?’, *Accounting Forum* 37 (2103), pp. 249–67."
)
_NOTE_TORN_TITLE = "13. P. Steiner, ‘Wealth and power: Quesnay’s political economy of the"
_NOTE_TORN_TAIL = "*Private Sector Myths* (London: Anthem Press, 2013)."
_NOTE_COMMENTARY = (
    "6. GDP (Gross domestic product) superseded GNP as the standard measure of output in the "
    "1980s. The difference is not relevant to value creation."
)


@pytest.mark.parametrize(
    "text",
    [
        _NOTE_URL,
        _NOTE_REPORT,
        _NOTE_ARTICLE,
        _NOTE_TORN_TITLE,
        _NOTE_TORN_TAIL,
        "### *Economy: What Should Change?* (Washington DC: Bureau of",
        "1. R. Sahay, M. Cihak, P. N\u2019Diaye, A. Barajas, R. Bi, D. Ayala, Y. Gao,",
        "3. Studenski, *Income of Nations*, p. 127.",
        "16. C. A. E. Goodhart, ‘Competition and credit control’, Financial Markets",
        "title=Economia+non+osservata+-+04%2Fdic%2F2015+- +Testo+integrale+con+nota+metodologica.pdf",
    ],
)
def test_a_reference_reads_as_a_citation_by_its_form(text: str) -> None:
    from docxaicorrector.pipeline.output_validation import is_citation_form_paragraph

    assert is_citation_form_paragraph(text) is True


@pytest.mark.parametrize(
    "text",
    [
        _NOTE_COMMENTARY,
        "2. See Figure 1 in Chapter 7 for details.",
        "11. There was only one test so far.",
        # A quotation is commentary however it is enclosed: a span longer than a title is not
        # taken out, so its running words count.
        "25. The full quote is: ‘The labour of some of the most respectable orders in the society "
        "is, like that of menial servants, unproductive of any value, and does not fix or realize "
        "itself in any permanent subject, or vendible commodity, which endures after that labour is past.’",
        # Codex acceptance review 2026-11-07, finding 1: few running words is not a reference.
        "See Figure 1 for details.",
        "(This argument assumes that all prices remain constant over time.)",
        "\u201cCan you be more precise?\u201d",
        "\u8fd9\u4e00\u8bba\u70b9\u5047\u8bbe\u6240\u6709\u4ef7\u683c\u968f\u65f6\u95f4\u4fdd\u6301\u4e0d\u53d8\u3002",
        "Notes",
        # No positive mark of a reference at all: such a line stays on the diagnostic path.
        "15. Ibid.",
        "1489.",
        # The R-7 note of Creating Wealth: commentary that happens to name works and years.
        "Maynard Keynes — Knapp and Chartalism are cited approvingly in its opening pages. "
        "Chartalism experienced a revival under Abba P. Lerner in *The* *Economics of Control* (1944) "
        "and later in *The Economics of Employment* (1951).",
    ],
)
def test_anti_vacuum_commentary_does_not_read_as_a_citation(text: str) -> None:
    from docxaicorrector.pipeline.output_validation import is_citation_form_paragraph

    assert is_citation_form_paragraph(text) is False


def _echo(payload: SimpleNamespace, statuses: list[str] | None = None) -> MarkerPreservedBlockText:
    texts = payload.target_text.split("\n\n")
    resolved = statuses or [PARAGRAPH_STATUS_ACCEPTED] * len(texts)
    return MarkerPreservedBlockText(
        payload.target_text,
        tuple(
            ParagraphDisposition(pid, text, status)
            for pid, text, status in zip(payload.paragraph_ids, texts, resolved)
        ),
    )


def _fallback_artifacts(monkeypatch) -> list[dict[str, object]]:
    written: list[dict[str, object]] = []
    monkeypatch.setattr(
        block_execution, "_write_controlled_block_fallback_artifact", lambda **kwargs: written.append(kwargs)
    )
    return written


def _statuses(chunk: str) -> list[str]:
    return [disposition.status for disposition in block_execution.marker_paragraph_dispositions(chunk) or ()]


def test_a_notes_block_the_model_kept_whole_is_policy_kept_not_a_fallback(monkeypatch) -> None:
    written = _fallback_artifacts(monkeypatch)
    payload = _payload(texts=[_NOTE_REPORT, _NOTE_URL], roles=["list", "body"], section=BACK_MATTER_SECTION_NOTES)

    run = _run(payload, model_answer=_echo(payload), classification="source_text_fallback")

    assert run.outcome is None
    assert len(run.model_calls) == 1  # unlike FR-011 the model WAS asked: notes carry commentary
    assert written == []
    assert run.state.processed_chunks == [payload.target_text]
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [
        PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
    ] * 2
    assert not any(entry.get("controlled_fallback") for entry in run.state.generated_paragraph_registry)
    events = [event for event, _ in run.events]
    assert events.count("block_controlled_fallback") == 0
    assert events.count("block_apparatus_kept_by_model") == 1
    assert run.snapshot["controlled_block_fallback_block_count"] == 0
    assert run.snapshot["untranslated_prose_block_delivery_count"] == 0
    assert run.snapshot["back_matter_model_kept_paragraph_count"] == 2
    assert run.snapshot["back_matter_model_kept_fallback_block_count"] == 1
    # "Kept without a call" is a different family and stays untouched.
    assert run.snapshot["back_matter_policy_kept_block_count"] == 0
    assert run.snapshot["back_matter_source_paragraph_counts"] == {"notes": 2}


def test_anti_vacuum_an_unchanged_commentary_note_keeps_the_block_a_fallback(monkeypatch) -> None:
    written = _fallback_artifacts(monkeypatch)
    payload = _payload(
        texts=[_NOTE_REPORT, _NOTE_COMMENTARY], roles=["list", "list"], section=BACK_MATTER_SECTION_NOTES
    )

    run = _run(payload, model_answer=_echo(payload), classification="source_text_fallback")

    assert len(written) == 1
    assert run.snapshot["controlled_block_fallback_block_count"] == 1
    assert run.snapshot["back_matter_model_kept_paragraph_count"] == 0
    assert run.snapshot["back_matter_model_kept_fallback_block_count"] == 0
    assert [event for event, _ in run.events].count("block_controlled_fallback") == 1
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [
        PARAGRAPH_STATUS_ACCEPTED
    ] * 2


def test_a_translated_note_beside_a_kept_reference_relabels_only_the_reference(monkeypatch) -> None:
    written = _fallback_artifacts(monkeypatch)
    payload = _payload(
        texts=[_NOTE_COMMENTARY, _NOTE_ARTICLE], roles=["list", "list"], section=BACK_MATTER_SECTION_NOTES
    )
    translated = "6. ВВП пришёл на смену ВНП."
    answer = MarkerPreservedBlockText(
        "\n\n".join([translated, _NOTE_ARTICLE]),
        (
            ParagraphDisposition("p0000", translated, PARAGRAPH_STATUS_ACCEPTED),
            ParagraphDisposition("p0001", _NOTE_ARTICLE, PARAGRAPH_STATUS_ACCEPTED),
        ),
    )

    run = _run(payload, model_answer=answer)

    assert written == []
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [
        PARAGRAPH_STATUS_ACCEPTED,
        PARAGRAPH_STATUS_POLICY_KEPT_SOURCE,
    ]
    assert run.state.processed_chunks == [answer]
    assert run.snapshot["back_matter_model_kept_paragraph_count"] == 1
    assert run.snapshot["back_matter_model_kept_fallback_block_count"] == 0
    assert run.snapshot["back_matter_translated_paragraph_counts"] == {"notes": 1}


def test_an_omitted_reference_keeps_its_own_status() -> None:
    """``omitted`` is the generator's word for a loss; FR-006 relabels only what it ACCEPTED."""
    payload = _payload(texts=[_NOTE_REPORT, _NOTE_URL], roles=["list", "body"], section=BACK_MATTER_SECTION_NOTES)
    answer = _echo(payload, [PARAGRAPH_STATUS_ACCEPTED, "omitted"])

    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=answer)

    assert kept is not None
    assert kept.whole_block is False
    assert _statuses(kept.processed_chunk) == [PARAGRAPH_STATUS_POLICY_KEPT_SOURCE, "omitted"]
    assert kept.processed_chunk == answer  # the text is the model's, to the character


@pytest.mark.parametrize(
    ("override", "operation"),
    [
        pytest.param({"section": BACK_MATTER_SECTION_INDEX}, "translate", id="the-index-is-translated"),
        pytest.param({"section": None}, "translate", id="outside-the-back-matter"),
        pytest.param({"toc_dominant": True}, "translate", id="toc-routed"),
        pytest.param({"job_kind": "passthrough"}, "translate", id="passthrough"),
        pytest.param({}, "edit", id="not-a-translation"),
        pytest.param({}, "audiobook", id="audiobook-is-not-D1"),
    ],
)
def test_outside_notes_and_references_of_a_translation_nothing_is_relabelled(
    override: dict[str, Any], operation: str
) -> None:
    arguments: dict[str, Any] = {"section": BACK_MATTER_SECTION_NOTES, **override}
    payload = _payload(texts=[_NOTE_REPORT, _NOTE_URL], roles=["list", "body"], **arguments)
    context = SimpleNamespace(processing_operation=operation)

    assert block_execution.model_kept_apparatus(context=context, payload=payload, processed_chunk=_echo(payload)) is None


def test_a_prose_region_paragraph_is_never_relabelled() -> None:
    payload = _payload(
        texts=[_NOTE_REPORT, _NOTE_URL],
        roles=["list", "body"],
        regions=["back_matter", "prose"],
        section=BACK_MATTER_SECTION_NOTES,
    )

    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_echo(payload))

    assert kept is not None and kept.whole_block is False
    assert _statuses(kept.processed_chunk) == [PARAGRAPH_STATUS_POLICY_KEPT_SOURCE, PARAGRAPH_STATUS_ACCEPTED]


def test_anti_vacuum_a_prose_region_echo_still_announces_untranslated_prose(monkeypatch) -> None:
    """The 059 invariant is out of reach: a notes block carrying a PROSE-region paragraph that
    comes back unchanged stays a fallback and is announced, whatever its other paragraphs are."""
    _fallback_artifacts(monkeypatch)
    payload = _payload(
        texts=[_NOTE_REPORT, _NOTE_URL],
        roles=["list", "body"],
        regions=["back_matter", "prose"],
        section=BACK_MATTER_SECTION_NOTES,
    )
    payload.narration_include = True

    run = _run(payload, model_answer=_echo(payload), classification="source_text_fallback")

    assert run.snapshot["controlled_block_fallback_block_count"] == 1
    assert run.snapshot["untranslated_prose_block_delivery_count"] == 1
    assert run.snapshot["back_matter_model_kept_fallback_block_count"] == 0


@pytest.mark.parametrize("narration_include", [False, True])
def test_without_markers_the_decision_is_per_block(monkeypatch, narration_include: bool) -> None:
    """No per-paragraph record, no status to carry: the whole block qualifies or nothing does,
    and only where the document layer already keeps it out of the narration."""
    written = _fallback_artifacts(monkeypatch)
    payload = _payload(texts=[_NOTE_REPORT, _NOTE_URL], roles=["list", "body"], section=BACK_MATTER_SECTION_NOTES)
    payload.narration_include = narration_include

    run = _run(payload, model_answer=payload.target_text, classification="source_text_fallback", marker_mode=False)

    expected_fallbacks = 1 if narration_include else 0
    assert len(written) == expected_fallbacks
    assert run.snapshot["controlled_block_fallback_block_count"] == expected_fallbacks
    assert run.snapshot["back_matter_model_kept_fallback_block_count"] == 1 - expected_fallbacks
    assert run.state.narration_chunks == []


def test_a_model_kept_reference_is_neither_narrated_nor_a_loss_in_either_channel() -> None:
    payload = _payload(texts=[_NOTE_REPORT, _NOTE_URL], roles=["list", "body"], section=BACK_MATTER_SECTION_NOTES)
    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_echo(payload))
    assert kept is not None

    text, withheld = block_execution.narration_projection_for_processed_block(
        kept.processed_chunk, processing_operation="translate"
    )
    assert (text, withheld) == ("", [])
    facts = quality_gate.build_source_text_delivery_facts([kept.processed_chunk])
    assert facts["block_count"] == 0


def test_the_run_summary_prints_the_model_kept_counters() -> None:
    import importlib.util

    harness_path = _REPO_ROOT / "tests" / "artifacts" / "real_document_pipeline" / "run_lietaer_validation.py"
    spec = importlib.util.spec_from_file_location("run_lietaer_validation_model_kept_probe", harness_path)
    assert spec is not None and spec.loader is not None
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    lines = harness._build_model_accounting_summary_lines(
        {"back_matter_model_kept_paragraph_count": 414, "back_matter_model_kept_fallback_block_count": 209}
    )

    assert "model_accounting_back_matter_model_kept_paragraph_count=414" in lines
    assert "model_accounting_back_matter_model_kept_fallback_block_count=209" in lines


# --- Codex acceptance review 2026-11-07, findings 1 and 3: counter-proofs through the block ---


@pytest.mark.parametrize(
    ("text", "role"),
    [
        pytest.param("See Figure 1 for details.", "body", id="a-short-sentence"),
        pytest.param("(This argument assumes that all prices remain constant over time.)", "body", id="a-whole-parenthetical"),
        pytest.param("“Can you be more precise?”", "body", id="a-quoted-dialogue-line"),
        pytest.param(
            "这一论点假设所有价格随时间保持不变。",
            "body",
            id="a-cjk-paragraph",
        ),
        pytest.param("Notes", "heading", id="a-heading-echo"),
        # Even a heading that LOOKS like a reference: D1 translates the apparatus headings.
        pytest.param("### *Economy: What Should Change?* (Washington DC: Bureau of", "heading", id="a-reference-shaped-heading"),
    ],
)
def test_an_echoed_non_reference_stays_a_controlled_fallback(monkeypatch, text: str, role: str) -> None:
    written = _fallback_artifacts(monkeypatch)
    payload = _payload(texts=[text], roles=[role], section=BACK_MATTER_SECTION_NOTES)

    run = _run(payload, model_answer=_echo(payload), classification="source_text_fallback")

    assert len(written) == 1
    assert run.snapshot["controlled_block_fallback_block_count"] == 1
    assert run.snapshot["back_matter_model_kept_paragraph_count"] == 0
    assert run.snapshot["back_matter_model_kept_fallback_block_count"] == 0
    assert [entry["paragraph_status"] for entry in run.state.generated_paragraph_registry] == [PARAGRAPH_STATUS_ACCEPTED]
    assert [event for event, _ in run.events].count("block_apparatus_kept_by_model") == 0


def test_a_torn_reference_is_relabelled_whole_or_not_at_all() -> None:
    """Finding 3: assembly welds the two halves of a torn entry back together, but never halves
    of different narration admissibility. A translated head with an echoed tail therefore keeps
    the tail ``accepted`` -- the CW p1623/p1624 case -- and an echoed pair is relabelled together."""
    head = "Complementary Currency.” Paper presented for publication in the *International Journal for Community Currency*"
    tail = "Vol. 10 (2006). [online]. [cited November 2, 2010]. www.uea.ac.uk/env/ijccr/abstracts/vol10(3)lietaer.html."
    payload = _payload(texts=[head, tail], roles=["body", "body"], section=BACK_MATTER_SECTION_NOTES)
    translated_head = "Complementary Currency.” Статья, представленная в *International Journal for Community Currency*"
    answer = MarkerPreservedBlockText(
        "\n\n".join([translated_head, tail]),
        (
            ParagraphDisposition("p0000", translated_head, PARAGRAPH_STATUS_ACCEPTED),
            ParagraphDisposition("p0001", tail, PARAGRAPH_STATUS_ACCEPTED),
        ),
    )

    assert block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=answer) is None

    kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=_echo(payload))
    assert kept is not None and kept.whole_block is True
    assert _statuses(kept.processed_chunk) == [PARAGRAPH_STATUS_POLICY_KEPT_SOURCE] * 2


# Opt-in replay over the 2026-11-07 RERUN on the spec 063 code (``aca048a``) -- a different set
# of recorded runs from the one above, hence its own variable: point
# ``DOCXAI_TRANSLATE_RERUN_REPLAY_ROOT`` at ``D:\Temp\docxai-runs\2026-11-07-translate-after``.
# Every back-matter block the model answered is re-classified by the PRODUCTION pair rule and
# re-decided by the PRODUCTION ``model_kept_apparatus``. (book, report, controlled fallbacks
# recorded, controlled fallbacks after FR-006, paragraphs relabelled) measured 2026-11-07.
_RERUN_REPLAY_ROOT_ENV = "DOCXAI_TRANSLATE_RERUN_REPLAY_ROOT"
_RERUN_REPLAY_ROOT = os.environ.get(_RERUN_REPLAY_ROOT_ENV, "").strip()
_FR006_REPLAY_BOOKS = [
    ("value_of_everything", "mazzucato_pdf_full_benchmark_report.json", 209, 15, 331),
    ("rethinking_money", "lietaer_pdf_full_benchmark_report.json", 0, 0, 78),
    ("creating_wealth", "creatingwealth_pdf_full_benchmark_report.json", 0, 0, 110),
    ("money_sustainability", "money_sustainability_pdf_full_heldout_report.json", 0, 0, 1),
]


@pytest.mark.skipif(
    not _RERUN_REPLAY_ROOT, reason=f"Set {_RERUN_REPLAY_ROOT_ENV} to the recorded translate-rerun directory."
)
@pytest.mark.parametrize(
    ("book", "report_name", "recorded_fallbacks", "fallbacks_after", "relabelled"),
    _FR006_REPLAY_BOOKS,
    ids=[book[0] for book in _FR006_REPLAY_BOOKS],
)
def test_fr006_replay_on_recorded_translate_runs(book, report_name, recorded_fallbacks, fallbacks_after, relabelled) -> None:
    """Replayed through ASSEMBLY, not only through the status counts (Codex review finding 3):
    the final markdown and the final registry with FR-006 applied must equal the ones without it,
    and the replay without it must reproduce the run's own recorded final registry."""
    from collections import Counter as _Counter

    from docxaicorrector.document.semantic_blocks import build_marker_wrapped_block_text
    from docxaicorrector.pipeline import output_validation as ov
    from docxaicorrector.pipeline.reader_cleanup_rebuild import _resolve_final_generated_paragraph_registry

    book_dir = Path(_RERUN_REPLAY_ROOT) / book
    report_path = book_dir / report_name
    source_path = book_dir / "source_paragraphs.json"
    if not report_path.is_file() or not source_path.is_file():
        pytest.skip(f"recorded run for {book} is absent under {book_dir}")
    with report_path.open(encoding="utf-8") as handle:
        state = json.load(handle)["runtime"]["state"]
    registry = state["processed_paragraph_registry"]
    chunks = state["processed_block_markdowns"]
    recorded_final = state.get("final_generated_paragraph_registry")
    del state
    if recorded_final is None:  # a blocked run: the runner's own replay of its final registry
        replayed_path = book_dir / "final_registry_replayed.json"
        if not replayed_path.is_file():
            pytest.skip(f"{book}: blocked run without final_registry_replayed.json")
        with replayed_path.open(encoding="utf-8") as handle:
            recorded_final = json.load(handle)["final_generated_paragraph_registry"]
    with source_path.open(encoding="utf-8") as handle:
        source = json.load(handle)

    def unit(record: dict[str, Any]) -> ParagraphUnit:
        return ParagraphUnit(
            text=record["text"],
            role=record["role"],
            paragraph_id=record["paragraph_id"],
            heading_level=record.get("heading_level"),
            list_kind=record.get("list_kind"),
            structural_role=record.get("structural_role") or "body",
            source_index=int(record["source_index"]),
            asset_id=record.get("asset_id"),
        )

    record_by_id = {record["paragraph_id"]: record for record in source["paragraphs"]}
    source_units = [unit(record) for record in source["paragraphs"]]
    job_by_ids = {tuple(job["paragraph_ids"]): job for job in source["jobs"] if job["job_kind"] == "llm"}
    entries_by_block: dict[int, list[dict[str, Any]]] = {}
    for entry in registry:
        entries_by_block.setdefault(entry["block_index"], []).append(entry)

    recorded, after = 0, 0
    relabel_ids: set[str] = set()
    converted_blocks: set[int] = set()
    for block_index, entries in entries_by_block.items():
        ids = tuple(entry["paragraph_id"] for entry in entries)
        job = job_by_ids.get(ids)
        if job is None or not job.get("back_matter_section"):
            continue
        if all(entry.get("paragraph_status") == PARAGRAPH_STATUS_POLICY_KEPT_SOURCE for entry in entries):
            continue  # FR-011: kept without a model call, never classified
        units = [unit(record_by_id[pid]) for pid in ids]
        payload = SimpleNamespace(
            job_kind="llm",
            toc_dominant=False,
            target_text="\n\n".join(item.rendered_text for item in units).strip(),
            target_text_with_markers=build_marker_wrapped_block_text(units, paragraph_ids=list(ids)),
            paragraph_ids=list(ids),
            paragraph_regions=list(job["paragraph_regions"]),
            structural_roles=[item.structural_role for item in units],
            back_matter_section=job["back_matter_section"],
            narration_include=False,
        )
        dispositions = tuple(
            ParagraphDisposition(
                entry["paragraph_id"], entry["text"], entry.get("paragraph_status") or PARAGRAPH_STATUS_ACCEPTED
            )
            for entry in entries
        )
        chunk = MarkerPreservedBlockText("\n\n".join(d.text for d in dispositions), dispositions)
        recorded += int(any(entry.get("controlled_fallback") for entry in entries))
        status = ov.classify_processed_block(payload.target_text, chunk, languages_differ=True)
        if status not in {"valid", "source_text_fallback"}:
            after += 1
            continue
        kept = block_execution.model_kept_apparatus(context=_TRANSLATE, payload=payload, processed_chunk=chunk)
        if status == "source_text_fallback" and (kept is None or not kept.whole_block):
            after += 1
            continue
        if kept is None:
            continue
        if status == "source_text_fallback":
            converted_blocks.add(block_index)
        for old, new in zip(dispositions, block_execution.marker_paragraph_dispositions(kept.processed_chunk) or ()):
            if old.status != new.status:
                relabel_ids.add(new.paragraph_id)

    after_registry = [dict(entry) for entry in registry]
    for entry in after_registry:
        if entry["paragraph_id"] in relabel_ids:
            entry["paragraph_status"] = PARAGRAPH_STATUS_POLICY_KEPT_SOURCE
        if entry["block_index"] in converted_blocks:
            for key in ("controlled_fallback", "controlled_fallback_kind", "controlled_fallback_narration_excluded"):
                entry.pop(key, None)

    def assemble(paragraph_registry: list[dict[str, Any]]) -> tuple[str, list[tuple[object, ...]]]:
        result = ov.assemble_final_markdown(
            processed_chunks=chunks, generated_paragraph_registry=paragraph_registry, source_paragraphs=source_units
        )
        final = _resolve_final_generated_paragraph_registry(
            markdown_text=result.final_markdown,
            generated_paragraph_registry=ov.build_generated_paragraph_registry_from_entries(result.entries),
        )
        return result.final_markdown, [
            (entry.get("paragraph_id"), entry.get("text"), tuple(cast(list[str], entry.get("merged_paragraph_ids") or [])))
            for entry in (final or [])
        ]

    base_markdown, base_final = assemble(registry)
    after_markdown, after_final = assemble(after_registry)
    print(json.dumps({"book": book, "recorded_fallbacks": recorded, "after": after, "relabelled": len(relabel_ids)}))

    assert (recorded, after, len(relabel_ids)) == (recorded_fallbacks, fallbacks_after, relabelled)
    # The replay IS the run: without FR-006 it reproduces the recorded final registry.
    assert [text for _, text, _ in base_final] == [entry.get("text") for entry in recorded_final]
    # FR-006 changes statuses, never the delivered artifact: same markdown, same paragraphs,
    # same merges, and the 061 invariants (numbers, footnote markers) hold trivially on it.
    assert after_markdown == base_markdown
    assert after_final == base_final
    assert _Counter(re.findall(r"\d+", after_markdown)) == _Counter(re.findall(r"\d+", base_markdown))
