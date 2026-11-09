"""Generate ``src/docxaicorrector/text/unicode_emoji_data.py`` from Unicode's ``emoji-data.txt``.

Developer tool, not runtime: the product has no network and never runs this. The pinned data
version (15.1.0) is its own constant, not the runtime's ``unicodedata.unidata_version`` (CI runs
Python 3.12 = Unicode 15.0.0, 3.13 = 15.1.0). The runtime's Unicode MAJOR version must equal the
vendored one, so the emoji properties and the general categories never come from different major
releases (spec 070 research R1). A test fails when either fact drifts.

Source (download once, keep outside the repository):
    https://www.unicode.org/Public/15.1.0/ucd/emoji/emoji-data.txt

Run (WSL):
    bash -lc ". .venv/bin/activate && python scripts/generate-unicode-emoji-data.py <path-to-emoji-data.txt>"

The output is deterministic: the same input file yields the same bytes. ``--check`` compares the
module on disk with what the input would produce instead of writing it.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "src" / "docxaicorrector" / "text" / "unicode_emoji_data.py"
PINNED_VERSION = "15.1.0"
# (property name in emoji-data.txt, constant name in the generated module), in output order.
PROPERTIES: tuple[tuple[str, str], ...] = (
    ("Emoji", "EMOJI"),
    ("Emoji_Presentation", "EMOJI_PRESENTATION"),
    ("Emoji_Modifier", "EMOJI_MODIFIER"),
    ("Emoji_Modifier_Base", "EMOJI_MODIFIER_BASE"),
    ("Emoji_Component", "EMOJI_COMPONENT"),
    ("Extended_Pictographic", "EXTENDED_PICTOGRAPHIC"),
)
_LINE_PATTERN = re.compile(
    r"^(?P<start>[0-9A-Fa-f]{4,6})(?:\.\.(?P<end>[0-9A-Fa-f]{4,6}))?\s*;\s*(?P<prop>[A-Za-z_]+)\s*(?:#.*)?$"
)
_VERSION_PATTERN = re.compile(r"Emoji Version (\d+\.\d+)")


def parse_emoji_data(text: str) -> dict[str, list[tuple[int, int]]]:
    """Return ``{property: merged sorted (start, end) ranges}`` for the pinned properties."""
    wanted = {name for name, _ in PROPERTIES}
    ranges: dict[str, list[tuple[int, int]]] = {name: [] for name in wanted}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE_PATTERN.match(line)
        if match is None:
            raise ValueError(f"unparseable emoji-data line: {raw_line!r}")
        prop = match.group("prop")
        if prop not in wanted:
            continue
        start = int(match.group("start"), 16)
        end = int(match.group("end") or match.group("start"), 16)
        ranges[prop].append((start, end))
    return {name: _merge(items) for name, items in ranges.items()}


def _merge(items: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(items):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def render_module(source_bytes: bytes, version: str = PINNED_VERSION) -> str:
    data = parse_emoji_data(source_bytes.decode("utf-8"))
    for name, _ in PROPERTIES:
        if not data[name]:
            raise ValueError(f"property {name} has no ranges in the input; wrong file?")
    sha256 = hashlib.sha256(source_bytes).hexdigest()
    lines = [
        '"""Unicode Emoji property ranges (UTS #51), GENERATED - do not edit by hand.',
        "",
        f"Source: https://www.unicode.org/Public/{version}/ucd/emoji/emoji-data.txt",
        "Generator: scripts/generate-unicode-emoji-data.py (developer tool; the product never fetches data).",
        "The data version is pinned here (and as ``PINNED_VERSION`` in the generator), NOT taken from the runtime:",
        "CI runs Python 3.12 (Unicode 15.0.0) and 3.13 ships 15.1.0. The runtime's Unicode MAJOR version must equal the",
        "vendored one (15, so emoji properties and ``unicodedata`` categories never come from different major releases);",
        "general categories always come from the runtime. A test pins both facts.",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        f'UNICODE_EMOJI_DATA_VERSION = "{version}"',
        f'UNICODE_EMOJI_DATA_SHA256 = "{sha256}"',
        "",
    ]
    for prop, constant in PROPERTIES:
        lines.append(f"# {prop}")
        lines.append(f"{constant}: tuple[tuple[int, int], ...] = (")
        for start, end in data[prop]:
            lines.append(f"    (0x{start:04X}, 0x{end:04X}),")
        lines.append(")")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    parser.add_argument("emoji_data", type=Path, help="local copy of emoji-data.txt")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="compare with the output file instead of writing")
    args = parser.parse_args(argv)

    source_bytes = args.emoji_data.read_bytes()
    header_match = _VERSION_PATTERN.search(source_bytes.decode("utf-8")[:2000])
    if header_match is None or not PINNED_VERSION.startswith(header_match.group(1)):
        found = header_match.group(1) if header_match else "none"
        print(f"input is not Emoji Version {PINNED_VERSION} data (header says {found})", file=sys.stderr)
        return 2
    rendered = render_module(source_bytes)
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != rendered:
            print(f"{args.output} differs from what the input produces", file=sys.stderr)
            return 1
        print("up to date")
        return 0
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
