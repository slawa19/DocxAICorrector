import io
import zipfile
from types import SimpleNamespace
from typing import Any, cast

import lxml.etree as etree
import pytest
from docx import Document
from docx.document import Document as DocxDocument
from docx.styles.style import ParagraphStyle, _TableStyle

from PIL import Image

import generation
import image_shared
from image_generation import _normalize_generated_document_background

_THEME_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
_DRAWINGML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _as_openai_client(client: object) -> Any:
    return cast(Any, client)


def _as_paragraph_style(style: object) -> ParagraphStyle:
    return cast(ParagraphStyle, style)


def _as_table_style(style: object) -> _TableStyle:
    return cast(_TableStyle, style)


def _pt(value: object) -> float:
    return cast(Any, value).pt


def _numbering_level_signature(level: Any) -> dict[str, str | None]:
    level_xml = cast(Any, level)
    return {
        "num_fmt": _first_xpath_value(level_xml, './*[local-name()="numFmt"]/@*[local-name()="val"]'),
        "lvl_text": _first_xpath_value(level_xml, './*[local-name()="lvlText"]/@*[local-name()="val"]'),
        "left": _first_xpath_value(level_xml, './*[local-name()="pPr"]/*[local-name()="ind"]/@*[local-name()="left"]'),
        "hanging": _first_xpath_value(level_xml, './*[local-name()="pPr"]/*[local-name()="ind"]/@*[local-name()="hanging"]'),
        "after": _first_xpath_value(level_xml, './*[local-name()="pPr"]/*[local-name()="spacing"]/@*[local-name()="after"]'),
        "line": _first_xpath_value(level_xml, './*[local-name()="pPr"]/*[local-name()="spacing"]/@*[local-name()="line"]'),
        "line_rule": _first_xpath_value(level_xml, './*[local-name()="pPr"]/*[local-name()="spacing"]/@*[local-name()="lineRule"]'),
        "ascii_font": _first_xpath_value(level_xml, './*[local-name()="rPr"]/*[local-name()="rFonts"]/@*[local-name()="ascii"]'),
        "hansi_font": _first_xpath_value(level_xml, './*[local-name()="rPr"]/*[local-name()="rFonts"]/@*[local-name()="hAnsi"]'),
        "cs_font": _first_xpath_value(level_xml, './*[local-name()="rPr"]/*[local-name()="rFonts"]/@*[local-name()="cs"]'),
    }


def _first_xpath_value(node: Any, expression: str) -> str | None:
    values = cast(list[str], node.xpath(expression))
    return values[0] if values else None


def _find_matching_abstract_numbers(
    document: Any,
    *,
    num_fmt: str,
    level_texts: tuple[str, ...],
    body_font: str | None = None,
) -> list[Any]:
    numbering = document.part.numbering_part.element
    matches = []
    for abstract_num in numbering.xpath('./*[local-name()="abstractNum"]'):
        levels = cast(list[Any], abstract_num.xpath('./*[local-name()="lvl"]'))
        if len(levels) != len(level_texts):
            continue
        signatures = [_numbering_level_signature(level) for level in levels]
        expected_signatures = [
            {
                "num_fmt": num_fmt,
                "lvl_text": level_text,
                "left": str(720 + (index * 360)),
                "hanging": "360",
                "after": "80",
                "line": "264",
                "line_rule": "auto",
                "ascii_font": body_font,
                "hansi_font": body_font,
                "cs_font": body_font,
            }
            for index, level_text in enumerate(level_texts)
        ]
        if signatures == expected_signatures:
            matches.append(abstract_num)
    return matches


def _has_num_instance_for_abstract_num(document: Any, abstract_num: Any) -> bool:
    numbering = document.part.numbering_part.element
    abstract_num_id = cast(str | None, abstract_num.get(generation.qn("w:abstractNumId")))
    if abstract_num_id is None:
        return False
    return bool(
        numbering.xpath(
            f'./*[local-name()="num"]/*[local-name()="abstractNumId" and @*[local-name()="val"]="{abstract_num_id}"]'
        )
    )


def _paragraph_num_id(paragraph: Any) -> str | None:
    return _first_xpath_value(
        paragraph._p,
        './*[local-name()="pPr"]/*[local-name()="numPr"]/*[local-name()="numId"]/@*[local-name()="val"]',
    )


def _paragraph_ilvl(paragraph: Any) -> str | None:
    return _first_xpath_value(
        paragraph._p,
        './*[local-name()="pPr"]/*[local-name()="numPr"]/*[local-name()="ilvl"]/@*[local-name()="val"]',
    )


def _find_abstract_num_for_num_id(document: Any, num_id: str) -> Any | None:
    numbering = document.part.numbering_part.element
    abstract_num_ids = cast(
        list[Any],
        numbering.xpath(
            f'./*[local-name()="num" and @*[local-name()="numId"]="{num_id}"]/*[local-name()="abstractNumId"]/@*[local-name()="val"]'
        ),
    )
    if not abstract_num_ids:
        return None

    abstract_num_id = cast(str, abstract_num_ids[0])
    abstract_nums = cast(
        list[Any],
        numbering.xpath(f'./*[local-name()="abstractNum" and @*[local-name()="abstractNumId"]="{abstract_num_id}"]'),
    )
    return abstract_nums[0] if abstract_nums else None


