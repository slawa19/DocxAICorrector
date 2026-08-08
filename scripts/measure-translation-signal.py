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

  DELIVERED   the text that reached the artifact for a paragraph (`after`, and only where
              the outcome says it was found there). A completeness check MUST NOT flag it.
  FALLBACK*   the source text of the same paragraph (`before`). Not a synthetic
              construction: the generator returns the block's source text verbatim when the
              model gave no accepted answer (`generation/_generation.py:2013-2091`, four
              substitution branches), so `before` IS, byte for byte, what an untranslated
              delivery looks like. A completeness check MUST flag every one of these.
  CONTROL     delivered text that is legitimately NOT in the target language -- proper
              names, citations, index rows, URLs, acronyms, markup residue. A completeness
              check MUST NOT flag these either, and this is the half that breaks rules.

Candidate features, each computed on the delivered text alone or on the pair:

  target_letter_share  Cyrillic letters / (Cyrillic + Latin letters)   [single text]
  letter_count         Cyrillic + Latin letters                        [single text]
  length_ratio         len(after) / len(before)                        [pair, recorded]
  change_ratio         recorded character-level change                 [pair, recorded]
  identical            recorded byte equality                          [pair, recorded]
  source_equality      after == before and the source carries a letter [pair, derived]

DATA, AND WHY IT IS THIS DATA
-----------------------------
MAIN CORPUS -- the 2026-08-06 confirming run, five paragraph-pair dumps, 7 233 records:

    artifacts/audiobook_final_run/creating_wealth/all_paragraph_pairs.jsonl        1519
    artifacts/audiobook_final_run/money_sustainability/all_paragraph_pairs.jsonl   1318
    artifacts/audiobook_final_run/rethinking_money/all_paragraph_pairs.jsonl       1736
    artifacts/audiobook_final_run/value_of_everything/all_paragraph_pairs.jsonl    1277
    artifacts/audiobook_final_run/money_translate_docx/all_paragraph_pairs.jsonl   1383

Four books on the AUDIOBOOK path plus the same Money & Sustainability document on the
DOCUMENT path -- and that fifth run carries the result, because the two paths differ in the
one way that decides the question (section 7).

Those files are GITIGNORED on purpose (`.gitignore:80`, `artifacts/**/all_paragraph_pairs.jsonl`;
the dumps stay on disk beside the run that produced them, policy set by `f129a21`). They will
not be in the next reader's checkout, so this script RUNS WITHOUT THEM: each section that
needs them is skipped with a message naming what is missing, and the git-recoverable half
below still runs in full.

SECOND CORPUS -- recovered from git history. It is the only place with two things the dumps
do not carry: per-paragraph REGION decisions, and a delivered narration ARTIFACT.

    mkdir -p .run/data
    git show f2a49da:artifacts/audiobook_first_run/all_paragraph_pairs.jsonl \
        > .run/data/audiobook_first_run.jsonl
    git show f2a49da:artifacts/audiobook_first_run/source_blocks_with_narration_decision.json \
        > .run/data/source_blocks.json
    git show f2a49da:artifacts/audiobook_first_run/Money_Sustainability_pdf_full_heldout.tts.txt \
        > .run/data/delivered.tts.txt
    git show 7819933:artifacts/literary_edit_first_run/all_paragraph_pairs.jsonl \
        > .run/data/literary_edit_first_run.jsonl

WHICH PARAGRAPHS COUNT AS PROSE
-------------------------------
Two prose sets are reported side by side, because they disagree by a factor of two to three
and only one of them is the contract's:

  REGION prose (spec 059 A-6): source registry minus front matter, minus bounded TOC, minus
  the back-matter region. Reconstructed from the run's own recorded block decisions
  (`source_blocks_with_narration_decision.json`), available for ONE run.

  `source_is_prose`, the flag carried in every dump. No code in this repository produces it;
  section 2 reconstructs it on all five books and shows it is a LENGTH SCREEN. Numbers
  computed on the flag are reported next to numbers computed on everything the run delivered,
  so the difference is visible rather than assumed.

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
AUDIOBOOK_BOOKS = ("creating_wealth", "money_sustainability", "rethinking_money", "value_of_everything")
DOCUMENT_BOOKS = ("money_translate_docx",)
FINAL_RUN_BOOKS = AUDIOBOOK_BOOKS + DOCUMENT_BOOKS

# `narration_landed` / `docx_landed` mean the delivered text was found in the artifact. Any
# other outcome means the dump cannot say what the artifact holds instead -- section 9.
DELIVERED_OUTCOMES = frozenset({"narration_landed", "docx_landed"})

