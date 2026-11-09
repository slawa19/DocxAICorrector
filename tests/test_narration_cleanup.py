"""Spec 070 T-E3 / T-E4: deterministic narration cleanup (FR-005). Only the unambiguous goes; letters,
diacritics, quotes, dashes, ellipsis, bracketed text and the signs the model must rewrite stay."""

from __future__ import annotations

import random

import pytest

from docxaicorrector.text.narration_cleanup import (
    clean_narration_paragraph,
    find_emoji_sequences,
    find_html_tags,
)


def clean(text: str) -> str:
    return clean_narration_paragraph(text).text


# --- emoji: whole sequences ---------------------------------------------------------------------

FAMILY = "\U0001F468‍\U0001F469‍\U0001F467"  # man ZWJ woman ZWJ girl
FLAG = "\U0001F1F7\U0001F1FA"  # two regional indicators
TAG_FLAG = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"  # black flag + tags + cancel
KEYCAP = "1️⃣"
SKIN_TONE = "\U0001F44D\U0001F3FD"  # thumbs up + medium skin tone
HEART = "❤️"  # red heart with VS16
RAINBOW_FLAG = "\U0001F3F3️‍\U0001F308"  # white flag VS16 ZWJ rainbow
EYE_IN_SPEECH = "\U0001F441‍\U0001F5E8"  # text-default base inside a ZWJ chain


@pytest.mark.parametrize(
    "sequence",
    [FAMILY, FLAG, TAG_FLAG, KEYCAP, SKIN_TONE, HEART, RAINBOW_FLAG, EYE_IN_SPEECH, "\U0001F600", "©️", "1⃣"],
    ids=["zwj_family", "flag", "tag_flag", "keycap", "skin_tone", "heart_vs16", "zwj_with_vs16", "zwj_text_base", "plain", "copyright_vs16", "keycap_no_vs16"],
)
def test_emoji_sequence_is_removed_whole(sequence: str) -> None:
    assert find_emoji_sequences(f"a{sequence}b") == [(1, 1 + len(sequence))]
    assert clean(f"Слово {sequence} дальше.") == "Слово дальше."
    result = clean_narration_paragraph(f"Слово {sequence} дальше.")
    assert result.stats.emoji_sequence_count == 1


def test_emoji_between_letters_does_not_weld_the_words_and_at_the_end_leaves_no_space() -> None:
    assert clean("до\U0001F600после") == "до после"
    assert clean("Конец.\U0001F600") == "Конец."
    assert clean("Конец \U0001F600.") == "Конец."


def test_two_adjacent_sequences_are_two_spans() -> None:
    text = f"{FLAG}{HEART}"
    assert find_emoji_sequences(text) == [(0, 2), (2, 4)]


@pytest.mark.parametrize(
    "kept",
    [
        "Ёж и ёлка, café, naïve, Привет, мир",
        "й́ и е́ с комбинирующим ударением",
        "«кавычки», „лапки“, “angle”",
        "тире — длинное и – среднее",
        "многоточие… и три точки...",
        "[авторская вставка] остаётся",
        "№ 5, § 3, → стрелка, © без вариации",
        "Язык C# и 5 * 3 и #1 и 2",
        "текстовые по умолчанию ™ ↔ ☺",
        "ZWJ‍внутри и FE0F️ сам по себе",
        "одиночный региональный \U0001F1F7 и одиночный модификатор \U0001F3FD",
        "5️ цифра с селектором вариации остаётся",
        "snake_case_name и a_b",
    ],
)
def test_nothing_but_emoji_sequences_is_damaged(kept: str) -> None:
    assert clean(kept) == kept
    assert find_emoji_sequences(kept) == []


# --- HTML ---------------------------------------------------------------------------------------


def test_inline_tags_are_removed_and_their_content_kept() -> None:
    assert clean("<u>слово</u>") == "слово"
    assert clean("сло<b>во</b> и <i>другое</i>") == "слово и другое"
    assert clean('<span class="x" id=\'y\'>текст</span>') == "текст"
    assert clean("<sup>2</sup>") == "2"
    assert clean("м<sub>1</sub>") == "м1"


def test_br_and_block_tags_become_a_space_not_a_weld() -> None:
    assert clean("слово<br/>слово") == "слово слово"
    assert clean("слово<br>слово") == "слово слово"
    assert clean("слово<BR />слово") == "слово слово"
    assert clean("<p>а</p><p>б</p>") == "а б"
    assert clean("<ul><li>раз</li><li>два</li></ul>") == "раз два"


def test_a_lone_less_than_is_not_a_tag() -> None:
    assert clean("a < b и c > d") == "a < b и c > d"
    assert clean("5 <3 и 4> 2") == "5 <3 и 4> 2"
    assert find_html_tags("a < b и c > d") == []


def test_prose_with_valueless_words_between_angle_brackets_is_not_a_tag() -> None:
    assert clean("если a<b and c>d") == "если a<b and c>d"


def test_entities_are_expanded_only_when_terminated() -> None:
    assert clean("Том&amp;Джерри") == "Том&Джерри"
    assert clean("a&nbsp;b") == "a b"
    assert clean("дата&#8212;дата") == "дата—дата"
    assert clean("x&#x41;y") == "xAy"
    assert clean("?a=1&copy=2") == "?a=1&copy=2"  # no semicolon: not an entity
    assert clean("&unknownentity; остаётся") == "&unknownentity; остаётся"


def test_an_escaped_tag_is_stripped_the_same_way_once() -> None:
    assert clean("&lt;b&gt;слово&lt;/b&gt;") == "слово"