def _pandoc_available() -> bool:
    generation.ensure_pandoc_available.cache_clear()
    try:
        generation.ensure_pandoc_available()
    except RuntimeError:
        return False
    finally:
        generation.ensure_pandoc_available.cache_clear()
    return True


class RetryableError(Exception):
    status_code = 429


def test_generate_markdown_block_retries_once_then_returns(monkeypatch):
    attempts = []
    sleep_calls = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            raise RetryableError("rate limited")
        return SimpleNamespace(output_text="```markdown\nИсправленный текст\n```")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="   ",
        context_after="\n\t",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    user_payload = attempts[0]["input"][1]["content"][0]["text"]
    assert "[CONTEXT BEFORE]\n[no context]" in user_payload
    assert "[TARGET BLOCK]\ntarget" in user_payload
    assert "[CONTEXT AFTER]\n[no context]" in user_payload
    assert attempts[0]["max_output_tokens"] >= 512


def test_generate_markdown_block_retries_on_empty_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(output_text="")
        return SimpleNamespace(output_text="Исправленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-empty",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert len(logged_events) == 1
    assert logged_events[0][0][1] == "model_empty_response_shape"
    assert logged_events[0][1]["error_code"] == "empty_response"


def test_generate_markdown_block_retries_on_incomplete_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])
        return SimpleNamespace(status="completed", output_text="Исправленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-incomplete",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Исправленный текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert attempts[0]["max_output_tokens"] == 512
    assert attempts[1]["max_output_tokens"] == 1024
    assert logged_events[0][0][1] == "model_empty_response_shape"
    assert logged_events[0][1]["error_code"] == "incomplete_response"


def test_generate_markdown_block_uses_degraded_prompt_after_persistent_empty_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) <= 2:
            return SimpleNamespace(output_text="")
        return SimpleNamespace(output_text="Восстановленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-empty-recovery",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Восстановленный текст"
    assert len(attempts) == 3
    assert sleep_calls == [1]
    assert "[TARGET BLOCK ONLY]\ntarget" in attempts[-1]["input"][1]["content"][0]["text"]
    assert "[CONTEXT BEFORE]" not in attempts[-1]["input"][1]["content"][0]["text"]
    assert logged_events[-1][0][1] == "markdown_empty_response_recovery_started"


def test_generate_markdown_block_raises_on_empty_model_output(monkeypatch):
    logged_events = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="```\n\n```"))
    )
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-collapsed",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "collapsed_output" in str(exc)
        assert logged_events[0][1]["error_code"] == "collapsed_output"
    else:
        raise AssertionError("Expected RuntimeError for a collapsed model response")


def test_generate_markdown_block_retries_on_collapsed_output(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(output_text="```markdown\n   \n```")
        return SimpleNamespace(output_text="Итоговый текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-collapsed-retry",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == "Итоговый текст"
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert len(logged_events) == 1
    assert logged_events[0][1]["error_code"] == "collapsed_output"


def test_generate_markdown_block_retries_without_max_output_tokens_when_sdk_rejects_it():
    calls = []

    def create_response(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise TypeError("unexpected keyword argument 'max_output_tokens'")
        return SimpleNamespace(output_text="ok")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=1,
    )

    assert result == "ok"
    assert "max_output_tokens" in calls[0]
    assert "max_output_tokens" not in calls[1]


def test_generate_markdown_block_retries_without_temperature_when_model_rejects_it():
    calls = []

    class UnsupportedTemperatureError(Exception):
        status_code = 400

    def create_response(**kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise UnsupportedTemperatureError("Unsupported parameter: 'temperature' is not supported with this model.")
        return SimpleNamespace(output_text="ok")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5-mini",
        system_prompt="system",
        target_text="target",
        context_before="before",
        context_after="after",
        max_retries=1,
    )

    assert result == "ok"
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]


def test_generate_markdown_block_raises_after_persistent_empty_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        return SimpleNamespace(output_text="")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-persistent-empty",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=3,
        )
    except RuntimeError as exc:
        assert "empty_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when all attempts return an empty response")

    assert len(attempts) == 4
    assert sleep_calls == [1, 2]
    assert len(logged_events) == 5
    assert any(args[1] == "markdown_empty_response_recovery_started" for args, _ in logged_events)


def test_generate_markdown_block_falls_back_to_source_after_persistent_incomplete_response(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-persistent-incomplete",
    )

    target_text = "Короткий исходный абзац, который должен сохраниться без падения пайплайна."
    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text=target_text,
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == target_text
    assert len(attempts) == 3
    assert sleep_calls == [1]
    assert attempts[0]["max_output_tokens"] == 512
    assert attempts[1]["max_output_tokens"] == 1024
    assert attempts[2]["max_output_tokens"] == 1536
    assert any(args[1] == "markdown_empty_response_recovery_started" for args, _ in logged_events)
    assert logged_events[-1][0][1] == "markdown_incomplete_response_source_fallback"


