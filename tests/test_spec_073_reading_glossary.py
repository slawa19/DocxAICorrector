"""Spec 073 WP-E: the reading glossary of an audiobook run -- its core (FR-004, SC-002 mechanism, SC-007).

Every text here is invented and of the same FORM as what the rule reads (Constitution VII): ``ABC``,
``AbC-DE``, ``XY-12``, ``ЖЗИ``, generated spellings ``Q<letter><letter>``. No book text, no list of
abbreviations, no reading of any real abbreviation. The model is never called: every call goes to a
double of ``request_text_completion`` that counts what it was asked.
"""

from __future__ import annotations

import json
import logging
import string
from types import SimpleNamespace
from typing import Any, cast

import pytest

import docxaicorrector.generation._generation as generation
from docxaicorrector.generation.model_response import IncompleteResponse


# ---------------------------------------------------------------------------------------------
# Doubles
# ---------------------------------------------------------------------------------------------


class _Http503(Exception):
    status_code = 503


class _Client:
    """A client the step must pass through as it is: ``with_options`` would be a policy of its own."""

    def __init__(self) -> None:
        self.with_options_calls: list[dict[str, object]] = []

    def with_options(self, **kwargs: object) -> "_Client":
        self.with_options_calls.append(dict(kwargs))
        return self


def _request_candidates(request: dict[str, object]) -> list[dict[str, object]]:
    user = cast(list[dict[str, Any]], request["input"])[1]
    return json.loads(user["content"][0]["text"])["candidates"]


def _answer_all(request: dict[str, object]) -> str:
    return json.dumps(
        {"readings": [{"abbreviation": item["abbreviation"], "reading": "чтение"} for item in _request_candidates(request)]},
        ensure_ascii=False,
    )


class _Completion:
    """``request_text_completion`` double. ``script[n]`` decides the n-th call: an exception to raise,
    a string to return, or a callable of the request; past the script every call answers all."""

    def __init__(self, script: list[object] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[SimpleNamespace] = []

    def __call__(self, client: object, request: dict[str, object], *, usage_stage: str, should_stop: object = None) -> str:
        self.calls.append(SimpleNamespace(client=client, request=dict(request), usage_stage=usage_stage, should_stop=should_stop))
        step = self.script.pop(0) if self.script else _answer_all
        if isinstance(step, BaseException):
            raise step
        if callable(step):
            return cast(str, step(request))
        return cast(str, step)

    def batch_sizes(self) -> list[int]:
        return [len(_request_candidates(call.request)) for call in self.calls]


class _Log:
    def __init__(self) -> None:
        self.events: list[tuple[int, str, dict[str, object]]] = []

    def __call__(self, level: int, event: str, message: str, **context: object) -> str:
        self.events.append((level, event, dict(context)))
        return "evt"

    def named(self, event: str) -> list[tuple[int, str, dict[str, object]]]:
        return [item for item in self.events if item[1] == event]


class _Artifacts:
    def __init__(self) -> None:
        self.written: list[dict[str, object]] = []

    def __call__(self, payload: dict[str, object], *, context: object) -> str:
        self.written.append(json.loads(json.dumps(payload, ensure_ascii=False)))
        return f"/fake/run_glossaries/artifact_{len(self.written)}.json"


def _spellings(count: int) -> list[str]:
    """``count`` distinct spellings of the candidate form, generated (no list): ``Q`` keeps them from
    ever being a roman numeral."""

    letters = string.ascii_uppercase
    return [f"Q{letters[index // 26]}{letters[index % 26]}" for index in range(count)]


def _paragraph(paragraph_id: str, text: str, block_index: int = 1) -> Any:
    from docxaicorrector.pipeline.reading_glossary import ReadingParagraph

    return ReadingParagraph(paragraph_id=paragraph_id, block_index=block_index, text=text)


def _paragraphs_with(spellings: list[str]) -> list[Any]:
    return [_paragraph(f"p{index}", f"Здесь стоит {spelling} в обычной фразе.") for index, spelling in enumerate(spellings)]


def _run(paragraphs: list[Any], *, completion: _Completion | None = None, max_retries: int = 3, should_stop=None, **overrides: Any):
    from docxaicorrector.pipeline.reading_glossary import run_reading_glossary

    completion = completion or _Completion()
    log = overrides.pop("log", None) or _Log()
    artifacts = overrides.pop("artifacts", None) or _Artifacts()
    sleeps: list[float] = overrides.pop("sleeps", None) if "sleeps" in overrides else []
    client = overrides.pop("client", None) or _Client()
    result = run_reading_glossary(
        paragraphs=paragraphs,
        client=client,
        model_id="model-x",
        max_retries=max_retries,
        should_stop=should_stop or (lambda: False),
        log_event=log,
        filename="book.docx",
        artifact_context=SimpleNamespace(run_id="run-7", source_token="tok"),
        request_text_completion_fn=completion,
        sleep_fn=sleeps.append,
        write_artifact_fn=artifacts,
    )
    return result, completion, log, artifacts, sleeps


# ---------------------------------------------------------------------------------------------
# T-E1: what must NOT change -- the 063 usage of its stage, the block's pauses
# ---------------------------------------------------------------------------------------------


class _ResponsesClient:
    def __init__(self, text: str, *, input_tokens: int, output_tokens: int) -> None:
        self._text = text
        self._usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens, cost=0.0007)
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: object) -> object:
        return SimpleNamespace(status="completed", output_text=self._text, usage=self._usage)


