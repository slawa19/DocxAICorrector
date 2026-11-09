"""Spec 070 T-E2: the vendored Unicode Emoji data is pinned to the runtime's Unicode version, and the
generator that produces it is deterministic (research R1)."""

from __future__ import annotations

import importlib.util
import unicodedata
from pathlib import Path

import pytest

from docxaicorrector.text import unicode_emoji_data as data

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = REPO_ROOT / "scripts" / "generate-unicode-emoji-data.py"


def _in(ranges: tuple[tuple[int, int], ...], code: int) -> bool:
    return any(start <= code <= end for start, end in ranges)


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_unicode_emoji_data", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vendored_emoji_data_version_is_the_generators_pinned_version() -> None:
    assert data.UNICODE_EMOJI_DATA_VERSION == _load_generator().PINNED_VERSION


def test_runtime_unicode_major_version_equals_the_vendored_one() -> None:
    """Holds on Python 3.12 (Unicode 15.0.0) and 3.13 (15.1.0) alike: the emoji properties are
    15.x, the general categories come from the runtime; a different MAJOR would mix releases."""

    runtime_major = int(unicodedata.unidata_version.split(".")[0])
    vendored_major = int(data.UNICODE_EMOJI_DATA_VERSION.split(".")[0])
    assert runtime_major == vendored_major


def test_vendored_module_is_reproduced_by_the_generator_when_the_source_file_is_available() -> None:
    source = REPO_ROOT / ".run" / "emoji-data.txt"
    if not source.is_file():
        pytest.skip("emoji-data.txt is not vendored; download it from the URL in the module docstring to run this check")
    generator = _load_generator()
    expected = generator.render_module(source.read_bytes())
    actual = (REPO_ROOT / "src" / "docxaicorrector" / "text" / "unicode_emoji_data.py").read_text(encoding="utf-8")
    assert actual == expected


def test_unicode_emoji_data_records_the_source_digest() -> None:
    assert len(data.UNICODE_EMOJI_DATA_SHA256) == 64
    assert set(data.UNICODE_EMOJI_DATA_SHA256) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    ("code", "prop", "expected"),
    [
        (0x1F600, "EMOJI_PRESENTATION", True),  # grinning face
        (0x1F600, "EXTENDED_PICTOGRAPHIC", True),
        (0x1F3FB, "EMOJI_MODIFIER", True),  # light skin tone
        (0x1F3FB, "EMOJI_COMPONENT", True),
        (0x00A9, "EMOJI", True),  # copyright sign: emoji, text presentation by default
        (0x00A9, "EMOJI_PRESENTATION", False),
        (0x1F44D, "EMOJI_MODIFIER_BASE", True),  # thumbs up takes a skin tone
        (0x0031, "EMOJI_COMPONENT", True),  # digit: a keycap component
        (0x0031, "EMOJI_PRESENTATION", False),
        (0x200D, "EMOJI_COMPONENT", True),
        (0xFE0F, "EMOJI_COMPONENT", True),
        (0x2116, "EMOJI_PRESENTATION", False),  # numero sign
        (0x2116, "EMOJI", False),
        (0x2192, "EMOJI_PRESENTATION", False),  # rightwards arrow
        (0x2192, "EMOJI", False),
        (0x0416, "EMOJI", False),  # a letter
        (0x00E9, "EMOJI", False),
    ],
)
def test_known_code_points_sit_in_their_standard_sets(code: int, prop: str, expected: bool) -> None:
    assert _in(getattr(data, prop), code) is expected


def test_ranges_are_sorted_and_non_overlapping() -> None:
    for name in ("EMOJI", "EMOJI_PRESENTATION", "EMOJI_MODIFIER", "EMOJI_MODIFIER_BASE", "EMOJI_COMPONENT", "EXTENDED_PICTOGRAPHIC"):
        ranges = getattr(data, name)
        assert ranges, name
        for (start, end), (next_start, _) in zip(ranges, ranges[1:]):
            assert start <= end < next_start


SYNTHETIC = """\
# emoji-data.txt
# Used with Emoji Version 15.1 and subsequent minor revisions (if any)
0023          ; Emoji                # E0.0   [1] (#)       hash sign
0030..0039    ; Emoji_Component      # E0.0  [10] (0..9)    digits
0031..0032    ; Emoji                # fake overlap to merge
0033          ; Emoji                # adjacent, merges with the previous range
1F600         ; Emoji_Presentation   # grinning face
1F44D         ; Emoji_Modifier_Base  # thumbs up
1F3FB..1F3FF  ; Emoji_Modifier       # skin tones
00A9          ; Extended_Pictographic # copyright
0041          ; Unrelated_Property   # ignored
"""


def test_generator_merges_ranges_and_is_deterministic() -> None:
    generator = _load_generator()
    parsed = generator.parse_emoji_data(SYNTHETIC)
    assert parsed["Emoji"] == [(0x23, 0x23), (0x31, 0x33)]
    assert parsed["Emoji_Component"] == [(0x30, 0x39)]
    first = generator.render_module(SYNTHETIC.encode("utf-8"))
    second = generator.render_module(SYNTHETIC.encode("utf-8"))
    assert first == second
    assert first.endswith(")\n")
    assert "\r" not in first
    assert "(0x0031, 0x0033)," in first
    assert 'UNICODE_EMOJI_DATA_VERSION = "15.1.0"' in first


def test_generator_rejects_a_file_without_a_wanted_property() -> None:
    generator = _load_generator()
    with pytest.raises(ValueError):
        generator.render_module(b"0041 ; Unrelated_Property # x\n")


def test_generator_rejects_unparseable_lines() -> None:
    generator = _load_generator()
    with pytest.raises(ValueError):
        generator.parse_emoji_data("not a data line\n")