def test_generate_markdown_block_falls_back_to_source_after_persistent_incomplete_response_for_long_block(monkeypatch):
    attempts = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        return SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-persistent-incomplete-long",
    )

    target_text = "Длинный блок. " * 150
    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text=target_text,
        context_before="before",
        context_after="after",
        max_retries=2,
    )

    assert result == target_text
    assert len(attempts) == 3
    assert logged_events[-1][0][1] == "markdown_incomplete_response_source_fallback"


def test_generate_markdown_block_passthrough_for_image_only_target(monkeypatch):
    logged_events = []
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(AssertionError("must not call API"))))
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-image-only",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="[[DOCX_IMAGE_img_001]]",
        context_before="before",
        context_after="after",
        max_retries=1,
    )

    assert result == "[[DOCX_IMAGE_img_001]]"
    assert logged_events[0][0][1] == "image_only_target_passthrough"


def test_generate_markdown_block_passthrough_for_placeholder_only_marker_target(monkeypatch):
    logged_events = []
    client = SimpleNamespace(responses=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(AssertionError("must not call API"))))
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-placeholder-only",
    )

    target_text = "[[DOCX_PARA_p0001]]\n[[DOCX_IMAGE_img_001]]"
    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text=target_text,
        context_before="before",
        context_after="after",
        max_retries=1,
        expected_paragraph_ids=["p0001"],
        marker_mode=True,
    )

    assert result == target_text
    assert logged_events[0][0][1] == "image_only_target_passthrough"


def test_generate_markdown_block_raises_on_missing_output_text(monkeypatch):
    logged_events = []
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace())
    )
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-missing-output",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "empty_response" in str(exc)
        assert logged_events[0][1]["error_code"] == "empty_response"
    else:
        raise AssertionError("Expected RuntimeError when output_text is missing")


def test_extract_response_output_text_falls_back_to_supported_response_output_items():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[SimpleNamespace(type="output_text", text="Структурированный ответ")]
            )
        ]
    )

    assert generation._extract_response_output_text(response) == "Структурированный ответ"


def test_extract_response_output_text_reads_supported_nested_text_value_from_response_output():
    response = SimpleNamespace(
        output=[
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="output_text",
                        text=SimpleNamespace(value="Ответ из value-поля"),
                    )
                ]
            )
        ]
    )

    assert generation._extract_response_output_text(response) == "Ответ из value-поля"


def test_generate_markdown_block_raises_on_unsupported_response_shape_in_output_items(monkeypatch):
    sleep_calls = []
    attempts = []

    def create_response(**_):
        attempts.append("call")
        return SimpleNamespace(
            output=[SimpleNamespace(content=[SimpleNamespace(type="refusal", text="not supported")])]
        )

    client = SimpleNamespace(
        responses=SimpleNamespace(create=create_response)
    )
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "unsupported_response_shape" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for unsupported response output shape")

    assert attempts == ["call"]
    assert sleep_calls == []


def test_generate_markdown_block_raises_when_supported_response_output_collapses_after_normalization(monkeypatch):
    logged_events = []
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=lambda **_: SimpleNamespace(
                output=[SimpleNamespace(content=[SimpleNamespace(type="output_text", text="```markdown\n   \n```")])]
            )
        )
    )
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-supported-collapse",
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "collapsed_output" in str(exc)
        assert logged_events[0][1]["error_code"] == "collapsed_output"
    else:
        raise AssertionError("Expected RuntimeError when normalized fallback output collapses")


def test_generate_markdown_block_raises_on_non_string_output_text():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text=["invalid"]))
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=1,
        )
    except RuntimeError as exc:
        assert "неподдерживаемом формате" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when output_text is not a string")


def test_generate_markdown_block_rejects_max_retries_less_than_one():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="unused"))
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=0,
        )
    except ValueError as exc:
        assert "max_retries" in str(exc)
    else:
        raise AssertionError("Expected ValueError when max_retries is less than 1")


def test_generate_markdown_block_rejects_non_integer_max_retries():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="unused"))
    )

    try:
        generation.generate_markdown_block(
            client=_as_openai_client(client),
            model="gpt-5.4",
            system_prompt="system",
            target_text="target",
            context_before="before",
            context_after="after",
            max_retries=cast(int, 1.5),
        )
    except TypeError as exc:
        assert "max_retries" in str(exc)
    else:
        raise AssertionError("Expected TypeError when max_retries is not an integer")


def test_extract_normalized_markdown_logs_empty_response_shape(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-empty-shape",
    )

    try:
        generation._extract_normalized_markdown(SimpleNamespace())
    except RuntimeError as exc:
        assert "empty_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for empty response shape")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "empty_response"
    assert kwargs["raw_output_len"] == 0


def test_extract_normalized_markdown_raises_on_incomplete_response(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-incomplete-shape",
    )

    try:
        generation._extract_normalized_markdown(
            SimpleNamespace(status="incomplete", output=[SimpleNamespace(type="reasoning", status="incomplete")])
        )
    except RuntimeError as exc:
        assert "incomplete_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for incomplete response")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "incomplete_response"


