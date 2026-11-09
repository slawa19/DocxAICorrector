"""Spec 070 WP-G: the audiobook block, end to end through the ordinary block entry point.

Every test drives ``block_execution.process_single_block`` with the REAL execution path
(``execute_processing_block`` -> ``_generate_block_chunk`` -> plan/merge -> finalize), a
double for the block generator (it records what the model was sent) and a double for the SDK
client the one repair call goes through (``pipeline.audiobook_repair`` -> the real
``request_text_completion``), so "one call" is counted where the money is spent.

All texts are invented, of the same FORM as book text; no book of the corpus is quoted
(Constitution VII).
"""

from __future__ import annotations

import logging
import re
from functools import partial
from types import SimpleNamespace
from typing import Any, Callable

import pytest

import docxaicorrector.pipeline.block_execution as block_execution
from docxaicorrector.core import model_accounting
from docxaicorrector.generation._generation import (
    MarkerPreservedBlockText,
    ParagraphDisposition,
    marker_paragraph_dispositions,
)
from docxaicorrector.pipeline import audiobook_repair
from docxaicorrector.pipeline.audiobook_pass import (
    NarrationParagraphRecord,
    audiobook_narration_summary,
)
from docxaicorrector.pipeline.contracts import BlockExecutionPayload, ProcessingInitialization, ProcessingState
from docxaicorrector.pipeline.job_parsing import is_marker_mode_enabled
from docxaicorrector.pipeline.narration_postprocess import _build_narration_text, assemble_narration_records
from docxaicorrector.pipeline.output_validation import classify_processed_block
from docxaicorrector.pipeline.support import resolve_system_prompt
from docxaicorrector.text.narration_coverage import CoverageResult

# --------------------------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------------------------

_MARKER = re.compile(r"\[\[DOCX_PARA_([A-Za-z0-9_]+)\]\]")


def _payload(*paragraphs: tuple[str, str, str, str | None], job_kind: str | None = None) -> BlockExecutionPayload:
    """``(paragraph_id, text, structural_role, exclusion_reason)`` per paragraph."""

    ids = [item[0] for item in paragraphs]
    texts = [item[1] for item in paragraphs]
    reasons = [item[3] for item in paragraphs]
    narrated = any(reason is None for reason in reasons)
    return BlockExecutionPayload(
        job_kind=job_kind or ("llm" if narrated else "passthrough"),
        target_chars=sum(len(text) for text in texts),
        context_chars=0,
        target_text="\n\n".join(texts),
        target_text_with_markers="\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(ids, texts)),
        paragraph_ids=ids,
        context_before="",
        context_after="",
        structural_roles=[item[2] for item in paragraphs],
        paragraph_regions=["prose"] * len(paragraphs),
        narration_include=narrated,
        paragraph_count=len(paragraphs),
        narration_exclusion_reasons=reasons,
    )


class _Generator:
    """The block generator double: answers each SENT id by a rule and records every call."""

    def __init__(self, answer: Callable[[str, str], tuple[str, str]]) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        if kwargs.get("expected_paragraph_ids") is None:
            return kwargs["target_text"]  # no markers: the plain text back
        ids = list(kwargs["expected_paragraph_ids"])
        sources = dict(_split_marked(kwargs["target_text"]))
        dispositions = [
            ParagraphDisposition(paragraph_id=pid, text=text, status=status)
            for pid in ids
            for text, status in [self.answer(pid, sources[pid])]
        ]
        return MarkerPreservedBlockText("\n\n".join(item.text for item in dispositions), dispositions)


