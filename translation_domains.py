from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
DOMAINS_DIR = PROMPTS_DIR / "domains"

_THEOLOGY_TERM_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Great Tribulation", re.compile(r"\bgreat tribulation\b", re.IGNORECASE)),
    ("rapture", re.compile(r"\brapture\b", re.IGNORECASE)),
    ("pre-tribulation", re.compile(r"\bpre[- ]tribulation\b", re.IGNORECASE)),
    ("mid-tribulation", re.compile(r"\bmid[- ]tribulation\b", re.IGNORECASE)),
    ("post-tribulation", re.compile(r"\bpost[- ]tribulation\b", re.IGNORECASE)),
    ("Antichrist", re.compile(r"\bantichrist\b", re.IGNORECASE)),
    ("mark of the beast", re.compile(r"\bmark of the beast\b", re.IGNORECASE)),
    ("Revelation", re.compile(r"\brevelation\b", re.IGNORECASE)),
    ("abomination of desolation", re.compile(r"\babomination of desolation\b", re.IGNORECASE)),
    ("dispensationalists", re.compile(r"\bdispensationalists?\b", re.IGNORECASE)),
)


@lru_cache(maxsize=8)
def load_domain_instructions(*, translation_domain: str) -> str:
    normalized = str(translation_domain or "").strip().lower()
    if not normalized or normalized == "general":
        return ""
    if normalized != "theology":
        return ""

    glossary_path = DOMAINS_DIR / "theology_glossary_ru.txt"
    try:
        glossary_text = glossary_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    if not glossary_text:
        return ""
    return (
        "ДОМЕН ПЕРЕВОДА: богословие / эсхатология.\n"
        "Соблюдайте терминологическую консистентность, предпочитайте естественную богословскую русскую речь, "
        "не подменяйте doctrinal nuance и не оставляйте англоязычные термины без необходимости.\n\n"
        "ГЛОССАРИЙ И ПРЕДПОЧТИТЕЛЬНЫЕ ЭКВИВАЛЕНТЫ:\n"
        f"{glossary_text}"
    )


def build_terminology_plan(*, source_text: str, translation_domain: str) -> str:
    normalized = str(translation_domain or "").strip().lower()
    if normalized != "theology":
        return ""

    hits: list[str] = []
    for label, pattern in _THEOLOGY_TERM_PATTERNS:
        if pattern.search(source_text) and label not in hits:
            hits.append(label)
    if not hits:
        return ""

    glossary_text = load_domain_instructions(translation_domain=normalized)
    if not glossary_text:
        return ""

    selected_lines: list[str] = []
    glossary_lines = glossary_text.splitlines()
    for hit in hits:
        for line in glossary_lines:
            if hit.casefold() in line.casefold() and line not in selected_lines:
                selected_lines.append(line)
                break
    if not selected_lines:
        return ""
    return "ТЕРМИНОЛОГИЧЕСКИЙ ПЛАН ДЛЯ ТЕКУЩЕГО ДОКУМЕНТА:\n" + "\n".join(selected_lines)


def build_translation_domain_instructions(*, translation_domain: str, source_text: str) -> str:
    domain_instructions = load_domain_instructions(translation_domain=translation_domain)
    if not domain_instructions:
        return ""
    terminology_plan = build_terminology_plan(source_text=source_text, translation_domain=translation_domain)
    if terminology_plan:
        return f"{domain_instructions}\n\n{terminology_plan}"
    return domain_instructions


__all__ = [
    "build_translation_domain_instructions",
    "build_terminology_plan",
    "load_domain_instructions",
]