def test_extract_normalized_markdown_raises_hard_on_non_completed_response(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-non-completed-shape",
    )

    try:
        generation._extract_normalized_markdown(SimpleNamespace(status="failed"))
    except RuntimeError as exc:
        assert "non_completed_response" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for non-completed response")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "non_completed_response"


def test_incomplete_response_is_retryable():
    assert generation._is_retryable_empty_generation_error(RuntimeError("incomplete_response")) is True


def test_non_completed_response_is_not_retryable():
    assert generation._is_retryable_empty_generation_error(RuntimeError("non_completed_response")) is False


def test_extract_normalized_markdown_logs_collapsed_output_shape(monkeypatch):
    logged_events = []
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-collapsed-shape",
    )

    try:
        generation._extract_normalized_markdown(SimpleNamespace(output_text="```markdown\n\n```") )
    except RuntimeError as exc:
        assert "collapsed_output" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError for collapsed response shape")

    assert len(logged_events) == 1
    args, kwargs = logged_events[0]
    assert args[1] == "model_empty_response_shape"
    assert kwargs["error_code"] == "collapsed_output"
    assert kwargs["raw_output_len"] > 0


def test_ensure_pandoc_available_converts_os_error(monkeypatch):
    def raise_os_error():
        raise OSError("pandoc missing")

    generation.ensure_pandoc_available.cache_clear()
    monkeypatch.setattr(generation.pypandoc, "get_pandoc_version", raise_os_error)

    try:
        generation.ensure_pandoc_available()
    except RuntimeError as exc:
        assert "WSL runtime" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError when pandoc is unavailable")
    finally:
        generation.ensure_pandoc_available.cache_clear()


def test_convert_markdown_to_docx_bytes_calls_pandoc_and_reads_output(monkeypatch, tmp_path):
    monkeypatch.setattr(generation, "ensure_pandoc_available", lambda: None)

    def fake_convert_file(source_path, *, to, format, outputfile, extra_args):
        assert source_path.endswith("result.md")
        assert to == "docx"
        assert format == "md"
        assert any(str(argument).startswith("--reference-doc=") for argument in extra_args)
        with open(outputfile, "wb") as file_handle:
            file_handle.write(b"docx-bytes")

    monkeypatch.setattr(generation.pypandoc, "convert_file", fake_convert_file)

    result = generation.convert_markdown_to_docx_bytes("# Title")

    assert result == b"docx-bytes"


def test_normalize_model_output_strips_any_code_fence_language_tag():
    assert generation.normalize_model_output("```python\nprint(1)\n```") == "print(1)"


def test_normalize_model_output_returns_empty_for_whitespace_only_fenced_block():
    assert generation.normalize_model_output("```markdown\n   \n\t\n```") == ""


def test_parse_json_object_with_backtick_in_content():
    result = image_shared.parse_json_object(
        '```json\n{"key": "val`ue"}\n```',
        empty_message="empty",
        no_json_message="nojson",
    )

    assert result == {"key": "val`ue"}


def test_parse_json_object_fence_without_newline():
    result = image_shared.parse_json_object(
        '```{"key": 1}```',
        empty_message="empty",
        no_json_message="nojson",
    )

    assert result == {"key": 1}


def test_call_responses_create_with_retry_retries_without_timeout_on_final_attempt():
    calls = []

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise TypeError("unexpected keyword argument 'timeout'")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
    )

    assert result.output_text == "ok"
    assert calls == [
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        {"model": "gpt-5.4", "input": []},
    ]


def test_call_responses_create_with_retry_does_not_double_consume_budget_after_timeout_removal():
    class BudgetExceeded(RuntimeError):
        pass

    class Budget:
        def __init__(self):
            self.used_calls = 0

        def consume(self, operation_name):
            if self.used_calls >= 1:
                raise BudgetExceeded("exhausted")
            self.used_calls += 1

    calls = []
    budget = Budget()

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise TypeError("unexpected keyword argument 'timeout'")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
        budget=budget,
    )

    assert result.output_text == "ok"
    assert budget.used_calls == 1
    assert calls == [
        {"model": "gpt-5.4", "input": [], "timeout": 1},
        {"model": "gpt-5.4", "input": []},
    ]


def test_call_responses_create_with_retry_consumes_budget_only_after_retryable_success():
    class Budget:
        def __init__(self):
            self.used_calls = 0

        def ensure_available(self, operation_name):
            return None

        def consume(self, operation_name):
            self.used_calls += 1

    calls = []
    budget = Budget()

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise RetryableError("rate limited")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5.4", "input": []},
        max_retries=2,
        retryable_error_predicate=lambda exc: isinstance(exc, RetryableError),
        budget=budget,
    )

    assert result.output_text == "ok"
    assert len(calls) == 2
    assert budget.used_calls == 1


