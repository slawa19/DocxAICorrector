"""Measure what actually distinguishes a TRANSLATED paragraph from an UNTRANSLATED one.

Reconnaissance for the spec about prose loss (`specs/059-verdict-never-reaches-the-screen`,
part A). That spec deliberately names no threshold number, because a number invented at the
desk is the same forbidden literal as a word list, only written as a digit (Constitution
VII). This script produces the numbers a threshold would have to be argued from -- or the
evidence that no threshold can be argued at all.

The existing check cannot answer the question. `has_unexplained_english_residuals`
(`pipeline/output_validation.py:363`) opens with
`if not _CYRILLIC_CHAR_PATTERN.search(text): return False`, so a fully English answer is
reported VALID: it looks for English specks inside Russian and never for missing Russian. It
then keys on a five-word list, which Constitution VII forbids outright.

WHAT IS MEASURED
----------------
Three classes, all built from recorded material, none from a fresh run:

  DELIVERED   the text that reached the artifact for a prose paragraph (`after`).
              A completeness check MUST NOT flag these.
  FALLBACK*   the source text of the same paragraph (`before`). Not a synthetic
              construction: on the document path the generator returns the block's source
              text verbatim when the model gave no accepted answer
              (`generation/_generation.py:2013-2091`, four substitution branches), so
              `before` IS, byte for byte, what an untranslated delivery looks like.
              A completeness check MUST flag every one of these.
  CONTROL     delivered text that is legitimately NOT in the target language -- proper
              names, citations, index rows, URLs, acronyms, markup residue. A completeness
              check MUST NOT flag these either, and this is the half that breaks rules.

Candidate features, each computed on the delivered text alone or on the pair:

  target_letter_share  Cyrillic letters / (Cyrillic + Latin letters)   [single text]
  letter_count         Cyrillic + Latin letters                        [single text]
  length_ratio         len(after) / len(before)                        [pair, recorded]
  change_ratio         recorded character-level change                 [pair, recorded]
  identical            recorded byte equality                          [pair, recorded]
  source_equality      after == before and the source carries a letter  [pair, derived]

WHICH PARAGRAPHS COUNT AS PROSE
-------------------------------
Two different prose sets are reported side by side, because they disagree by a factor of
nearly three and only one of them is the contract's:

  REGION prose (spec 059 A-6): source registry minus front matter, minus bounded TOC, minus
  the back-matter region. Reconstructed here from the run's own recorded block decisions
  (`source_blocks_with_narration_decision.json`: `narration_include`, `reason`, per-paragraph
  `role`), which is the same decision `_resolve_narration_include` made during the run.

  `source_is_prose`, the flag carried in the paragraph-pair dump. No code in this repository
  produces it; section 1 reconstructs what it is and shows it is a LENGTH SCREEN, not the
  region definition. Every measurement is therefore reported on the region set, with the
  flag's own subset shown next to it so the difference is visible rather than assumed.

DATA, AND WHY IT IS THIS DATA
-----------------------------
The material was tracked in git and later removed by `f129a21` ("keep only what a human
reads"). It is recovered from history, not from any working tree, so this measurement is
reproducible from a clean clone:

    mkdir -p .run/data
    git show f2a49da:artifacts/audiobook_first_run/all_paragraph_pairs.jsonl \
        > .run/data/audiobook_first_run.jsonl
    git show f2a49da:artifacts/audiobook_first_run/source_blocks_with_narration_decision.json \
        > .run/data/source_blocks.json
    git show f2a49da:artifacts/audiobook_first_run/Money_Sustainability_pdf_full_heldout.tts.txt \
        > .run/data/delivered.tts.txt
    git show 7819933:artifacts/literary_edit_first_run/all_paragraph_pairs.jsonl \
        > .run/data/literary_edit_first_run.jsonl

The paragraph-pair dumps of the four-book and the five-book runs were NEVER tracked (see the
`f129a21` message), so per-paragraph coverage is ONE book: Money & Sustainability, audiobook
path, en->ru. Cross-book coverage comes from the five tracked
`artifacts/audiobook_final_run/*/comparison_paragraphs.md`, which quote source and delivered
text for a sample per book -- a BIASED sample (random 60 plus the three extremes), reported
as such and never mixed into the full-book numbers.

All recorded runs are en->ru. Every "target alphabet" number below is therefore a Cyrillic
number, and the claim that the same shape holds for another target language IS NOT TESTED BY
THIS CORPUS. Said once, here, so no table below is read as a general result.

Run (WSL, stdlib only, no LLM, no network):
    python3 scripts/measure-translation-signal.py
    python3 scripts/measure-translation-signal.py --json .run/translation_signal.json
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / ".run" / "data"
AUDIOBOOK_PAIRS = DATA_DIR / "audiobook_first_run.jsonl"
SOURCE_BLOCKS = DATA_DIR / "source_blocks.json"
DELIVERED_NARRATION = DATA_DIR / "delivered.tts.txt"
LITERARY_EDIT_PAIRS = DATA_DIR / "literary_edit_first_run.jsonl"
FINAL_RUN_DIR = PROJECT_ROOT / "artifacts" / "audiobook_final_run"
FINAL_RUN_BOOKS = (
    "creating_wealth",
    "money_sustainability",
    "rethinking_money",
    "value_of_everything",
    "money_translate_docx",
)

RECOVERY_HINT = (
    "Recover the recorded material from git history first -- see this file's docstring:\n"
    "  mkdir -p .run/data\n"
    "  git show f2a49da:artifacts/audiobook_first_run/all_paragraph_pairs.jsonl > .run/data/audiobook_first_run.jsonl\n"
    "  git show f2a49da:artifacts/audiobook_first_run/source_blocks_with_narration_decision.json "
    "> .run/data/source_blocks.json\n"
    "  git show f2a49da:artifacts/audiobook_first_run/Money_Sustainability_pdf_full_heldout.tts.txt "
    "> .run/data/delivered.tts.txt\n"
    "  git show 7819933:artifacts/literary_edit_first_run/all_paragraph_pairs.jsonl "
    "> .run/data/literary_edit_first_run.jsonl"
)

# Target alphabet of every recorded run: en -> ru. Not a per-book literal -- it is the run's
# declared target language, and the only one the corpus contains.
CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN = re.compile(r"[A-Za-z]")

SOURCE_QUOTE_LABELS = ("**Исходный абзац:**", "**Оригинал:**")
DELIVERED_QUOTE_LABELS = ("**В озвучку попало:**", "**Перевод в документе:**")
SECTION_HEADING = re.compile(r"^## (.+)$")
ENTRY_HEADING = re.compile(r"^### \d+\. `([^`]+)`")

LETTER_FLOORS = (0, 20, 60, 120, 250)
CUTS = (0.10, 0.20, 0.30, 0.50, 0.70, 0.90)

# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------


def letter_counts(text: str) -> tuple[int, int]:
    return len(CYRILLIC.findall(text)), len(LATIN.findall(text))


def letter_count(text: str) -> int:
    cyrillic, latin = letter_counts(text)
    return cyrillic + latin


def target_letter_share(text: str) -> float | None:
    """Share of target-alphabet letters among alphabetic characters, or None if no letters.

    None is a real answer, not a missing value: a paragraph with no letters at all (a page
    number, an image placeholder, a row of asterisks) carries no language evidence either
    way, and any rule that assigns it a share has invented one.
    """
    cyrillic, latin = letter_counts(text)
    total = cyrillic + latin
    if total == 0:
        return None
    return cyrillic / total


# ---------------------------------------------------------------------------
# Control-group form buckets
#
# MEASUREMENT SCAFFOLDING, not a proposed production rule. Constitution VII forbids
# reconstructing structure from the shape of the text; labelling a research corpus by shape
# so it can be counted is a different act from shipping the shape as a detector, and nothing
# here is proposed for shipping. Buckets are form-based (no word lists) so the labelling is
# reproducible by re-running this file.
# ---------------------------------------------------------------------------

MARKUP_PLACEHOLDER = re.compile(r"\[\[DOCX_(?:IMAGE|PARA)_[^\]]*\]\]")
URL_OR_DOI = re.compile(r"(?:https?://|www\.[a-z0-9-]+\.|[a-z0-9-]+\.(?:com|net|org|ru)\b|doi\.org|\b10\.\d{4,}/)", re.IGNORECASE)
PAGE_RANGE = re.compile(r"\d+\s*[–—-]\s*\d+")
WORD = re.compile(r"[A-Za-zЀ-ӿ][A-Za-zЀ-ӿ'’]*")


def share_or(text: str, default: float) -> float:
    """Explicit fallback for texts with no letters. `share or default` is a bug: 0.0 is falsy."""
    share = target_letter_share(text)
    return default if share is None else share


def digit_share(text: str) -> float:
    if not text:
        return 0.0
    return sum(character.isdigit() for character in text) / len(text)


def classify_control_form(text: str) -> str:
    """One form bucket per delivered text; first match wins, order is deliberate."""
    stripped = text.strip()
    if MARKUP_PLACEHOLDER.search(stripped):
        return "markup_placeholder"
    letters = letter_count(stripped)
    if letters == 0:
        return "no_letters_at_all"
    if URL_OR_DOI.search(stripped):
        return "url_or_domain"
    if letters < 20:
        return "under_20_letters"
    separators = stripped.count(",") + stripped.count(";")
    if digit_share(stripped) >= 0.10 and (PAGE_RANGE.search(stripped) or separators >= 3):
        return "numeric_reference_row"
    words = WORD.findall(stripped)
    if words and all(word.isupper() for word in words) and len(words) <= 8:
        return "acronym_or_allcaps"
    if words and not stripped.endswith((".", "!", "?", "…")) and len(words) <= 12:
        capitalised = sum(1 for word in words if word[:1].isupper())
        if capitalised / len(words) >= 0.6:
            return "titlecase_name_run"
    return "running_text_shape"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"missing {path}\n{RECOVERY_HINT}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_paragraph_regions(path: Path) -> dict[str, dict[str, Any]]:
    """Per-paragraph region decision, exactly as the run recorded it."""
    if not path.exists():
        raise SystemExit(f"missing {path}\n{RECOVERY_HINT}")
    blocks = json.loads(path.read_text(encoding="utf-8"))
    regions: dict[str, dict[str, Any]] = {}
    for block in blocks:
        for paragraph_id, paragraph_role in zip(block["paragraph_ids"], block["paragraph_roles"]):
            regions[paragraph_id] = {
                "block_index": block["block_index"],
                "narration_include": block["narration_include"],
                "exclusion_reason": block["reason"],
                "role": paragraph_role["role"],
                "heading_level": paragraph_role["heading_level"],
            }
    return regions


def parse_comparison_paragraphs(path: Path) -> list[dict[str, str]]:
    """Extract (paragraph_id, section, source, delivered) from a tracked comparison file."""
    entries: list[dict[str, str]] = []
    section = ""
    current: dict[str, str] | None = None
    slot: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        section_match = SECTION_HEADING.match(line)
        if section_match:
            section = section_match.group(1)
            slot = None
            continue
        entry_match = ENTRY_HEADING.match(line)
        if entry_match:
            if current and current["source"] and current["delivered"]:
                entries.append(current)
            current = {"paragraph_id": entry_match.group(1), "section": section, "source": "", "delivered": ""}
            slot = None
            continue
        if current is None:
            continue
        if line.strip() in SOURCE_QUOTE_LABELS:
            slot = "source"
            continue
        if line.strip() in DELIVERED_QUOTE_LABELS:
            slot = "delivered"
            continue
        if line.startswith(">") and slot:
            current[slot] = (current[slot] + " " + line.lstrip("> ").strip()).strip()
    if current and current["source"] and current["delivered"]:
        entries.append(current)
    return entries


# ---------------------------------------------------------------------------
# Distribution reporting
# ---------------------------------------------------------------------------


def quantiles(values: Sequence[float]) -> dict[str, Any]:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "min": None, "p01": None, "p05": None, "p25": None, "median": None, "p95": None, "max": None}

    def at(fraction: float) -> float:
        index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
        return ordered[index]

    return {
        "n": len(ordered),
        "min": round(ordered[0], 4),
        "p01": round(at(0.01), 4),
        "p05": round(at(0.05), 4),
        "p25": round(at(0.25), 4),
        "median": round(statistics.median(ordered), 4),
        "p95": round(at(0.95), 4),
        "max": round(ordered[-1], 4),
    }


COLUMNS = ("min", "p01", "p05", "p25", "median", "p95", "max")


def render_distribution_table(title: str, rows: Sequence[tuple[str, Sequence[float]]]) -> list[str]:
    lines = [title, "  class                              n     min    p01    p05    p25    med    p95    max"]
    for name, values in rows:
        stats = quantiles(values)
        if stats["n"] == 0:
            lines.append(f"  {name:<32} {0:>4}" + "     --" * 7)
            continue
        lines.append(
            f"  {name:<32} {stats['n']:>4}  " + "  ".join(f"{float(stats[key]):>5.3f}" for key in COLUMNS)
        )
    return lines


# ---------------------------------------------------------------------------
# 1. What the data is
# ---------------------------------------------------------------------------


def section_data_shape(
    rows: list[dict[str, Any]], regions: dict[str, dict[str, Any]], report: dict[str, Any]
) -> list[str]:
    lines = ["", "=" * 104, "1. WHAT THE DATA IS, AND WHAT `source_is_prose` ACTUALLY MEANS", "=" * 104]
    lines.append(f"paragraph pairs: {len(rows)}   outcomes: {dict(Counter(row['outcome'] for row in rows))}")
    lines.append(f"recorded fields: {sorted(rows[0].keys())}")
    lines.append("")
    lines.append(
        f"block decisions cover {len(regions)} paragraphs; "
        f"{sum(1 for row in rows if row['paragraph_id'] in regions)} of {len(rows)} pairs join to a region decision."
    )
    lines.append(
        "region exclusions the run itself recorded: "
        + str(dict(Counter(info["exclusion_reason"] for info in regions.values() if not info["narration_include"])))
    )
    lines.append(
        "roles inside the included region: "
        + str(dict(Counter(info["role"] for info in regions.values() if info["narration_include"])))
    )

    region_prose = [row for row in rows if regions[row["paragraph_id"]]["narration_include"]]
    flagged = [row for row in rows if row["source_is_prose"]]
    lines.append("")
    lines.append("TWO PROSE SETS, and they disagree:")
    lines.append(f"  REGION prose (spec 059 A-6, reconstructed from the run's own decision): {len(region_prose)}")
    lines.append(
        f"  `source_is_prose` == true:                                                {len(flagged)} "
        f"({100 * len(flagged) / max(1, len(region_prose)):.1f}% of the region set)"
    )
    lines.append(
        f"  paragraphs the flag calls prose from OUTSIDE the region set: "
        f"{sum(1 for row in flagged if not regions[row['paragraph_id']]['narration_include'])}"
    )

    def score(name: str, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        covered = sum(1 for row in rows if predicate(row) and row["source_is_prose"])
        extra = sum(1 for row in rows if predicate(row) and not row["source_is_prose"])
        missed = sum(1 for row in rows if not predicate(row) and row["source_is_prose"])
        lines.append(f"  {name:<56} covers={covered:<4} extra={extra:<4} missed={missed}")
        return {"predicate": name, "covers": covered, "extra": extra, "missed": missed}

    lines.append("")
    lines.append("No code in this repository produces `source_is_prose`. Reconstructing it (missed=0 => NECESSARY):")
    candidates = [
        score("not heading", lambda row: not row["source_is_heading"]),
        score("not heading and len(before) >= 250", lambda row: not row["source_is_heading"] and len(row["before"]) >= 250),
        score(
            "not heading, len >= 250, first char uppercase",
            lambda row: not row["source_is_heading"]
            and len(row["before"]) >= 250
            and row["before"].lstrip()[:1].isupper(),
        ),
    ]
    shortest = min((len(row["before"]) for row in flagged), default=0)
    lines.append(f"shortest source text carrying source_is_prose=true: {shortest} characters (no exceptions)")

    unexplained = [
        row
        for row in rows
        if not row["source_is_heading"]
        and len(row["before"]) >= 250
        and row["before"].lstrip()[:1].isupper()
        and not row["source_is_prose"]
    ]
    lines.append(
        f"paragraphs meeting every necessary condition yet flagged NOT prose: {len(unexplained)} "
        f"({100 * len(unexplained) / max(1, len(unexplained) + len(flagged)):.1f}% of that population) -- "
        "plainly prose, and the flag drops them:"
    )
    for row in unexplained[:4]:
        lines.append(f"    {row['paragraph_id']} ({len(row['before'])} chars) {row['before'][:104]!r}")

    ordinals = sorted(row["ordinal"] for row in flagged)
    runs = 1 + sum(1 for previous, current in zip(ordinals, ordinals[1:]) if current != previous + 1)
    lines.append(
        f"the flagged set occupies {runs} separate ordinal runs over {ordinals[0]}..{ordinals[-1]}: "
        "scattered, so it is a per-paragraph screen and not a region"
    )
    lines.append("")
    lines.append(
        "VERDICT ON THE FLAG: a length+shape screen (>= 250 characters, non-heading, capital initial) that\n"
        "  sees 35.9% of the contract's prose set and demonstrably drops real prose. Usable to pick a reading\n"
        "  sample. NOT usable as the prose definition, and its 250-character floor is itself the kind of form\n"
        "  threshold Constitution VII refuses in production. Every table below is on the REGION set."
    )

    report["data_shape"] = {
        "pairs": len(rows),
        "outcomes": dict(Counter(row["outcome"] for row in rows)),
        "region_prose": len(region_prose),
        "flagged_prose": len(flagged),
        "region_exclusions": dict(
            Counter(info["exclusion_reason"] for info in regions.values() if not info["narration_include"])
        ),
        "roles_included": dict(Counter(info["role"] for info in regions.values() if info["narration_include"])),
        "flag_candidates": candidates,
        "flag_shortest_prose_chars": shortest,
        "flag_unexplained_exclusions": len(unexplained),
        "flag_unexplained_examples": [row["paragraph_id"] for row in unexplained[:10]],
        "flag_ordinal_runs": runs,
    }
    return lines


# ---------------------------------------------------------------------------
# 2. Features per class
# ---------------------------------------------------------------------------


def section_features(
    rows: list[dict[str, Any]], regions: dict[str, dict[str, Any]], report: dict[str, Any]
) -> list[str]:
    lines = [
        "",
        "=" * 104,
        "2. CANDIDATE FEATURES PER CLASS -- Money & Sustainability, audiobook path, whole book",
        "=" * 104,
    ]
    landed = [row for row in rows if row["outcome"] == "narration_landed" and regions[row["paragraph_id"]]["narration_include"]]
    lines.append(f"REGION prose paragraphs that reached the artifact: {len(landed)}")

    def shares(texts: list[str]) -> list[float]:
        return [value for value in (target_letter_share(text) for text in texts) if value is not None]

    by_role = {role: [row for row in landed if regions[row["paragraph_id"]]["role"] == role] for role in ("body", "list", "heading")}
    lines.append("")
    lines.extend(
        render_distribution_table(
            "FEATURE 1 -- target_letter_share, Cyrillic / (Cyrillic + Latin):",
            [
                ("DELIVERED, all region prose", shares([row["after"] for row in landed])),
                ("  role=body", shares([row["after"] for row in by_role["body"]])),
                ("  role=list", shares([row["after"] for row in by_role["list"]])),
                ("  role=heading", shares([row["after"] for row in by_role["heading"]])),
                ("DELIVERED, source_is_prose subset", shares([row["after"] for row in landed if row["source_is_prose"]])),
                ("FALLBACK (source text, all)", shares([row["before"] for row in landed])),
            ],
        )
    )
    no_letters = sum(1 for row in landed if letter_count(row["after"]) == 0)
    lines.append(
        f"  delivered paragraphs with NO letters at all (share undefined): {no_letters} -- "
        "page numbers, asterisk dividers, placeholders"
    )
    lines.append("")
    lines.extend(
        render_distribution_table(
            "FEATURE 2 -- length_ratio (recorded, len(after)/len(before)):",
            [
                ("DELIVERED, all region prose", [row["length_ratio"] for row in landed]),
                ("  role=body", [row["length_ratio"] for row in by_role["body"]]),
                ("DELIVERED, source_is_prose subset", [row["length_ratio"] for row in landed if row["source_is_prose"]]),
            ],
        )
    )
    lines.append("  FALLBACK is length_ratio == 1.0 by construction: the source text is returned verbatim.")
    lines.append("")
    lines.extend(
        render_distribution_table(
            "FEATURE 3 -- change_ratio (recorded):",
            [
                ("DELIVERED, all region prose", [row["change_ratio"] for row in landed]),
                ("DELIVERED, source_is_prose subset", [row["change_ratio"] for row in landed if row["source_is_prose"]]),
            ],
        )
    )
    identical = [row for row in landed if row["identical"]]
    lines.append("  FALLBACK is change_ratio == 0.0 and identical == true by construction.")
    lines.append("")
    lines.append(f"FEATURE 4 -- identical: {len(identical)} of {len(landed)} delivered paragraphs are byte-equal to source.")
    for row in identical:
        lines.append(
            f"    {row['paragraph_id']} letters={letter_count(row['before']):<3} "
            f"form={classify_control_form(row['before']):<20} {row['before'][:70]!r}"
        )
    with_letters = [row for row in identical if letter_count(row["before"]) > 0]
    lines.append(
        f"  of those, source carries at least one letter: {len(with_letters)} "
        f"({', '.join(row['paragraph_id'] for row in with_letters) or 'none'})"
    )

    lines.append("")
    buckets = Counter()
    for row in landed:
        letters = letter_count(row["before"])
        buckets[
            "0" if letters == 0 else "1-19" if letters < 20 else "20-59" if letters < 60 else "60-119" if letters < 120 else "120+"
        ] += 1
    short = buckets["0"] + buckets["1-19"] + buckets["20-59"]
    lines.append(f"FEATURE 5 -- letter_count of the SOURCE text, bucketed: {dict(buckets)}")
    lines.append(
        f"  {short} of {len(landed)} region-prose paragraphs ({100 * short / len(landed):.1f}%) carry fewer than 60 letters.\n"
        "  Any share-based rule that needs a letter floor of 60 to stay quiet is BLIND to that quarter of the set."
    )

    report["features"] = {
        "region_prose_landed": len(landed),
        "target_letter_share": {
            "delivered_all": quantiles(shares([row["after"] for row in landed])),
            "delivered_body": quantiles(shares([row["after"] for row in by_role["body"]])),
            "delivered_list": quantiles(shares([row["after"] for row in by_role["list"]])),
            "delivered_heading": quantiles(shares([row["after"] for row in by_role["heading"]])),
            "delivered_flagged_subset": quantiles(shares([row["after"] for row in landed if row["source_is_prose"]])),
            "fallback_all": quantiles(shares([row["before"] for row in landed])),
        },
        "delivered_without_letters": no_letters,
        "length_ratio_delivered": quantiles([row["length_ratio"] for row in landed]),
        "change_ratio_delivered": quantiles([row["change_ratio"] for row in landed]),
        "identical_delivered": len(identical),
        "identical_delivered_with_letters": [row["paragraph_id"] for row in with_letters],
        "source_letter_buckets": dict(buckets),
        "source_under_60_letters": short,
    }
    return lines


# ---------------------------------------------------------------------------
# 3. Control group
# ---------------------------------------------------------------------------


def section_control_group(
    rows: list[dict[str, Any]], regions: dict[str, dict[str, Any]], report: dict[str, Any]
) -> list[str]:
    lines = [
        "",
        "=" * 104,
        "3. CONTROL GROUP -- delivered text that is legitimately NOT in the target language",
        "=" * 104,
    ]
    landed = [row for row in rows if row["outcome"] == "narration_landed" and regions[row["paragraph_id"]]["narration_include"]]
    members = [row for row in landed if share_or(row["after"], 0.0) < 0.9]
    lines.append(
        "How it is collected, and the method's limit stated first: every delivered paragraph whose\n"
        "target_letter_share is under 0.90 or undefined is pulled out and bucketed BY FORM. The 0.90 cut is a\n"
        "collection net, not a proposed threshold -- it is set loose deliberately so the group is not selected by\n"
        "the same number the report is trying to justify. Buckets are form-based, no word lists."
    )
    lines.append("")
    lines.append(f"  {len(members)} of {len(landed)} delivered paragraphs fall in the net.")
    lines.append("")
    lines.append("  form bucket                 count  in flag's prose set  median letters  median target_share")
    bucket_report: dict[str, Any] = {}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in members:
        grouped.setdefault(classify_control_form(row["after"]), []).append(row)
    for name, group in sorted(grouped.items(), key=lambda item: -len(item[1])):
        group_shares = [value for value in (target_letter_share(row["after"]) for row in group) if value is not None]
        letters = [letter_count(row["after"]) for row in group]
        median_share = f"{statistics.median(group_shares):.3f}" if group_shares else "n/a"
        lines.append(
            f"  {name:<27} {len(group):>5}  {sum(1 for row in group if row['source_is_prose']):>19}  "
            f"{statistics.median(letters):>14.0f}  {median_share:>19}"
        )
        bucket_report[name] = {
            "count": len(group),
            "in_flag_prose_set": sum(1 for row in group if row["source_is_prose"]),
            "median_letters": statistics.median(letters),
            "target_share": quantiles(group_shares),
            "examples": [row["after"][:120] for row in group[:3]],
        }
    lines.append(f"  {'TOTAL':<27} {sum(len(group) for group in grouped.values()):>5}")

    lines.append("")
    lines.append("The hardest members, quoted -- lowest target share with at least 20 letters:")
    hardest = sorted(
        (row for row in members if letter_count(row["after"]) >= 20),
        key=lambda row: share_or(row["after"], 1.0),
    )[:8]
    for row in hardest:
        lines.append(
            f"    {row['paragraph_id']} share={target_letter_share(row['after']):.3f} "
            f"letters={letter_count(row['after']):<4} [{classify_control_form(row['after'])}]"
        )
        lines.append(f"        {row['after'][:150]!r}")
    lines.append("")
    lines.append(
        "LIMIT OF THIS CONTROL GROUP, said plainly: it is small, and it is small for two structural reasons.\n"
        "  (a) On the audiobook path an untranslated block is DROPPED, not delivered (block_execution.py:975-995),\n"
        "      so the corpus cannot contain the very failures the check exists to catch.\n"
        "  (b) The back-matter region on this book was excluded before the model saw it (bibliography, notes,\n"
        "      TOC), which is exactly where legitimately-English rows live. What survives to be delivered is\n"
        "      mostly running prose, so the control group cannot price a false-alarm rate on apparatus.\n"
        "  The one book where apparatus DID survive into delivery is Rethinking Money -- section 6."
    )
    report["control_group"] = {"net": "target_letter_share < 0.90 or undefined", "members": len(members), "buckets": bucket_report}
    return lines


# ---------------------------------------------------------------------------
# 4. Threshold sweep and the pair rule
# ---------------------------------------------------------------------------


def section_threshold_sweep(
    rows: list[dict[str, Any]], regions: dict[str, dict[str, Any]], report: dict[str, Any]
) -> list[str]:
    lines = ["", "=" * 104, "4. IS THERE A GAP? THRESHOLD SWEEP AGAINST THE PAIR RULE", "=" * 104]
    landed = [row for row in rows if row["outcome"] == "narration_landed" and regions[row["paragraph_id"]]["narration_include"]]

    lines.append(
        "Rule A (single-text share): FLAG delivered text when letter_count >= floor AND target_letter_share < cut.\n"
        "  TP  = FALLBACK caught  (every one of them must be; this is the owner's requirement, not a target)\n"
        "  FP1 = DELIVERED wrongly flagged (a false alarm on a good translation)\n"
        "  MISS= FALLBACK below the letter floor, invisible to the rule at any cut"
    )
    sweep: list[dict[str, Any]] = []
    for floor in LETTER_FLOORS:
        blind = sum(1 for row in landed if letter_count(row["before"]) < floor)
        lines.append("")
        lines.append(f"  letter floor = {floor:<4} (FALLBACK paragraphs below it and therefore invisible: {blind})")
        lines.append("    cut      TP                        FP1")
        for cut in CUTS:

            def flagged(text: str) -> bool:
                if letter_count(text) < floor:
                    return False
                share = target_letter_share(text)
                return share is not None and share < cut

            true_positive = sum(1 for row in landed if flagged(row["before"]))
            false_positive = sum(1 for row in landed if flagged(row["after"]))
            lines.append(
                f"    {cut:.2f}   {true_positive:>5}/{len(landed):<5} ({100 * true_positive / len(landed):5.1f}%)"
                f"      {false_positive:>4}/{len(landed):<5} ({100 * false_positive / len(landed):5.1f}%)"
            )
            sweep.append(
                {
                    "letter_floor": floor,
                    "cut": cut,
                    "tp": true_positive,
                    "fp": false_positive,
                    "of": len(landed),
                    "blind_below_floor": blind,
                }
            )
    report["threshold_sweep"] = sweep

    delivered = [value for value in (target_letter_share(row["after"]) for row in landed) if value is not None]
    fallback = [value for value in (target_letter_share(row["before"]) for row in landed) if value is not None]
    lines.append("")
    lines.append("THE GAP, stated as two numbers:")
    lines.append(f"  highest target share ever reached by a FALLBACK text : {max(fallback):.4f}")
    lines.append(f"  lowest  target share ever reached by a DELIVERED text: {min(delivered):.4f}")
    lines.append(f"  raw gap = {min(delivered) - max(fallback):+.4f}")
    ordered_delivered = sorted(delivered)
    lines.append(
        f"  but the delivered tail is thin, not empty: p01={ordered_delivered[len(ordered_delivered) // 100]:.3f}, "
        f"and {sum(1 for value in delivered if value < 0.3)} delivered paragraphs sit under 0.30"
    )
    with_floor = [
        target_letter_share(row["after"]) for row in landed if letter_count(row["after"]) >= 60 and target_letter_share(row["after"]) is not None
    ]
    lines.append(
        f"  with a 60-letter floor the delivered minimum rises to {min(with_floor):.4f} "
        f"over {len(with_floor)} paragraphs -- the low tail is entirely SHORT text"
    )
    report["gap"] = {
        "max_fallback_share": round(max(fallback), 4),
        "min_delivered_share": round(min(delivered), 4),
        "raw_gap": round(min(delivered) - max(fallback), 4),
        "delivered_under_0_30": sum(1 for value in delivered if value < 0.3),
        "min_delivered_share_60_letter_floor": round(min(with_floor), 4),
    }

    lines.append("")
    lines.append("-" * 104)
    lines.append(
        "Rule B (the pair): FLAG when delivered == source verbatim AND the source carries at least one letter.\n"
        "  No threshold, no word list, no alphabet: byte equality against the paragraph's own source."
    )
    true_positive = sum(1 for row in landed if letter_count(row["before"]) > 0)
    false_positive = [row for row in landed if row["after"] == row["before"] and letter_count(row["before"]) > 0]
    blind = sum(1 for row in landed if letter_count(row["before"]) == 0)
    lines.append(f"  TP  FALLBACK caught:              {true_positive}/{len(landed)} ({100 * true_positive / len(landed):.1f}%)")
    lines.append(f"  MISS source with no letters:      {blind}/{len(landed)} (nothing to translate, so nothing is lost)")
    lines.append(f"  FP1 DELIVERED wrongly flagged:    {len(false_positive)}/{len(landed)} ({100 * len(false_positive) / len(landed):.2f}%)")
    for row in false_positive:
        lines.append(
            f"      {row['paragraph_id']} [{classify_control_form(row['before'])}] "
            f"classes={row['manual_edit_classes']} {row['before'][:80]!r}"
        )
    report["pair_rule"] = {
        "tp": true_positive,
        "of": len(landed),
        "miss_source_without_letters": blind,
        "fp": len(false_positive),
        "fp_ids": [row["paragraph_id"] for row in false_positive],
    }

    lines.append("")
    lines.append("Where rule B must NOT be exported -- the literary-edit run (document path, ru -> ru editing):")
    if LITERARY_EDIT_PAIRS.exists():
        edit_rows = load_jsonl(LITERARY_EDIT_PAIRS)
        identical_rows = [row for row in edit_rows if row["after"] == row["before"] and letter_count(row["before"]) > 0]
        lines.append(
            f"  byte-identical deliveries: {len(identical_rows)}/{len(edit_rows)} "
            f"({100 * len(identical_rows) / len(edit_rows):.1f}%). In an EDITING step an untouched paragraph is the"
        )
        lines.append(
            "  correct outcome, so byte equality is decisive ONLY where source and target language differ. That is a\n"
            "  property of the step, checkable from the job, not a tuning knob."
        )
        report["pair_rule"]["literary_edit_identical"] = [len(identical_rows), len(edit_rows)]
    return lines


# ---------------------------------------------------------------------------
# 5. The delivered artifact
# ---------------------------------------------------------------------------


MARKDOWN_NOISE = re.compile(r"[*#>`\[\]•–—-]+")


def _normalise_for_block_lookup(text: str) -> str:
    return re.sub(r"\s+", " ", MARKDOWN_NOISE.sub(" ", text)).strip().casefold()


@lru_cache(maxsize=1)
def _normalised_source_blocks() -> tuple[str, ...]:
    blocks = json.loads(SOURCE_BLOCKS.read_text(encoding="utf-8"))
    return tuple(_normalise_for_block_lookup(block["text"]) for block in blocks)


def _found_in_a_source_block(line: str) -> bool:
    """Is this delivered line the source text of some block, modulo markdown noise?

    Substitution happens per block, so a delivered fallback line can carry several source
    paragraphs at once and match none of them individually. This asks the question at the
    granularity where the substitution is actually made.
    """
    probe = _normalise_for_block_lookup(line)[:70]
    return bool(probe) and any(probe in block for block in _normalised_source_blocks())


def section_delivered_artifact(rows: list[dict[str, Any]], report: dict[str, Any]) -> list[str]:
    """The one place in the corpus where untranslated prose was really DELIVERED to a listener."""
    lines = ["", "=" * 104, "5. THE DELIVERED ARTIFACT -- real untranslated prose, not a simulation", "=" * 104]
    if not DELIVERED_NARRATION.exists():
        lines.append(f"missing {DELIVERED_NARRATION} -- skipped")
        return lines
    lines.append(
        "Everything above treated the source text as a stand-in for a fallback delivery. This section needs no\n"
        "stand-in. `Money_Sustainability_pdf_full_heldout.tts.txt` is the narration as DELIVERED on 2026-08-04;\n"
        "the commit that tracked it says so in as many words -- 'the artifact as delivered on 2026-08-04, before\n"
        "the three fixes that followed ... kept as the before-picture, not as a current sample' (f2a49da). Its run\n"
        "recorded `model_output_discarded_block_count=6` with reasons `{marker_validation_source_fallback: 6,\n"
        "marker_chunk_collapse: 1}` and had no `narration_excluded_source_fallback_*` counter at all, so those\n"
        "blocks went into the audiobook in English. Constitution VIII applies: this is a BEFORE picture. The same\n"
        "book on 2026-08-06 shows 2 fallback blocks, now DROPPED instead (5 581 characters missing) -- the two\n"
        "shapes of loss spec 059 A-1 describes, both recorded, on one book."
    )
    artifact_lines = [line.strip() for line in DELIVERED_NARRATION.read_text(encoding="utf-8").splitlines() if line.strip()]
    source_texts = {row["before"].strip() for row in rows}
    total_letters = sum(letter_count(line) for line in artifact_lines)
    lines.append("")
    lines.append(f"delivered narration lines: {len(artifact_lines)}; letters: {total_letters}")
    lines.append("")
    lines.append("  floor  cut    lines flagged   letters flagged   share of artifact")
    sweep: list[dict[str, Any]] = []
    for floor in (0, 20, 60, 120):
        for cut in (0.10, 0.30, 0.50):
            hits = [
                line
                for line in artifact_lines
                if letter_count(line) >= floor
                and target_letter_share(line) is not None
                and target_letter_share(line) < cut
            ]
            hit_letters = sum(letter_count(line) for line in hits)
            lines.append(
                f"  {floor:>5}  {cut:.2f}  {len(hits):>13}   {hit_letters:>15}   {100 * hit_letters / total_letters:>16.2f}%"
            )
            sweep.append({"letter_floor": floor, "cut": cut, "lines": len(hits), "letters": hit_letters})

    english = [
        line
        for line in artifact_lines
        if letter_count(line) >= 60 and target_letter_share(line) is not None and target_letter_share(line) < 0.10
    ]
    english_letters = sum(letter_count(line) for line in english)
    verbatim = sum(1 for line in english if line in source_texts)
    lines.append("")
    lines.append(
        f"UNTRANSLATED PROSE ACTUALLY SHIPPED: {len(english)} lines, {english_letters} letters, "
        f"{100 * english_letters / total_letters:.2f}% of the artifact."
    )
    inside_block = sum(1 for line in english if _found_in_a_source_block(line))
    lines.append(
        f"  {verbatim} of them are byte-equal to a recorded SOURCE paragraph. Substitution happens at BLOCK level, so\n"
        "  the rest carry several paragraphs at once and match no single paragraph byte for byte: "
        f"{inside_block} of the {len(english)}\n"
        "  are found inside a recorded source block once markdown noise is normalised away on both sides.\n"
        "  Granularity matters more than the feature here -- a pair comparison run at paragraph granularity sees\n"
        f"  {verbatim} of {len(english)}; run where the substitution actually happens, it sees {inside_block}."
    )
    lines.append(
        "  NOT ONE of them appears in the paragraph-pair dump as a delivered text. The dump records only paragraphs\n"
        "  whose delivered text was found in the artifact, so it is SURVIVOR-BIASED by construction: the failures the\n"
        "  check exists to catch are exactly what it omits. Any 'paragraphs left in English' figure computed from the\n"
        "  dump rather than from the artifact is measuring the survivors."
    )
    lines.append("")
    lines.append("  longest six, quoted:")
    for line in sorted(english, key=lambda item: -letter_count(item))[:6]:
        lines.append(f"    letters={letter_count(line):<5} {line[:130]!r}")

    scored = [(target_letter_share(line), line) for line in artifact_lines]
    scored = [(share, line) for share, line in scored if share is not None]
    untranslated_max = max((share for share, line in scored if share < 0.10 and letter_count(line) >= 20), default=0.0)
    legitimate = [(share, line) for share, line in scored if share >= 0.10 and letter_count(line) >= 20]
    legitimate_min = min((share for share, _ in legitimate), default=1.0)
    lines.append("")
    lines.append("THE GAP ON THE REAL ARTIFACT (letter floor 20, which excludes only TTS tags and OCR debris):")
    lines.append(f"  highest target share among UNTRANSLATED delivered lines : {untranslated_max:.4f}")
    lines.append(f"  lowest  target share among LEGITIMATE delivered lines   : {legitimate_min:.4f}")
    lines.append(f"  GAP = {legitimate_min - untranslated_max:+.4f}, and nothing lies inside it")
    lines.append("")
    lines.append("  the legitimate floor, quoted -- the five lowest, so the margin can be judged rather than trusted:")
    for share, line in sorted(legitimate)[:5]:
        lines.append(f"    share={share:.3f} letters={letter_count(line):<4} [{classify_control_form(line)}] {line[:110]!r}")
    lines.append("")
    lines.append(
        "  Read the gap for what it is: on ONE artifact, in ONE language pair, the two populations sit at 0.00 and\n"
        "  0.41 with nothing between. That is a wide margin, and it is also a single observation of a margin."
    )
    report["delivered_artifact"] = {
        "lines": len(artifact_lines),
        "letters": total_letters,
        "sweep": sweep,
        "untranslated_lines": len(english),
        "untranslated_letters": english_letters,
        "untranslated_share_of_artifact": round(100 * english_letters / total_letters, 2),
        "byte_equal_to_a_source_paragraph": verbatim,
        "max_share_untranslated": round(untranslated_max, 4),
        "min_share_legitimate": round(legitimate_min, 4),
        "gap": round(legitimate_min - untranslated_max, 4),
    }
    return lines


# ---------------------------------------------------------------------------
# 6. Cross-book
# ---------------------------------------------------------------------------


def section_cross_book(report: dict[str, Any]) -> list[str]:
    lines = [
        "",
        "=" * 104,
        "6. CROSS-BOOK CHECK -- five tracked runs, BIASED sample (random 60 plus the three extremes)",
        "=" * 104,
    ]
    lines.append(
        "The per-paragraph dumps of these runs were never tracked, so these pairs are the quoted samples from\n"
        "comparison_paragraphs.md. They over-represent the extremes on purpose, which makes them a fair place to\n"
        "look for the WORST delivered paragraph and an unfair place to read a median. Both are reported."
    )
    lines.append("")
    lines.append("  book                 pairs  delivered: min    p05    median   FALLBACK max  identical")
    per_book: dict[str, Any] = {}
    totals = Counter()
    for book in FINAL_RUN_BOOKS:
        path = FINAL_RUN_DIR / book / "comparison_paragraphs.md"
        if not path.exists():
            continue
        entries = parse_comparison_paragraphs(path)
        delivered = [value for value in (target_letter_share(item["delivered"]) for item in entries) if value is not None]
        source = [value for value in (target_letter_share(item["source"]) for item in entries) if value is not None]
        identical = sum(1 for item in entries if item["delivered"].strip() == item["source"].strip())
        stats = quantiles(delivered)
        totals["pairs"] += len(entries)
        totals["identical"] += identical
        lines.append(
            f"  {book:<20} {len(entries):>5}       {min(delivered):>8.4f}  {float(stats['p05']):.3f}  "
            f"{float(stats['median']):.4f}  {max(source):>12.4f}  {identical:>9}"
        )
        per_book[book] = {
            "pairs": len(entries),
            "delivered_target_share": stats,
            "source_target_share": quantiles(source),
            "identical": identical,
        }
    lines.append(f"  {'TOTAL':<20} {totals['pairs']:>5}{'':>44}{totals['identical']:>11}")
    assert totals["pairs"] == sum(book["pairs"] for book in per_book.values())

    lines.append("")
    lines.append("Sweep on the pooled cross-book sample (source text as FALLBACK, delivered text as DELIVERED):")
    pooled = [item for book in FINAL_RUN_BOOKS for item in parse_comparison_paragraphs(FINAL_RUN_DIR / book / "comparison_paragraphs.md") if (FINAL_RUN_DIR / book / "comparison_paragraphs.md").exists()]
    lines.append("    floor  cut     TP                      FP")
    cross_sweep: list[dict[str, Any]] = []
    for floor in (0, 20, 60):
        for cut in (0.10, 0.30, 0.50, 0.70):

            def flagged(text: str) -> bool:
                if letter_count(text) < floor:
                    return False
                share = target_letter_share(text)
                return share is not None and share < cut

            true_positive = sum(1 for item in pooled if flagged(item["source"]))
            false_positive = sum(1 for item in pooled if flagged(item["delivered"]))
            lines.append(
                f"    {floor:>5}  {cut:.2f}  {true_positive:>4}/{len(pooled):<4} ({100 * true_positive / len(pooled):5.1f}%)"
                f"     {false_positive:>3}/{len(pooled):<4} ({100 * false_positive / len(pooled):5.1f}%)"
            )
            cross_sweep.append({"letter_floor": floor, "cut": cut, "tp": true_positive, "fp": false_positive, "of": len(pooled)})

    lines.append("")
    lines.append("Worst delivered paragraph per book, quoted, so every number above is inspectable:")
    worst_report: dict[str, Any] = {}
    for book in FINAL_RUN_BOOKS:
        path = FINAL_RUN_DIR / book / "comparison_paragraphs.md"
        if not path.exists():
            continue
        entries = [item for item in parse_comparison_paragraphs(path) if target_letter_share(item["delivered"]) is not None]
        worst = min(entries, key=lambda item: share_or(item["delivered"], 1.0))
        share = share_or(worst["delivered"], 0.0)
        lines.append(
            f"  {book} / {worst['paragraph_id']} share={share:.4f} letters={letter_count(worst['delivered'])} "
            f"[{classify_control_form(worst['delivered'])}] section={worst['section']!r}"
        )
        lines.append(f"      {worst['delivered'][:160]!r}")
        worst_report[book] = {
            "paragraph_id": worst["paragraph_id"],
            "share": round(share, 4),
            "letters": letter_count(worst["delivered"]),
            "form": classify_control_form(worst["delivered"]),
            "text": worst["delivered"][:200],
        }
    report["cross_book"] = {
        "per_book": per_book,
        "totals": dict(totals),
        "pooled_sweep": cross_sweep,
        "worst_delivered": worst_report,
    }
    return lines


# ---------------------------------------------------------------------------
# 7. The index
# ---------------------------------------------------------------------------


def section_index_case(report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 104, "7. THE RETHINKING MONEY INDEX -- 422 paragraphs no region covers", "=" * 104]
    lines.append(
        "spec 054 measured it (specs/054-audiobook-mode-review-and-run/spec.md:495-497): notes 264/264 cut,\n"
        "bibliography 177/177 cut, index 10 of 432 -- 422 paragraphs and 22 906 characters of index survive into\n"
        "the narrated set. Under FR-A8 (prose = registry minus front matter minus TOC minus back matter) those 422\n"
        "arrive as PROSE, because no region claims them."
    )
    findings: dict[str, Any] = {}
    for book in FINAL_RUN_BOOKS:
        path = FINAL_RUN_DIR / book / "comparison_paragraphs.md"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^## Абзацы, оставшиеся в озвучке на английском \((\d+)\)", text, re.MULTILINE)
        declared = int(match.group(1)) if match else None
        entries = [item for item in parse_comparison_paragraphs(path) if item["section"].startswith("Абзацы, оставшиеся")]
        findings[book] = {"declared_count": declared, "quoted": len(entries)}
        lines.append("")
        lines.append(f"  {book}: paragraphs the run itself recorded as left in English = {declared}")
        for item in entries:
            share = target_letter_share(item["delivered"])
            lines.append(
                f"      {item['paragraph_id']}: target_share={0.0 if share is None else round(share, 4)}, "
                f"letters={letter_count(item['delivered'])}, form={classify_control_form(item['delivered'])}, "
                f"identical_to_source={item['delivered'].strip() == item['source'].strip()}"
            )
            lines.append(f"        {item['delivered'][:170]!r}")

    average_chars = 22906 / 422
    lines.append("")
    lines.append(
        "WHY THE RECORDED '0 and 1' NUMBERS UNDERSTATE THE RESIDUE. Each comparison_paragraphs.md states the\n"
        "detector that produced those sections: 'at least 60 letters, under 30% Cyrillic'. The surviving index\n"
        f"averages {average_chars:.1f} characters per paragraph (22 906 / 422), so the majority of the residue sits BELOW\n"
        "that 60-letter floor and was never counted. The single hit that did clear the floor is an index row of 161\n"
        "letters, delivered byte-identical to its English source. So '1 paragraph left in English' is a property of\n"
        "the floor, not a measurement of the book."
    )
    lines.append("")
    lines.append(
        "CONSEQUENCE FOR THE CONTRACT. Under FR-A5 a quality rejection on a prose paragraph loses\n"
        "`fallback_continue` and escalates to `fail`. Any share-based completeness rule therefore turns those\n"
        "index rows into hard run failures on a book whose prose is in fact fully translated -- while the pair rule\n"
        "(rule B) flags exactly the same rows, because they are delivered verbatim. Neither rule can tell an index\n"
        "row from lost prose: the difference is REGION, and the region detector is the thing that misses them.\n"
        "The honest order of work is therefore: close the index region first, then wire the invariant. Otherwise\n"
        "the invariant's first act on this corpus is to fail a good book several hundred times."
    )
    report["index_case"] = {"per_book": findings, "index_avg_chars": round(average_chars, 1)}
    return lines


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_report() -> tuple[str, dict[str, Any]]:
    rows = load_jsonl(AUDIOBOOK_PAIRS)
    regions = load_paragraph_regions(SOURCE_BLOCKS)
    missing = [row["paragraph_id"] for row in rows if row["paragraph_id"] not in regions]
    if missing:
        raise SystemExit(f"{len(missing)} pairs have no region decision, e.g. {missing[:5]}")
    report: dict[str, Any] = {}
    lines = [
        "TRANSLATION-SIGNAL MEASUREMENT",
        "Recorded runs only. No paid run, no network, no LLM, stdlib only.",
        f"Full-book corpus : {AUDIOBOOK_PAIRS.relative_to(PROJECT_ROOT)} -- {len(rows)} pairs,"
        " Money & Sustainability, audiobook path, en->ru",
        f"Region decisions : {SOURCE_BLOCKS.relative_to(PROJECT_ROOT)} -- the run's own narration_include per block",
        f"Cross-book corpus: {FINAL_RUN_DIR.relative_to(PROJECT_ROOT)}/*/comparison_paragraphs.md -- 5 books, sampled",
        "",
        "Every target-alphabet number below is a CYRILLIC number, because every recorded run is en->ru.",
        "Whether the same shape holds for another target language is NOT tested by this corpus.",
    ]
    lines += section_data_shape(rows, regions, report)
    lines += section_features(rows, regions, report)
    lines += section_control_group(rows, regions, report)
    lines += section_threshold_sweep(rows, regions, report)
    lines += section_delivered_artifact(rows, report)
    lines += section_cross_book(report)
    lines += section_index_case(report)
    return "\n".join(lines), report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
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