def test_stage_usage_without_argument_is_the_glossary_extraction_stage_and_each_stage_reads_its_own():
    from docxaicorrector.core import model_accounting
    from docxaicorrector.generation._generation import request_text_completion
    from docxaicorrector.pipeline import glossary_phase

    request = {"model": "m", "input": [], "temperature": 0.2, "max_output_tokens": 1024}
    with model_accounting.run_model_accounting_scope(run_id="run-u", source_token="token-u"):
        request_text_completion(
            _ResponsesClient("{}", input_tokens=1200, output_tokens=300),
            request,
            usage_stage=model_accounting.STAGE_GLOSSARY_EXTRACTION,
        )
        request_text_completion(
            _ResponsesClient("{}", input_tokens=500, output_tokens=40),
            request,
            usage_stage=model_accounting.STAGE_AUDIOBOOK_READING_GLOSSARY,
        )
        default_usage = glossary_phase._stage_usage()
        explicit_default = glossary_phase._stage_usage(stage_name=model_accounting.STAGE_GLOSSARY_EXTRACTION)
        reading_usage = glossary_phase._stage_usage(stage_name="audiobook_reading_glossary")

    assert model_accounting.STAGE_AUDIOBOOK_READING_GLOSSARY == "audiobook_reading_glossary"
    assert default_usage == explicit_default
    assert default_usage["prompt_tokens"] == 1200 and default_usage["completion_tokens"] == 300
    assert reading_usage["prompt_tokens"] == 500 and reading_usage["completion_tokens"] == 40


def test_retry_backoff_seconds_is_the_block_pause():
    assert [generation.retry_backoff_seconds(attempt) for attempt in range(1, 7)] == [1, 2, 4, 8, 8, 8]


def test_block_retry_loop_sleeps_by_retry_backoff_seconds(monkeypatch):
    asked: list[int] = []
    sleeps: list[float] = []

    def backoff(attempt: int) -> float:
        asked.append(attempt)
        return 0.25 * attempt

    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text="")))
    monkeypatch.setattr(generation, "retry_backoff_seconds", backoff)
    monkeypatch.setattr(generation.time, "sleep", sleeps.append)
    monkeypatch.setattr(generation, "log_event", lambda *args, **kwargs: "evt")

    generation.generate_markdown_block(
        client=cast(Any, client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="Короткий исходный абзац для проверки пауз между попытками.",
        context_before="before",
        context_after="after",
        max_retries=3,
    )

    assert asked == [1, 2]
    assert sleeps == [0.25, 0.5]


# ---------------------------------------------------------------------------------------------
# T-E2: the form of a candidate
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Слово ABC в тексте.", ("ABC",)),
        ("Слово AbC-DE в тексте.", ("AbC-DE",)),
        ("Слово XY-12 в тексте.", ("XY-12",)),
        ("Слово ЖЗИ в тексте.", ("ЖЗИ",)),
        ("Слово ЖЗИ⁷ со сноской.", ("ЖЗИ",)),
        ("Слово Abc в тексте.", ()),
        ("Слово aBc в тексте.", ()),
        ("Глава IV и год MMXX.", ()),
        ("Адрес www.ABC-DE.example в тексте.", ()),
        ("ABCD EFGH XY", ()),
        ("Одна буква A и B.", ()),
    ],
)
def test_candidate_form(text, expected):
    from docxaicorrector.pipeline.reading_glossary import reading_candidate_units

    assert reading_candidate_units(text) == expected


def test_candidate_form_address_mask_is_not_vacuous():
    from docxaicorrector.pipeline.reading_glossary import reading_candidate_units

    assert reading_candidate_units("Адрес ABC-DE.example и ещё ABC-DE рядом.") == ("ABC-DE",)
    assert reading_candidate_units("Адрес www.ABC-DE.example рядом.") == ()


def test_candidates_keep_the_exact_spelling():
    from docxaicorrector.pipeline.reading_glossary import extract_reading_candidates

    candidates = extract_reading_candidates([_paragraph("p1", "Тут ABC, тут Abc и снова ABC.")])

    assert [(item.abbreviation, item.occurrences) for item in candidates] == [("ABC", 2)]


# ---------------------------------------------------------------------------------------------
# T-E3: selection -- frequency, then first appearance; the limit; the context
# ---------------------------------------------------------------------------------------------