def test_call_responses_create_with_retry_retries_without_temperature_on_bad_request():
    calls = []

    class UnsupportedTemperatureError(Exception):
        status_code = 400

    class Client:
        class Responses:
            def create(self, **kwargs):
                calls.append(dict(kwargs))
                if len(calls) == 1:
                    raise UnsupportedTemperatureError("Unsupported parameter: 'temperature' is not supported with this model.")
                return SimpleNamespace(output_text="ok")

        responses = Responses()

    result = image_shared.call_responses_create_with_retry(
        Client(),
        {"model": "gpt-5-mini", "input": [], "temperature": 0.4},
        max_retries=1,
        retryable_error_predicate=lambda exc: False,
    )

    assert result.output_text == "ok"
    assert calls == [
        {"model": "gpt-5-mini", "input": [], "temperature": 0.4},
        {"model": "gpt-5-mini", "input": []},
    ]


def test_normalize_generated_document_background_whitens_dark_border_only():
    image = Image.new("RGBA", (12, 12), (0, 0, 0, 255))
    for x_coord in range(3, 9):
        for y_coord in range(3, 9):
            image.putpixel((x_coord, y_coord), (200, 0, 0, 255))

    normalized = _normalize_generated_document_background(image)

    assert normalized.getpixel((0, 0)) == (255, 255, 255, 255)
    assert normalized.getpixel((5, 5)) == (200, 0, 0, 255)


def test_generate_markdown_block_strips_image_placeholders_from_context(monkeypatch):
    captured_inputs = []

    def create_response(**kwargs):
        captured_inputs.append(kwargs.get("input", []))
        return SimpleNamespace(output_text="Исправленный текст")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="Основной текст без placeholder'а",
        context_before="Предшествующий блок\n\n[[DOCX_IMAGE_img_001]]\n\nДополнительный текст",
        context_after="[[DOCX_IMAGE_img_002]] Следующий блок",
        max_retries=1,
    )

    assert result == "Исправленный текст"
    assert len(captured_inputs) == 1
    all_prompt_text = " ".join(
        item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
        for message in captured_inputs[0]
        for content_item in (
            message.get("content", []) if isinstance(message, dict) else getattr(message, "content", [])
        )
        for item in ([content_item] if isinstance(content_item, dict) else [])
    )
    assert "[[DOCX_IMAGE_img_" not in all_prompt_text


def test_generate_markdown_block_marker_mode_preserves_markers_and_returns_clean_markdown(monkeypatch):
    captured_inputs = []

    def create_response(**kwargs):
        captured_inputs.append(kwargs.get("input", []))
        return SimpleNamespace(
            output_text="[[DOCX_PARA_p0001]]\nИсправленный заголовок\n\n[[DOCX_PARA_p0002]]\nИсправленный абзац"
        )

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="[[DOCX_PARA_p0001]]\n# Заголовок\n\n[[DOCX_PARA_p0002]]\nАбзац",
        context_before="before",
        context_after="after",
        max_retries=1,
        expected_paragraph_ids=["p0001", "p0002"],
        marker_mode=True,
    )

    assert result == "Исправленный заголовок\n\nИсправленный абзац"
    prompt_text = captured_inputs[0][1]["content"][0]["text"]
    assert "[TARGET BLOCK WITH MARKERS]" in prompt_text
    assert "Preserve every marker exactly" in prompt_text


def test_generate_markdown_block_marker_mode_retries_and_recovers_when_markers_are_lost(monkeypatch):
    attempts = []
    sleep_calls = []
    logged_events = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) <= 2:
            return SimpleNamespace(output_text="Маркеры потеряны")
        return SimpleNamespace(output_text="[[DOCX_PARA_p0001]]\nВосстановленный абзац")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)
    monkeypatch.setattr(
        generation,
        "log_event",
        lambda *args, **kwargs: logged_events.append((args, kwargs)) or "evt-marker-recovery",
    )

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="[[DOCX_PARA_p0001]]\nАбзац",
        context_before="before",
        context_after="after",
        max_retries=2,
        expected_paragraph_ids=["p0001"],
        marker_mode=True,
    )

    assert result == "Восстановленный абзац"
    assert len(attempts) == 3
    assert sleep_calls == [1]
    assert logged_events[-1][0][1] == "markdown_empty_response_recovery_started"
    assert "[TARGET BLOCK WITH MARKERS ONLY]" in attempts[-1]["input"][1]["content"][0]["text"]


def test_detect_context_leakage_finds_verbatim_fragment_absent_from_target():
    leaked_fragment = generation._detect_context_leakage(
        response_text=(
            "Исправленный блок. Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние."
        ),
        target_text="Исправленный блок.",
        context_before=(
            "Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние."
        ),
        context_after="Следующий абзац без совпадений.",
    )

    assert leaked_fragment == "Возможно, вы взяли эту книгу, думая"


def test_generate_markdown_block_retries_on_context_leakage_and_reinforces_prompt(monkeypatch):
    attempts = []
    sleep_calls = []

    def create_response(**kwargs):
        attempts.append(dict(kwargs))
        if len(attempts) == 1:
            return SimpleNamespace(
                output_text=(
                    "Исправленный блок. Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние."
                )
            )
        return SimpleNamespace(output_text="Исправленный блок.")

    client = SimpleNamespace(responses=SimpleNamespace(create=create_response))
    monkeypatch.setattr(generation.time, "sleep", sleep_calls.append)

    result = generation.generate_markdown_block(
        client=_as_openai_client(client),
        model="gpt-5.4",
        system_prompt="system",
        target_text="Исправленный блок.",
        context_before="Возможно, вы взяли эту книгу, думая, что она подскажет, как увеличить личное состояние.",
        context_after="Следующий абзац без совпадений.",
        max_retries=2,
    )

    assert result == "Исправленный блок."
    assert len(attempts) == 2
    assert sleep_calls == [1]
    assert generation._CONTEXT_LEAKAGE_RETRY_WARNING in attempts[1]["input"][1]["content"][0]["text"]