def test_html_counts_are_reported() -> None:
    stats = clean_narration_paragraph("<b>а</b>&amp;<br/>б").stats
    assert stats.html_tag_count == 3
    assert stats.html_entity_count == 1


# --- pipeline tokens, brackets, markdown, markers ----------------------------------------------


def test_only_pipeline_tokens_are_removed_from_square_brackets() -> None:
    assert clean("до [[DOCX_IMAGE_img_001]] после") == "до после"
    assert clean("до[[DOCX_TABLE_tbl_2]]после") == "до после"
    assert clean("[[x]] остаётся") == "[[x]] остаётся"
    assert clean("[авторская вставка] и [serious] и [Примеч. ред.]") == "[авторская вставка] и [serious] и [Примеч. ред.]"
    assert clean_narration_paragraph("[[DOCX_IMAGE_img_001]]").text == ""
    assert clean_narration_paragraph("а [[DOCX_IMAGE_img_001]]").stats.internal_token_count == 1


def test_heading_quote_and_bullet_prefixes_are_removed() -> None:
    assert clean("# Заголовок") == "Заголовок"
    assert clean("### Глубокий заголовок") == "Глубокий заголовок"
    assert clean("> цитата") == "цитата"
    assert clean("- пункт") == "пункт"
    assert clean("* пункт") == "пункт"
    assert clean("+ пункт") == "пункт"
    assert clean("• пункт") == "пункт"
    assert clean("● пункт") == "пункт"
    assert clean("◦ пункт") == "пункт"
    assert clean("‣ пункт") == "пункт"


def test_a_decoration_glyph_at_line_start_is_removed_as_a_separate_token() -> None:
    assert clean("★ Слово") == "Слово"  # a star
    assert clean("→ Слово") == "Слово"  # an arrow (Sm)
    assert clean("★★ Слово") == "Слово"
    assert clean("★Слово") == "★Слово"  # welded: not a separate token
    assert clean("Слово ★ слово") == "Слово ★ слово"  # only at line start


def test_numero_sign_at_line_start_is_not_a_decoration() -> None:
    assert clean("№ 5 в списке") == "№ 5 в списке"


def test_a_year_before_a_period_is_not_a_list_marker() -> None:
    assert clean("1990. Год") == "1990. Год"
    assert clean("2. пункт") == "2. пункт"


def test_a_bullet_glyph_welded_inside_a_token_is_left_alone() -> None:
    assert clean("4●5") == "4●5"
    assert clean("Значение 4●5 осталось.") == "Значение 4●5 осталось."


def test_a_bullet_glyph_behind_other_prefix_is_removed() -> None:
    assert clean("> • пункт") == "пункт"
    assert clean("## ● Заголовок") == "Заголовок"


def test_links_keep_their_text_and_bare_urls_are_left_for_the_detector() -> None:
    assert clean("[текст](http://x.y)") == "текст"
    assert clean("см. https://x.org дальше") == "см. https://x.org дальше"


def test_emphasis_and_backticks_are_removed_without_touching_intraword_markers() -> None:
    assert clean("**сильно** и *курсив* и __тоже__ и _так_") == "сильно и курсив и тоже и так"
    assert clean("код `x` здесь") == "код x здесь"
    assert clean("snake_case_name, a*b*c и 5 * 3 * 2") == "snake_case_name, a*b*c и 5 * 3 * 2"


def test_whitespace_is_collapsed_and_blank_lines_dropped() -> None:
    assert clean("  а \t  б  \n\n  в  ") == "а б\nв"
    assert clean("а\r\nб") == "а\nб"


def test_markdown_counts_are_reported() -> None:
    stats = clean_narration_paragraph("# **а** `б`").stats
    assert stats.markdown_syntax_count == 4
    assert clean_narration_paragraph("★ а").stats.decoration_marker_count == 1


# --- idempotence --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "# **Заголовок** <u>с</u> разметкой &amp; \U0001F600",
        "&amp;lt;b&amp;gt;x",
        "- - * пункт",
        "> # ## вложено",
        "★ ★ ★ текст",
        f"до {FAMILY}{FLAG} после [[DOCX_IMAGE_i_1]]",
        "a *b _c_ d* e",
    ],
)
def test_cleanup_is_idempotent(text: str) -> None:
    once = clean(text)
    assert clean(once) == once


def test_cleanup_is_idempotent_on_random_mixtures() -> None:
    alphabet = ["а", "б", " ", "\n", "#", "*", "_", "-", ">", "<", "b", "/", "&", ";", "amp", "lt", "gt", "`", "[", "]", "(", ")",
                "★", "→", "\U0001F600", "‍", "️", "1", "⃣", "•", "[[DOCX_IMAGE_a_1]]", "<br/>", "<u>", "</u>"]
    generator = random.Random(70)
    for _ in range(400):
        text = "".join(generator.choice(alphabet) for _ in range(generator.randint(1, 24)))
        once = clean(text)
        assert clean(once) == once, repr(text)


# --- purity guard (T-E8) ------------------------------------------------------------------------


@pytest.mark.parametrize("module", ["narration_cleanup", "narration_residue", "narration_coverage", "unicode_emoji_data"])
def test_narration_text_modules_import_neither_the_pipeline_nor_streamlit_nor_the_network(module: str) -> None:
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "src" / "docxaicorrector" / "text" / f"{module}.py"
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    forbidden = ("docxaicorrector.pipeline", "streamlit", "openai", "requests", "httpx", "urllib", "socket")
    assert not [name for name in imported if name.startswith(forbidden)], imported