DUMPS_HINT = (
    "SKIPPED -- the five paragraph-pair dumps are gitignored (.gitignore:80) and live on disk beside\n"
    "  the run that produced them: artifacts/audiobook_final_run/<book>/all_paragraph_pairs.jsonl.\n"
    "  Without them only the git-recoverable half of this report is produced."
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

LETTER_FLOORS = (0, 20, 60, 120)
CUTS = (0.10, 0.20, 0.30, 0.50)

# The empty band measured on ONE book in the first pass. Section 5 tests whether it survives.
ONE_BOOK_BAND_TOP = 0.4118

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


def share_or(text: str, default: float) -> float:
    """Explicit fallback for texts with no letters. `share or default` is a bug: 0.0 is falsy."""
    share = target_letter_share(text)
    return default if share is None else share


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
URL_OR_DOI = re.compile(
    r"(?:https?://|www\.[a-z0-9-]+\.|[a-z0-9-]+\.(?:com|net|org|ru)\b|doi\.org|\b10\.\d{4,}/)", re.IGNORECASE
)
PAGE_RANGE = re.compile(r"\d+\s*[–—-]\s*\d+")
WORD = re.compile(r"[A-Za-zЀ-ӿ][A-Za-zЀ-ӿ'’]*")


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


def load_final_run_dumps() -> dict[str, list[dict[str, Any]]]:
    """The five 2026-08-06 dumps, in a fixed order, skipping any that are not on disk."""
    corpus: dict[str, list[dict[str, Any]]] = {}
    for book in FINAL_RUN_BOOKS:
        path = FINAL_RUN_DIR / book / "all_paragraph_pairs.jsonl"
        if path.exists():
            corpus[book] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return corpus


def delivered_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row["outcome"] in DELIVERED_OUTCOMES]


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


def shares_of(texts: Sequence[str]) -> list[float]:
    return [value for value in (target_letter_share(text) for text in texts) if value is not None]


# ---------------------------------------------------------------------------
# 1. The corpus
# ---------------------------------------------------------------------------


