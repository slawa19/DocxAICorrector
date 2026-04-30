from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


_SUPPORTED_RESPONSE_TEXT_TYPES = frozenset({"output_text", "text"})


@dataclass(frozen=True)
class ResponseTextTraversal:
    raw_output_text: str | None
    collected_texts: tuple[str, ...]
    saw_output_items: bool
    saw_supported_text_shape: bool
    saw_empty_content_container: bool


def read_response_field(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _coerce_response_text_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    nested_value = read_response_field(value, "value")
    if isinstance(nested_value, str):
        return nested_value
    return None


def _extract_text_from_content_item(content_item: object, *, unsupported_message: str) -> tuple[str | None, bool]:
    item_type = read_response_field(content_item, "type")
    if item_type not in _SUPPORTED_RESPONSE_TEXT_TYPES:
        return None, False
    text_value = _coerce_response_text_value(read_response_field(content_item, "text"))
    if text_value is None:
        raise RuntimeError(unsupported_message)
    return text_value, True


def collect_response_text_traversal(response: object, *, unsupported_message: str) -> ResponseTextTraversal:
    output_text = getattr(response, "output_text", None)
    raw_output_text: str | None = None
    if output_text is not None:
        if not isinstance(output_text, str):
            raise RuntimeError(unsupported_message)
        raw_output_text = output_text
        if output_text.strip():
            return ResponseTextTraversal(
                raw_output_text=raw_output_text,
                collected_texts=(output_text,),
                saw_output_items=False,
                saw_supported_text_shape=True,
                saw_empty_content_container=False,
            )

    output_items = read_response_field(response, "output")
    if output_items is None:
        return ResponseTextTraversal(
            raw_output_text=raw_output_text,
            collected_texts=(),
            saw_output_items=False,
            saw_supported_text_shape=False,
            saw_empty_content_container=False,
        )
    if isinstance(output_items, (str, bytes)) or not isinstance(output_items, Iterable):
        raise RuntimeError(unsupported_message)

    collected_texts: list[str] = []
    saw_output_items = False
    saw_supported_text_shape = False
    saw_empty_content_container = False

    for output_item in output_items:
        saw_output_items = True

        direct_text, direct_supported = _extract_text_from_content_item(
            output_item,
            unsupported_message=unsupported_message,
        )
        if direct_supported:
            saw_supported_text_shape = True
            if direct_text:
                collected_texts.append(direct_text)
            continue

        content_items = read_response_field(output_item, "content")
        if content_items is None:
            continue
        if isinstance(content_items, (str, bytes)) or not isinstance(content_items, Iterable):
            raise RuntimeError(unsupported_message)

        content_list = list(content_items)
        if not content_list:
            saw_empty_content_container = True
            continue

        for content_item in content_list:
            extracted_text, supported = _extract_text_from_content_item(
                content_item,
                unsupported_message=unsupported_message,
            )
            if not supported:
                continue
            saw_supported_text_shape = True
            if extracted_text:
                collected_texts.append(extracted_text)

    return ResponseTextTraversal(
        raw_output_text=raw_output_text,
        collected_texts=tuple(collected_texts),
        saw_output_items=saw_output_items,
        saw_supported_text_shape=saw_supported_text_shape,
        saw_empty_content_container=saw_empty_content_container,
    )
