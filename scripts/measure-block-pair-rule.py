"""The pair rule counted at BLOCK granularity, on the five recorded runs.

Companion to ``scripts/measure-translation-signal.py`` and to
``specs/059-verdict-never-reaches-the-screen/measurement-translation-signal.md``. That
measurement counted the pair rule ("the delivered text is byte-identical to its own
source") per PARAGRAPH and found 26 false alarms on 7 103 delivered records (its section
5). But the substitution the rule exists to catch happens on a BLOCK -- the unit the
pipeline sends to the model -- and the decision it feeds is taken on a block as well
(``pipeline/block_execution.py:1172``). The spec says so in as many words
(``spec.md``, "Гранулярность важнее признака").

So this script asks the same question at the granularity where the answer is used, on the
same recorded material, with no new run and no LLM: group the recorded pairs by
``call_index`` -- the dump's own record of which model call carried the paragraph -- and
fire the rule only when EVERY delivered paragraph of the block is byte-identical to its
own source and the block's source carries at least one letter.

WHAT THIS MEASURES, AND WHAT IT DOES NOT
----------------------------------------
It measures FALSE ALARMS: how often the rule would fire on a block the run delivered
normally. Every such block is printed in full, so the answer is a list to read, not a
ratio to trust.

It does NOT measure recall. The dumps are survivor-biased by construction (measurement
section 9): ``after`` records what the MODEL returned, and a controlled fallback
substitutes the source AFTER that answer is rejected, so a substituted block appears in
the dump as a normal (rejected) answer, not as a substitution. Any "completeness" number
computed from these files counts survivors. Recall is a prediction here, not a
measurement.

DATA
----
    artifacts/audiobook_final_run/creating_wealth/all_paragraph_pairs.jsonl
    artifacts/audiobook_final_run/money_sustainability/all_paragraph_pairs.jsonl
    artifacts/audiobook_final_run/rethinking_money/all_paragraph_pairs.jsonl
    artifacts/audiobook_final_run/value_of_everything/all_paragraph_pairs.jsonl
    artifacts/audiobook_final_run/money_translate_docx/all_paragraph_pairs.jsonl

Those files are gitignored on purpose (``.gitignore:80``) and live on disk beside the run
that produced them. The next reader will not have them, so this script RUNS WITHOUT THEM:
a missing book prints SKIPPED naming the path, and the totals say how many books were
actually read. Standard library only, no network, no model.

USAGE
-----
    python3 scripts/measure-block-pair-rule.py [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = REPO_ROOT / "artifacts" / "audiobook_final_run"
BOOKS = (
    "creating_wealth",
    "money_sustainability",
    "rethinking_money",
    "value_of_everything",
    "money_translate_docx",
)
# "Carries a letter" in any script: the rule must not fire on a block that is nothing but
# digits, punctuation or markup, because there is nothing in it to translate. This is a
# Unicode word-character class minus digits and underscore -- not an alphabet, and not a
# threshold.
_LETTER_PATTERN = re.compile(r"[^\W\d_]", re.UNICODE)


def _load_blocks(path: Path) -> "OrderedDict[Any, list[dict[str, Any]]]":
    blocks: OrderedDict[Any, list[dict[str, Any]]] = OrderedDict()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        blocks.setdefault(record.get("call_index"), []).append(record)
    return blocks


def _pair_rule_fires(records: list[dict[str, Any]]) -> bool:
    answered = [record for record in records if record.get("after") is not None]
    if not answered:
        return False
    if not all(
        str(record.get("after") or "").strip() == str(record.get("before") or "").strip()
        for record in answered
    ):
        return False
    return any(_LETTER_PATTERN.search(str(record.get("before") or "")) for record in answered)


def build_report() -> tuple[str, dict[str, Any]]:
    lines: list[str] = [
        "PAIR RULE AT BLOCK GRANULARITY -- false alarms on five recorded runs",
        "=" * 72,
        "",
    ]
    report: dict[str, Any] = {"books": {}, "totals": {}}
    total_blocks = 0
    total_firing = 0
    books_read = 0

    for book in BOOKS:
        path = RUN_DIR / book / "all_paragraph_pairs.jsonl"
        if not path.exists():
            lines.append(f"{book:<24} SKIPPED -- missing {path.relative_to(REPO_ROOT)}")
            report["books"][book] = {"skipped": True, "path": str(path)}
            continue
        books_read += 1
        blocks = _load_blocks(path)
        firing = [(call_index, records) for call_index, records in blocks.items() if _pair_rule_fires(records)]
        total_blocks += len(blocks)
        total_firing += len(firing)
        lines.append(
            f"{book:<24} records={sum(len(r) for r in blocks.values()):>5}  "
            f"blocks={len(blocks):>4}  pair rule fires on {len(firing)}"
        )
        report["books"][book] = {
            "skipped": False,
            "records": sum(len(r) for r in blocks.values()),
            "blocks": len(blocks),
            "firing_blocks": len(firing),
            "firing": [
                {
                    "call_index": call_index,
                    "paragraph_ids": [str(record.get("paragraph_id") or "") for record in records],
                    "source_texts": [str(record.get("before") or "") for record in records],
                }
                for call_index, records in firing
            ],
        }
        for call_index, records in firing:
            ids = ", ".join(str(record.get("paragraph_id") or "?") for record in records)
            lines.append(f"    call_index={call_index}  n={len(records)}  ids={ids}")
            for record in records:
                preview = str(record.get("before") or "").replace("\n", " ")
                lines.append(f"        {preview[:160]!r}")

    lines.append("")
    lines.append(
        f"TOTAL  books read {books_read}/{len(BOOKS)}  blocks {total_blocks}  firing {total_firing}"
    )
    lines.append("")
    lines.append(
        "Read the list, not the ratio. A firing block is a false alarm only if the run\n"
        "delivered it correctly; what separates one from a genuinely lost block is the\n"
        "REGION it sits in (spec 059, A-6), which this script does not resolve."
    )
    report["totals"] = {
        "books_read": books_read,
        "books_expected": len(BOOKS),
        "blocks": total_blocks,
        "firing_blocks": total_firing,
    }
    return "\n".join(lines), report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json", type=Path, default=None, help="also write the machine-readable report here")
    args = parser.parse_args(argv)
    text, report = build_report()
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