def test_candidates_are_ordered_by_frequency_then_first_appearance():
    from docxaicorrector.pipeline.reading_glossary import extract_reading_candidates

    candidates = extract_reading_candidates(
        [
            _paragraph("p1", "Сначала DEF, потом GHK.", block_index=1),
            _paragraph("p2", "Потом XYZ и ещё XYZ.", block_index=2),
        ]
    )

    assert [item.abbreviation for item in candidates] == ["XYZ", "DEF", "GHK"]
    assert [item.first_block_index for item in candidates] == [2, 1, 1]
    assert all(item.sent for item in candidates)


def test_limit_drops_the_rarest_and_latest_candidate():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_MAX_CANDIDATES, extract_reading_candidates

    spellings = _spellings(READING_GLOSSARY_MAX_CANDIDATES + 1)
    rare = spellings[0]
    # The rare one comes FIRST in the text: frequency, not position, decides the cut.
    paragraphs = [_paragraph("p0", f"Редкое {rare} один раз.")]
    paragraphs += [_paragraph(f"p{index}", f"Тут {spelling} и {spelling}.") for index, spelling in enumerate(spellings[1:], 1)]

    candidates = extract_reading_candidates(paragraphs)

    assert len(candidates) == READING_GLOSSARY_MAX_CANDIDATES + 1
    assert sum(1 for item in candidates if item.sent) == READING_GLOSSARY_MAX_CANDIDATES
    dropped = [item.abbreviation for item in candidates if not item.sent]
    assert dropped == [rare]


def test_limit_ties_drop_the_latest():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_MAX_CANDIDATES, extract_reading_candidates

    spellings = _spellings(READING_GLOSSARY_MAX_CANDIDATES + 1)
    candidates = extract_reading_candidates(_paragraphs_with(spellings))

    assert [item.abbreviation for item in candidates if not item.sent] == [spellings[-1]]


def test_context_is_bounded_and_holds_the_first_occurrence():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_CONTEXT_CHARS, extract_reading_candidates

    text = "слово " * 100 + "Здесь впервые ABC-DE стоит. " + "слово " * 100 + "И ещё ABC-DE."
    (candidate,) = extract_reading_candidates([_paragraph("p1", text)])

    assert READING_GLOSSARY_CONTEXT_CHARS == 160
    assert len(candidate.context) <= READING_GLOSSARY_CONTEXT_CHARS
    assert "впервые ABC-DE" in candidate.context


# ---------------------------------------------------------------------------------------------
# T-E4: batches, the call, Stop
# ---------------------------------------------------------------------------------------------


def test_batches_of_forty_one_call_each_with_the_stage_the_stop_and_the_client_as_given():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_BATCH_SIZE

    client = _Client()
    should_stop = lambda: False  # noqa: E731
    glossary, completion, _log, _artifacts, sleeps = _run(
        _paragraphs_with(_spellings(85)), client=client, should_stop=should_stop
    )

    assert READING_GLOSSARY_BATCH_SIZE == 40
    assert completion.batch_sizes() == [40, 40, 5]
    assert all(call.usage_stage == "audiobook_reading_glossary" for call in completion.calls)
    assert all(call.should_stop is should_stop for call in completion.calls)
    assert all(call.client is client for call in completion.calls)
    assert client.with_options_calls == []
    assert sleeps == []
    assert glossary.status == "built"
    assert (glossary.batch_count, glossary.call_count, glossary.retry_count) == (3, 3, 0)
    assert len(glossary.entries) == 85


def test_one_batch_answered_first_time_is_exactly_one_call():
    glossary, completion, *_ = _run([_paragraph("p1", "Слово ABC и XYZ.")])

    assert len(completion.calls) == 1
    assert glossary.status == "built"
    assert [entry.abbreviation for entry in glossary.entries] == ["ABC", "XYZ"]


def test_no_candidates_no_call():
    glossary, completion, log, artifacts, _ = _run([_paragraph("p1", "Обычный текст без сокращений.")])

    assert completion.calls == []
    assert glossary.status == "no_candidates"
    assert artifacts.written == []
    (built,) = log.named("audiobook_reading_glossary_built")
    assert built[0] == logging.INFO and built[2]["status"] == "no_candidates"


def test_stop_before_the_step_no_call():
    glossary, completion, log, artifacts, _ = _run(_paragraphs_with(_spellings(3)), should_stop=lambda: True)

    assert completion.calls == []
    assert glossary.status == "stopped"
    assert artifacts.written == []
    assert log.events == []


def test_stop_before_the_second_batch_one_call():
    completion = _Completion()
    glossary, completion, log, artifacts, _ = _run(
        _paragraphs_with(_spellings(45)), completion=completion, should_stop=lambda: len(completion.calls) >= 1
    )

    assert len(completion.calls) == 1
    assert glossary.status == "stopped"
    assert artifacts.written == []


def test_stop_during_the_call_is_stopped():
    from docxaicorrector.pipeline.contracts import LatePhaseStopped

    glossary, completion, *_ = _run(_paragraphs_with(_spellings(3)), completion=_Completion([LatePhaseStopped()]))

    assert len(completion.calls) == 1
    assert glossary.status == "stopped"


