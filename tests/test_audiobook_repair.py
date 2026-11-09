"""Spec 070 WP-F: the one-call residue repair and its accounting stage."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest

from docxaicorrector.core import model_accounting
from docxaicorrector.pipeline import audiobook_repair
from docxaicorrector.pipeline.audiobook_repair import RepairItem, repair_block_residue

_ITEMS = (
    RepairItem("p1", "В 1999 году вышло 5 книг.", ("digits",)),
    RepairItem("p2", "Адрес сайта example dot org.", ("url",)),
)
_FIXTURE_PROMPT = "FIXTURE REPAIR PROMPT"


class _Client:
    def __init__(self, answer: Any, cost: float = 0.002) -> None:
        self.answer = answer
        self.cost = cost
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self._create)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(
            status="completed",
            output_text=self.answer,
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20, cost=self.cost),
        )


def _events() -> tuple[list[tuple[int, str, dict[str, Any]]], Any]:
    seen: list[tuple[int, str, dict[str, Any]]] = []

    def log_event(level: int, event: str, message: str, **context: Any) -> str:
        seen.append((level, event, context))
        return event

    return seen, log_event


def _run(client: _Client, *, stop: bool = False, before: str = "", after: str = "", **extra: Any):
    seen, log_event = _events()
    with model_accounting.run_model_accounting_scope(run_id="r"):
        outcome = repair_block_residue(
            client=client,
            model_id="m",
            system_prompt=_FIXTURE_PROMPT,
            items=_ITEMS,
            context_before=before,
            context_after=after,
            should_stop=lambda: stop,
            log_event=log_event,
            block_index=7,
            filename="f.docx",
            **extra,
        )
        snapshot: dict[str, Any] = dict(model_accounting.snapshot_run_model_accounting())
        snapshot["stages"] = dict(snapshot["stages"])  # type: ignore[call-overload]
    return outcome, seen, snapshot


_GOOD = "[[DOCX_PARA_p1]]\nВ тысяча девятьсот девяносто девятом вышло пять книг.\n\n[[DOCX_PARA_p2]]\nАдрес сайта.\n"
_PREVIOUS = {item.paragraph_id: item.text for item in _ITEMS}


def test_accepted_answer_is_one_call_with_texts_by_id_and_bounded_request() -> None:
    client = _Client(_GOOD)
    outcome, _, _ = _run(client, before="a" * 900 + "TAILEND", after="HEADSTART" + "b" * 900)
    assert len(client.calls) == 1
    assert outcome.status == "accepted" and outcome.reason is None and outcome.call_made
    assert outcome.texts == {
        "p1": "В тысяча девятьсот девяносто девятом вышло пять книг.",
        "p2": "Адрес сайта.",
    }
    prompt = client.calls[0]["input"][-1]["content"][0]["text"]
    assert "[[DOCX_PARA_p1]]\nВ 1999 году" in prompt and "[[DOCX_PARA_p2]]" in prompt
    before_part = prompt.split("[CONTEXT BEFORE]\n")[1].split("\n\n[TARGET BLOCK")[0]
    after_part = prompt.split("[CONTEXT AFTER]\n")[1]
    assert before_part.endswith("TAILEND") and len(before_part) == audiobook_repair.REPAIR_CONTEXT_MAX_CHARS
    assert after_part.startswith("HEADSTART") and len(after_part) == audiobook_repair.REPAIR_CONTEXT_MAX_CHARS
    assert client.calls[0]["input"][0]["content"][0]["text"] == _FIXTURE_PROMPT


@pytest.mark.parametrize(
    ("answer", "reason", "status"),
    [
        ("[[DOCX_PARA_p2]]\nB\n\n[[DOCX_PARA_p1]]\nA\n", "marker_mismatch", "rejected"),  # swapped
        ("[[DOCX_PARA_p1]]\nA\n", "marker_mismatch", "rejected"),  # skipped
        ("[[DOCX_PARA_p1]]\nA\n\n[[DOCX_PARA_p1]]\nA\n", "marker_mismatch", "rejected"),  # duplicate
        ("Вступление\n[[DOCX_PARA_p1]]\nA\n\n[[DOCX_PARA_p2]]\nB\n", "marker_mismatch", "rejected"),  # text before
        ("[[DOCX_PARA_p1]]\nA\n\n[[DOCX_PARA_p2]]\n", "empty_paragraph", "rejected"),
        (RuntimeError("network"), "error", "failed"),
    ],
)
def test_rejections_keep_previous_text_after_exactly_one_call(answer: Any, reason: str, status: str) -> None:
    client = _Client(answer)
    outcome, events, _ = _run(client)
    assert len(client.calls) == 1, "no retry, no ladder"
    assert (outcome.status, outcome.reason) == (status, reason)
    assert dict(outcome.texts) == _PREVIOUS
    assert outcome.call_made is True
    failed = [e for e in events if e[1] == "audiobook_repair_failed"]
    assert len(failed) == 1 and failed[0][2]["reason"] == reason and failed[0][0] == logging.WARNING
    assert not any(e[1] == "audiobook_repair_completed" for e in events)


def test_marker_record_lost_is_a_failed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from docxaicorrector.generation._generation import MarkerParagraphRecordLost

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise MarkerParagraphRecordLost("stage")

    monkeypatch.setattr(audiobook_repair, "split_marker_preserved_paragraph_dispositions", boom)
    outcome, _, _ = _run(_Client(_GOOD))
    assert (outcome.status, outcome.reason, outcome.error_class) == ("failed", "error", "MarkerParagraphRecordLost")
    assert dict(outcome.texts) == _PREVIOUS


def test_stop_before_the_call_makes_no_call() -> None:
    client = _Client(_GOOD)
    outcome, events, snapshot = _run(client, stop=True)
    assert client.calls == []
    assert (outcome.status, outcome.reason, outcome.call_made) == ("skipped", "stopped", False)
    assert dict(outcome.texts) == _PREVIOUS
    assert [e[2]["reason"] for e in events if e[1] == "audiobook_repair_failed"] == ["stopped"]
    assert not any(e[1] == "audiobook_repair_started" for e in events)
    assert "audiobook_repair" not in snapshot["stages"]


def test_cost_is_booked_under_the_repair_stage_even_for_a_rejected_answer() -> None:
    accepted: dict[str, Any] = _run(_Client(_GOOD, cost=0.002))[2]["stages"]
    rejected = _run(_Client("[[DOCX_PARA_p1]]\nA\n", cost=0.003))[2]["stages"]
    for stages, cost in ((accepted, 0.002), (rejected, 0.003)):
        stage = stages["audiobook_repair"]
        assert stage["model_call_count"] == 1
        assert stage["cost_usd_reported_by_provider"] == pytest.approx(cost)
        assert "text_generation" not in stages


def test_failed_call_without_response_books_no_dollars() -> None:
    _, _, snapshot = _run(_Client(RuntimeError("network")))
    assert "text_generation" not in snapshot["stages"]
    assert snapshot["stages"].get("audiobook_repair", {}).get("cost_usd_reported_by_provider", 0.0) == 0.0


def test_events_carry_contract_fields_and_no_full_text() -> None:
    _, events, _ = _run(
        _Client(_GOOD),
        residue_after_by_class=lambda texts: {"digits": 0, "url": len(texts) - 2},
    )
    by_name = {e[1]: e for e in events}
    started = by_name["audiobook_repair_started"]
    assert started[0] == logging.DEBUG
    assert started[2] == {
        "filename": "f.docx",
        "block_index": 7,
        "paragraph_ids": ["p1", "p2"],
        "residue_classes": ["digits", "url"],
        "model": "m",
    }
    completed = by_name["audiobook_repair_completed"]
    assert completed[0] == logging.INFO
    assert completed[2]["residue_before_by_class"] == {"digits": 1, "url": 1}
    assert completed[2]["residue_after_by_class"] == {"digits": 0, "url": 0}
    for _, _, context in events:
        assert "тысяча" not in repr(context) and "1999" not in repr(context)


def test_stage_constant() -> None:
    assert model_accounting.STAGE_AUDIOBOOK_REPAIR == "audiobook_repair"


def _counting_sdk_client(status_code: int, seen: list[httpx2.Request]) -> Any:
    from openai import OpenAI

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(status_code, json={"error": {"message": "synthetic server fault"}})

    # The run's client as ``core.config`` builds it: the SDK default ``max_retries`` (2).
    return OpenAI(api_key="k", base_url="http://provider.invalid/v1", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_the_repair_call_is_exactly_one_http_attempt_even_when_the_sdk_would_retry() -> None:
    """Spec 070 FR-006 / R5: AT MOST ONE paid call. The SDK retries a 5xx silently (``max_retries=2``
    = 3 requests); the repair call must derive a no-retry client so the provider sees one request."""

    seen: list[httpx2.Request] = []
    client = _counting_sdk_client(500, seen)
    outcome, _, _ = _run(client)  # type: ignore[arg-type]
    assert len(seen) == 1
    assert outcome.status == "failed" and outcome.reason == "error" and outcome.call_made
    assert outcome.texts == _PREVIOUS


def test_the_main_clients_own_retry_budget_is_left_alone() -> None:
    seen: list[httpx2.Request] = []
    client = _counting_sdk_client(500, seen)
    _run(client)  # type: ignore[arg-type]
    assert client.max_retries == 2  # the per-call client is a copy; generation keeps its retries
    seen.clear()
    with pytest.raises(Exception):
        client.responses.create(model="m", input="x")
    assert len(seen) == 3  # the main call still gets the SDK's 1 + 2 attempts


def test_a_client_without_with_options_is_used_as_is() -> None:
    client = _Client(_GOOD)
    outcome, _, _ = _run(client)
    assert outcome.status == "accepted" and len(client.calls) == 1