def _split_marked(text: str) -> list[tuple[str, str]]:
    matches = list(_MARKER.finditer(text))
    return [
        (match.group(1), text[match.end() : matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip())
        for i, match in enumerate(matches)
    ]


class _RepairClient:
    """The SDK double the repair goes through; ``answer`` builds the answer from the request."""

    def __init__(self, answer: Callable[[list[tuple[str, str]]], str] | Exception | None = None) -> None:
        self.answer = answer
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        target = self.target_paragraphs(kwargs)
        text = self.answer(target) if callable(self.answer) else ""
        return SimpleNamespace(
            status="completed",
            output_text=text,
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, cost=0.001),
        )

    @staticmethod
    def user_prompt(request: dict[str, Any]) -> str:
        return str(request["input"][-1]["content"][0]["text"])

    @staticmethod
    def system_prompt(request: dict[str, Any]) -> str:
        return str(request["input"][0]["content"][0]["text"])

    def target_paragraphs(self, request: dict[str, Any]) -> list[tuple[str, str]]:
        prompt = self.user_prompt(request)
        target = prompt.split("[TARGET BLOCK WITH MARKERS]", 1)[1].split("[CONTEXT AFTER]", 1)[0]
        return _split_marked(target)


def _words_for_digits(paragraphs: list[tuple[str, str]]) -> str:
    """A well-formed repair answer: every number written out, nothing else changed."""

    return "\n\n".join(
        f"[[DOCX_PARA_{pid}]]\n{re.sub(r'[0-9]+', 'сколько-то', text)}" for pid, text in paragraphs
    )


def _swapped(paragraphs: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"[[DOCX_PARA_{pid}]]\nтекст" for pid, _ in reversed(paragraphs))


def _no_op(**_kwargs: Any) -> None:
    return None


def _unexpected(**kwargs: Any) -> None:
    raise AssertionError(f"unexpected failure path: {kwargs.get('exc') or kwargs.get('rejection_kind')}")


def _run(
    payload: BlockExecutionPayload,
    *,
    generator: _Generator,
    repair_client: _RepairClient | None = None,
    operation: str = "audiobook",
    classification: str | None = None,
    stop: bool = False,
    load_system_prompt: Any = "fixture",
    state: ProcessingState | None = None,
    index: int = 1,
    app_config: dict[str, Any] | None = None,
) -> SimpleNamespace:
    state = state if state is not None else ProcessingState()
    events: list[tuple[int, str, dict[str, Any]]] = []
    client = repair_client if repair_client is not None else _RepairClient()
    dependencies = SimpleNamespace(
        generate_markdown_block=generator,
        log_event=lambda level, event, _message, **context: events.append((level, event, context)),
        should_stop_processing=lambda _runtime: stop,
    )
    if load_system_prompt == "fixture":
        dependencies.load_system_prompt = lambda **kwargs: f"FIXTURE PROMPT {kwargs.get('prompt_variant', 'default')}"
    elif load_system_prompt is not None:
        dependencies.load_system_prompt = load_system_prompt
    emitters = SimpleNamespace(emit_status=_no_op_runtime, emit_state=_no_op_runtime, emit_log=_no_op_runtime)
    context = SimpleNamespace(
        processing_operation=operation,
        model="fixture-model",
        model_id="fixture-model",
        model_selector="fixture-model",
        canonical_model_selector="fixture-model",
        model_provider="openai",
        max_retries=1,
        runtime=object(),
        uploaded_filename="book.docx",
        on_progress=lambda **_kwargs: None,
        app_config=app_config or {},
        source_language=None if operation == "audiobook" else "ru",
        target_language=None if operation == "audiobook" else "ru",
        document_segments=(),
        run_id="run-070",
    )
    initialization = ProcessingInitialization(client=client, job_count=1, text_client=client, text_model_id="fixture-model")

    def classify(target_text: str, processed_chunk: str, **kwargs: Any) -> str:
        if classification is not None:
            return classification
        return classify_processed_block(target_text, processed_chunk, **kwargs)

    with model_accounting.run_model_accounting_scope(run_id="run-070"):
        outcome = block_execution.process_single_block(
            context=context,
            dependencies=dependencies,
            emitters=emitters,
            state=state,
            initialization=initialization,
            index=index,
            job=object(),
            parse_processing_job_fn=lambda *, job: payload,
            handle_invalid_processing_job_fn=_unexpected,
            emit_block_started_fn=_no_op,
            is_marker_mode_enabled_fn=is_marker_mode_enabled,
            execute_processing_block_fn=partial(
                block_execution.execute_processing_block,
                is_marker_mode_enabled_fn=is_marker_mode_enabled,
                resolve_system_prompt_fn=resolve_system_prompt,
            ),
            handle_block_generation_failure_fn=_unexpected,
            classify_processed_block_fn=classify,
            handle_processed_block_rejection_fn=_unexpected,
            append_marker_registry_entries_fn=partial(
                block_execution.append_marker_registry_entries,
                build_processed_paragraph_registry_entries_fn=block_execution.build_processed_paragraph_registry_entries,
            ),
            handle_marker_registry_failure_fn=_unexpected,
            emit_block_completed_fn=_no_op,
        )
        accounting = dict(model_accounting.snapshot_run_model_accounting())
    return SimpleNamespace(outcome=outcome, state=state, events=events, client=client, accounting=accounting)


