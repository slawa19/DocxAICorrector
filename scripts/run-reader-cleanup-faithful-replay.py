"""Replay of the three recorded reader-cleanup runs.

Two modes. **Offline (the default)** makes no LLM calls and no network requests; it is the
canonical stand described below. **``--live``** runs the same three books through the same
``run_reader_cleanup`` against the real provider from the repository ``.env`` — that mode
COSTS MONEY (order 1.1-1.6M input tokens per book) and must be asked for explicitly. See
``### Live mode`` at the bottom of this docstring.


Spec 052 claimed the three books replayed byte-identically, but the claim lived in a
throwaway script: the newest artifact under ``.run/reader_cleanup_faithful_replay/`` was
weeks older than the code it vouched for, so nobody could re-check it. This is that stand,
kept in the repository so the claim can be re-run and diffed.

What it does: for each recorded book it reconstructs the model's answers from the recorded
report (``accepted_cleanup_operations + ignored_cleanup_operations`` IS the proposed set),
feeds them back through ``run_reader_cleanup`` with a canned provider, and reports what the
current code makes of them — the sha256 of the delivered markdown, how many operations were
accepted and of which kinds, and why the rest were rejected. ``reproduces_recorded_accepted``
says whether today's code accepts exactly the operation set the recorded run accepted.

The replay runs under today's DEFAULT allowed-operation set, which the summary records per book
as ``allowed_operations``. Since 2026-08-03 that is the two heading operations (spec 052), so
recorded ``remove_inline_noise`` / ``delete_block`` / ``split_block`` answers come back as
``operation_not_allowed_by_cleanup_contract`` — that is the current code's verdict, not a fault
in the recording.

**It is a diagnostic, not a target, and it is currently False for all three books.** Today's
code refuses operations that destroyed image anchors and no longer has ``reclassify_role`` at
all, so the recorded set cannot be reproduced without reintroducing the defects spec 052 was
written to remove. The baseline for "did my change move anything" is the committed summary at
``artifacts/reader_cleanup_replay/faithful_replay_summary.json`` — the previous state of the
CODE. ``accepted_only_in_replay`` / ``accepted_only_in_recording`` stay useful because *which*
operations diverge is how a surprise gets noticed. See spec 052,
``### Why the baseline is not the recorded run``.

Usage (WSL, repo root):

    . .venv/bin/activate
    export PYTHONPATH="$PWD/src:$PWD"
    python scripts/run-reader-cleanup-faithful-replay.py

    # write the summary somewhere else (e.g. a "before" snapshot to diff against)
    python scripts/run-reader-cleanup-faithful-replay.py --out /tmp/before.json

The default output path is tracked in git so the next person can diff a fresh run against
the committed one; the recorded inputs under ``.run/`` are NOT (``.run/`` is gitignored),
so on a clean checkout the script exits 2 and says which directory is missing.

### Live mode

``--live`` replaces the canned provider with the real one. It reads the SAME
``<book>.faithful.raw.md`` inputs (post-translation Russian markdown, before cleanup), so
no translation is re-run and no money is spent on it, and calls the model configured by
``DOCX_AI_READER_CLEANUP_MODEL`` in the repository ``.env``.
``DOCX_AI_READER_CLEANUP_ENABLED`` is deliberately ``false`` in ``.env`` and is NOT read
here — the flag is the consent, and the config is forced enabled in memory only.

Per book it writes, under ``.run/reader_cleanup_live_run/<timestamp>/<book>/``:

* ``<book>.live.cleaned.md``  — the delivered markdown
* ``<book>.live.raw.md``      — the input, copied so before/after diffs need one directory
* ``<book>.live.reader_cleanup_report.json`` — the full report payload
* ``<book>.live.usage.json``  — per-call token usage, wall time, and totals

Token usage is measured, not estimated: ``_call_responses_create`` and
``_call_chat_completions_create`` in ``docxaicorrector.generation._generation`` are wrapped
for the duration of the run and every response's ``usage`` object is recorded. A call whose
response carries no usage is counted in ``calls_without_usage`` rather than silently
dropped, so a zero total can never be mistaken for a free run.

Usage (WSL, repo root) — NOT via pytest, whose conftest strips API keys::

    . .venv/bin/activate
    export PYTHONPATH="$PWD/src:$PWD"
    python scripts/run-reader-cleanup-faithful-replay.py --live --book lietaer
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast


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
    resolve_reader_cleanup_config,
    run_reader_cleanup,
)


# The operation set a production run gets when no config or run profile narrows it further.
# The recorded runs predate the narrowing (spec 052 / the first live run: the heading pair
# removed 18 visible defects against 4 caused, the rest 0 against 12), and this stand asks
# what TODAY'S code does with those recorded answers — so the set comes from today's default
# rather than from the recording. An empty ``app_config`` is how the default is expressed
# without reading ``config.toml`` or ``.env``, which the offline stand must not need;
# ``tests/test_config.py`` pins the shipped ``config.toml`` list to the same value.
DEFAULT_ALLOWED_OPERATIONS = resolve_reader_cleanup_config(
    app_config={}, fallback_model=""
).allowed_operations


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
        allowed_operations=DEFAULT_ALLOWED_OPERATIONS,
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
        "allowed_operations": sorted(config.allowed_operations),
        "cleaned_markdown_sha256": hashlib.sha256(result.cleaned_markdown.encode("utf-8")).hexdigest(),
        "raw_block_count": payload["stats"]["raw_block_count"],
        "recorded_raw_block_count": report["stats"]["raw_block_count"],
        # What a ``toc_like`` block actually gets is IMMUNITY AT VALIDATION, not exclusion
        # from the request. With ``keep_toc`` true — the default, and what these runs used —
        # ``_select_cleanup_blocks`` returns every block, so these blocks are serialised into
        # the payload and paid for in tokens; ``_build_protected_block_ids`` then refuses any
        # operation targeting them. Only ``keep_toc=false`` withholds them from the model.
        # This field used to be documented as blocks the model never sees, which named a
        # token saving the pass does not make.
        "toc_like_block_count": sum(1 for block in build_cleanup_blocks(raw_markdown) if block.is_toc_like),
        "toc_like_blocks_sent_to_model": bool(config.keep_toc),
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


# --------------------------------------------------------------------------------------
# Live mode
# --------------------------------------------------------------------------------------

LIVE_RUN_ROOT = ROOT_DIR / ".run" / "reader_cleanup_live_run"


class _UsageRecorder:
    """Record token usage for every text call made while it is installed.

    The pass's own report has no idea what a chunk cost — ``generate_markdown_block``
    returns a string. So the two functions that actually reach the provider are wrapped
    and each response's ``usage`` is read off. Both SDK shapes are handled: the Responses
    API (``input_tokens`` / ``output_tokens``) and the Chat Completions fallback OpenRouter
    forces for some models (``prompt_tokens`` / ``completion_tokens``).
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.calls_without_usage = 0
        self._generation: Any = None
        self._originals: dict[str, Any] = {}

    def _record(self, *, api_surface: str, response: object, elapsed_ms: float, stage: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            self.calls_without_usage += 1
            self.calls.append(
                {"stage": stage, "api_surface": api_surface, "elapsed_ms": elapsed_ms, "usage_available": False}
            )
            return

        def _field(*names: str) -> int:
            for name in names:
                value = getattr(usage, name, None)
                if value is None and isinstance(usage, dict):
                    value = usage.get(name)
                if isinstance(value, int) and not isinstance(value, bool):
                    return value
            return 0

        input_tokens = _field("input_tokens", "prompt_tokens")
        output_tokens = _field("output_tokens", "completion_tokens")
        self.calls.append(
            {
                "stage": stage,
                "api_surface": api_surface,
                "elapsed_ms": elapsed_ms,
                "usage_available": True,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": _field("total_tokens") or (input_tokens + output_tokens),
            }
        )

    def install(self, *, stage_getter: Any) -> None:
        import time as _time

        from docxaicorrector.generation import _generation

        self._generation = _generation
        for name, api_surface in (("_call_responses_create", "responses"), ("_call_chat_completions_create", "chat.completions")):
            original = getattr(_generation, name)
            self._originals[name] = original

            def _wrapped(client: Any, request_kwargs: Any, *, _original: Any = original, _surface: str = api_surface) -> object:
                started_at = _time.perf_counter()
                response = _original(client, request_kwargs)
                self._record(
                    api_surface=_surface,
                    response=response,
                    elapsed_ms=round((_time.perf_counter() - started_at) * 1000, 3),
                    stage=stage_getter(),
                )
                return response

            setattr(_generation, name, _wrapped)

    def uninstall(self) -> None:
        for name, original in self._originals.items():
            setattr(self._generation, name, original)
        self._originals.clear()

    def totals(self) -> dict[str, Any]:
        input_tokens = sum(int(call.get("input_tokens", 0)) for call in self.calls)
        output_tokens = sum(int(call.get("output_tokens", 0)) for call in self.calls)
        by_stage: dict[str, dict[str, int]] = {}
        for call in self.calls:
            bucket = by_stage.setdefault(str(call.get("stage") or "?"), {"calls": 0, "input_tokens": 0, "output_tokens": 0})
            bucket["calls"] += 1
            bucket["input_tokens"] += int(call.get("input_tokens", 0))
            bucket["output_tokens"] += int(call.get("output_tokens", 0))
        return {
            "model_call_count": len(self.calls),
            "calls_without_usage": self.calls_without_usage,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "by_stage": dict(sorted(by_stage.items())),
        }


def run_live_book(book: str, *, out_dir: Path, max_retries: int) -> dict[str, Any]:
    import time as _time

    from docxaicorrector.core.config import (
        get_client_for_model_selector,
        load_app_config,
        resolve_model_selector,
    )
    from docxaicorrector.generation._generation import generate_markdown_block
    from docxaicorrector.reader_cleanup_mvp import (
        build_reader_cleanup_global_plan_system_prompt,
        build_reader_cleanup_schema_repair_system_prompt,
        build_reader_cleanup_system_prompt,
        resolve_reader_cleanup_config,
    )

    book_dir = RECORDED_RUN_DIR / book
    raw_markdown = (book_dir / f"{book}.faithful.raw.md").read_text(encoding="utf-8")

    app_config = dict(load_app_config())
    # ``.env`` keeps DOCX_AI_READER_CLEANUP_ENABLED=false on purpose. ``--live`` is the
    # consent for this one process; the file is never touched.
    app_config["reader_cleanup_enabled"] = True
    config = resolve_reader_cleanup_config(
        app_config=app_config,
        fallback_model=str(app_config.get("reader_cleanup_model") or ""),
    )
    selector = resolve_model_selector(
        config.model, "responses_text", config_like=app_config, source_name="reader cleanup live run"
    )
    client = get_client_for_model_selector(config.model, "responses_text", config_like=app_config)

    system_prompt = build_reader_cleanup_system_prompt()
    schema_repair_prompt = build_reader_cleanup_schema_repair_system_prompt()
    global_plan_prompt = build_reader_cleanup_global_plan_system_prompt()

    stage = {"name": "cleanup"}
    recorder = _UsageRecorder()
    recorder.install(stage_getter=lambda: stage["name"])

    def _call(prompt: str, payload: dict[str, Any], *, context_before: str = "", context_after: str = "") -> str:
        return generate_markdown_block(
            client=cast(Any, client),
            model=selector.model_id,
            system_prompt=prompt,
            target_text=json.dumps(payload, ensure_ascii=False, indent=2),
            context_before=context_before,
            context_after=context_after,
            max_retries=max(1, max_retries),
            expected_paragraph_ids=None,
            marker_mode=False,
        )

    def _operation_provider(payload: dict[str, Any], chunk_index: int, chunk_count: int) -> str:
        stage["name"] = str(payload.get("pass_name") or "cleanup")
        # ``_build_cleanup_chunks`` numbers chunks from 1, so no +1 here.
        print(f"    [{book}] chunk {chunk_index}/{chunk_count}", flush=True)
        return _call(
            system_prompt,
            payload,
            context_before=str(payload.get("context_before_preview") or ""),
            context_after=str(payload.get("context_after_preview") or ""),
        )

    def _repair_provider(payload: dict[str, Any], chunk_index: int, _chunk_count: int) -> str:
        stage["name"] = "schema_repair"
        print(f"    [{book}] schema repair for chunk {chunk_index}", flush=True)
        return _call(schema_repair_prompt, payload)

    def _global_plan_provider(payload: dict[str, Any]) -> str:
        stage["name"] = "global_plan"
        return _call(global_plan_prompt, payload)

    started_at = _time.perf_counter()
    try:
        result = run_reader_cleanup(
            markdown_text=raw_markdown,
            config=config,
            operation_provider=_operation_provider,
            repair_provider=_repair_provider,
            global_plan_provider=_global_plan_provider if config.global_plan_enabled else None,
            model_resolution={
                "requested_selector": config.model,
                "canonical_selector": selector.canonical_selector,
                "provider": selector.provider,
                "model_id": selector.model_id,
                "run_mode": "live_first_production_run",
            },
        )
    finally:
        recorder.uninstall()
    elapsed_s = round(_time.perf_counter() - started_at, 3)

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{book}.live.raw.md").write_text(raw_markdown, encoding="utf-8")
    (out_dir / f"{book}.live.cleaned.md").write_text(result.cleaned_markdown, encoding="utf-8")
    (out_dir / f"{book}.live.reader_cleanup_report.json").write_text(
        json.dumps(result.report_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    usage = {
        "book": book,
        "model_selector": config.model,
        "canonical_selector": selector.canonical_selector,
        "model_id": selector.model_id,
        "elapsed_seconds": elapsed_s,
        **recorder.totals(),
        "calls": recorder.calls,
    }
    (out_dir / f"{book}.live.usage.json").write_text(
        json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    payload = result.report_payload
    stats = dict(cast(dict[str, Any], payload.get("stats") or {}))
    accepted = list(cast(list[dict[str, Any]], payload.get("accepted_cleanup_operations") or []))
    ignored = list(cast(list[dict[str, Any]], payload.get("ignored_cleanup_operations") or []))
    totals = recorder.totals()
    return {
        "book": book,
        "mode": "live",
        "output_dir": str(out_dir),
        "elapsed_seconds": elapsed_s,
        "model": config.model,
        "cleanup_settings": payload.get("cleanup_settings"),
        "stage_status": payload.get("stage_status"),
        "changed": bool(payload.get("changed")),
        "raw_char_count": len(raw_markdown),
        "cleaned_char_count": len(result.cleaned_markdown),
        "stats": stats,
        "accepted_count": len(accepted),
        "accepted_by_operation": dict(sorted(Counter(str(e.get("operation", "delete_block")) for e in accepted).items())),
        "accepted_by_reason": dict(sorted(Counter(str(e.get("reason", "")) for e in accepted).items())),
        "ignored_count": len(ignored),
        "ignored_by_reason": dict(sorted(Counter(str(e.get("ignored_reason")) for e in ignored).items())),
        "cleaned_markdown_sha256": hashlib.sha256(result.cleaned_markdown.encode("utf-8")).hexdigest(),
        "tokens": {key: value for key, value in totals.items() if key != "by_stage"},
        "tokens_by_stage": totals["by_stage"],
        "failure": payload.get("failure"),
    }


def _print_live_book(data: dict[str, Any]) -> None:
    tokens = cast(dict[str, Any], data["tokens"])
    print(f"=== {data['book']} (LIVE)")
    print(f"    stage_status / changed  : {data['stage_status']} / {data['changed']}")
    print(f"    chars in / out          : {data['raw_char_count']} -> {data['cleaned_char_count']}")
    print(f"    chunks / failed         : {data['stats'].get('cleanup_chunk_count')} / {data['stats'].get('failed_chunk_count')}")
    print(f"    proposed / accepted     : {data['stats'].get('proposed_cleanup_operation_count')} / {data['accepted_count']}")
    print(f"    accepted by operation   : {data['accepted_by_operation'] or '{}'}")
    print(f"    model calls             : {tokens['model_call_count']} (no usage: {tokens['calls_without_usage']})")
    print(f"    tokens in / out         : {tokens['input_tokens']} / {tokens['output_tokens']}")
    print(f"    wall time               : {data['elapsed_seconds']}s")
    print(f"    artifacts               : {data['output_dir']}")


def _print_book(data: dict[str, Any]) -> None:
    print(f"=== {data['book']}")
    print(f"    allowed operations      : {', '.join(data['allowed_operations']) or 'all'}")
    print(f"    cleaned markdown sha256 : {data['cleaned_markdown_sha256']}")
    print(f"    blocks / chunks         : {data['raw_block_count']} (recorded {data['recorded_raw_block_count']})"
          f" / {data['chunk_count']} (recorded {data['recorded_chunk_count']}), failed {data['failed_chunk_count']}")
    sent = "sent to the model, immune only at validation" if data["toc_like_blocks_sent_to_model"] else "withheld from the model (keep_toc=false)"
    print(f"    toc_like blocks         : {data['toc_like_block_count']} ({sent})")
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
    parser.add_argument(
        "--live",
        action="store_true",
        help="COSTS MONEY: call the real provider from .env instead of replaying the recorded answers",
    )
    parser.add_argument("--live-label", default="", help="live mode: suffix for the output directory name")
    parser.add_argument(
        "--live-out-dir",
        type=Path,
        default=None,
        help="live mode: write into this exact directory instead of a fresh timestamped one "
        "(use it to add a book to a run you already paid for)",
    )
    parser.add_argument("--max-retries", type=int, default=2, help="live mode: retries per model call")
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

    if args.live:
        label = f"_{args.live_label}" if args.live_label else ""
        run_dir = args.live_out_dir or (LIVE_RUN_ROOT / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}{label}")
        live_books: dict[str, Any] = {}
        existing_summary = run_dir / "live_run_summary.json"
        if existing_summary.is_file():
            # Never overwrite the record of a book someone already paid for.
            live_books.update(json.loads(existing_summary.read_text(encoding="utf-8")).get("books") or {})
        for book in books:
            print(f"--- live run: {book}", flush=True)
            live_books[book] = run_live_book(
                book, out_dir=run_dir / book, max_retries=max(1, int(args.max_retries))
            )
            _print_live_book(live_books[book])
            # Written after every book so an interrupted run still leaves the books it paid for.
            (run_dir / "live_run_summary.json").write_text(
                json.dumps(
                    {"mode": "live", "recorded_run": RECORDED_RUN_DIR.name, "books": live_books},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        print(f"\nlive summary written to {run_dir / 'live_run_summary.json'}")
        return 0

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