# ---------------------------------------------------------------------------------------------
# T-E4a: a failing batch retries ITSELF, by the block's policy
# ---------------------------------------------------------------------------------------------


def test_failing_batch_is_retried_alone_after_the_block_pause():
    completion = _Completion([_answer_all, _Http503("unavailable"), _answer_all, _answer_all])
    glossary, completion, _log, _artifacts, sleeps = _run(_paragraphs_with(_spellings(85)), completion=completion)

    assert len(completion.calls) == 4
    assert completion.batch_sizes() == [40, 40, 40, 5]
    first_of_second = _request_candidates(completion.calls[1].request)
    assert _request_candidates(completion.calls[2].request) == first_of_second
    assert glossary.retry_count == 1 and glossary.call_count == 4 and glossary.batch_count == 3
    assert sleeps == [generation.retry_backoff_seconds(1)]
    assert glossary.status == "built" and len(glossary.entries) == 85


def test_unparseable_answer_is_retried():
    glossary, completion, _log, _artifacts, sleeps = _run(
        [_paragraph("p1", "Слово ABC.")], completion=_Completion(["нет здесь JSON", _answer_all])
    )

    assert len(completion.calls) == 2
    assert glossary.retry_count == 1
    assert sleeps == [generation.retry_backoff_seconds(1)]
    assert [entry.abbreviation for entry in glossary.entries] == ["ABC"]


def test_answer_without_readings_list_is_retried():
    glossary, completion, *_ = _run([_paragraph("p1", "Слово ABC.")], completion=_Completion(['{"other": []}', _answer_all]))

    assert len(completion.calls) == 2
    assert glossary.status == "built"


def test_truncated_answer_grows_the_budget():
    glossary, completion, *_ = _run(
        [_paragraph("p1", "Слово ABC.")], completion=_Completion([IncompleteResponse("cut"), _answer_all])
    )

    first, second = (cast(int, call.request["max_output_tokens"]) for call in completion.calls)
    assert second > first
    assert glossary.retry_count == 1


def test_plain_exception_is_not_retried_and_the_model_is_unavailable():
    from docxaicorrector.pipeline.reading_glossary import ReadingGlossaryUnavailable

    with pytest.raises(ReadingGlossaryUnavailable) as raised:
        _run([_paragraph("p1", "Слово ABC.")], completion=_Completion([RuntimeError("bad request shape")]))

    assert raised.value.reason == "error"
    assert raised.value.attempts == 1
    assert raised.value.batch_index == 1
    assert raised.value.error_class == "RuntimeError"


# ---------------------------------------------------------------------------------------------
# T-E4b: one re-request of the candidates left without a reading
# ---------------------------------------------------------------------------------------------


def _first_pass_leaves_three(request: dict[str, object]) -> str:
    """Answer all but: the first unanswered, the second and third with readings the form refuses."""

    items = _request_candidates(request)
    readings = [{"abbreviation": item["abbreviation"], "reading": "чтение"} for item in items[3:]]
    readings.append({"abbreviation": items[1]["abbreviation"], "reading": "Latin"})
    readings.append({"abbreviation": items[2]["abbreviation"], "reading": "чтение 7"})
    return json.dumps({"readings": readings}, ensure_ascii=False)


def test_rerequest_asks_the_three_left_once_and_resolves_them():
    spellings = _spellings(10)
    glossary, completion, log, *_ = _run(_paragraphs_with(spellings), completion=_Completion([_first_pass_leaves_three]))

    assert len(completion.calls) == 2
    assert completion.batch_sizes() == [10, 3]
    assert [item["abbreviation"] for item in _request_candidates(completion.calls[1].request)] == spellings[:3]
    assert glossary.rerequested == tuple(spellings[:3])
    assert glossary.unresolved == ()
    assert glossary.status == "built" and len(glossary.entries) == 10
    (built,) = log.named("audiobook_reading_glossary_built")
    assert built[2]["rerequested_count"] == 3 and built[2]["unresolved_count"] == 0
    assert log.named("audiobook_reading_glossary_unresolved") == []


def test_rerequest_happens_once_even_when_it_leaves_one():
    spellings = _spellings(10)

    def leaves_first(request: dict[str, object]) -> str:
        items = _request_candidates(request)[1:]
        return json.dumps({"readings": [{"abbreviation": item["abbreviation"], "reading": "чтение"} for item in items]})

    glossary, completion, log, *_ = _run(
        _paragraphs_with(spellings), completion=_Completion([_first_pass_leaves_three, leaves_first, _answer_all])
    )

    assert len(completion.calls) == 2
    assert glossary.unresolved == (spellings[0],)
    assert glossary.status == "built"
    (built,) = log.named("audiobook_reading_glossary_built")
    assert built[2]["unresolved_count"] == 1


def test_no_rerequest_when_the_first_pass_answered_all():
    glossary, completion, *_ = _run(_paragraphs_with(_spellings(10)))

    assert len(completion.calls) == 1
    assert glossary.rerequested == ()