def test_strip_image_placeholders_removes_only_placeholder_tokens():
    result = generation._strip_image_placeholders(
        "Текст перед\n\n[[DOCX_IMAGE_img_001]]\n\nТекст после"
    )
    assert "[[DOCX_IMAGE_img_" not in result
    assert "Текст перед" in result
    assert "Текст после" in result


def test_build_reference_docx_configures_body_and_heading_baselines(tmp_path):
    reference_docx_path = tmp_path / "reference.docx"

    generation._build_reference_docx(reference_docx_path)

    document = Document(str(reference_docx_path))
    styles = document.styles

    normal_style = _as_paragraph_style(styles["Normal"])
    body_text_style = _as_paragraph_style(styles["Body Text"])
    list_paragraph_style = _as_paragraph_style(styles["List Paragraph"])
    caption_style = _as_paragraph_style(styles["Caption"])
    table_grid_style = _as_table_style(styles["Table Grid"])
    normal_attrs = _style_rfonts_attrs(document, "Normal")
    heading_attrs = _style_rfonts_attrs(document, "Heading 1")
    list_attrs = _style_rfonts_attrs(document, "List Paragraph")
    caption_attrs = _style_rfonts_attrs(document, "Caption")

    assert _pt(normal_style.font.size) == 11
    assert _pt(normal_style.paragraph_format.space_after) == 8
    assert normal_style.paragraph_format.line_spacing == 1.15
    assert "Aptos" not in normal_attrs.values()

    assert _pt(body_text_style.font.size) == 11
    assert _pt(body_text_style.paragraph_format.space_after) == 8
    assert body_text_style.paragraph_format.line_spacing == 1.15

    heading_sizes = []
    heading_space_before = []
    heading_space_after = []
    for level in range(1, 7):
        style = _as_paragraph_style(styles[f"Heading {level}"])
        heading_sizes.append(_pt(style.font.size))
        heading_space_before.append(_pt(style.paragraph_format.space_before))
        heading_space_after.append(_pt(style.paragraph_format.space_after))
        assert style.font.bold is True
        assert style.paragraph_format.keep_with_next is True
        assert style.paragraph_format.line_spacing == 1.1

    assert heading_sizes == sorted(heading_sizes, reverse=True)
    assert heading_space_before == sorted(heading_space_before, reverse=True)
    assert heading_space_after == sorted(heading_space_after, reverse=True)
    assert "Aptos Display" not in heading_attrs.values()

    assert _pt(list_paragraph_style.font.size) == 11
    assert _pt(list_paragraph_style.paragraph_format.space_before) == 0
    assert _pt(list_paragraph_style.paragraph_format.space_after) == 4
    assert list_paragraph_style.paragraph_format.line_spacing == 1.1
    assert "Aptos" not in list_attrs.values()

    assert _pt(caption_style.font.size) == 10
    assert caption_style.font.italic is True
    assert _pt(caption_style.paragraph_format.space_before) == 4
    assert _pt(caption_style.paragraph_format.space_after) == 10
    assert "Aptos" not in caption_attrs.values()

    assert _pt(table_grid_style.font.size) == 10
    assert table_grid_style.font.name is None


def test_build_reference_docx_ensures_decimal_and_bullet_numbering_definitions(tmp_path):
    reference_docx_path = tmp_path / "reference.docx"

    generation._build_reference_docx(reference_docx_path)

    document = Document(str(reference_docx_path))
    decimal_matches = _find_matching_abstract_numbers(
        document,
        num_fmt="decimal",
        level_texts=("%1.", "%1.%2.", "%1.%2.%3."),
    )
    bullet_matches = _find_matching_abstract_numbers(
        document,
        num_fmt="bullet",
        level_texts=(chr(0x2022), chr(0x25E6), chr(0x25AA)),
    )

    assert len(decimal_matches) == 1
    assert len(bullet_matches) == 1
    assert _has_num_instance_for_abstract_num(document, decimal_matches[0])
    assert _has_num_instance_for_abstract_num(document, bullet_matches[0])


def test_ensure_reference_numbering_definitions_is_idempotent_for_baseline_definitions():
    document = Document()

    generation._ensure_reference_numbering_definitions(document)
    generation._ensure_reference_numbering_definitions(document)

    decimal_matches = _find_matching_abstract_numbers(
        document,
        num_fmt="decimal",
        level_texts=("%1.", "%1.%2.", "%1.%2.%3."),
    )
    bullet_matches = _find_matching_abstract_numbers(
        document,
        num_fmt="bullet",
        level_texts=(chr(0x2022), chr(0x25E6), chr(0x25AA)),
    )

    assert len(decimal_matches) == 1
    assert len(bullet_matches) == 1
    assert _has_num_instance_for_abstract_num(document, decimal_matches[0])
    assert _has_num_instance_for_abstract_num(document, bullet_matches[0])