def _no_op_runtime(_runtime: object, **_kwargs: Any) -> None:
    return None


def _records(state: ProcessingState) -> dict[str, NarrationParagraphRecord]:
    return {record.paragraph_id: record for record in state.narration_paragraphs}


def _delivered(state: ProcessingState) -> dict[str, ParagraphDisposition]:
    dispositions = marker_paragraph_dispositions(state.processed_chunks[-1])
    assert dispositions is not None, "the delivered block lost its per-paragraph record"
    return {item.paragraph_id: item for item in dispositions}


def _events(run: SimpleNamespace, event_id: str) -> list[dict[str, Any]]:
    return [context for _level, event, context in run.events if event == event_id]


def _accepted(_pid: str, source: str) -> tuple[str, str]:
    return f"Озвучено: {source}", "accepted"


@pytest.fixture(autouse=True)
def _no_fallback_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(block_execution, "_write_controlled_block_fallback_artifact", lambda **_kwargs: None)


_PROSE_A = "Первый абзац рассказывает о старой гавани и её жителях."
_PROSE_B = "Третий абзац продолжает рассказ о долгой зиме в посёлке."
_TOC_LINE = "Глава первая ........ 5"


# --------------------------------------------------------------------------------------------
# T-G2: only the narrated subset reaches the model; the excluded paragraphs stay in the DOCX
# --------------------------------------------------------------------------------------------


def test_the_model_is_sent_only_the_narrated_paragraphs_of_a_mixed_block() -> None:
    payload = _payload(("p1", _PROSE_A, "body", None), ("p2", _TOC_LINE, "toc_entry", "toc"), ("p3", _PROSE_B, "body", None))
    generator = _Generator(_accepted)

    run = _run(payload, generator=generator)

    assert run.outcome is None
    assert len(generator.calls) == 1
    sent = generator.calls[0]
    assert sent["expected_paragraph_ids"] == ["p1", "p3"]
    assert [pid for pid, _ in _split_marked(sent["target_text"])] == ["p1", "p3"]
    # The excluded text never reaches the request at all.
    assert _TOC_LINE not in sent["target_text"]
    # The DOCX keeps it as its own source, kept by policy -- not a loss.
    delivered = _delivered(run.state)
    assert list(delivered) == ["p1", "p2", "p3"]
    assert delivered["p2"].text == _TOC_LINE
    assert delivered["p2"].status == "policy_kept_source"
    registry = {entry["paragraph_id"]: entry for entry in run.state.generated_paragraph_registry}
    assert registry["p2"]["paragraph_status"] == "policy_kept_source"
    # The exclusion is recorded with its reason and address, before the answer.
    assert [(e["paragraph_id"], e["block_index"], e["reason"]) for e in run.state.narration_exclusions] == [("p2", 1, "toc")]
    assert run.state.narration_expected_paragraph_ids == ["p1", "p3"]
    # Only the narrated ids have a narration record.
    assert [record.paragraph_id for record in run.state.narration_paragraphs] == ["p1", "p3"]