# ---------------------------------------------------------------------------------------------
# T-E4c: the model is unavailable -- the step fails, it does not degrade
# ---------------------------------------------------------------------------------------------


def test_batch_that_exhausts_its_attempts_raises_unavailable_after_writing_what_was_accepted():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_STATUSES, ReadingGlossaryUnavailable

    artifacts = _Artifacts()
    log = _Log()
    completion = _Completion([_answer_all, _Http503("a"), _Http503("b"), _Http503("c")])
    with pytest.raises(ReadingGlossaryUnavailable) as raised:
        _run(_paragraphs_with(_spellings(85)), completion=completion, max_retries=3, artifacts=artifacts, log=log)

    error = raised.value
    assert (error.reason, error.batch_index, error.attempts) == ("error", 2, 3)
    assert error.error_class == "_Http503"
    assert len(completion.calls) == 4  # batch 3 is never asked
    (artifact,) = artifacts.written
    assert len(cast(list[object], artifact["readings"])) == 40
    assert artifact["run_id"] == "run-7"
    assert error.artifact_path == "/fake/run_glossaries/artifact_1.json"
    assert error.candidate_count == 85 and error.sent_count == 85
    assert log.named("audiobook_reading_glossary_built") == []
    assert READING_GLOSSARY_STATUSES == ("built", "no_candidates", "stopped")


def test_same_batch_answered_on_the_last_attempt_is_built():
    completion = _Completion([_answer_all, _Http503("a"), _Http503("b"), _answer_all, _answer_all])
    glossary, completion, _log, _artifacts, sleeps = _run(_paragraphs_with(_spellings(85)), completion=completion, max_retries=3)

    assert glossary.status == "built"
    assert glossary.retry_count == 2
    assert sleeps == [generation.retry_backoff_seconds(1), generation.retry_backoff_seconds(2)]


def test_unparseable_on_every_attempt_names_its_reason():
    from docxaicorrector.pipeline.reading_glossary import ReadingGlossaryUnavailable

    with pytest.raises(ReadingGlossaryUnavailable) as raised:
        _run([_paragraph("p1", "Слово ABC.")], completion=_Completion(["нет", "нет"]), max_retries=2)

    assert (raised.value.reason, raised.value.attempts) == ("no_json", 2)


# ---------------------------------------------------------------------------------------------
# T-E5: the answer's form and the levels of the events
# ---------------------------------------------------------------------------------------------


def _sent(*spellings: str) -> list[Any]:
    from docxaicorrector.pipeline.reading_glossary import ReadingCandidate

    return [ReadingCandidate(abbreviation=item, occurrences=1, first_block_index=1, context="", sent=True) for item in spellings]


@pytest.mark.parametrize(
    ("readings", "reason"),
    [
        ([{"abbreviation": "Abc", "reading": "чтение"}], "not_a_candidate"),
        ([{"abbreviation": "ABC", "reading": "   "}], "empty_reading"),
        ([{"abbreviation": "ABC", "reading": "чтение abc"}], "latin_in_reading"),
        ([{"abbreviation": "ABC", "reading": "чтение 1"}], "digit_in_reading"),
        ([{"abbreviation": "ABC", "reading": "кувэ²"}], "digit_in_reading"),
        ([{"abbreviation": "ABC", "reading": "..."}], "not_cyrillic_reading"),
        ([{"abbreviation": "ABC", "reading": "—"}], "not_cyrillic_reading"),
        ([{"abbreviation": "ABC", "reading": "Ω"}], "not_cyrillic_reading"),
        ([{"abbreviation": "ABC", "reading": "字"}], "not_cyrillic_reading"),
        ([{"abbreviation": "ABC", "reading": "чтение"}, {"abbreviation": "ABC", "reading": "другое"}], "duplicate"),
    ],
)
def test_each_rejection_reason(readings, reason):
    from docxaicorrector.pipeline.reading_glossary import READING_REJECTION_REASONS, parse_reading_glossary_response

    entries, rejected = parse_reading_glossary_response(json.dumps({"readings": readings}, ensure_ascii=False), sent=_sent("ABC"))

    assert set(rejected) == set(READING_REJECTION_REASONS)
    assert rejected[reason] == 1
    assert sum(rejected.values()) == 1
    if reason == "duplicate":
        assert [(entry.abbreviation, entry.reading) for entry in entries] == [("ABC", "чтение")]
    else:
        assert entries == ()


def test_reading_keeps_its_stress_mark():
    from docxaicorrector.pipeline.reading_glossary import parse_reading_glossary_response

    reading = "чте́ние"
    entries, _ = parse_reading_glossary_response(json.dumps({"readings": [{"abbreviation": "ABC", "reading": reading}]}), sent=_sent("ABC"))

    assert entries[0].reading == reading