def test_build_reference_docx_without_font_config_does_not_write_aptos_to_numbering(tmp_path):
    reference_docx_path = tmp_path / "reference.docx"

    generation._build_reference_docx(reference_docx_path)

    with zipfile.ZipFile(reference_docx_path) as docx_archive:
        numbering_xml = docx_archive.read("word/numbering.xml").decode("utf-8")

    assert "Aptos" not in numbering_xml


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_convert_markdown_to_docx_bytes_applies_reference_doc_heading_baseline():
    result = generation.convert_markdown_to_docx_bytes("# Заголовок\n\nАбзац")

    document = Document(io.BytesIO(result))
    heading = document.paragraphs[0]
    heading_style = _as_paragraph_style(heading.style)

    assert heading.text == "Заголовок"
    assert heading_style.name == "Heading 1"
    assert heading_style.font.name is None
    assert _pt(heading_style.font.size) == 18
    assert _pt(heading_style.paragraph_format.space_before) == 18
    assert _pt(heading_style.paragraph_format.space_after) == 8
    assert heading_style.paragraph_format.keep_with_next is True
    assert heading_style.paragraph_format.line_spacing == 1.1

    with zipfile.ZipFile(io.BytesIO(result)) as docx_archive:
        document_xml = docx_archive.read("word/document.xml").decode("utf-8")
    assert "Заголовок" in document_xml


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_convert_markdown_to_docx_bytes_preserves_ordered_list_word_numbering_semantics():
    result = generation.convert_markdown_to_docx_bytes("1. Первый пункт\n2. Второй пункт\n3. Третий пункт")

    document = Document(io.BytesIO(result))
    list_paragraphs = document.paragraphs[:3]

    assert [paragraph.text for paragraph in list_paragraphs] == [
        "Первый пункт",
        "Второй пункт",
        "Третий пункт",
    ]

    num_ids = [_paragraph_num_id(paragraph) for paragraph in list_paragraphs]
    ilvls = [_paragraph_ilvl(paragraph) for paragraph in list_paragraphs]

    assert all(num_id is not None for num_id in num_ids)
    assert ilvls == ["0", "0", "0"]
    assert len(set(cast(list[str], num_ids))) == 1

    abstract_num = _find_abstract_num_for_num_id(document, cast(str, num_ids[0]))
    assert abstract_num is not None

    # Pandoc may choose any concrete numId and may materialize a full 9-level
    # decimal definition, so the stable contract here is real Word numbering
    # semantics for the emitted list paragraphs rather than an exact custom
    # reference-doc baseline signature.
    levels = cast(list[Any], abstract_num.xpath('./*[local-name()="lvl"]'))
    assert levels

    signatures = [_numbering_level_signature(level) for level in levels]
    assert all(signature["num_fmt"] == "decimal" for signature in signatures)
    assert signatures[0]["lvl_text"] == "%1."
    assert signatures[0]["left"] is not None
    assert signatures[0]["hanging"] is not None


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_convert_markdown_to_docx_bytes_preserves_superscript_and_subscript_inline_tags():
    result = generation.convert_markdown_to_docx_bytes("Alpha<sup>13</sup> beta\n\nH<sub>2</sub>O")

    document = Document(io.BytesIO(result))

    first_runs = document.paragraphs[0].runs
    second_runs = document.paragraphs[1].runs

    assert document.paragraphs[0].text == "Alpha13 beta"
    assert first_runs[1].text == "13"
    assert first_runs[1].font.superscript is True

    assert document.paragraphs[1].text == "H2O"
    assert second_runs[1].text == "2"
    assert second_runs[1].font.subscript is True


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_convert_markdown_to_docx_bytes_preserves_inline_html_line_breaks():
    result = generation.convert_markdown_to_docx_bytes("Line one<br/>Line two")

    document = Document(io.BytesIO(result))

    assert len(document.paragraphs) == 1
    assert "w:br" in document.paragraphs[0]._p.xml


# ---------------------------------------------------------------------------
# _patch_reference_theme_fonts
# ---------------------------------------------------------------------------

def _theme_font(doc, slot: str) -> str | None:
    """Return the Latin typeface for *slot* ('major' or 'minor') from theme XML."""
    try:
        theme_part = doc.part.part_related_by(_THEME_REL)
    except KeyError:
        return None
    root = etree.fromstring(theme_part.blob)
    elements = root.findall(f".//{{{_DRAWINGML_NS}}}{slot}Font/{{{_DRAWINGML_NS}}}latin")
    return elements[0].get("typeface") if elements else None


def test_patch_reference_theme_fonts_sets_both_slots():
    doc = Document()
    generation._patch_reference_theme_fonts(doc, body_font="Times New Roman", heading_font="Georgia")

    assert _theme_font(doc, "minor") == "Times New Roman"
    assert _theme_font(doc, "major") == "Georgia"


