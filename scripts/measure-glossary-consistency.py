"""Spec 063 P2 / SC-006: does a run's translation follow a glossary, term by term?

Companion to ``specs/063-translation-fidelity/research.md`` (R9) and ``tasks.md`` (T017, T020).
Standard library only, no repository import, no network, no model — run it with
``python3 -I``.

WHAT IT MEASURES
----------------
For every entry of a glossary (``source_term -> target_term``) and every recorded pair of a run
(``pairs.jsonl``: one object per source paragraph with ``source_text`` and ``target_text``) whose
SOURCE contains the term (whole words, case-insensitive, English plural and possessive allowed):
does the TARGET contain the fixed rendering? The rendering is matched by word stems — each word
of ``target_term`` longer than two letters is cut to its first ``max(3, len - 3)`` letters and
must open some word of the target text — so a declined Russian form counts («банковских
долговых денег» for «банковские долговые деньги») while a different word does not («Монтпилиер»
for «Монпелье», «устойчивость» for «жизнестойкость»).

Pairs the run delivered as their own source (``controlled_fallback``) are counted apart: the
model never rendered them, so they say nothing about consistency.

The same glossary applied to a run made WITHOUT it (2026-11-07) and to a run made WITH it is the
"with glossary and without" comparison of SC-006. This is a proxy built for repeatability; the
SC-006 verdict itself stays with the reviewers' terminology scripts, which also read the
non-adherent pairs (a pronoun or a legitimate paraphrase is not a second rendering).

USAGE
-----
    python3 -I scripts/measure-glossary-consistency.py --pairs <run>/pairs.jsonl \\
        --glossary <.run/run_glossaries/....json> [--json out.json] [--show 10]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_LETTERS = r"[^\W\d_]"
_TARGET_WORD_RE = re.compile(_LETTERS + r"+")


def _load_terms(path: Path) -> list[dict[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw = data.get("terms") if isinstance(data, dict) else data
    terms = []
    for entry in raw or []:
        if isinstance(entry, dict) and entry.get("source_term") and entry.get("target_term"):
            terms.append(
                {
                    "source_term": str(entry["source_term"]),
                    "target_term": str(entry["target_term"]),
                    "kind": str(entry.get("kind") or "term"),
                    "note": str(entry.get("note") or ""),
                }
            )
    return terms


def _load_pairs(path: Path) -> list[dict[str, Any]]:
    pairs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            pairs.append(json.loads(line))
    return pairs


def _source_pattern(source_term: str) -> re.Pattern[str]:
    words = [re.escape(word) for word in re.findall(_LETTERS + r"(?:" + _LETTERS + r"|['’\-])*", source_term)]
    if not words:
        return re.compile(r"(?!x)x")
    body = r"[\s\-]+".join(words)
    return re.compile(r"(?<![^\W_])" + body + r"(?:e?s)?(?:['’]s)?(?![^\W_])", re.IGNORECASE)


def _fold(text: str) -> str:
    return text.lower().replace("ё", "е")


def _target_stems(target_term: str) -> list[str]:
    stems = []
    for word in _TARGET_WORD_RE.findall(_fold(target_term)):
        if len(word) <= 2:
            continue
        stems.append(word[: max(3, len(word) - 3)])
    return stems


def _target_has(stems: list[str], target_text: str) -> bool:
    words = _TARGET_WORD_RE.findall(_fold(target_text))
    return bool(stems) and all(any(word.startswith(stem) for word in words) for stem in stems)


def _strip_markup(text: str) -> str:
    return re.sub(r"\*+", "", text or "")


def measure(pairs: list[dict[str, Any]], terms: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for term in terms:
        pattern = _source_pattern(term["source_term"])
        stems = _target_stems(term["target_term"])
        source_pairs = adherent = fallback = 0
        other_idx: list[int] = []
        for pair in pairs:
            if pair.get("missing"):
                continue
            if not pattern.search(_strip_markup(str(pair.get("source_text") or ""))):
                continue
            if pair.get("controlled_fallback"):
                fallback += 1
                continue
            source_pairs += 1
            if _target_has(stems, str(pair.get("target_text") or "")):
                adherent += 1
            else:
                other_idx.append(int(pair.get("idx", -1)))
        rows.append(
            {
                **term,
                "target_stems": stems,
                "source_pairs": source_pairs,
                "adherent_pairs": adherent,
                "adherence": round(adherent / source_pairs, 4) if source_pairs else None,
                "controlled_fallback_pairs": fallback,
                "other_idx": other_idx,
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--show", type=int, default=8, help="non-adherent idx printed per term")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    rows = measure(_load_pairs(args.pairs), _load_terms(args.glossary))
    measured = [row for row in rows if row["source_pairs"]]
    full = [row for row in measured if row["adherence"] == 1.0]
    ninety = [row for row in measured if (row["adherence"] or 0) >= 0.9]
    for row in sorted(rows, key=lambda item: (item["adherence"] is None, item["adherence"] or 0)):
        share = "—" if row["adherence"] is None else f"{row['adherence']:.0%}"
        print(
            f"{share:>5}  {row['adherent_pairs']:>4}/{row['source_pairs']:<4} fb={row['controlled_fallback_pairs']:<3} "
            f"{row['source_term']} -> {row['target_term']}  other idx: {row['other_idx'][: args.show]}"
        )
    print(
        f"terms={len(rows)} measured={len(measured)} all_pairs_follow={len(full)} "
        f"at_least_90pct={len(ninety)} (share of measured: "
        f"{(len(full) / len(measured)) if measured else 0:.0%} / {(len(ninety) / len(measured)) if measured else 0:.0%})"
    )
    if args.json:
        args.json.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
