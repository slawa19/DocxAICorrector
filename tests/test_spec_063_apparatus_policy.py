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