def test_full_answer_is_info_and_events_carry_no_spelling_or_reading():
    glossary, _completion, log, _artifacts, _ = _run([_paragraph("p1", "Слово ABC и XYZ.")])

    assert [(level, event) for level, event, _ in log.events] == [(logging.INFO, "audiobook_reading_glossary_built")]
    context = log.events[0][2]
    for key in (
        "filename", "status", "candidate_count", "sent_count", "accepted_count", "rerequested_count", "unresolved_count",
        "dropped_by_limit_count", "rejected_by_reason", "batch_count", "call_count", "retry_count", "prompt_tokens",
        "completion_tokens", "cost_usd", "artifact_path",
    ):
        assert key in context
    rendered = json.dumps(log.events, ensure_ascii=False)
    assert "ABC" not in rendered and "XYZ" not in rendered and "чтение" not in rendered


def test_unresolved_adds_a_warning_with_review_data():
    def refuses_first(request: dict[str, object]) -> str:
        items = _request_candidates(request)[1:]
        return json.dumps({"readings": [{"abbreviation": item["abbreviation"], "reading": "чтение"} for item in items]})

    spellings = _spellings(3)
    _glossary, _completion, log, *_ = _run(_paragraphs_with(spellings), completion=_Completion([refuses_first, refuses_first]))

    assert [(level, event) for level, event, _ in log.events] == [
        (logging.INFO, "audiobook_reading_glossary_built"),
        (logging.WARNING, "audiobook_reading_glossary_unresolved"),
    ]
    warning = log.events[1][2]
    assert warning["review_data"] is True and warning["unresolved_count"] == 1
    assert spellings[0] not in json.dumps(log.events, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------
# T-E6: the artifact
# ---------------------------------------------------------------------------------------------


def test_artifact_carries_the_contract_fields_and_its_path_reaches_the_event():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_SCHEMA

    spellings = _spellings(10)
    glossary, _completion, log, artifacts, _ = _run(_paragraphs_with(spellings), completion=_Completion([_first_pass_leaves_three]))

    (artifact,) = artifacts.written
    assert artifact["schema"] == READING_GLOSSARY_SCHEMA == "audiobook_reading_glossary/v1"
    assert artifact["run_id"] == "run-7" and artifact["filename"] == "book.docx" and artifact["model"] == "model-x"
    assert artifact["status"] == "built"
    candidates = cast(list[dict[str, object]], artifact["candidates"])
    assert set(candidates[0]) >= {"abbreviation", "occurrences", "sent", "rerequested", "resolved"}
    assert [item["abbreviation"] for item in candidates if item["rerequested"]] == spellings[:3]
    assert all(item["resolved"] for item in candidates)
    assert len(cast(list[object], artifact["readings"])) == 10
    assert artifact["unresolved"] == []
    batches = cast(list[dict[str, object]], artifact["batches"])
    assert [(item["pass"], item["size"], item["attempts"]) for item in batches] == [("first", 10, 1), ("rerequest", 3, 1)]
    rejected = cast(dict[str, int], artifact["rejected_by_reason"])
    assert rejected["latin_in_reading"] == 1 and rejected["digit_in_reading"] == 1
    assert set(cast(dict[str, object], artifact["usage"])) == {"prompt_tokens", "completion_tokens", "cost_usd"}
    assert glossary.artifact_path == "/fake/run_glossaries/artifact_1.json"
    assert log.named("audiobook_reading_glossary_built")[0][2]["artifact_path"] == glossary.artifact_path


def test_artifact_names_the_candidates_the_limit_dropped():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_MAX_CANDIDATES

    spellings = _spellings(READING_GLOSSARY_MAX_CANDIDATES + 1)
    glossary, _completion, log, artifacts, _ = _run(_paragraphs_with(spellings))

    candidates = cast(list[dict[str, object]], artifacts.written[0]["candidates"])
    assert [item["abbreviation"] for item in candidates if not item["sent"]] == [spellings[-1]]
    assert log.named("audiobook_reading_glossary_built")[0][2]["dropped_by_limit_count"] == 1
    assert glossary.entry_for(spellings[-1]) is None
    assert glossary.entry_for(spellings[0]) is not None


# ---------------------------------------------------------------------------------------------
# T-E7: the section of one block
# ---------------------------------------------------------------------------------------------


def _glossary(*pairs: tuple[str, str]) -> Any:
    from docxaicorrector.pipeline.reading_glossary import ReadingEntry, ReadingGlossary

    return ReadingGlossary(status="built", entries=tuple(ReadingEntry(abbreviation=a, reading=r) for a, r in pairs))


def test_section_header_is_the_contract_literal():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_SECTION_HEADER

    assert READING_GLOSSARY_SECTION_HEADER == (
        "КАК ЧИТАТЬ СОКРАЩЕНИЯ ЭТОЙ КНИГИ (каждое сокращение из списка читайте ровно так; "
        "если чтение — слово, склоняйте его по смыслу):"
    )


def test_section_holds_only_the_block_entries_in_order_of_first_appearance():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_SECTION_HEADER, reading_section_for_block

    glossary = _glossary(("ABC", "эй-би-си"), ("XYZ", "икс-игрек-зет"), ("DEF", "ди-и-эф"))

    first = reading_section_for_block(glossary, ["Тут XYZ, а потом ABC.", "И снова ABC."])
    second = reading_section_for_block(glossary, ["Только DEF."])

    assert first == f"{READING_GLOSSARY_SECTION_HEADER}\n- XYZ -> икс-игрек-зет\n- ABC -> эй-би-си"
    assert second == f"{READING_GLOSSARY_SECTION_HEADER}\n- DEF -> ди-и-эф"
    # No memory of the previous call: the first block's entries never reach the second.
    assert reading_section_for_block(glossary, ["Тут XYZ, а потом ABC.", "И снова ABC."]) == first


def test_section_is_empty_without_entries_of_the_block():
    from docxaicorrector.pipeline.reading_glossary import reading_section_for_block

    glossary = _glossary(("ABC", "эй-би-си"))

    assert reading_section_for_block(glossary, ["Тут Abc и abc."]) == ""
    assert reading_section_for_block(glossary, []) == ""
    assert reading_section_for_block(None, ["Тут ABC."]) == ""


def test_section_is_cut_by_its_budget():
    from docxaicorrector.pipeline.reading_glossary import READING_GLOSSARY_SECTION_MAX_CHARS, reading_section_for_block

    spellings = _spellings(80)
    glossary = _glossary(*((spelling, "чтение " * 6) for spelling in spellings))

    section = reading_section_for_block(glossary, [" ".join(spellings)])

    assert READING_GLOSSARY_SECTION_MAX_CHARS == 2000
    assert len(section) <= READING_GLOSSARY_SECTION_MAX_CHARS
    assert section.endswith("\n- ...")


# ---------------------------------------------------------------------------------------------
# T-E8: the phase
# ---------------------------------------------------------------------------------------------


def _job(paragraph_ids: list[str], texts: list[str], reasons: list[str | None] | None = None) -> dict[str, object]:
    marked = "\n\n".join(f"[[DOCX_PARA_{pid}]]\n{text}" for pid, text in zip(paragraph_ids, texts))
    job: dict[str, object] = {
        "job_kind": "llm",
        "target_chars": len(marked),
        "context_chars": 0,
        "target_text": "\n\n".join(texts),
        "target_text_with_markers": marked,
        "paragraph_ids": list(paragraph_ids),
        "context_before": "",
        "context_after": "",
    }
    if reasons is not None:
        job["narration_exclusion_reasons"] = list(reasons)
    return job


class _Recorder:
    def __init__(self, result: object = None) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.result = result

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return self.result


def _phase_doubles(operation: str, jobs: list[dict[str, object]], *, stop: bool = False):
    from docxaicorrector.pipeline.contracts import ProcessingState

    context = SimpleNamespace(
        processing_operation=operation,
        jobs=jobs,
        max_retries=2,
        model="context-model",
        uploaded_filename="book.docx",
        run_id="run-9",
        source_token="tok",
        runtime=object(),
    )
    log = _Log()
    present_error = _Recorder("Модель недоступна.")
    dependencies = SimpleNamespace(
        log_event=log, present_error=present_error, should_stop_processing=lambda runtime: stop
    )
    emitters = SimpleNamespace(emit_status=_Recorder(), emit_state=_Recorder())
    client = _Client()
    initialization = SimpleNamespace(text_client=client, client=object(), text_model_id="text-model", job_count=len(jobs))
    state = ProcessingState()
    return context, dependencies, emitters, state, initialization, log, present_error, client


def _call_phase(context, dependencies, emitters, state, initialization, *, completion, failed=None, artifacts=None, sleeps=None):
    from docxaicorrector.pipeline.reading_glossary import run_reading_glossary_phase

    return run_reading_glossary_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        emit_failed_result_fn=cast(Any, failed or _Recorder("failed")),
        request_text_completion_fn=completion,
        sleep_fn=(sleeps if sleeps is not None else []).append,
        write_artifact_fn=artifacts or _Artifacts(),
    )


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_phase_does_nothing_outside_the_audiobook(operation):
    jobs = [_job(["p1"], ["Слово ABC."])]
    context, dependencies, emitters, state, initialization, log, _present, _client = _phase_doubles(operation, jobs)
    completion = _Completion()
    before = dict(vars(context))

    outcome = _call_phase(context, dependencies, emitters, state, initialization, completion=completion)

    assert outcome is None
    assert completion.calls == []
    assert getattr(state, "audiobook_reading_glossary", None) is None
    assert vars(context) == before
    assert log.events == []


