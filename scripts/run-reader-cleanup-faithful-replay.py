"""Offline replay of the three recorded reader-cleanup runs. No LLM calls, no network.

Spec 052 claimed the three books replayed byte-identically, but the claim lived in a
throwaway script: the newest artifact under ``.run/reader_cleanup_faithful_replay/`` was
weeks older than the code it vouched for, so nobody could re-check it. This is that stand,
kept in the repository so the claim can be re-run and diffed.

What it does: for each recorded book it reconstructs the model's answers from the recorded
report (``accepted_cleanup_operations + ignored_cleanup_operations`` IS the proposed set),
feeds them back through ``run_reader_cleanup`` with a canned provider, and reports what the
current code makes of them — the sha256 of the delivered markdown, how many operations were
accepted and of which kinds, and why the rest were rejected. ``reproduces_recorded_accepted``
is the headline: True means today's code accepts exactly the operation set the recorded run
accepted.

Usage (WSL, repo root):

    . .venv/bin/activate
    export PYTHONPATH="$PWD/src:$PWD"
    python scripts/run-reader-cleanup-faithful-replay.py

    # write the summary somewhere else (e.g. a "before" snapshot to diff against)
    python scripts/run-reader-cleanup-faithful-replay.py --out /tmp/before.json

The default output path is tracked in git so the next person can diff a fresh run against
the committed one; the recorded inputs under ``.run/`` are NOT (``.run/`` is gitignored),
so on a clean checkout the script exits 2 and says which directory is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT_DIR / "src"


# Make the repo-root shared bootstrap importable, then pin src first (F5/R29).
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
from docxaicorrector_bootstrap import ensure_src_first_import_order

ensure_src_first_import_order(ROOT_DIR, SRC_ROOT)

from docxaicorrector.reader_cleanup_mvp import (  # noqa: E402
    ReaderCleanupConfig,
    build_cleanup_blocks,
    run_reader_cleanup,
)


RECORDED_RUN_DIR = ROOT_DIR / ".run" / "reader_cleanup_faithful_replay" / "20260618T124238Z_faithful_reclassify_replay"
DEFAULT_SUMMARY_PATH = ROOT_DIR / "artifacts" / "reader_cleanup_replay" / "faithful_replay_summary.json"
BOOKS = ("creating_wealth", "lietaer", "mazzucato")

# The fields a recorded operation entry shares with a model response item. Everything else
# on the entry (``chunk_index``, ``ignored_reason``, ``after_state``, ...) is bookkeeping
# the pass adds itself and must not be fed back in.
_RESPONSE_FIELDS = (
    "id",
    "text_hash",
    "operation",
    "reason",
    "confidence",
    "evidence_before",
    "expected_after_preview",
    "safety_note",
    "split_substrings",
    "noise_substring",
    "next_id",
    "next_text_hash",
    "pre_body_stub",
    "heading_substring",
    "body_substring",
    "post_body_continuation",
    "target_role",
)

_REPLAY_PLACEHOLDER = "replayed_from_recorded_report"


def _to_response_item(entry: dict[str, Any]) -> dict[str, Any]:
    item = {key: value for key, value in entry.items() if key in _RESPONSE_FIELDS}
    item.setdefault("operation", "delete_block")
    # Entries rolled back by the global delete-safety limit are serialised by
    # ``_serialize_delete_block`` alone, so they carry no audit strings. The response parser
    # requires them to be non-empty; they are never read when applying a delete.
    if not str(item.get("evidence_before") or "").strip():
        item["evidence_before"] = _REPLAY_PLACEHOLDER
    if not str(item.get("safety_note") or "").strip():
        item["safety_note"] = _REPLAY_PLACEHOLDER
    if item["operation"] != "delete_block" and "expected_after_preview" not in item:
        item["expected_after_preview"] = ""
    return item


def _responses_by_chunk(report: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    by_chunk: dict[int, list[dict[str, Any]]] = {}
    proposed = list(report["accepted_cleanup_operations"]) + list(report["ignored_cleanup_operations"])
    for entry in proposed:
        chunk_index = int(entry.get("chunk_index", 0))
        by_chunk.setdefault(chunk_index, []).append(_to_response_item(entry))
    return by_chunk


def _operation_key(entry: dict[str, Any]) -> str:
    return "|".join(
        str(entry.get(field, ""))
        for field in ("id", "operation", "reason", "expected_after_preview", "after_state")
    )


def replay_book(book: str) -> dict[str, Any]:
    book_dir = RECORDED_RUN_DIR / book
    raw_markdown = (book_dir / f"{book}.faithful.raw.md").read_text(encoding="utf-8")
    report = json.loads((book_dir / f"{book}.faithful.reader_cleanup_report.json").read_text(encoding="utf-8"))
    settings = report["cleanup_settings"]

    config = ReaderCleanupConfig(
        enabled=True,
        model=settings["model_selector"],
        chunk_size=settings["chunk_size"],
        overlap_blocks_before=settings["overlap_blocks_before"],
        overlap_blocks_after=settings["overlap_blocks_after"],
        global_plan_enabled=settings["global_plan_enabled"],
        policy=report["policy"],
    )
    by_chunk = _responses_by_chunk(report)

    def provider(_payload: dict[str, Any], chunk_index: int, _chunk_count: int) -> str:
        return json.dumps(
            {"cleanup_operations": by_chunk.get(chunk_index, []), "warnings": []},
            ensure_ascii=False,
        )

    result = run_reader_cleanup(
        markdown_text=raw_markdown,
        config=config,
        operation_provider=provider,
        repair_provider=None,
        global_plan_provider=None,
    )
    payload = result.report_payload
    accepted = list(payload["accepted_cleanup_operations"])
    ignored = list(payload["ignored_cleanup_operations"])
    replayed_keys = sorted(_operation_key(entry) for entry in accepted)
    recorded_keys = sorted(_operation_key(entry) for entry in report["accepted_cleanup_operations"])

    return {
        "book": book,
        "cleaned_markdown_sha256": hashlib.sha256(result.cleaned_markdown.encode("utf-8")).hexdigest(),
        "raw_block_count": payload["stats"]["raw_block_count"],
        "recorded_raw_block_count": report["stats"]["raw_block_count"],
        # A ``toc_like`` block is withheld from the model entirely, so this count is the
        # size of the pass's blind spot on this book.
        "toc_like_block_count": sum(1 for block in build_cleanup_blocks(raw_markdown) if block.is_toc_like),
        "chunk_count": payload["stats"]["cleanup_chunk_count"],
        "recorded_chunk_count": report["stats"]["cleanup_chunk_count"],
        "failed_chunk_count": payload["stats"]["failed_chunk_count"],
        "proposed_count": sum(len(items) for items in by_chunk.values()),
        "accepted_count": len(accepted),
        "accepted_by_operation": dict(sorted(Counter(str(e.get("operation", "delete_block")) for e in accepted).items())),
        "accepted_by_reason": dict(sorted(Counter(str(e.get("reason", "")) for e in accepted).items())),
        "ignored_count": len(ignored),
        "ignored_by_reason": dict(sorted(Counter(str(e.get("ignored_reason")) for e in ignored).items())),
        "recorded_accepted_count": len(recorded_keys),
        "reproduces_recorded_accepted": replayed_keys == recorded_keys,
        "accepted_only_in_replay": sorted(set(replayed_keys) - set(recorded_keys)),
        "accepted_only_in_recording": sorted(set(recorded_keys) - set(replayed_keys)),
        "accepted_keys": replayed_keys,
    }


def _print_book(data: dict[str, Any]) -> None:
    print(f"=== {data['book']}")
    print(f"    cleaned markdown sha256 : {data['cleaned_markdown_sha256']}")
    print(f"    blocks / chunks         : {data['raw_block_count']} (recorded {data['recorded_raw_block_count']})"
          f" / {data['chunk_count']} (recorded {data['recorded_chunk_count']}), failed {data['failed_chunk_count']}")
    print(f"    toc_like blocks         : {data['toc_like_block_count']}")
    print(f"    proposed / accepted     : {data['proposed_count']} / {data['accepted_count']}"
          f" (recorded accepted {data['recorded_accepted_count']})")
    print(f"    accepted by operation   : {data['accepted_by_operation'] or '{}'}")
    print(f"    accepted by reason      : {data['accepted_by_reason'] or '{}'}")
    print(f"    ignored ({data['ignored_count']}) by reason:")
    for reason, count in sorted(data["ignored_by_reason"].items(), key=lambda item: (-item[1], item[0])):
        print(f"        {count:5d}  {reason}")
    print(f"    reproduces_recorded_accepted = {data['reproduces_recorded_accepted']}")
    for key in data["accepted_only_in_replay"]:
        print(f"        + only in replay    : {key}")
    for key in data["accepted_only_in_recording"]:
        print(f"        - only in recording : {key}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_SUMMARY_PATH,
        help=f"where to write the summary JSON (default: {DEFAULT_SUMMARY_PATH.relative_to(ROOT_DIR).as_posix()})",
    )
    parser.add_argument("--book", action="append", choices=BOOKS, help="replay only these books (repeatable)")
    args = parser.parse_args()

    if not RECORDED_RUN_DIR.is_dir():
        print(
            "recorded run not found: "
            f"{RECORDED_RUN_DIR.relative_to(ROOT_DIR).as_posix()}\n"
            "The recorded books live under .run/, which is gitignored — copy the recorded "
            "run into place before replaying.",
            file=sys.stderr,
        )
        return 2

    books = tuple(args.book) if args.book else BOOKS
    summary = {
        "recorded_run": RECORDED_RUN_DIR.name,
        "books": {book: replay_book(book) for book in books},
    }
    for data in summary["books"].values():
        _print_book(data)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"\nsummary written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
