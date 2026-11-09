"""Spec 069 WP-2: the request profile of a generation call (FR-003, FR-006; SC-006).

Section A is the GOLDEN of SC-006 and Anti-regression 1: a call made WITHOUT a request
profile — every ``edit``, ``audiobook`` and ``single`` translate call today — sends the SDK
exactly the bytes it sent before spec 069. It was written and run green against the
unmodified generator (``main`` @ ``15cbcb3``) before a line of ``_generation.py`` changed;
the digests below are what that code sent. A digest that moves means a request without a
profile changed, which SC-006 forbids.

The texts are invented (Constitution VII): a harbour, a ferry, a lighthouse — no corpus book.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from typing import Any, Callable, cast

import pytest

import docxaicorrector.core.model_accounting as model_accounting
import docxaicorrector.generation._generation as generation

# --- the scripted model ------------------------------------------------------------------

_INCOMPLETE = "<<incomplete>>"
_MARKER_VIOLATION = "Ответ без единого маркера абзаца."

# Long enough that every budget is above the 512-token floor, so a multiplier is visible.
_P1 = (
    "The lighthouse keeper counted seven gulls before noon, wrote their number in a narrow ledger "
    "with a blunt pencil, and then climbed the spiral stair once more to wipe the salt from the great "
    "lens, because the evening fog was expected early and the fishing boats from the northern cove "
    "would need the beam long before the bell in the village square rang for supper and the shutters "
    "of the bakery were drawn."
)
_P2_S1 = (
    "Rain moved over the quiet harbour in long grey curtains, drumming on the tarpaulins of the moored "
    "dinghies, filling the gutters of the customs house, and chasing the last few traders from the "
    "cobbled quay towards the warm doorway of the tavern."
)
_P2_S2 = (
    "The ferry waited by the pier with its engine idling, its captain leaning on the rail beside a crate "
    "of oranges, watching the clock above the ticket office and wondering whether the late passengers "
    "from the inland train would arrive before the tide turned."
)
_P2 = f"{_P2_S1} {_P2_S2}"
_P2_S1_RU = (
    "Дождь шёл над тихой гаванью длинными серыми завесами, барабанил по брезенту пришвартованных "
    "лодок, наполнял водостоки таможни и гнал последних торговцев с мощёной набережной к тёплому "
    "порогу таверны."
)
_P2_S2_RU = (
    "Паром ждал у причала с работающим мотором; капитан стоял у поручня рядом с ящиком апельсинов, "
    "смотрел на часы над кассой и гадал, успеют ли опоздавшие пассажиры с поезда до смены прилива."
)
_ANSWERS = {
    _P1: (
        "Смотритель маяка насчитал семь чаек до полудня, записал их число в узкую тетрадь тупым "
        "карандашом и снова поднялся по винтовой лестнице, чтобы стереть соль с большой линзы: "
        "вечерний туман ждали рано, и рыбацким лодкам из северной бухты луч понадобится задолго до "
        "того, как колокол на площади позовёт к ужину и в пекарне закроют ставни."
    ),
    _P2: f"{_P2_S1_RU} {_P2_S2_RU}",
    _P2_S1: _P2_S1_RU,
    _P2_S2: _P2_S2_RU,
}
_CONTEXT_BEFORE = "Earlier the tide was low."
_CONTEXT_AFTER = "Later the lamps were lit."
_MARKER_TARGET = f"[[DOCX_PARA_p0001]]\n{_P1}\n\n[[DOCX_PARA_p0002]]\n{_P2}"
_MARKER_IDS = ["p0001", "p0002"]
_PLAIN_TARGET = f"{_P1}\n\n{_P2}"

_OPERATIONS: dict[str, dict[str, Any]] = {
    # The generator does not know the operation; what differs between them at this layer is
    # the system prompt and whether the short-source absorption rule is on (translate only).
    "edit": {"system_prompt": "SYNTHETIC EDIT SYSTEM PROMPT", "detect_short_source_absorption": False},
    "audiobook": {"system_prompt": "SYNTHETIC AUDIOBOOK SYSTEM PROMPT", "detect_short_source_absorption": False},
    "translate": {"system_prompt": "SYNTHETIC TRANSLATE SYSTEM PROMPT", "detect_short_source_absorption": True},
}
_MODELS = {
    "responses": "gpt-5.4",
    "chat": "google/gemini-3.1-flash-lite-preview",
    "anthropic": "anthropic:claude-haiku-5.5",
}


def _target_of(prompt: str) -> str:
    """The text the prompt asks about: between its ``[TARGET BLOCK…]`` header and ``[CONTEXT AFTER]``."""

    tail = prompt.split("[TARGET BLOCK", 1)[-1]
    tail = tail.split("]\n", 1)[-1]
    return tail.split("\n\n[CONTEXT AFTER]", 1)[0].strip()


def _answer_for(scenario: str, target: str) -> str:
    if scenario == "first_attempt":
        return f"[[DOCX_PARA_p0001]]\n{_ANSWERS[_P1]}\n\n[[DOCX_PARA_p0002]]\n{_ANSWERS[_P2]}"
    if scenario == "ladder":
        # Every batched request (attempts, recovery) breaks the marker contract; each
        # per-paragraph ladder request — which carries no marker — is answered.
        if "[[DOCX_PARA_" in target:
            return _MARKER_VIOLATION
        return _ANSWERS[target]
    if scenario == "incomplete":
        # The whole block and the whole second paragraph run out of budget; the first
        # paragraph and each sentence of the second are answered.
        if target in (_PLAIN_TARGET, _P2):
            return _INCOMPLETE
        return _ANSWERS[target]
    raise AssertionError(scenario)


def _snapshot(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


class _ScriptedClient:
    """One provider path, recording every SDK call it receives, answering by the target."""

    def __init__(self, path: str, scenario: str, *, answer: Callable[[str, str], str] = _answer_for) -> None:
        self.path = path
        self.scenario = scenario
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._answer = answer
        if path == "responses":
            self.responses = SimpleNamespace(create=self._responses_create)
        elif path == "chat":
            self.base_url = "https://openrouter.ai/api/v1"
            self.responses = SimpleNamespace(create=self._responses_refused)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat_create))
        elif path == "anthropic":
            self.messages = SimpleNamespace(create=self._anthropic_create)
        else:
            raise AssertionError(path)

    def _answer_text(self, prompt: str) -> str:
        return self._answer(self.scenario, _target_of(prompt))

    def _responses_create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("responses.create", _snapshot(kwargs)))
        answer = self._answer_text(kwargs["input"][-1]["content"][0]["text"])
        if answer == _INCOMPLETE:
            return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])
        return SimpleNamespace(output_text=answer)

    def _responses_refused(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("responses.create", _snapshot(kwargs)))

        class ResponsesUnsupported(Exception):
            status_code = 400

        raise ResponsesUnsupported("Responses API unsupported for this model; use chat.completions instead.")

    def _chat_create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("chat.completions.create", _snapshot(kwargs)))
        answer = self._answer_text(kwargs["messages"][-1]["content"])
        if answer == _INCOMPLETE:
            return SimpleNamespace(
                choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content="partial"))]
            )
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=answer))])

    def _anthropic_create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("messages.create", _snapshot(kwargs)))
        answer = self._answer_text(kwargs["messages"][-1]["content"])
        if answer == _INCOMPLETE:
            return SimpleNamespace(stop_reason="max_tokens", content=[SimpleNamespace(text="partial")])
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(text=answer)])


@pytest.fixture(autouse=True)
def _quiet_generator(monkeypatch, tmp_path):
    from docxaicorrector.generation import marker_attempt_capture

    monkeypatch.setattr(generation.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(marker_attempt_capture, "MARKER_ATTEMPT_DIAGNOSTICS_DIR", tmp_path / "marker_attempts")
    model_accounting.reset_run_model_accounting()
    yield
    model_accounting.reset_run_model_accounting()


def _run_block(client: _ScriptedClient, operation: str, scenario: str, **extra: Any) -> str:
    options = _OPERATIONS[operation]
    marker_mode = scenario != "incomplete"
    return generation.generate_markdown_block(
        client=client,  # type: ignore[arg-type]
        model=_MODELS[client.path],
        system_prompt=options["system_prompt"],
        target_text=_MARKER_TARGET if marker_mode else _PLAIN_TARGET,
        context_before=_CONTEXT_BEFORE,
        context_after=_CONTEXT_AFTER,
        max_retries=2,
        expected_paragraph_ids=_MARKER_IDS if marker_mode else None,
        marker_mode=marker_mode,
        block_index=3,
        detect_short_source_absorption=options["detect_short_source_absorption"],
        **extra,
    )


def _budget_of(api: str, kwargs: dict[str, Any]) -> int | None:
    return kwargs.get("max_tokens") if api != "responses.create" else kwargs.get("max_output_tokens")


def _digest(calls: list[tuple[str, dict[str, Any]]]) -> str:
    # Key ORDER is part of the bytes an SDK serialises, so it is recorded next to the values.
    canonical = json.dumps(
        [{"api": api, "keys": list(kwargs), "kwargs": kwargs} for api, kwargs in calls],
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _fingerprint(calls: list[tuple[str, dict[str, Any]]]) -> tuple[str, int, list[int | None]]:
    return _digest(calls), len(calls), [_budget_of(api, kwargs) for api, kwargs in calls]


# --- A. golden: no profile → the request of today (SC-006) -------------------------------

# (operation, path, scenario) -> (digest of every SDK call, call count, budget of each call).
# Recorded on the unmodified generator, main @ 15cbcb3, before WP-2 touched it.
_GOLDEN_BLOCKS: dict[tuple[str, str, str], tuple[str, int, list[int | None]]] = {
    ("audiobook", "anthropic", "first_attempt"): ("a48dc8dcd6c7f4785f23d483", 1, [1260]),
    ("edit", "anthropic", "first_attempt"): ("72f0a6bc4401984c8756c6e8", 1, [1260]),
    ("translate", "anthropic", "first_attempt"): ("0d0c88026b6e47c949762b3e", 1, [1260]),
    ("audiobook", "chat", "first_attempt"): ("46a221600677ba59f30d4e62", 2, [1260, 1260]),
    ("edit", "chat", "first_attempt"): ("2466ce7517997f70d6e313a6", 2, [1260, 1260]),
    ("translate", "chat", "first_attempt"): ("42e02b4be2a7a19f9bebfe79", 2, [1260, 1260]),
    ("audiobook", "responses", "first_attempt"): ("6d712ab5e047d0b40fd0f5a7", 1, [1260]),
    ("edit", "responses", "first_attempt"): ("bdae1d2ebba3676f2c50f26f", 1, [1260]),
    ("translate", "responses", "first_attempt"): ("0e30e3394fc50a11acf1cf75", 1, [1260]),
    ("audiobook", "anthropic", "ladder"): ("3d125f6cc2eb31ce8241b8f5", 5, [1260, 1260, 1260, 540, 664]),
    ("edit", "anthropic", "ladder"): ("c70d5c448e0be188d6611cd6", 5, [1260, 1260, 1260, 540, 664]),
    ("translate", "anthropic", "ladder"): ("d4a3c2e942a4586167262727", 5, [1260, 1260, 1260, 540, 664]),
    ("audiobook", "chat", "ladder"): (
        "8a879ea57a2935cec787ec5b", 10, [1260, 1260, 1260, 1260, 1260, 1260, 540, 540, 664, 664]
    ),
    ("edit", "chat", "ladder"): (
        "c60fe2889b5b8586acad47cd", 10, [1260, 1260, 1260, 1260, 1260, 1260, 540, 540, 664, 664]
    ),
    ("translate", "chat", "ladder"): (
        "98e80584f0f4f733f5a14833", 10, [1260, 1260, 1260, 1260, 1260, 1260, 540, 540, 664, 664]
    ),
    ("audiobook", "responses", "ladder"): ("24721dbf4528edc988afcab8", 5, [1260, 1260, 1260, 540, 664]),
    ("edit", "responses", "ladder"): ("d6b12d07d37fd494fac9cca7", 5, [1260, 1260, 1260, 540, 664]),
    ("translate", "responses", "ladder"): ("11ee8cc44ffd00b1e3f57e83", 5, [1260, 1260, 1260, 540, 664]),
    ("audiobook", "anthropic", "incomplete"): (
        "8edf73909909631223fb2ab7", 9, [1208, 2416, 2416, 540, 664, 1328, 1536, 512, 512]
    ),
    ("edit", "anthropic", "incomplete"): (
        "297c95874dad475953acc2f9", 9, [1208, 2416, 2416, 540, 664, 1328, 1536, 512, 512]
    ),
    ("translate", "anthropic", "incomplete"): (
        "0cc3cd9a82f52b116b785504", 9, [1208, 2416, 2416, 540, 664, 1328, 1536, 512, 512]
    ),
    ("audiobook", "chat", "incomplete"): (
        "90446d86e04259cd1dfd8266",
        18,
        [1208, 1208, 2416, 2416, 2416, 2416, 540, 540, 664, 664, 1328, 1328, 1536, 1536, 512, 512, 512, 512],
    ),
    ("edit", "chat", "incomplete"): (
        "59848c9647c8251ecdb96a19",
        18,
        [1208, 1208, 2416, 2416, 2416, 2416, 540, 540, 664, 664, 1328, 1328, 1536, 1536, 512, 512, 512, 512],
    ),
    ("translate", "chat", "incomplete"): (
        "ac1de3996a17f18cbb42e473",
        18,
        [1208, 1208, 2416, 2416, 2416, 2416, 540, 540, 664, 664, 1328, 1328, 1536, 1536, 512, 512, 512, 512],
    ),
    ("audiobook", "responses", "incomplete"): (
        "675063d43689de97dd804147", 9, [1208, 2416, 2416, 540, 664, 1328, 1536, 512, 512]
    ),
    ("edit", "responses", "incomplete"): (
        "1fb354986b684c8739184a99", 9, [1208, 2416, 2416, 540, 664, 1328, 1536, 512, 512]
    ),
    ("translate", "responses", "incomplete"): (
        "2fbde56d5c5730ea8a5b656f", 9, [1208, 2416, 2416, 540, 664, 1328, 1536, 512, 512]
    ),
}

_GOLDEN_GLOSSARY: dict[str, tuple[str, int, list[int | None]]] = {
    "anthropic": ("c1e7f9da9d5f2addbd5b2e57", 1, [1024]),
    "chat": ("ec335d3724faa01301905f44", 2, [1024, 1024]),
    "responses": ("d9d2e65b8db21c72efff4dcb", 1, [1024]),
}


@pytest.mark.parametrize("operation", sorted(_OPERATIONS))
@pytest.mark.parametrize("path", sorted(_MODELS))
@pytest.mark.parametrize("scenario", ["first_attempt", "ladder", "incomplete"])
def test_sc006_block_requests_without_a_profile_are_byte_identical(operation, path, scenario):
    client = _ScriptedClient(path, scenario)

    result = _run_block(client, operation, scenario)

    assert result.strip(), "the scripted model answers every scenario"
    assert _fingerprint(client.calls) == _GOLDEN_BLOCKS[(operation, path, scenario)], json.dumps(
        client.calls, ensure_ascii=False, indent=1
    )


def test_sc006_every_scenario_reaches_the_call_it_pins():
    """Anti-vacuum for the golden: the scenarios really exercise recovery, boost and ladder."""

    client = _ScriptedClient("responses", "ladder")
    _run_block(client, "translate", "ladder")
    prompts = [kwargs["input"][-1]["content"][0]["text"] for _, kwargs in client.calls]
    assert any("[TARGET BLOCK WITH MARKERS ONLY]" in prompt for prompt in prompts), "recovery call"
    assert sum("[[DOCX_PARA_" not in prompt for prompt in prompts) == 2, "one ladder call per paragraph"

    client = _ScriptedClient("responses", "incomplete")
    _run_block(client, "translate", "incomplete")
    budgets = [kwargs["max_output_tokens"] for _, kwargs in client.calls]
    prompts = [kwargs["input"][-1]["content"][0]["text"] for _, kwargs in client.calls]
    assert budgets[0] > 512 and budgets[1] == 2 * budgets[0], "the retry doubles the budget"
    assert any("[TARGET BLOCK ONLY]" in prompt for prompt in prompts), "recovery call"
    assert any(_target_of(prompt) == _P2_S2 for prompt in prompts), "sentence-group ladder call"


@pytest.mark.parametrize("path", sorted(_MODELS))
def test_sc006_text_completion_without_a_profile_is_byte_identical(path):
    client = _ScriptedClient(path, "first_attempt", answer=lambda _scenario, _target: '{"terms": []}')
    request = {
        "model": _MODELS[path],
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": "SYNTHETIC GLOSSARY INSTRUCTIONS"}]},
            {"role": "user", "content": [{"type": "input_text", "text": '{"candidates": []}'}]},
        ],
        "temperature": 0.2,
        "max_output_tokens": 1024,
    }

    text = generation.request_text_completion(client, request, usage_stage=model_accounting.STAGE_GLOSSARY_EXTRACTION)

    assert text == '{"terms": []}'
    assert _fingerprint(client.calls) == _GOLDEN_GLOSSARY[path], json.dumps(client.calls, ensure_ascii=False, indent=1)


# --- B. the profile: reasoning by API path, budget multiplier, accounting stage ------------

_LOW_TRIPLE: dict[str, Any] = {
    "reasoning_effort": "low",
    "output_budget_multiplier": 3.0,
    "usage_stage": "literary_polish",
}


def _profile(**overrides: Any) -> Any:
    return generation.GenerationRequestProfile(**{**_LOW_TRIPLE, **overrides})


def _stages() -> dict[str, Any]:
    return cast(dict[str, Any], model_accounting.snapshot_run_model_accounting()["stages"])


def _sent(client: _ScriptedClient, api: str) -> list[dict[str, Any]]:
    return [kwargs for name, kwargs in client.calls if name == api]


def _prompt_of(api: str, kwargs: dict[str, Any]) -> str:
    if api == "responses.create":
        return kwargs["input"][-1]["content"][0]["text"]
    return kwargs["messages"][-1]["content"]


def _capture_events(monkeypatch, *modules: Any) -> list[tuple[int, str, dict[str, Any]]]:
    events: list[tuple[int, str, dict[str, Any]]] = []

    def capture(level, event, message, **context):
        events.append((level, event, dict(context)))
        return f"evt-{event}"

    for module in modules:
        monkeypatch.setattr(module, "log_event", capture)
    return events


def test_profile_is_frozen_and_its_default_is_the_request_of_today():
    import dataclasses

    default = generation.GenerationRequestProfile()
    assert (default.reasoning_effort, default.output_budget_multiplier, default.usage_stage) == (
        None,
        1.0,
        model_accounting.STAGE_TEXT_GENERATION,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        default.reasoning_effort = "low"  # type: ignore[misc]
    bad_arguments: tuple[dict[str, Any], ...] = (
        {"output_budget_multiplier": 0},
        {"output_budget_multiplier": float("nan")},
        {"output_budget_multiplier": True},
        {"reasoning_effort": " "},
        {"usage_stage": ""},
    )
    for bad in bad_arguments:
        with pytest.raises(ValueError):
            generation.GenerationRequestProfile(**bad)


def test_profile_for_model_takes_the_multiplier_of_the_model():
    haiku = generation.GenerationRequestProfile.for_model(
        "openrouter:anthropic/claude-haiku-5.5", usage_stage="literary_polish"
    )
    assert (haiku.reasoning_effort, haiku.output_budget_multiplier, haiku.usage_stage) == (
        None,
        3.0,
        "literary_polish",
    )
    gemini = generation.GenerationRequestProfile.for_model("openrouter:google/gemini-3.7-flash", reasoning_effort="low")
    assert (gemini.reasoning_effort, gemini.output_budget_multiplier, gemini.usage_stage) == (
        "low",
        1.0,
        model_accounting.STAGE_TEXT_GENERATION,
    )


def test_default_profile_sends_the_same_bytes_as_no_profile():
    """``request_profile=GenerationRequestProfile()`` and ``None`` are one request."""

    without = _ScriptedClient("responses", "ladder")
    _run_block(without, "translate", "ladder")
    explicit = _ScriptedClient("responses", "ladder")
    _run_block(explicit, "translate", "ladder", request_profile=generation.GenerationRequestProfile())
    assert explicit.calls == without.calls


def test_responses_request_carries_reasoning_only_with_a_profile():
    plain = _ScriptedClient("responses", "first_attempt")
    _run_block(plain, "translate", "first_attempt")
    profiled = _ScriptedClient("responses", "first_attempt")
    _run_block(profiled, "translate", "first_attempt", request_profile=_profile())

    [plain_request] = _sent(plain, "responses.create")
    [profiled_request] = _sent(profiled, "responses.create")
    assert "reasoning" not in plain_request
    assert profiled_request["reasoning"] == {"effort": "low"}
    # Everything else is the request of today, and the budget is the multiplied one.
    assert profiled_request["max_output_tokens"] == min(3 * plain_request["max_output_tokens"], 16384)
    rest = {key: value for key, value in profiled_request.items() if key not in {"reasoning", "max_output_tokens"}}
    assert rest == {key: value for key, value in plain_request.items() if key != "max_output_tokens"}


def test_profile_without_reasoning_sends_no_reasoning_key():
    """The second pass of ``standard`` sends no parameter (contract §4: "без параметра")."""

    client = _ScriptedClient("responses", "first_attempt")
    _run_block(client, "translate", "first_attempt", request_profile=_profile(reasoning_effort=None))
    assert client.calls and all("reasoning" not in kwargs for _, kwargs in client.calls)


def test_chat_completions_carries_reasoning_in_extra_body():
    client = _ScriptedClient("chat", "first_attempt")
    _run_block(client, "translate", "first_attempt", request_profile=_profile())

    [refused] = _sent(client, "responses.create")
    [chat] = _sent(client, "chat.completions.create")
    assert refused["reasoning"] == {"effort": "low"}
    assert chat["extra_body"] == {"reasoning": {"effort": "low"}}
    assert "reasoning" not in chat
    assert chat["max_tokens"] == refused["max_output_tokens"]

    plain = _ScriptedClient("chat", "first_attempt")
    _run_block(plain, "translate", "first_attempt")
    assert plain.calls and all("extra_body" not in kwargs for _, kwargs in plain.calls)


@pytest.mark.parametrize("path", ["responses", "chat"])
def test_text_completion_carries_reasoning_with_a_profile(path):
    client = _ScriptedClient(path, "first_attempt", answer=lambda _scenario, _target: "{}")
    request: dict[str, object] = {
        "model": _MODELS[path],
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "{}"}]}],
        "temperature": 0.2,
        "max_output_tokens": 3072,
    }

    generation.request_text_completion(
        client,
        request,
        usage_stage=model_accounting.STAGE_GLOSSARY_EXTRACTION,
        request_profile=_profile(),
    )

    sent = client.calls[-1][1]
    if path == "responses":
        assert sent["reasoning"] == {"effort": "low"}
        # The budget is the builder's: the glossary formula already applied the multiplier.
        assert sent["max_output_tokens"] == 3072
    else:
        assert sent["extra_body"] == {"reasoning": {"effort": "low"}}
        assert sent["max_tokens"] == 3072
    assert "reasoning" not in request, "the caller's request is not mutated"
    # The explicit stage of the call wins over the profile's: the glossary stays glossary.
    stages = _stages()
    assert set(stages) == {model_accounting.STAGE_GLOSSARY_EXTRACTION}


class _ReasoningRejected(Exception):
    status_code = 400
    code = "unsupported_parameter"

    def __init__(self) -> None:
        super().__init__("Unsupported parameter: 'reasoning' is not supported with this model.")


def test_responses_rejection_of_reasoning_drops_it_and_warns(monkeypatch):
    import docxaicorrector.image.shared as image_shared

    events = _capture_events(monkeypatch, image_shared)
    calls: list[dict[str, Any]] = []

    def create(**kwargs: Any) -> SimpleNamespace:
        calls.append(dict(kwargs))
        if "reasoning" in kwargs:
            raise _ReasoningRejected()
        return SimpleNamespace(output_text="Готово.")

    result = generation.generate_markdown_block(
        client=SimpleNamespace(responses=SimpleNamespace(create=create)),  # type: ignore[arg-type]
        model="gpt-5.4",
        system_prompt="system",
        target_text="Ready.",
        context_before="",
        context_after="",
        max_retries=1,
        request_profile=_profile(),
    )

    assert result == "Готово."
    assert [("reasoning" in call) for call in calls] == [True, False]
    dropped = [event for event in events if event[1] == "model_call_param_dropped"]
    assert [(level, context["param"], context["stage"]) for level, _, context in dropped] == [
        (30, "reasoning", "literary_polish")
    ]
    assert "nested_in" not in dropped[0][2]


def test_chat_rejection_of_nested_reasoning_drops_it_and_warns(monkeypatch):
    import docxaicorrector.image.shared as image_shared

    events = _capture_events(monkeypatch, image_shared)
    chat_calls: list[dict[str, Any]] = []

    class ResponsesUnsupported(Exception):
        status_code = 400

    def responses_create(**kwargs: Any) -> SimpleNamespace:
        raise ResponsesUnsupported("Responses API unsupported for this model; use chat.completions instead.")

    def chat_create(**kwargs: Any) -> SimpleNamespace:
        chat_calls.append(json.loads(json.dumps(kwargs, ensure_ascii=False)))
        if "reasoning" in (kwargs.get("extra_body") or {}):
            raise _ReasoningRejected()
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="Готово."))])

    client = SimpleNamespace(
        base_url="https://openrouter.ai/api/v1",
        responses=SimpleNamespace(create=responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create)),
    )

    result = generation.generate_markdown_block(
        client=client,  # type: ignore[arg-type]
        model="google/gemini-3.7-flash",
        system_prompt="system",
        target_text="Ready.",
        context_before="",
        context_after="",
        max_retries=1,
        request_profile=_profile(),
    )

    assert result == "Готово."
    assert [call.get("extra_body") for call in chat_calls] == [{"reasoning": {"effort": "low"}}, None]
    dropped = [event for event in events if event[1] == "model_call_param_dropped"]
    assert [(context["param"], context["nested_in"], context["stage"]) for _, _, context in dropped] == [
        ("reasoning", "extra_body", "literary_polish")
    ]


def test_nested_drop_keeps_the_other_extra_body_keys_and_does_not_mutate_them(monkeypatch):
    import docxaicorrector.image.shared as image_shared

    _capture_events(monkeypatch, image_shared)
    extra_body = {"reasoning": {"effort": "low"}, "provider": {"order": ["x"]}}
    payload: dict[str, object] = {"model": "m", "extra_body": extra_body}

    assert image_shared.drop_rejected_optional_param(_ReasoningRejected(), payload, {"reasoning"}, stage="s")
    assert payload["extra_body"] == {"provider": {"order": ["x"]}}
    assert extra_body == {"reasoning": {"effort": "low"}, "provider": {"order": ["x"]}}
    # Not removable → not dropped, wherever it sits.
    payload = {"model": "m", "extra_body": {"reasoning": {"effort": "low"}}}
    assert not image_shared.drop_rejected_optional_param(_ReasoningRejected(), payload, {"temperature"}, stage="s")
    assert payload["extra_body"] == {"reasoning": {"effort": "low"}}


def test_anthropic_never_receives_reasoning_and_warns_once_per_model_and_effort(monkeypatch):
    monkeypatch.setattr(generation, "_REASONING_UNSUPPORTED_WARNED", set())
    events = _capture_events(monkeypatch, generation)

    for effort in ("low", "low", "high"):
        client = _ScriptedClient("anthropic", "first_attempt")
        _run_block(client, "translate", "first_attempt", request_profile=_profile(reasoning_effort=effort))
        assert client.calls
        assert all("reasoning" not in kwargs and "extra_body" not in kwargs for _, kwargs in client.calls)

    warned = [context for _, event, context in events if event == "reasoning_effort_not_supported_for_provider"]
    assert warned == [
        {"provider": "anthropic", "model": "claude-haiku-5-5", "reasoning_effort": "low", "stage": "literary_polish"},
        {"provider": "anthropic", "model": "claude-haiku-5-5", "reasoning_effort": "high", "stage": "literary_polish"},
    ]


# T2.5 — the profile reaches every call of the block, one test per point. Each was shown to
# fail with the hand-over at its point removed (WP-2 report, anti-vacuum).


def test_profile_reaches_the_recovery_call():
    client = _ScriptedClient("responses", "ladder")
    _run_block(client, "translate", "ladder", request_profile=_profile())

    recovery = [
        kwargs
        for api, kwargs in client.calls
        if "[TARGET BLOCK WITH MARKERS ONLY]" in _prompt_of(api, kwargs)
    ]
    assert len(recovery) == 1
    assert recovery[0]["reasoning"] == {"effort": "low"}
    assert recovery[0]["max_output_tokens"] == 3 * 1260


def test_profile_reaches_the_boosted_retry_and_the_boosted_recovery():
    client = _ScriptedClient("responses", "incomplete")
    _run_block(client, "translate", "incomplete", request_profile=_profile())

    block_calls = [kwargs for api, kwargs in client.calls if _target_of(_prompt_of(api, kwargs)) == _PLAIN_TARGET]
    # 3 x 1208 first; the boost doubles it; the recovery is rebuilt at 3 x 1208 and boosted.
    assert [kwargs["max_output_tokens"] for kwargs in block_calls] == [3 * 1208, 6 * 1208, 6 * 1208]
    assert all(kwargs["reasoning"] == {"effort": "low"} for kwargs in block_calls)


def test_profile_reaches_the_ladder_calls():
    client = _ScriptedClient("responses", "ladder")
    _run_block(client, "translate", "ladder", request_profile=_profile())

    ladder = [kwargs for api, kwargs in client.calls if "[[DOCX_PARA_" not in _prompt_of(api, kwargs)]
    assert len(ladder) == 2
    assert all(kwargs["reasoning"] == {"effort": "low"} for kwargs in ladder)
    assert [kwargs["max_output_tokens"] for kwargs in ladder] == [3 * 540, 3 * 664]


def test_profile_reaches_the_nested_generation_of_a_divided_paragraph():
    client = _ScriptedClient("responses", "incomplete")
    _run_block(client, "translate", "incomplete", request_profile=_profile())

    sentences = [
        kwargs
        for api, kwargs in client.calls
        if _target_of(_prompt_of(api, kwargs)) in {_P2_S1, _P2_S2}
    ]
    assert len(sentences) == 2
    assert all(kwargs["reasoning"] == {"effort": "low"} for kwargs in sentences)
    assert all(kwargs["max_output_tokens"] == 3 * 512 for kwargs in sentences)


@pytest.mark.parametrize("path", sorted(_MODELS))
def test_profile_books_every_call_under_its_own_stage(path):
    client = _ScriptedClient(path, "ladder")
    _run_block(client, "translate", "ladder", request_profile=_profile())

    stages = _stages()
    # On the Chat path the refused Responses call is not an answer and is not booked.
    answered = [name for name, _ in client.calls if not (path == "chat" and name == "responses.create")]
    assert set(stages) == {"literary_polish"}
    assert stages["literary_polish"]["model_call_count"] == len(answered) == 5


def test_without_a_profile_calls_stay_text_generation():
    client = _ScriptedClient("chat", "ladder")
    _run_block(client, "translate", "ladder")
    assert set(_stages()) == {model_accounting.STAGE_TEXT_GENERATION}


def test_ladder_divides_against_the_budget_of_the_profile(monkeypatch):
    """FR-006: the ladder sizes its sentence groups from the SAME multiplied budget."""

    events = _capture_events(monkeypatch, generation)
    sentence = "The harbour clock struck " + "once more and again, " * 22 + "and then fell silent."
    # Half of it is over 4 096 (the m = 3 limit) and the whole is under 12 288 (the m = 1 one).
    divisible = " ".join([sentence] * 20)
    assert 2 * 4096 < len(divisible) < 12288
    undividable = sentence * 9  # no whitespace after any terminal: one sentence
    assert 4096 < len(undividable) < 12288

    outcome = generation._ladder_translate_unit(
        client=_ScriptedClient("responses", "incomplete", answer=lambda _scenario, _target: _INCOMPLETE),  # type: ignore[arg-type]
        model="anthropic/claude-haiku-5.5",
        system_prompt="system",
        unit_text=undividable,
        unit_label="p0001",
        context_before="",
        context_after="",
        max_retries=1,
        block_index=0,
        request_profile=_profile(),
    )
    assert outcome.text is None
    ceiling = [context for _, event, context in events if event == "degradation_ladder_sentence_exceeds_output_ceiling"]
    assert ceiling and ceiling[0]["budgetable_chars"] == 4096

    assert len(generation._ladder_sentence_groups(divisible)) == 2
    assert len(generation._ladder_sentence_groups(divisible, budget_multiplier=3.0)) == 3