def test_a_block_with_nothing_excluded_is_sent_whole() -> None:
    """Anti-vacuum: the subset rule subtracts only what the document layer excluded."""

    payload = _payload(("p1", _PROSE_A, "body", None), ("p2", _PROSE_B, "body", None))
    generator = _Generator(_accepted)

    run = _run(payload, generator=generator)

    assert generator.calls[0]["expected_paragraph_ids"] == ["p1", "p2"]
    assert generator.calls[0]["target_text"] == payload.target_text_with_markers
    assert run.state.narration_exclusions == []


def test_a_wholly_excluded_block_makes_no_call_and_still_reports_its_exclusions() -> None:
    payload = _payload(("p1", _TOC_LINE, "toc_entry", "toc"), ("p2", "(i)", "body", "fragment"))
    generator = _Generator(_accepted)

    run = _run(payload, generator=generator)

    assert generator.calls == []
    assert run.client.calls == []
    assert run.state.narration_paragraphs == []
    assert run.state.narration_expected_paragraph_ids == []
    assert [(e["paragraph_id"], e["reason"]) for e in run.state.narration_exclusions] == [("p1", "toc"), ("p2", "fragment")]


# --------------------------------------------------------------------------------------------
# T-G3: an empty answer, a restored paragraph and a controlled fallback are NARRATED from source
# --------------------------------------------------------------------------------------------


def _empty_for(target: str) -> Callable[[str, str], tuple[str, str]]:
    def answer(pid: str, source: str) -> tuple[str, str]:
        if pid == target:
            # The generator's own outcome for an empty last answer: the source, ``omitted``.
            return source, "omitted"
        return f"Озвучено: {source}", "accepted"

    return answer


def test_an_empty_answer_is_narrated_from_its_source_with_needs_review() -> None:
    payload = _payload(("p1", _PROSE_A, "body", None), ("p2", _PROSE_B, "body", None))

    run = _run(payload, generator=_Generator(_empty_for("p2")))

    records = _records(run.state)
    assert records["p2"].text == _PROSE_B
    assert records["p2"].needs_review_reasons == ("empty_answer",)
    assert records["p1"].needs_review_reasons == ()
    # The denominator is not shrunk by the empty answer.
    assert run.state.narration_expected_paragraph_ids == ["p1", "p2"]
    summary = audiobook_narration_summary(run.state)
    assert summary["missing_paragraph_ids"] == []
    assert summary["needs_review_by_reason"] == {"empty_answer": 1}


def test_an_accepted_answer_that_cleans_down_to_nothing_is_an_empty_answer() -> None:
    """Edge Cases: there is no legitimate empty answer -- an emoji-only answer is one."""

    payload = _payload(("p1", _PROSE_A, "body", None))

    run = _run(payload, generator=_Generator(lambda _pid, _source: ("\U0001F600", "accepted")))

    record = _records(run.state)["p1"]
    assert record.text == _PROSE_A
    assert record.needs_review_reasons == ("empty_answer",)


def test_a_restored_paragraph_is_narrated_with_its_own_reason() -> None:
    payload = _payload(("p1", _PROSE_A, "body", None), ("p2", _PROSE_B, "body", None))

    def answer(pid: str, source: str) -> tuple[str, str]:
        return (source, "source_restored") if pid == "p1" else (f"Озвучено: {source}", "accepted")

    run = _run(payload, generator=_Generator(answer))

    records = _records(run.state)
    assert records["p1"].text == _PROSE_A
    assert records["p1"].needs_review_reasons == ("source_restored",)


