"""Spec 070 FR-004: the audiobook system prompt, tested by how it is assembled.

The old tests of this prompt (``tests/test_config.py``) asserted that phrases were present, which
passes for any text that happens to contain them.  These tests assert the properties of the
assembled string instead (``contracts/prompts.md`` section 0): it does not depend on the language
pair, the intensity or the document context; it carries nothing of the shared translate/edit
template; its example pairs obey the rule the prompt states; the repair variant swaps only the
mode instructions and drops the example.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

import docxaicorrector.core.config as config
from docxaicorrector.pipeline.support import build_system_prompt_arguments

_PROMPTS = Path(config.PROMPTS_DIR)
_MARKER = re.compile(r"\[\[DOCX_PARA_[A-Za-z0-9_.]+\]\]")
_ALLOWED_BRACKETS = ("[CONTEXT BEFORE]", "[TARGET BLOCK]", "[CONTEXT AFTER]")


def _load(**overrides: str) -> str:
    config.load_system_prompt.cache_clear()
    try:
        arguments = {"operation": "audiobook", "source_language": "en", "target_language": "ru"}
        arguments.update(overrides)
        return config.load_system_prompt(**arguments)
    finally:
        config.load_system_prompt.cache_clear()


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8").strip()


def _sections(prompt: str) -> dict[str, str]:
    parts = re.split(r"^### (.+)$", prompt, flags=re.MULTILINE)
    return {parts[index].strip(): parts[index + 1].strip() for index in range(1, len(parts) - 1, 2)}


def test_prompt_does_not_depend_on_language_pair_intensity_or_context():
    baseline = _load()
    variants = [
        _load(source_language="auto", target_language="en"),
        _load(source_language="de", target_language="de"),
        _load(source_language="not-a-language", target_language="not-a-language-either"),
        _load(editorial_intensity="conservative"),
        _load(editorial_intensity="not-an-intensity"),
        _load(document_context_prompt="Книга о вымышленном городе. Глоссарий: ратуша -> town hall."),
    ]
    assert all(variant == baseline for variant in variants)


def test_prompt_has_no_unfilled_placeholders_or_template_markup():
    prompt = _load()
    assert "{" not in prompt and "}" not in prompt
    assert "[[IF" not in prompt and "[[END" not in prompt


def test_prompt_names_no_language_and_carries_no_intensity_text():
    prompt = _load()
    for language in config.DEFAULT_SUPPORTED_LANGUAGES:
        assert language.label not in prompt
    for intensity in config.EDITORIAL_INTENSITY_VALUES:
        first_line = _read(f"editorial_intensity_{intensity}.txt").splitlines()[0]
        distinctive = first_line.split("{target_language}")[0].strip()
        assert distinctive and distinctive not in prompt


def test_prompt_shares_no_line_with_the_translate_edit_template():
    prompt_lines = {line.strip() for line in _load().splitlines() if line.strip()}
    shared = {line.strip() for line in _read("system_prompt.txt").splitlines() if len(line.strip()) > 25}
    assert prompt_lines & shared == set()


def test_prompt_has_no_bracket_tags_beyond_the_input_format_and_paragraph_markers():
    prompt = _load()
    stripped = _MARKER.sub("", prompt)
    for allowed in _ALLOWED_BRACKETS:
        stripped = stripped.replace(allowed, "")
    assert re.findall(r"\[[^\[\]]*\]", stripped) == []


def test_prompt_sections_are_the_contract_sections_in_order():
    sections = list(_sections(_load()))
    assert sections == ["ЦЕЛЬ", "ИНСТРУКЦИИ РЕЖИМА", "РАБОТА С КОНТЕКСТОМ", "МАРКЕРЫ АБЗАЦЕВ", "ВЫВОД", "ПРИМЕР", "БЕЗОПАСНОСТЬ"]


def test_marker_section_names_the_marker_and_forbids_an_empty_paragraph():
    section = _sections(_load())["МАРКЕРЫ АБЗАЦЕВ"]
    assert "[[DOCX_PARA_" in section
    assert "пуст" in section


def test_mode_instructions_and_example_are_substituted_into_their_sections():
    sections = _sections(_load())
    assert sections["ИНСТРУКЦИИ РЕЖИМА"] == _read("operation_audiobook.txt")
    assert sections["ПРИМЕР"] == _read("example_audiobook.txt")


def _example_pairs() -> list[tuple[str, str]]:
    body = _read("example_audiobook.txt")
    pairs = []
    for chunk in body.split("Пример принципа:")[1:]:
        _, rest = chunk.split("Вход:", 1)
        source, result = rest.split("Выход:", 1)
        pairs.append((source.strip(), result.strip()))
    return pairs


def test_every_example_is_labelled_as_a_principle_and_has_a_pair():
    pairs = _example_pairs()
    assert 3 <= len(pairs) <= 4
    assert _read("example_audiobook.txt").count("Пример принципа:") == len(pairs)


def test_example_pairs_keep_the_same_markers_with_non_empty_text_under_each():
    for source, result in _example_pairs():
        assert _MARKER.findall(source) == _MARKER.findall(result)
        assert _MARKER.findall(result)
        for chunk in _MARKER.split(result)[1:]:
            assert chunk.strip()


def test_example_results_are_readable_aloud():
    """What the examples teach: no digits, no signs, no all-capital words in the results."""

    for _, result in _example_pairs():
        text = _MARKER.sub("", result)
        assert not re.search(r"\d", text)
        assert not re.search(r"[%№§&€$£]", text)
        assert not re.search(r"\b[А-ЯЁA-Z]{4,}\b", text)
        assert "[" not in text and "(" not in text


def test_repair_variant_is_the_same_template_with_repair_instructions_and_no_example():
    default = _sections(_load())
    repair = _sections(_load(prompt_variant="repair"))
    assert repair["ИНСТРУКЦИИ РЕЖИМА"] == _read("operation_audiobook_repair.txt")
    assert "ПРИМЕР" not in repair
    for name in ("ЦЕЛЬ", "РАБОТА С КОНТЕКСТОМ", "МАРКЕРЫ АБЗАЦЕВ", "ВЫВОД", "БЕЗОПАСНОСТЬ"):
        assert repair[name] == default[name]
    assert _read("example_audiobook.txt") not in _load(prompt_variant="repair")


def test_repair_variant_also_ignores_language_intensity_and_context():
    assert _load(prompt_variant="repair") == _load(
        prompt_variant="repair",
        source_language="auto",
        target_language="en",
        editorial_intensity="conservative",
        document_context_prompt="Любой контекст.",
    )


@pytest.mark.parametrize("operation", ["translate", "edit"])
def test_repair_variant_does_not_exist_for_other_operations(operation: str):
    with pytest.raises(RuntimeError):
        _load(operation=operation, prompt_variant="repair")


class _ForbiddenConfig(Mapping):
    def __getitem__(self, key):
        raise AssertionError(f"audiobook arguments must not read app_config[{key!r}]")

    def get(self, key, default=None):
        raise AssertionError(f"audiobook arguments must not read app_config.get({key!r})")

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0


def _context(operation: str, app_config) -> SimpleNamespace:
    return SimpleNamespace(
        processing_operation=operation,
        source_language="en",
        target_language="ru",
        app_config=app_config,
        document_context_prompt="Контекст книги.",
    )


def test_audiobook_arguments_do_not_read_intensity_and_carry_no_languages_or_context():
    arguments = build_system_prompt_arguments(context=_context("audiobook", _ForbiddenConfig()))
    assert arguments["operation"] == "audiobook"
    assert arguments["source_language"] == ""
    assert arguments["target_language"] == ""
    assert arguments["editorial_intensity"] == ""
    assert arguments["document_context_prompt"] == ""


def test_audiobook_repair_arguments_keep_the_variant():
    arguments = build_system_prompt_arguments(context=_context("audiobook", {}), prompt_variant="repair")
    assert arguments["prompt_variant"] == "repair"


def test_translate_arguments_still_read_intensity_and_languages():
    arguments = build_system_prompt_arguments(context=_context("translate", {"editorial_intensity_default": "conservative"}))
    assert arguments["editorial_intensity"] == "conservative"
    assert (arguments["source_language"], arguments["target_language"]) == ("en", "ru")


def test_arguments_for_audiobook_load_the_prompt_the_loader_builds():
    arguments = build_system_prompt_arguments(context=_context("audiobook", {}))
    config.load_system_prompt.cache_clear()
    try:
        assert config.load_system_prompt(**arguments) == _load()
    finally:
        config.load_system_prompt.cache_clear()