def test_phase_reads_only_narrated_paragraphs_and_keeps_the_glossary_in_state():
    jobs = [
        _job(["p1", "p2"], ["Слово ABC в теле.", "Исключённый DEF."], [None, "toc"]),
        _job(["p3"], ["И ещё XYZ."]),
    ]
    context, dependencies, emitters, state, initialization, log, present, client = _phase_doubles("audiobook", jobs)
    completion = _Completion()
    before = dict(vars(context))

    outcome = _call_phase(context, dependencies, emitters, state, initialization, completion=completion)

    assert outcome is None
    assert vars(context) == before
    sent = [item["abbreviation"] for item in _request_candidates(completion.calls[0].request)]
    assert sent == ["ABC", "XYZ"]
    assert completion.calls[0].client is client
    assert completion.calls[0].request["model"] == "text-model"
    glossary = state.audiobook_reading_glossary  # type: ignore[attr-defined]
    assert glossary.status == "built"
    assert [entry.abbreviation for entry in glossary.entries] == ["ABC", "XYZ"]
    assert {item.first_block_index for item in glossary.candidates} == {1, 2}
    assert present.calls == []


def test_phase_passes_the_context_max_retries():
    jobs = [_job(["p1"], ["Слово ABC."])]
    context, dependencies, emitters, state, initialization, *_ = _phase_doubles("audiobook", jobs)
    from docxaicorrector.pipeline.reading_glossary import run_reading_glossary_phase

    completion = _Completion([_Http503("a"), _Http503("b"), _Http503("c")])
    run_reading_glossary_phase(
        context=context,
        dependencies=dependencies,
        emitters=emitters,
        state=state,
        initialization=initialization,
        emit_failed_result_fn=cast(Any, _Recorder("failed")),
        request_text_completion_fn=completion,
        sleep_fn=lambda seconds: None,
        write_artifact_fn=_Artifacts(),
    )

    assert len(completion.calls) == context.max_retries == 2