def test_a_controlled_fallback_block_is_narrated_from_source_and_counted_whole() -> None:
    payload = _payload(("p1", _PROSE_A, "body", None), ("p2", _TOC_LINE, "toc_entry", "toc"), ("p3", _PROSE_B, "body", None))

    run = _run(payload, generator=_Generator(_accepted), classification="heading_only_output")

    records = _records(run.state)
    assert list(records) == ["p1", "p3"]
    assert records["p1"].text == _PROSE_A and records["p3"].text == _PROSE_B
    assert all(record.needs_review_reasons == ("source_fallback",) for record in records.values())
    assert run.state.narration_expected_paragraph_ids == ["p1", "p3"]
    # The DOCX carries what is narrated; the excluded paragraph stays as its source.
    delivered = _delivered(run.state)
    assert delivered["p1"].text == _PROSE_A and delivered["p1"].status == "source_restored"
    assert delivered["p2"].text == _TOC_LINE and delivered["p2"].status == "policy_kept_source"
    assert len(_events(run, "block_controlled_fallback")) == 1


# --------------------------------------------------------------------------------------------
# T-G4: residue -> at most ONE repair call per block
# --------------------------------------------------------------------------------------------

_DIGITS_A = "В 1999 году в посёлке жили 300 рыбаков и их семьи."
_DIGITS_B = "К весне цена сети выросла на 15 процентов за месяц."


def _echo(_pid: str, source: str) -> tuple[str, str]:
    return source, "accepted"


def _residue_payload() -> BlockExecutionPayload:
    return _payload(("p1", _DIGITS_A, "body", None), ("p2", _PROSE_A, "body", None), ("p3", _DIGITS_B, "body", None))


def test_residue_in_two_paragraphs_costs_exactly_one_repair_call_and_the_answer_ships() -> None:
    client = _RepairClient(_words_for_digits)

    run = _run(_residue_payload(), generator=_Generator(_echo), repair_client=client)

    assert len(client.calls) == 1
    asked = [pid for pid, _ in client.target_paragraphs(client.calls[0])]
    assert asked == ["p1", "p3"]  # only the paragraphs with residue, under their markers
    assert client.system_prompt(client.calls[0]) == "FIXTURE PROMPT repair"
    records = _records(run.state)
    assert "1999" not in records["p1"].text and "сколько-то" in records["p1"].text
    assert records["p1"].needs_review_reasons == ()
    assert [finding.residue_class for finding in records["p1"].residue_before] == ["digits"]
    assert records["p1"].residue_after == ()
    # The DOCX carries the repaired text too.
    assert _delivered(run.state)["p3"].text == records["p3"].text
    assert run.state.narration_repair_counters["call_count"] == 1
    assert run.state.narration_repair_counters["accepted_block_count"] == 1
    completed = _events(run, "audiobook_repair_completed")
    assert len(completed) == 1
    assert completed[0]["residue_before_by_class"] == {"digits": 2}
    assert completed[0]["residue_after_by_class"] == {}
    # The paid call is booked under its own stage.
    stages = run.accounting["stages"]
    assert stages["audiobook_repair"]["model_call_count"] == 1


def test_a_broken_repair_answer_keeps_the_previous_text_and_there_is_no_second_call() -> None:
    client = _RepairClient(_swapped)

    run = _run(_residue_payload(), generator=_Generator(_echo), repair_client=client)

    assert len(client.calls) == 1
    records = _records(run.state)
    assert records["p1"].text == _DIGITS_A
    assert records["p1"].needs_review_reasons == ("residue", "repair_failed")
    assert records["p2"].needs_review_reasons == ()
    assert run.state.narration_repair_counters["rejected_by_reason.marker_mismatch"] == 1
    summary = audiobook_narration_summary(run.state)
    assert summary["residue_after_by_class"] == {"digits": {"paragraphs": 2, "occurrences": 3}}
    assert summary["repair_rejected_by_reason"] == {"marker_mismatch": 1}