def test_patch_reference_theme_fonts_only_heading():
    doc = Document()
    original_minor = _theme_font(doc, "minor")
    generation._patch_reference_theme_fonts(doc, body_font=None, heading_font="Georgia")

    assert _theme_font(doc, "major") == "Georgia"
    assert _theme_font(doc, "minor") == original_minor  # body slot unchanged


def test_patch_reference_theme_fonts_only_body():
    doc = Document()
    original_major = _theme_font(doc, "major")
    generation._patch_reference_theme_fonts(doc, body_font="Arial", heading_font=None)

    assert _theme_font(doc, "minor") == "Arial"
    assert _theme_font(doc, "major") == original_major  # heading slot unchanged


def test_patch_reference_theme_fonts_does_not_touch_style_rfonts_ascii():
    """Patching the theme must not alter w:ascii on individual heading styles.

    The OOXML contract is that w:asciiTheme resolves via the theme, so
    w:ascii should remain unset unless an explicit style font override writes it.
    """
    doc = Document()
    from docx.oxml.ns import qn as _qn

    generation._patch_reference_theme_fonts(doc, body_font="Arial", heading_font="Georgia")

    h1 = doc.styles["Heading 1"]
    rpr = h1.element.find(_qn("w:rPr"))
    if rpr is not None:
        rfonts = rpr.find(_qn("w:rFonts"))
        if rfonts is not None:
            # w:ascii was NOT set by _patch_reference_theme_fonts — only the theme blob changed.
            assert rfonts.get(_qn("w:ascii")) is None


def _style_rfonts_attrs(doc: DocxDocument, style_name: str) -> dict[str, str]:
    from docx.oxml.ns import qn as _qn

    style = doc.styles[style_name]
    rpr = style.element.find(_qn("w:rPr"))
    if rpr is None:
        return {}
    rfonts = rpr.find(_qn("w:rFonts"))
    if rfonts is None:
        return {}
    return {key: value for key, value in rfonts.attrib.items()}


def test_build_reference_docx_applies_configured_fonts_to_effective_styles(tmp_path):
    from docx.oxml.ns import qn as _qn

    reference_docx_path = tmp_path / "reference.docx"

    generation._build_reference_docx(
        reference_docx_path,
        body_font="Times New Roman",
        heading_font="Georgia",
    )

    reference_doc = Document(reference_docx_path)
    body_attrs = _style_rfonts_attrs(reference_doc, "Normal")
    heading_attrs = _style_rfonts_attrs(reference_doc, "Heading 1")
    caption_attrs = _style_rfonts_attrs(reference_doc, "Caption")

    with zipfile.ZipFile(reference_docx_path) as docx_archive:
        numbering_xml = docx_archive.read("word/numbering.xml").decode("utf-8")

    assert body_attrs[_qn("w:ascii")] == "Times New Roman"
    assert body_attrs[_qn("w:hAnsi")] == "Times New Roman"
    assert heading_attrs[_qn("w:ascii")] == "Georgia"
    assert heading_attrs[_qn("w:hAnsi")] == "Georgia"
    assert caption_attrs[_qn("w:ascii")] == "Times New Roman"
    assert "Times New Roman" in numbering_xml
    assert _theme_font(reference_doc, "minor") == "Times New Roman"
    assert _theme_font(reference_doc, "major") == "Georgia"


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_convert_markdown_to_docx_bytes_theme_fonts_applied_when_configured():
    from docx.oxml.ns import qn as _qn

    result = generation.convert_markdown_to_docx_bytes(
        "# Заголовок\n\nАбзац",
        body_font="Times New Roman",
        heading_font="Georgia",
    )

    with zipfile.ZipFile(io.BytesIO(result)) as z:
        theme_xml = z.read("word/theme/theme1.xml").decode("utf-8")

    result_doc = Document(io.BytesIO(result))
    body_attrs = _style_rfonts_attrs(result_doc, "Normal")
    heading_attrs = _style_rfonts_attrs(result_doc, "Heading 1")

    assert "Georgia" in theme_xml
    assert "Times New Roman" in theme_xml
    assert body_attrs[_qn("w:ascii")] == "Times New Roman"
    assert heading_attrs[_qn("w:ascii")] == "Georgia"


@pytest.mark.skipif(not _pandoc_available(), reason="pandoc is unavailable in current runtime")
def test_convert_markdown_to_docx_bytes_no_font_args_leaves_theme_unchanged():
    """When no font args are passed the theme in the output must not contain
    any font name that was not already present in the python-docx default template.
    'Aptos' must NOT appear in the theme — it should only appear via w:ascii on styles.
    """
    result = generation.convert_markdown_to_docx_bytes("# Заголовок\n\nАбзац")

    with zipfile.ZipFile(io.BytesIO(result)) as z:
        theme_xml = z.read("word/theme/theme1.xml").decode("utf-8")
        numbering_xml = z.read("word/numbering.xml").decode("utf-8")
        styles_xml = z.read("word/styles.xml").decode("utf-8")

    # The default template uses Calibri/Cambria, not Aptos, in its theme slots.
    assert "Aptos" not in theme_xml
    assert "Aptos" not in numbering_xml
    assert "Aptos" not in styles_xml