def test_phase_unavailable_takes_the_block_failure_path():
    jobs = [_job(["p1"], ["Слово ABC."])]
    context, dependencies, emitters, state, initialization, log, present, _client = _phase_doubles("audiobook", jobs)
    failed = _Recorder("failed-outcome")
    artifacts = _Artifacts()
    cause = _Http503("down")

    outcome = _call_phase(
        context, dependencies, emitters, state, initialization,
        completion=_Completion([cause, cause]), failed=failed, artifacts=artifacts,
    )

    assert outcome == "failed-outcome"
    ((args, kwargs),) = present.calls
    assert args[0] == "audiobook_reading_glossary_failed"
    assert args[1] is cause
    for key in ("filename", "reason", "batch_index", "attempts", "error_class", "candidate_count", "sent_count", "artifact_path"):
        assert key in kwargs
    assert kwargs["reason"] == "error" and kwargs["attempts"] == 2 and kwargs["artifact_path"] == "/fake/run_glossaries/artifact_1.json"
    state_calls = [kw for _args, kw in emitters.emit_state.calls]
    assert any(kw.get("latest_docx_bytes", "absent") is None and "Модель недоступна." in str(kw.get("last_error")) for kw in state_calls)
    ((_fargs, fkwargs),) = failed.calls
    assert fkwargs["runtime"] is context.runtime
    assert "Модель недоступна." in str(fkwargs["detail"])
    assert fkwargs["block_count"] == 1
    assert getattr(state, "audiobook_reading_glossary", None) is None
    assert log.named("audiobook_reading_glossary_built") == []
    assert len(artifacts.written) == 1


def test_phase_stop_before_the_step_is_not_a_failure():
    jobs = [_job(["p1"], ["Слово ABC."])]
    context, dependencies, emitters, state, initialization, _log, present, _client = _phase_doubles("audiobook", jobs, stop=True)
    completion = _Completion()

    outcome = _call_phase(context, dependencies, emitters, state, initialization, completion=completion)

    assert outcome is None
    assert completion.calls == []
    assert state.audiobook_reading_glossary.status == "stopped"  # type: ignore[attr-defined]
    assert present.calls == []


@pytest.mark.parametrize(
    "reading", ["чтение", "кувэ́", "два слова", "ка-вэ", "ка‐вэ", "ка‑вэ"]
)
def test_cyrillic_readings_are_accepted(reading):
    from docxaicorrector.pipeline.reading_glossary import ReadingCandidate, parse_reading_glossary_response

    sent = [ReadingCandidate(abbreviation="ABC", occurrences=1, first_block_index=1, context="", sent=True)]
    accepted, rejected = parse_reading_glossary_response(
        json.dumps({"readings": [{"abbreviation": "ABC", "reading": reading}]}), sent=sent
    )
    assert [entry.reading for entry in accepted] == [reading]
    assert not any(rejected.values())


@pytest.mark.parametrize(("narration_include", "expected"), [(False, 0), (True, 1)])
def test_legacy_block_without_reasons_follows_narration_include(narration_include, expected):
    from docxaicorrector.pipeline.reading_glossary import (
        ReadingParagraph,
        extract_reading_candidates,
        narrated_source_paragraphs,
    )

    payload = SimpleNamespace(
        paragraph_ids=[],
        target_text="Сокращение XQZ встречается здесь.",
        narration_exclusion_reasons=None,
        narration_include=narration_include,
    )
    paragraphs = [
        ReadingParagraph(paragraph_id=paragraph_id, block_index=1, text=text)
        for paragraph_id, text in narrated_source_paragraphs(payload)
    ]
    assert [item.abbreviation for item in extract_reading_candidates(paragraphs)] == (["XQZ"] if expected else [])