def test_a_failed_repair_call_is_counted_as_a_failed_call() -> None:
    client = _RepairClient(RuntimeError("network down"))

    run = _run(_residue_payload(), generator=_Generator(_echo), repair_client=client)

    assert len(client.calls) == 1
    assert run.state.narration_repair_counters["failed_call_count"] == 1
    assert audiobook_narration_summary(run.state)["repair_failed_call_count"] == 1


def test_stop_before_the_repair_makes_no_call_and_still_delivers_the_block() -> None:
    client = _RepairClient(_words_for_digits)

    run = _run(_residue_payload(), generator=_Generator(_echo), repair_client=client, stop=True)

    assert run.outcome is None
    assert client.calls == []
    assert len(run.state.processed_chunks) == 1
    records = _records(run.state)
    assert records["p1"].text == _DIGITS_A
    assert "repair_failed" in records["p1"].needs_review_reasons
    assert run.state.narration_repair_counters["skipped_stopped_count"] == 1
    assert run.state.narration_repair_counters["call_count"] == 0


def test_a_block_without_residue_makes_no_repair_call() -> None:
    """Anti-vacuum: the call is spent only where the detector found something."""

    client = _RepairClient(_words_for_digits)

    run = _run(_payload(("p1", _PROSE_A, "body", None)), generator=_Generator(_echo), repair_client=client)

    assert client.calls == []
    assert run.state.narration_repair_counters.get("block_count", 0) == 0


def test_html_and_emoji_left_by_the_model_are_cleaned_without_a_call() -> None:
    client = _RepairClient(_words_for_digits)

    run = _run(
        _payload(("p1", _PROSE_A, "body", None)),
        generator=_Generator(lambda _pid, _src: ("Первый <u>абзац</u> о гавани\U0001F600 и её жителях.", "accepted")),
        repair_client=client,
    )

    assert client.calls == []
    assert _records(run.state)["p1"].text == "Первый абзац о гавани и её жителях."


def test_the_repair_call_carries_the_real_repair_prompt_file() -> None:
    """Integration with WP-C's real prompt files, through the run's own (real) loader: the
    repair call is sent the ``repair`` variant, not the block prompt."""

    from docxaicorrector.core.config import load_system_prompt

    client = _RepairClient(_words_for_digits)

    _run(_residue_payload(), generator=_Generator(_echo), repair_client=client, load_system_prompt=load_system_prompt)

    system_prompt = client.system_prompt(client.calls[0])
    assert system_prompt == audiobook_repair.load_repair_system_prompt()
    assert system_prompt != load_system_prompt(operation="audiobook")
    assert "[[DOCX_PARA_" in system_prompt
    assert "{{" not in system_prompt and "{target_language}" not in system_prompt


def test_without_an_injected_loader_the_repair_prompt_is_the_packaged_one() -> None:
    state = ProcessingState()

    prompt = block_execution._audiobook_repair_system_prompt(
        context=SimpleNamespace(processing_operation="audiobook"), dependencies=SimpleNamespace(), state=state
    )

    assert prompt == audiobook_repair.load_repair_system_prompt()
    assert state.audiobook_repair_system_prompt == prompt  # built once per run


# --------------------------------------------------------------------------------------------
# FR-007: the coverage signal, per paragraph, after the digits
# --------------------------------------------------------------------------------------------

_LONG_SOURCE = "Рыбаки поселения обсуждали строительство нового причала вместе с соседями 1999 года."


