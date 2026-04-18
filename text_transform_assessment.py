from __future__ import annotations

from collections import Counter
from typing import TypedDict


class TextTransformAssessment(TypedDict):
    dominant_language: str | None
    dominant_script: str
    target_language_script_match: bool | None
    mixed_script_detected: bool


_LANGUAGE_SCRIPT_MAP = {
    "ru": "cyrillic",
    "en": "latin",
    "de": "latin",
    "fr": "latin",
    "es": "latin",
    "it": "latin",
    "pl": "latin",
    "zh": "cjk",
    "ja": "cjk",
}


def expected_script_for_language(language_code: str | None) -> str | None:
    if language_code is None:
        return None
    normalized = language_code.strip().lower()
    if not normalized or normalized == "auto":
        return None
    return _LANGUAGE_SCRIPT_MAP.get(normalized)


def _classify_char_script(char: str) -> str | None:
    code_point = ord(char)
    if (
        0x0041 <= code_point <= 0x005A
        or 0x0061 <= code_point <= 0x007A
        or 0x00C0 <= code_point <= 0x024F
        or 0x1E00 <= code_point <= 0x1EFF
    ):
        return "latin"
    if (
        0x0400 <= code_point <= 0x04FF
        or 0x0500 <= code_point <= 0x052F
        or 0x2DE0 <= code_point <= 0x2DFF
        or 0xA640 <= code_point <= 0xA69F
        or 0x1C80 <= code_point <= 0x1C8F
    ):
        return "cyrillic"
    if (
        0x3040 <= code_point <= 0x309F
        or 0x30A0 <= code_point <= 0x30FF
        or 0x3400 <= code_point <= 0x4DBF
        or 0x4E00 <= code_point <= 0x9FFF
        or 0xF900 <= code_point <= 0xFAFF
        or 0xFF66 <= code_point <= 0xFF9D
    ):
        return "cjk"
    return None


def _script_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for char in text:
        script = _classify_char_script(char)
        if script is not None:
            counts[script] += 1
    return counts


def assess_text_transform_excerpt(
    text: str,
    *,
    target_language: str,
    excerpt_chars: int = 2000,
) -> TextTransformAssessment:
    excerpt = text[:excerpt_chars]
    counts = _script_counts(excerpt)
    if not counts:
        return {
            "dominant_language": None,
            "dominant_script": "unknown",
            "target_language_script_match": None,
            "mixed_script_detected": False,
        }

    dominant_script, dominant_count = counts.most_common(1)[0]
    mixed_script_detected = any(
        count >= 5 and count >= max(1, int(dominant_count * 0.1))
        for script, count in counts.items()
        if script != dominant_script
    )

    target_script = expected_script_for_language(target_language)
    target_language_script_match = None
    if target_script is not None and dominant_script != "unknown":
        target_language_script_match = dominant_script == target_script

    # Phase 1 only treats Russian as trivially knowable from script because it is
    # the only supported Cyrillic language. Latin and CJK targets remain advisory.
    dominant_language = "ru" if dominant_script == "cyrillic" and not mixed_script_detected else None
    return {
        "dominant_language": dominant_language,
        "dominant_script": dominant_script,
        "target_language_script_match": target_language_script_match,
        "mixed_script_detected": mixed_script_detected,
    }


def build_text_transform_warnings(
    *,
    operation: str,
    source_language: str,
    target_language: str,
    assessment: TextTransformAssessment,
) -> list[str]:
    warnings: list[str] = []

    def append_warning(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    dominant_language = assessment["dominant_language"]
    dominant_script = assessment["dominant_script"]
    target_language_script_match = assessment["target_language_script_match"]
    mixed_script_detected = assessment["mixed_script_detected"]
    source_script = expected_script_for_language(source_language)

    if operation == "translate" and source_language == target_language:
        append_warning(
            "Исходный и целевой язык совпадают. Если нужен только стилистический апгрейд текста, обычно лучше выбрать литературное редактирование."
        )

    if (
        source_language != "auto"
        and source_script is not None
        and dominant_script not in {"unknown", "mixed"}
        and source_script != dominant_script
    ):
        append_warning(
            "Указанный язык оригинала, вероятно, не совпадает со скриптом текста. Проверьте выбор языка перед запуском."
        )

    if mixed_script_detected:
        append_warning(
            "В отрывке обнаружено смешение скриптов или языковых вставок. Система будет стараться не трогать уже корректные фрагменты, но качество преобразования может быть неравномерным."
        )

    return warnings