def section_corpus(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "1. THE CORPUS -- five recorded runs, and what each record can and cannot say", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    lines.append("  book                   records  delivered  not delivered  outcomes")
    totals = Counter()
    per_book: dict[str, Any] = {}
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        outcomes = dict(Counter(row["outcome"] for row in rows))
        totals["records"] += len(rows)
        totals["delivered"] += len(delivered)
        totals["not_delivered"] += len(rows) - len(delivered)
        lines.append(f"  {book:<22} {len(rows):>8}  {len(delivered):>9}  {len(rows) - len(delivered):>13}  {outcomes}")
        per_book[book] = {"records": len(rows), "delivered": len(delivered), "outcomes": outcomes}
    lines.append(
        f"  {'TOTAL':<22} {totals['records']:>8}  {totals['delivered']:>9}  {totals['not_delivered']:>13}"
    )
    assert totals["records"] == sum(entry["records"] for entry in per_book.values())
    assert totals["delivered"] + totals["not_delivered"] == totals["records"]

    lines.append("")
    lines.append("Fields differ between the two paths, and the difference is not cosmetic:")
    for book, rows in corpus.items():
        lines.append(f"  {book:<22} {sorted(rows[0].keys())}")
    lines.append(
        "  The document run carries no `manual_edit_classes` and no `source_is_heading`, and names its\n"
        "  outcomes `docx_landed` / `not_found_in_docx`. Any comparison across the two paths uses only the\n"
        "  fields both carry."
    )
    report["corpus"] = {"per_book": per_book, "totals": dict(totals)}
    return lines


# ---------------------------------------------------------------------------
# 2. The prose flag
# ---------------------------------------------------------------------------


def section_prose_flag(
    corpus: dict[str, list[dict[str, Any]]], regions: dict[str, dict[str, Any]] | None, report: dict[str, Any]
) -> list[str]:
    lines = ["", "=" * 108, "2. WHAT `source_is_prose` ACTUALLY MEANS -- reconstructed on all five runs", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    lines.append("No code in this repository produces this flag. Reconstructing it from the data, per book:")
    lines.append("")
    lines.append("  book                   records  flagged   share  shortest flagged source  covered by 'len >= 250'")
    per_book: dict[str, Any] = {}
    for book, rows in corpus.items():
        flagged = [row for row in rows if row["source_is_prose"]]
        shortest = min((len(row["before"]) for row in flagged), default=0)
        # `source_is_heading` is absent on the document run; length alone is the shared condition.
        missed = sum(1 for row in flagged if len(row["before"]) < 250)
        lines.append(
            f"  {book:<22} {len(rows):>8}  {len(flagged):>7}  {100 * len(flagged) / len(rows):>5.1f}%  "
            f"{shortest:>23}  {'all of them' if missed == 0 else f'{missed} exceptions'}"
        )
        per_book[book] = {
            "records": len(rows),
            "flagged": len(flagged),
            "shortest_flagged_source_chars": shortest,
            "flagged_under_250": missed,
        }
    lines.append("")
    lines.append(
        "The same floor on every book: the shortest paragraph the flag calls prose is 250-253 characters, with\n"
        "no exceptions anywhere in 7 233 records. `source_is_prose` is a LENGTH SCREEN. It was built to pick a\n"
        "reading sample and it does that well; it is not the contract's prose, and its 250-character floor is\n"
        "exactly the kind of form threshold Constitution VII refuses in production."
    )

    if regions is not None:
        first_run = load_jsonl(AUDIOBOOK_PAIRS)
        region_prose = [row for row in first_run if regions[row["paragraph_id"]]["narration_include"]]
        flagged = [row for row in first_run if row["source_is_prose"]]
        lines.append("")
        lines.append("Against the REGION definition -- available for one run only, from its own block decisions:")
        lines.append(
            "  region exclusions recorded by the run: "
            + str(dict(Counter(info["exclusion_reason"] for info in regions.values() if not info["narration_include"])))
        )
        lines.append(f"  paragraphs in the source registry: {len(regions)}")
        lines.append(f"  REGION prose (spec 059 A-6):       {len(region_prose)}")
        lines.append(
            f"  `source_is_prose` == true:         {len(flagged)} "
            f"({100 * len(flagged) / len(region_prose):.1f}% of the region set)"
        )
        lines.append(
            "  roles inside the region: "
            + str(dict(Counter(info["role"] for info in regions.values() if info["narration_include"])))
        )
        unexplained = [
            row
            for row in first_run
            if not row["source_is_heading"]
            and len(row["before"]) >= 250
            and row["before"].lstrip()[:1].isupper()
            and not row["source_is_prose"]
        ]
        lines.append(
            f"  paragraphs meeting every necessary condition yet flagged NOT prose: {len(unexplained)} -- plainly prose:"
        )
        for row in unexplained[:3]:
            lines.append(f"      {row['paragraph_id']} ({len(row['before'])} chars) {row['before'][:96]!r}")
        report["prose_flag_region"] = {
            "registry_paragraphs": len(regions),
            "region_prose": len(region_prose),
            "flagged": len(flagged),
            "flag_share_of_region": round(100 * len(flagged) / len(region_prose), 1),
            "unexplained_exclusions": len(unexplained),
        }
    report["prose_flag"] = per_book
    return lines


# ---------------------------------------------------------------------------
# 3. Features
# ---------------------------------------------------------------------------


def section_features(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "3. CANDIDATE FEATURES, PER BOOK -- everything the run delivered, not the flag's subset", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    per_book: dict[str, Any] = {}

    lines.append("FEATURE 1 -- target_letter_share of the DELIVERED text:")
    lines.append("  book                      n     min    p01    p05    p25    med    p95    max   flag subset min")
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        values = shares_of([row["after"] for row in delivered])
        flagged = shares_of([row["after"] for row in delivered if row["source_is_prose"]])
        stats = quantiles(values)
        lines.append(
            f"  {book:<22} {stats['n']:>4}  "
            + "  ".join(f"{float(stats[key]):>5.3f}" for key in COLUMNS)
            + f"   {min(flagged):>14.3f}"
        )
        per_book.setdefault(book, {})["delivered_target_share"] = stats
        per_book[book]["flag_subset_min_share"] = round(min(flagged), 4)
    lines.append(
        "  The last column is the whole reason section 2 matters: read through the flag, the worst delivered\n"
        "  translation looks far cleaner than it is, because the flag admits no short text."
    )

    lines.append("")
    lines.append("FEATURE 1b -- target_letter_share of the SOURCE text (what a fallback delivery would show):")
    lines.append("  book                      n     max    p95    med   -- a single number decides this feature")
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        values = shares_of([row["before"] for row in delivered])
        stats = quantiles(values)
        lines.append(
            f"  {book:<22} {stats['n']:>4}  {float(stats['max']):>5.3f}  {float(stats['p95']):>5.3f}  {float(stats['median']):>5.3f}"
        )
        per_book[book]["source_target_share"] = stats
    lines.append("  No source paragraph in 7 233 records carries a single Cyrillic letter. The FALLBACK class is exact.")

    lines.append("")
    lines.append("FEATURE 2 -- length_ratio. FALLBACK is 1.0 by construction; compare that to the delivered spread:")
    lines.append("  book                      n     min    p01    p05    p25    med    p95    max")
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        stats = quantiles([row["length_ratio"] for row in delivered])
        lines.append(f"  {book:<22} {stats['n']:>4}  " + "  ".join(f"{float(stats[key]):>5.3f}" for key in COLUMNS))
        per_book[book]["length_ratio"] = stats
    lines.append("  Every median sits within a few percent of 1.0 -- the failure value is the middle of the norm.")

    lines.append("")
    lines.append("FEATURE 3 -- change_ratio. FALLBACK is 0.0 by construction:")
    lines.append("  book                      n     min    p01    p05    p25    med    p95    max")
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        stats = quantiles([row["change_ratio"] for row in delivered])
        lines.append(f"  {book:<22} {stats['n']:>4}  " + "  ".join(f"{float(stats[key]):>5.3f}" for key in COLUMNS))
        per_book[book]["change_ratio"] = stats

    lines.append("")
    lines.append("FEATURE 4 -- letter_count of the SOURCE, bucketed. This decides what a letter floor costs:")
    lines.append("  book                       0    1-19   20-59  60-119   120+   under 60")
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        buckets = Counter()
        for row in delivered:
            letters = letter_count(row["before"])
            buckets[
                "0"
                if letters == 0
                else "1-19"
                if letters < 20
                else "20-59"
                if letters < 60
                else "60-119"
                if letters < 120
                else "120+"
            ] += 1
        short = buckets["0"] + buckets["1-19"] + buckets["20-59"]
        lines.append(
            f"  {book:<22} {buckets['0']:>5} {buckets['1-19']:>7} {buckets['20-59']:>7} {buckets['60-119']:>7} "
            f"{buckets['120+']:>6}   {100 * short / len(delivered):>5.1f}%"
        )
        per_book[book]["source_letter_buckets"] = dict(buckets)
        per_book[book]["source_under_60_letters_pct"] = round(100 * short / len(delivered), 1)

    report["features"] = per_book
    return lines


# ---------------------------------------------------------------------------
# 4. Control group
# ---------------------------------------------------------------------------


def section_control_group(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "4. CONTROL GROUP -- delivered text that is legitimately NOT in the target language", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    lines.append(
        "Collection net, and its limit stated first: every delivered paragraph whose target_letter_share is\n"
        "under 0.90 or undefined, bucketed BY FORM. The 0.90 net is deliberately loose so the group is not\n"
        "selected by the number this report is trying to justify. Buckets are form-based, no word lists, and\n"
        "they are measurement scaffolding rather than a proposed detector."
    )
    lines.append("")
    forms = (
        "running_text_shape",
        "under_20_letters",
        "url_or_domain",
        "numeric_reference_row",
        "titlecase_name_run",
        "no_letters_at_all",
        "acronym_or_allcaps",
    )
    lines.append("  book                     net  " + "".join(f"{name[:13]:>15}" for name in forms))
    grand = Counter()
    per_book: dict[str, Any] = {}
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        net = [row for row in delivered if share_or(row["after"], 0.0) < 0.9]
        counted = Counter(classify_control_form(row["after"]) for row in net)
        grand.update(counted)
        lines.append(f"  {book:<22} {len(net):>5}  " + "".join(f"{counted[name]:>15}" for name in forms))
        per_book[book] = {"net": len(net), "of_delivered": len(delivered), "forms": dict(counted)}
    lines.append(f"  {'TOTAL':<22} {sum(grand.values()):>5}  " + "".join(f"{grand[name]:>15}" for name in forms))
    assert sum(grand.values()) == sum(entry["net"] for entry in per_book.values())

    lines.append("")
    lines.append(
        f"The control group is now {sum(grand.values())} paragraphs across five runs, against 75 on one book. It is no\n"
        "longer structurally starved -- and the reason is section 7: the document run delivers the reference\n"
        "apparatus the audiobook runs cut out before the model ever sees it."
    )
    report["control_group"] = {"per_book": per_book, "totals": dict(grand)}
    return lines


# ---------------------------------------------------------------------------
# 5. The gap
# ---------------------------------------------------------------------------


def _flagger(floor: int, cut: float) -> Callable[[str], bool]:
    def flagged(text: str) -> bool:
        if letter_count(text) < floor:
            return False
        share = target_letter_share(text)
        return share is not None and share < cut

    return flagged


def section_gap(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "5. IS THERE A GAP? -- the one-book answer tested on five runs", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    pooled = [row for rows in corpus.values() for row in delivered_rows(rows)]

    lines.append(
        "RULE A (single-text share): FLAG delivered text when letter_count >= floor and target_letter_share < cut.\n"
        "  TP = FALLBACK caught (the owner's requirement is all of them), FP = delivered text wrongly flagged."
    )
    lines.append("")
    lines.append("Pooled over all five runs, 7 103 delivered paragraphs:")
    lines.append("    floor  cut     TP                    FP")
    sweep: list[dict[str, Any]] = []
    for floor in LETTER_FLOORS:
        for cut in CUTS:
            flagged = _flagger(floor, cut)
            true_positive = sum(1 for row in pooled if flagged(row["before"]))
            false_positive = sum(1 for row in pooled if flagged(row["after"]))
            lines.append(
                f"    {floor:>5}  {cut:.2f}  {true_positive:>5}/{len(pooled)} ({100 * true_positive / len(pooled):5.1f}%)"
                f"   {false_positive:>4}/{len(pooled)} ({100 * false_positive / len(pooled):5.2f}%)"
            )
            sweep.append(
                {"letter_floor": floor, "cut": cut, "tp": true_positive, "fp": false_positive, "of": len(pooled)}
            )

    lines.append("")
    lines.append("The same rule per book, at the floor/cut the one-book pass recommended (floor 20, cut 0.20):")
    lines.append("  book                   delivered   TP            FP")
    flagged = _flagger(20, 0.20)
    per_book_rule: dict[str, Any] = {}
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        true_positive = sum(1 for row in delivered if flagged(row["before"]))
        false_positive = [row for row in delivered if flagged(row["after"])]
        lines.append(
            f"  {book:<22} {len(delivered):>9}   {true_positive:>5} ({100 * true_positive / len(delivered):5.1f}%)"
            f"   {len(false_positive):>4} ({100 * len(false_positive) / len(delivered):5.2f}%)"
        )
        per_book_rule[book] = {"tp": true_positive, "fp": len(false_positive), "of": len(delivered)}
    report["rule_a_sweep"] = sweep
    report["rule_a_per_book_floor20_cut020"] = per_book_rule

    lines.append("")
    lines.append("-" * 108)
    lines.append(
        f"DOES THE ONE-BOOK BAND SURVIVE? On Money & Sustainability's delivered artifact the untranslated lines sat\n"
        f"at 0.0000 and the lowest legitimate line at {ONE_BOOK_BAND_TOP:.4f}, with nothing between. Testing that band\n"
        "against every delivered paragraph of all five runs, at a 20-letter floor:"
    )
    lines.append("")
    lines.append("  book                   in the band  worst offender")
    band_report: dict[str, Any] = {}
    all_band: list[tuple[str, dict[str, Any]]] = []
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        band = [
            row
            for row in delivered
            if letter_count(row["after"]) >= 20
            and target_letter_share(row["after"]) is not None
            and target_letter_share(row["after"]) < ONE_BOOK_BAND_TOP
        ]
        all_band.extend((book, row) for row in band)
        worst = max(band, key=lambda row: letter_count(row["after"]), default=None)
        detail = (
            f"{worst['paragraph_id']} ({letter_count(worst['after'])} letters, share "
            f"{target_letter_share(worst['after']):.3f})"
            if worst
            else "-- none --"
        )
        lines.append(f"  {book:<22} {len(band):>11}  {detail}")
        band_report[book] = {"in_band": len(band), "worst": detail}
    lines.append(f"  {'TOTAL':<22} {len(all_band):>11}")
    assert len(all_band) == sum(entry["in_band"] for entry in band_report.values())

    lines.append("")
    lines.append("THE BAND IS NOT EMPTY. Every occupant, longest first, so the reader judges rather than trusts:")
    for book, row in sorted(all_band, key=lambda item: -letter_count(item[1]["after"]))[:14]:
        lines.append(
            f"    {book}/{row['paragraph_id']} share={target_letter_share(row['after']):.3f} "
            f"letters={letter_count(row['after']):<4} identical={row['identical']} "
            f"prose_flag={row['source_is_prose']} form={classify_control_form(row['after'])}"
        )
        lines.append(f"        {row['after'][:140]!r}")

    hard = [
        (book, row)
        for book, row in all_band
        if letter_count(row["after"]) >= 60 and target_letter_share(row["after"]) < 0.10
    ]
    lines.append("")
    lines.append(
        f"THE HARD CORE -- delivered text with at least 60 letters and under 10% target alphabet: {len(hard)} of "
        f"{len(pooled)}."
    )
    lines.append(
        "  Where they live matters more than how many: " + str(dict(Counter(book for book, _ in hard))) + "."
    )
    for book, row in hard:
        lines.append(
            f"    {book}/{row['paragraph_id']} share={target_letter_share(row['after']):.3f} "
            f"letters={letter_count(row['after'])} identical={row['identical']} prose_flag={row['source_is_prose']}"
        )
        lines.append(f"        {row['after'][:150]!r}")
    report["band"] = {"top": ONE_BOOK_BAND_TOP, "per_book": band_report, "total": len(all_band), "hard_core": len(hard)}
    return lines


# ---------------------------------------------------------------------------
# 6. Pair rule
# ---------------------------------------------------------------------------


def section_pair_rule(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "6. RULE B -- the pair: byte equality against the paragraph's own source", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    lines.append(
        "FLAG when delivered == source verbatim AND the source carries at least one letter.\n"
        "No threshold, no alphabet, no word list -- so Constitution VII is untouched by construction."
    )
    lines.append("")
    lines.append("  book                   delivered     TP  miss(no letters)    FP    FP rate")
    totals = Counter()
    per_book: dict[str, Any] = {}
    all_false: list[tuple[str, dict[str, Any]]] = []
    for book, rows in corpus.items():
        delivered = delivered_rows(rows)
        blind = sum(1 for row in delivered if letter_count(row["before"]) == 0)
        true_positive = len(delivered) - blind
        false_positive = [row for row in delivered if row["after"] == row["before"] and letter_count(row["before"]) > 0]
        all_false.extend((book, row) for row in false_positive)
        totals["delivered"] += len(delivered)
        totals["tp"] += true_positive
        totals["blind"] += blind
        totals["fp"] += len(false_positive)
        lines.append(
            f"  {book:<22} {len(delivered):>9}  {true_positive:>5}  {blind:>16}  {len(false_positive):>4}   "
            f"{100 * len(false_positive) / len(delivered):>6.2f}%"
        )
        per_book[book] = {
            "delivered": len(delivered),
            "tp": true_positive,
            "blind": blind,
            "fp": len(false_positive),
        }
    lines.append(
        f"  {'TOTAL':<22} {totals['delivered']:>9}  {totals['tp']:>5}  {totals['blind']:>16}  {totals['fp']:>4}   "
        f"{100 * totals['fp'] / totals['delivered']:>6.2f}%"
    )
    assert totals["tp"] + totals["blind"] == totals["delivered"]
    assert totals["fp"] == len(all_false)

    lines.append("")
    lines.append(f"EVERY false alarm, all {len(all_false)} of them, by form -- this is the price of the first line:")
    by_form = Counter(classify_control_form(row["before"]) for _, row in all_false)
    lines.append(f"  {dict(by_form)}")
    for book, row in sorted(all_false, key=lambda item: -letter_count(item[1]["before"])):
        lines.append(
            f"    {book}/{row['paragraph_id']} letters={letter_count(row['before']):<4} "
            f"form={classify_control_form(row['before']):<22} prose_flag={row['source_is_prose']}"
        )
        lines.append(f"        {row['before'][:130]!r}")
    lines.append("")
    lines.append(
        "Read the list, not the rate: with two exceptions the false alarms are acronym headings, bare proper\n"
        "names, bare URLs and index entries -- text with nothing in it to translate. The two exceptions are\n"
        "footnote continuation rows on the DOCUMENT path, and they are genuinely untranslated apparatus rather\n"
        "than a rule misfiring. Not one is a lost prose paragraph."
    )

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
            "  property of the job, readable from it, not a tuning knob."
        )
        report.setdefault("pair_rule", {})["literary_edit_identical"] = [len(identical_rows), len(edit_rows)]
    report.setdefault("pair_rule", {}).update(
        {
            "per_book": per_book,
            "totals": dict(totals),
            "false_alarm_forms": dict(by_form),
            "false_alarms": [f"{book}/{row['paragraph_id']}" for book, row in all_false],
        }
    )
    return lines


# ---------------------------------------------------------------------------
# 7. The two paths
# ---------------------------------------------------------------------------


def section_two_paths(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "7. WHY THE AUDIOBOOK PATH LOOKED CLEAN -- and the document path does not", "=" * 108]
    if not corpus:
        lines.append(DUMPS_HINT)
        return lines
    lines.append(
        "Both paths ran the same book. The audiobook run cuts the back-matter region BEFORE the model sees it\n"
        "(`reference_region`, `toc_structural_role` in `excluded_blocks.md`); the document run keeps footnotes and\n"
        "bibliography, because a reader wants them. So the two runs disagree about what reaches the delivered set."
    )
    lines.append("")
    lines.append("  path        book                   delivered  min share  min share (>=60 letters)  hard core")
    per_path: dict[str, Any] = {}
    for book, rows in corpus.items():
        path_name = "document" if book in DOCUMENT_BOOKS else "audiobook"
        delivered = delivered_rows(rows)
        values = shares_of([row["after"] for row in delivered])
        with_floor = [
            target_letter_share(row["after"])
            for row in delivered
            if letter_count(row["after"]) >= 60 and target_letter_share(row["after"]) is not None
        ]
        hard = sum(
            1
            for row in delivered
            if letter_count(row["after"]) >= 60
            and target_letter_share(row["after"]) is not None
            and target_letter_share(row["after"]) < 0.10
        )
        lines.append(
            f"  {path_name:<11} {book:<22} {len(delivered):>9}  {min(values):>9.4f}  {min(with_floor):>23.4f}  {hard:>9}"
        )
        per_path[book] = {
            "path": path_name,
            "min_share": round(min(values), 4),
            "min_share_60_letters": round(min(with_floor), 4),
            "hard_core": hard,
        }
    lines.append("")
    lines.append(
        "On all four AUDIOBOOK runs the delivered minimum at a 60-letter floor stays between 0.44 and 0.82 and the\n"
        "hard core is empty. On the DOCUMENT run it is 0.0000 and the hard core is not empty. The one-book gap was\n"
        "real, and it was a property of the REGION CUT, not of the language signal. The path that actually\n"
        "delivers untranslated text -- the one spec 059 A-1 says substitutes rather than drops -- is the path\n"
        "where the separation fails."
    )
    report["two_paths"] = per_path
    return lines


# ---------------------------------------------------------------------------
# 8. The index
# ---------------------------------------------------------------------------


def section_index_case(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "8. THE RETHINKING MONEY INDEX -- 422 paragraphs no region covers", "=" * 108]
    lines.append(
        "spec 054 measured it (`specs/054-audiobook-mode-review-and-run/spec.md:495-497`): notes 264/264 cut,\n"
        "bibliography 177/177 cut, index 10 of 432 -- 422 paragraphs and 22 906 characters of index survive into\n"
        "the narrated set. Under FR-A8 they arrive as PROSE, because no region claims them. The one-book pass\n"
        "predicted that any completeness rule would therefore fail this book several hundred times. Its dump is\n"
        "now here, so the prediction can be checked instead of repeated."
    )
    rows = corpus.get("rethinking_money")
    if not rows:
        lines.append("")
        lines.append(DUMPS_HINT)
        return lines
    delivered = delivered_rows(rows)
    last_ordinal = max(row["ordinal"] for row in rows)
    tail = [row for row in delivered if row["ordinal"] >= last_ordinal - 364]
    values = shares_of([row["after"] for row in tail])
    lines.append("")
    lines.append(
        f"  book tail (the last 365 ordinals, {len(tail)} delivered paragraphs -- the index and what follows it):"
    )
    stats = quantiles(values)
    lines.append(f"    delivered target share: " + ", ".join(f"{key}={stats[key]}" for key in COLUMNS))
    below = sum(1 for value in values if value < 0.5)
    identical = [row for row in tail if row["after"] == row["before"] and letter_count(row["before"]) > 0]
    lines.append(f"    delivered below 0.50 target share: {below} of {len(values)}")
    lines.append(f"    delivered byte-identical to source: {len(identical)} of {len(tail)}")
    lines.append("")
    lines.append("  What the index rows actually look like, taken in order rather than picked:")
    for row in tail[:5]:
        lines.append(f"    {row['paragraph_id']} share={share_or(row['after'], 0.0):.3f} identical={row['identical']}")
        lines.append(f"        src: {row['before'][:92]!r}")
        lines.append(f"        out: {row['after'][:92]!r}")
    lines.append("")
    lines.append(
        "THE PREDICTION WAS WRONG, AND IT WAS WRONG BY TWO ORDERS OF MAGNITUDE. The index was TRANSLATED --\n"
        "'Ecosystem, monetary, 59-60' comes back as 'Экосистема, денежная, 59-60', page numbers and all. Its\n"
        "median delivered share is 1.000. What stays verbatim is the handful of entries that are bare proper\n"
        "nouns, where there is nothing to translate."
    )
    lines.append("")
    lines.append("  Cost of a hard gate on this book, counted rather than feared:")
    for name, rule in (
        ("rule B (byte equality)", lambda row: row["after"] == row["before"] and letter_count(row["before"]) > 0),
        ("rule A, floor 20, cut 0.20", lambda row: _flagger(20, 0.20)(row["after"])),
        ("rule A, floor 60, cut 0.20", lambda row: _flagger(60, 0.20)(row["after"])),
    ):
        hits = [row for row in delivered if rule(row)]
        lines.append(f"    {name:<28} {len(hits):>4} of {len(delivered)} delivered paragraphs would fail the run")
    lines.append("")
    lines.append(
        "  A dozen or so is not several hundred, and it is still not zero: a run that hard-fails on 'Stripe,\n"
        "  115-116' has failed on nothing. The conclusion of the one-book pass survives in its weaker form --\n"
        "  neither rule can tell an index row from lost prose, because the difference is REGION and the region\n"
        "  detector does not claim them -- but the ORDER OF WORK it implied does not: closing the index region is\n"
        "  worth doing on its own merits, not as a precondition for the invariant."
    )
    report["index_case"] = {
        "tail_paragraphs": len(tail),
        "tail_share": stats,
        "tail_below_0_50": below,
        "tail_identical": len(identical),
    }
    return lines


# ---------------------------------------------------------------------------
# 9. Survivorship and the delivered artifact
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


def section_survivorship(corpus: dict[str, list[dict[str, Any]]], report: dict[str, Any]) -> list[str]:
    lines = ["", "=" * 108, "9. SURVIVORSHIP -- what the dumps cannot show, and the one artifact that can", "=" * 108]
    if corpus:
        lines.append(
            "A dump records a pair for every paragraph SENT to the model, and an `outcome` saying whether the\n"
            "model's answer was then found in the artifact. So the answer is always recorded; what is NOT recorded\n"
            "is what the artifact holds instead when the answer did not land."
        )
        lines.append("")
        lines.append("  book                   not delivered  model returned nothing  answer was in the target language")
        totals = Counter()
        per_book: dict[str, Any] = {}
        for book, rows in corpus.items():
            missing = [row for row in rows if row["outcome"] not in DELIVERED_OUTCOMES]
            silent = [row for row in missing if row["after"] is None]
            answered = [row for row in missing if row["after"] is not None]
            in_target = sum(1 for row in answered if share_or(row["after"], 0.0) >= 0.5)
            totals["missing"] += len(missing)
            totals["silent"] += len(silent)
            totals["in_target"] += in_target
            lines.append(f"  {book:<22} {len(missing):>13}  {len(silent):>22}  {in_target:>33}")
            per_book[book] = {
                "not_delivered": len(missing),
                "model_returned_nothing": len(silent),
                "answer_in_target_language": in_target,
                "outcomes": dict(Counter(row["outcome"] for row in missing)),
            }
        lines.append(
            f"  {'TOTAL':<22} {totals['missing']:>13}  {totals['silent']:>22}  {totals['in_target']:>33}"
        )
        assert totals["missing"] == sum(entry["not_delivered"] for entry in per_book.values())
        lines.append("")
        lines.append(
            f"  {totals['in_target']} of {totals['missing']} carry a perfectly good Russian answer that never reached the artifact, and only\n"
            f"  {totals['silent']} are cases where the model returned nothing at all. That is the shape of the loss on the audiobook\n"
            "  path: not English delivered, but nothing delivered. And it is why the dumps CANNOT be used to count\n"
            "  untranslated deliveries -- the untranslated text is precisely what they do not hold. Any 'paragraphs\n"
            "  left in English' figure computed from a dump is counting survivors."
        )
        report["survivorship"] = {"per_book": per_book, "totals": dict(totals)}

    lines.append("")
    lines.append("-" * 108)
    if not DELIVERED_NARRATION.exists():
        lines.append(f"delivered artifact not present ({DELIVERED_NARRATION}) -- skipped")
        return lines
    lines.append(
        "THE ONE PLACE THE UNTRANSLATED TEXT IS VISIBLE. `Money_Sustainability_pdf_full_heldout.tts.txt` is the\n"
        "narration as DELIVERED on 2026-08-04. The commit that tracked it says so: 'the artifact as delivered on\n"
        "2026-08-04, before the three fixes that followed ... kept as the before-picture, not as a current sample'\n"
        "(f2a49da). Constitution VIII: this is a BEFORE picture, not a claim about live code. Its run recorded\n"
        "`model_output_discarded_block_count=6` and had no `narration_excluded_source_fallback_*` counter at all,\n"
        "so those blocks went into the audiobook in English. The same book on 2026-08-06 shows 2 fallback blocks,\n"
        "now DROPPED instead (5 581 characters missing) -- the two shapes of loss spec 059 A-1 describes."
    )
    artifact_lines = [line.strip() for line in DELIVERED_NARRATION.read_text(encoding="utf-8").splitlines() if line.strip()]
    total_letters = sum(letter_count(line) for line in artifact_lines)
    english = [
        line
        for line in artifact_lines
        if letter_count(line) >= 60 and target_letter_share(line) is not None and target_letter_share(line) < 0.10
    ]
    english_letters = sum(letter_count(line) for line in english)
    first_run = load_jsonl(AUDIOBOOK_PAIRS) if AUDIOBOOK_PAIRS.exists() else []
    source_texts = {row["before"].strip() for row in first_run}
    landed_texts = {row["after"].strip() for row in first_run if row["outcome"] in DELIVERED_OUTCOMES}
    verbatim = sum(1 for line in english if line in source_texts)
    inside_block = sum(1 for line in english if _found_in_a_source_block(line)) if SOURCE_BLOCKS.exists() else 0
    in_dump = sum(1 for line in english if line in landed_texts)
    lines.append("")
    lines.append(f"  delivered narration lines: {len(artifact_lines)}; letters: {total_letters}")
    lines.append(
        f"  UNTRANSLATED PROSE ACTUALLY SHIPPED: {len(english)} lines, {english_letters} letters, "
        f"{100 * english_letters / total_letters:.2f}% of the artifact."
    )
    lines.append(f"    present in the paragraph dump as a DELIVERED text: {in_dump} -- the survivorship point, measured.")
    lines.append(
        f"    byte-equal to a recorded source PARAGRAPH: {verbatim}; found inside a source BLOCK once markdown\n"
        f"    noise is normalised on both sides: {inside_block}. Substitution happens per block, so a pair check run\n"
        f"    at paragraph granularity sees {verbatim} of {len(english)}; run where the substitution is made, {inside_block}."
    )
    lines.append("")
    lines.append("  longest four, quoted:")
    for line in sorted(english, key=lambda item: -letter_count(item))[:4]:
        lines.append(f"    letters={letter_count(line):<5} {line[:130]!r}")
    scored = [(target_letter_share(line), line) for line in artifact_lines]
    scored = [(share, line) for share, line in scored if share is not None]
    untranslated_max = max((share for share, line in scored if share < 0.10 and letter_count(line) >= 20), default=0.0)
    legitimate_min = min((share for share, line in scored if share >= 0.10 and letter_count(line) >= 20), default=1.0)
    lines.append("")
    lines.append(
        f"  On this artifact alone the two populations sit at {untranslated_max:.4f} and {legitimate_min:.4f}. Section 5 shows what\n"
        "  happens to that band once the document path is included."
    )
    report["delivered_artifact"] = {
        "lines": len(artifact_lines),
        "letters": total_letters,
        "untranslated_lines": len(english),
        "untranslated_letters": english_letters,
        "untranslated_share_of_artifact": round(100 * english_letters / total_letters, 2),
        "present_in_dump": in_dump,
        "byte_equal_to_a_source_paragraph": verbatim,
        "found_in_a_source_block": inside_block,
        "max_share_untranslated": round(untranslated_max, 4),
        "min_share_legitimate": round(legitimate_min, 4),
    }
    return lines


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def build_report() -> tuple[str, dict[str, Any]]:
    corpus = load_final_run_dumps()
    regions = load_paragraph_regions(SOURCE_BLOCKS) if SOURCE_BLOCKS.exists() and AUDIOBOOK_PAIRS.exists() else None
    report: dict[str, Any] = {}
    lines = [
        "TRANSLATION-SIGNAL MEASUREMENT",
        "Recorded runs only. No paid run, no network, no LLM, stdlib only.",
        "",
        f"Main corpus  : {len(corpus)} of {len(FINAL_RUN_BOOKS)} paragraph-pair dumps from the 2026-08-06 run"
        + (f" -- {sum(len(rows) for rows in corpus.values())} records" if corpus else " -- NONE FOUND"),
        f"Second corpus: {'present' if regions else 'absent'} -- git-recovered region decisions and delivered artifact",
        "",
        "Every target-alphabet number below is a CYRILLIC number, because every recorded run is en->ru.",
        "Whether the same shape holds for another target language is NOT tested by this corpus.",
    ]
    if not corpus:
        lines.append("")
        lines.append(DUMPS_HINT)
    lines += section_corpus(corpus, report)
    lines += section_prose_flag(corpus, regions, report)
    lines += section_features(corpus, report)
    lines += section_control_group(corpus, report)
    lines += section_gap(corpus, report)
    lines += section_pair_rule(corpus, report)
    lines += section_two_paths(corpus, report)
    lines += section_index_case(corpus, report)
    lines += section_survivorship(corpus, report)
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