def test_numbers_written_out_do_not_lower_coverage_but_a_dropped_sentence_does() -> None:
    payload = _payload(("p1", _LONG_SOURCE, "body", None), ("p2", _LONG_SOURCE, "body", None))

    def answer(pid: str, source: str) -> tuple[str, str]:
        if pid == "p1":
            return source.replace("1999", "тысяча девятьсот девяносто девятого"), "accepted"
        return "Рыбаки говорили.", "accepted"

    run = _run(payload, generator=_Generator(answer))

    records = _records(run.state)
    assert records["p1"].coverage.ratio == 1.0
    assert "low_coverage" not in records["p1"].needs_review_reasons
    assert records["p2"].coverage.ratio is not None and records["p2"].coverage.ratio < 0.6
    assert "low_coverage" in records["p2"].needs_review_reasons
    assert audiobook_narration_summary(run.state)["coverage_low_count"] == 1


# --------------------------------------------------------------------------------------------
# T-G5: assembly by id and preparation role
# --------------------------------------------------------------------------------------------


def _record(pid: str, text: str, role: str = "body") -> NarrationParagraphRecord:
    return NarrationParagraphRecord(
        paragraph_id=pid,
        block_index=1,
        role=role,
        text=text,
        needs_review_reasons=(),
        residue_before=(),
        residue_after=(),
        coverage=CoverageResult(0, 0, None),
    )


def test_the_tts_text_parses_back_into_the_expected_ids_with_the_joins_counted_by_pair() -> None:
    records = [
        _record("p1", "Глава первая", role="heading"),
        _record("p2", "началась тихо, и никто"),
        _record("p3", "не заметил перемен в посёлке."),
        _record("p4", "Следующий абзац начинается с прописной."),
    ]

    assembly = assemble_narration_records(records)

    assert assembly.join_pairs == (("p2", "p3"),)
    assert assembly.text == (
        "Глава первая\n\nначалась тихо, и никто не заметил перемен в посёлке.\n\nСледующий абзац начинается с прописной."
    )
    assert assembly.boundary_check == "ok"
    assert assembly.parsed_paragraph_count == len(records) - len(assembly.join_pairs)


def test_a_heading_is_never_joined_to_the_prose_under_it() -> None:
    """The heading ends without punctuation and the prose starts lowercase -- the form alone
    would join them; the preparation's role stops it."""

    assembly = assemble_narration_records([_record("p1", "Глава без точки", role="heading"), _record("p2", "началась с тишины.")])

    assert assembly.join_pairs == ()
    assert assembly.text == "Глава без точки\n\nначалась с тишины."


def test_a_markdown_heading_from_the_model_does_not_make_a_body_paragraph_a_heading() -> None:
    """The kind is the preparation's role, not the answer's Markdown (R8): a body paragraph the
    model returned as ``# …`` is cleaned to its text and still joins as body."""

    payload = _payload(("p1", "Однажды утром рыбаки", "body", None), ("p2", "вышли в море на рассвете.", "body", None))

    def answer(pid: str, source: str) -> tuple[str, str]:
        return (f"# {source}", "accepted") if pid == "p1" else (source, "accepted")

    run = _run(payload, generator=_Generator(answer))
    text = _build_narration_text(
        context=SimpleNamespace(processing_operation="audiobook", runtime=None, uploaded_filename="book.docx"),
        dependencies=SimpleNamespace(log_event=lambda *_a, **_k: None),
        emitters=None,
        state=run.state,
    )

    assert text == "Однажды утром рыбаки вышли в море на рассвете."
    assert run.state.narration_joined_paragraph_id_pairs == [("p1", "p2")]
    assert run.state.narration_paragraph_boundary_check == "ok"


def test_a_record_carrying_a_blank_line_is_reported_as_a_boundary_mismatch() -> None:
    """Counter-proof that the boundary check reads the FINAL text back, not the record count."""

    events: list[tuple[int, str, dict[str, Any]]] = []
    state = ProcessingState()
    state.narration_paragraphs = [_record("p1", "Первый абзац."), _record("p2", "Второй.\n\nСлипшийся третий.")]
    state.narration_expected_paragraph_ids = ["p1", "p2"]

    text = _build_narration_text(
        context=SimpleNamespace(processing_operation="audiobook", runtime=None, uploaded_filename="book.docx"),
        dependencies=SimpleNamespace(log_event=lambda level, event, _m, **ctx: events.append((level, event, ctx))),
        emitters=None,
        state=state,
    )

    assert text is not None  # delivery is not blocked
    assert state.narration_paragraph_boundary_check == "mismatch"
    mismatch = [ctx for level, event, ctx in events if event == "audiobook_paragraph_boundary_mismatch"]
    assert len(mismatch) == 1 and events[0][0] == logging.ERROR
    assert mismatch[0]["first_mismatch_paragraph_id"] == "p2"


def test_the_narration_text_is_assembled_by_id_across_blocks() -> None:
    state = ProcessingState()
    _run(_payload(("p1", _PROSE_A, "body", None)), generator=_Generator(_echo), state=state, index=1)
    _run(_payload(("p2", _PROSE_B, "body", None)), generator=_Generator(_echo), state=state, index=2)

    text = _build_narration_text(
        context=SimpleNamespace(processing_operation="audiobook", runtime=None, uploaded_filename="book.docx"),
        dependencies=SimpleNamespace(log_event=lambda *_a, **_k: None),
        emitters=None,
        state=state,
    )

    assert text == f"{_PROSE_A}\n\n{_PROSE_B}"
    summary = audiobook_narration_summary(state)
    assert summary["expected_paragraph_count"] == summary["delivered_paragraph_count"] == 2
    assert summary["paragraph_boundary_check"] == "ok"


# --------------------------------------------------------------------------------------------
# T-G6: translate and edit narrate nothing
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_build_no_narration_and_hold_no_narration_state(operation: str) -> None:
    payload = _payload(("p1", _DIGITS_A, "body", None), ("p2", _PROSE_A, "body", None))
    client = _RepairClient(_words_for_digits)

    run = _run(payload, generator=_Generator(_echo), operation=operation, repair_client=client)

    assert run.outcome is None
    assert client.calls == []
    state = run.state
    assert state.narration_paragraphs == []
    assert state.narration_expected_paragraph_ids == []
    assert state.narration_exclusions == []
    assert state.narration_repair_counters == {}
    assert (
        _build_narration_text(
            context=SimpleNamespace(processing_operation=operation, runtime=None),
            dependencies=None,
            emitters=None,
            state=state,
        )
        is None
    )


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_translate_and_edit_deliver_exactly_what_the_generator_answered(operation: str) -> None:
    """T-G1 characterization: through the ordinary block entry point in marker mode, the
    request carries every paragraph (no subset), and the delivered block and the paragraph
    registry are the generator's answer unchanged -- the audiobook pass never touches them."""

    payload = _payload(("p1", _DIGITS_A, "body", None), ("p2", _PROSE_A, "body", None))
    generator = _Generator(lambda _pid, source: (f"Ответ: {source}", "accepted"))

    run = _run(payload, generator=generator, operation=operation, app_config={"enable_paragraph_markers": True})

    assert generator.calls[0]["expected_paragraph_ids"] == ["p1", "p2"]
    assert generator.calls[0]["target_text"] == payload.target_text_with_markers
    delivered = run.state.processed_chunks[0]
    assert str(delivered) == f"Ответ: {_DIGITS_A}\n\nОтвет: {_PROSE_A}"
    assert [(item.paragraph_id, item.text, item.status) for item in _delivered(run.state).values()] == [
        ("p1", f"Ответ: {_DIGITS_A}", "accepted"),
        ("p2", f"Ответ: {_PROSE_A}", "accepted"),
    ]
    assert run.state.generated_paragraph_registry == [
        {"block_index": 1, "paragraph_id": "p1", "text": f"Ответ: {_DIGITS_A}", "paragraph_status": "accepted"},
        {"block_index": 1, "paragraph_id": "p2", "text": f"Ответ: {_PROSE_A}", "paragraph_status": "accepted"},
    ]
    assert run.client.calls == []
