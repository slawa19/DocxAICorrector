"""Spec 065 FR-010 / FR-004: does a run's translation follow its own glossary where a reader looks?

Companion to ``specs/065-glossary-reaches-the-reader/spec.md`` (FR-010, FR-004, SC-001, SC-002).
It replaces ``scripts/measure-glossary-consistency.py`` (the 063/064 SC-006 proxy) as the
measurer: the proxy counted every entry in every paragraph, so its number mixed three things a
reader never sees as a glossary failure — the pronoun *us* matched as «US», notes and
bibliography kept in English by policy, and general one-word entries (``today``, ``banking``)
whose correct Russian depends on part of speech. This is the reviewers' form metric of
2026-11-08 (``review/scripts/sc006_alt.py`` for Money & Sustainability, ``terms3.py`` for The
Value of Everything), with every rule decided by FORM, never by a list of words or a book.
Standard library only, no repository import, no network, no model — run it with ``python3 -I``.

SCOPE (which paragraph pairs are read)
-------------------------------------
Body prose only. A pair of ``pairs.jsonl`` is measured when it has a target text, its
``paragraph_status`` is ``accepted`` (or absent) and it is not a ``controlled_fallback`` —
policy-kept, fallback, omitted and source-restored pairs carry the source, not a rendering; its
``region`` is ``prose`` (not front/back matter, notes, bibliography or TOC); its role is not a
heading (``--headings`` adds headings), a TOC entry or an image. ``region``/``role`` come from the
pair; when the pair has none, from ``--paragraphs`` (the run's ``source_paragraphs.json``, the
``--dump-paragraphs`` file of ``measure-glossary-candidates.py``, or another run's
``pairs.jsonl``): by ``paragraph_id`` when the texts agree, else by an identical normalised
text, else from the nearest placed neighbours when both sides lie in one region; a pair still
without a region is measured and counted as ``measured_region_unknown``. ``--report`` (the
run's ``*_report.json``) fills a missing status from
``runtime.state.final_generated_paragraph_registry``. Excluded pairs are counted by reason.

TERM SELECTION (by the entry's form)
------------------------------------
Headline entries: names (``kind == name``) and entries whose source is multi-word, hyphenated,
capitalised (an abbreviation included) or carries a ``note``. A single lowercase word is general
vocabulary whose correct rendering depends on part of speech and sense; it is measured and
printed APART and never enters the headline. Not measured at all: an entry whose rendering
equals its source or is written in Latin script only (a kept occurrence cannot be told from an
adherent one). Only entries the prompt section carried enter the headline — the section's
list (``rendered_terms`` when the artifact has it, else the first ``rendered_term_count``
entries in stored order); a cut entry is coverage, not adherence, and is listed there with its
occurrences. An entry with fewer than ``--min-occurrences`` (3) measured occurrences is listed,
not counted.

MATCHING
--------
Source: whole words; an entry with an uppercase letter matches case-SENSITIVELY (``US`` never
matches the pronoun *us*), any other entry case-insensitively; English plural and possessive
allowed on the last word; a hyphen is a word boundary (``value`` is not counted inside
*value-based*); words of a multi-word entry may be joined by a space or a hyphen; Markdown
asterisks are ignored. An occurrence inside an occurrence of a longer entry the prompt carried
belongs to the longer entry (``complex flow`` inside *complex flow network*). An occurrence is
one paragraph pair. A pair whose target keeps the source term verbatim (Latin) as many times as
the source has it — a cited title, a gloss in parentheses, a kept bibliography span — is
excluded as ``kept_in_latin``.
Target: the stem rule of the 063 proxy — each word of the rendering longer than two letters is
cut to its first ``max(3, len - 3)`` letters (``ё`` read as ``е``, case and Markdown ignored), so
a declined form counts and another word does not; a rendering made only of words of one or two
letters (``ЕС``) is matched whole — plus one guard: all stems must open distinct words
inside a window of ``len(stems) + 3`` words (no more than three words between the parts, any
order), so «устойчивость … потрясений» three sentences apart is not «устойчивость к
потрясениям».

NUMBERS
-------
Per entry: occurrences measured, adherent, adherence; the dominant rendering and its share
(``glossary`` when the rendering itself; a non-adherent occurrence is labelled by the part of the
rendering it carries — ``partial: устойчивость`` — or ``none``; the script cannot name a word the
glossary does not contain); PASS when the dominant rendering is the glossary's and its share is
>= 90 % for an entry with >= 5 occurrences. Headline: adherent occurrences / measured
occurrences over the headline entries. Coverage: required entries (``candidates[].required``)
and form-selected entries the section cut, with their occurrences; required candidates the
glossary lacks (``unrendered_terms``); ``unrendered_required`` printed as the artifact states it
when present. Harm is a READING metric: the non-adherent pairs are printed (``--show N`` per
entry) so a reader counts the errors the glossary caused; no rule here can tell a wrong
rendering from a legitimate paraphrase or a pronoun.

CONTRAST PAIRS (FR-004)
-----------------------
Two entries the prompt carried whose renderings differ but share a word stem (``resilience ->
устойчивость к потрясениям`` / ``sustainability -> устойчивость``) and whose source terms occur
in one measured paragraph — there a reader can see one word for two concepts, and an adherence
count cannot (the bare «устойчивость» is adherent for ``sustainability``). Renderings with no
common stem are not contrast pairs: a missing rendering there is a miss of that entry, and no
rule can tell which word replaced it. A pair where one source term is a run of the other's words
(``value`` / ``create value``) is a composition the longer entry governs and is skipped; an
occurrence inside the other entry's occurrence does not count. Per paragraph, about the GLOSSARY
renderings: ``distinct`` when both appear at different words of the target as often as their
source terms occur, ``partly`` when both appear but one fewer times, ``collapsed`` when only one
appears and at least as often as the two source terms together, ``one_missing`` when only one
appears fewer times, ``neither`` otherwise. A target word that opens a stem of both renderings
belongs to the one whose stem it opens longer («денежной» is ``денежный``, not ``деньги``).

USAGE
-----
    python3 -I scripts/measure-glossary-adherence.py --pairs <run>/pairs.jsonl \\
        --glossary <run>/glossary.json [--paragraphs <run>/source_paragraphs.json] \\
        [--report <run>/<profile>_report.json] [--headings] [--min-occurrences 3] \\
        [--json out.json] [--show 5]
"""

from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

MEASURED_STATUSES = frozenset({"", "accepted"})
MEASURED_REGIONS = frozenset({"prose"})
SKIPPED_ROLES = frozenset({"image", "toc_entry", "toc_header"})
PASS_SHARE = 0.9
PASS_MIN_OCCURRENCES = 5
WINDOW_SLACK = 3

_WORD = r"[^\W_](?:[^\W_]|['’\-])*"
_TARGET_WORD_RE = re.compile(r"[^\W\d_]+")
_LATIN_LETTER_RE = re.compile(r"[A-Za-z]")
_ANY_LETTER_RE = re.compile(r"[^\W\d_]")
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


# --- loading -----------------------------------------------------------------------------------


def _read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("paragraphs", "pairs", "records"):
                if isinstance(data.get(key), list):
                    return [item for item in data[key] if isinstance(item, dict)]
            return [data]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _norm_text(text: str) -> str:
    text = (text or "").translate(_SUPERSCRIPTS)
    text = re.sub(r"[*_#]", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def _norm_key(term: str) -> str:
    return re.sub(r"\s+", " ", (term or "").strip()).casefold()


def load_pairs(
    pairs_path: Path,
    paragraphs_path: Path | None = None,
    report_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """The run's pairs, with region/role/status filled from the side inputs where missing."""

    pairs = _read_records(pairs_path)
    filled: Counter[str] = Counter()
    if paragraphs_path is not None:
        records = _read_records(paragraphs_path)
        by_id: dict[str, dict[str, Any]] = {}
        by_text: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in records:
            text = str(record.get("text") or record.get("source_text") or "")
            if record.get("paragraph_id"):
                by_id[str(record["paragraph_id"])] = record
            if text:
                by_text[_norm_text(text)].append(record)
        for pair in pairs:
            source = _norm_text(str(pair.get("source_text") or ""))
            record = by_id.get(str(pair.get("paragraph_id") or ""))
            if record is not None:
                text = str(record.get("text") or record.get("source_text") or "")
                if text and _norm_text(text) != source:
                    record = None
            route = "paragraph_id"
            if record is None and len(by_text.get(source, [])) == 1:
                record, route = by_text[source][0], "text"
            if record is None:
                continue
            for key in ("region", "role", "structural_role"):
                if pair.get(key) in (None, "") and record.get(key) not in (None, ""):
                    pair[key] = record[key]
                    filled[f"{key}_by_{route}"] += 1
        # A paragraph re-cut by another import has no twin; it lies inside one region when its
        # nearest placed neighbours on both sides agree.
        placed = [index for index, pair in enumerate(pairs) if pair.get("region") not in (None, "")]
        for before, after in zip(placed, placed[1:]):
            region = pairs[before]["region"]
            if after - before > 1 and pairs[after]["region"] == region:
                for index in range(before + 1, after):
                    pairs[index]["region"] = region
                    filled["region_by_neighbours"] += 1
    if report_path is not None:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        registry = ((report.get("runtime") or {}).get("state") or {}).get("final_generated_paragraph_registry") or []
        status_by_id: dict[str, dict[str, Any]] = {}
        for entry in registry if isinstance(registry, list) else []:
            if not isinstance(entry, dict):
                continue
            for paragraph_id in [entry.get("paragraph_id"), *(entry.get("merged_paragraph_ids") or [])]:
                if paragraph_id:
                    status_by_id[str(paragraph_id)] = entry
        for pair in pairs:
            entry = status_by_id.get(str(pair.get("paragraph_id") or ""))
            if entry is None:
                continue
            if not pair.get("paragraph_status") and entry.get("paragraph_status"):
                pair["paragraph_status"] = entry["paragraph_status"]
                filled["paragraph_status_by_report"] += 1
            if entry.get("controlled_fallback") and not pair.get("controlled_fallback"):
                pair["controlled_fallback"] = True
                filled["controlled_fallback_by_report"] += 1
    return pairs, dict(filled)


def scope_reason(pair: dict[str, Any], *, include_headings: bool = False) -> str | None:
    """None when the pair is body prose the model rendered; else the reason it is not read."""

    if pair.get("missing") or not str(pair.get("target_text") or "").strip():
        return "no_target"
    if pair.get("controlled_fallback"):
        return "status:controlled_fallback"
    status = str(pair.get("paragraph_status") or "")
    if status not in MEASURED_STATUSES:
        return f"status:{status}"
    region = pair.get("region")
    if region not in (None, "") and str(region) not in MEASURED_REGIONS:
        return f"region:{region}"
    roles = {str(pair.get("role") or ""), str(pair.get("structural_role") or "")}
    skipped = roles & SKIPPED_ROLES
    if skipped:
        return f"role:{sorted(skipped)[0]}"
    if "heading" in roles and not include_headings:
        return "role:heading"
    return None


# --- glossary entries --------------------------------------------------------------------------


class Entry:
    """One glossary entry with its form class and matchers (a plain class: the tests load this
    file by path, outside ``sys.modules``, where ``dataclass`` cannot resolve annotations)."""

    def __init__(
        self,
        *,
        source_term: str,
        target_term: str,
        kind: str = "term",
        note: str = "",
        position: int = 0,
        rendered: bool = True,
        required: bool = False,
    ) -> None:
        self.source_term = source_term
        self.target_term = target_term
        self.kind = kind
        self.note = note
        self.position = position
        self.rendered = rendered
        self.required = required
        self.form = entry_form(source_term, kind, note)
        self.unmeasurable = unmeasurable_reason(source_term, target_term)
        self.case_sensitive = any(char.isupper() for char in source_term)
        self.stems = target_stems(target_term)
        self.pattern = source_pattern(source_term, case_sensitive=self.case_sensitive)


def entry_form(source_term: str, kind: str, note: str) -> str:
    """The form class that decides whether an entry enters the headline."""

    if kind == "name":
        return "name"
    if re.search(r"\s", source_term.strip()):
        return "multi_word"
    if "-" in source_term:
        return "hyphenated"
    if any(char.isupper() for char in source_term):
        return "capitalised"
    if note.strip():
        return "noted"
    return "single_lowercase"


def headline_form(form: str) -> bool:
    return form != "single_lowercase"


def source_pattern(source_term: str, *, case_sensitive: bool) -> re.Pattern[str]:
    words = [re.escape(word) for word in re.findall(_WORD, source_term)]
    if not words:
        return re.compile(r"(?!x)x")
    body = r"[\s\-]+".join(words)
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(r"(?<![^\W_])(?<!-)" + body + r"(?:e?s)?(?:['’]s)?(?![^\W_])(?!-[^\W_])", flags)


def _fold(text: str) -> str:
    return text.lower().replace("ё", "е")


def _rendering_words(target_term: str) -> list[str]:
    """The words of a rendering that carry stems: longer than two letters, or all of them when
    none is (``ЕС``), in which case they are matched whole."""

    words = _TARGET_WORD_RE.findall(target_term)
    long_words = [word for word in words if len(word) > 2]
    return long_words or words


def target_stems(target_term: str) -> tuple[str, ...]:
    words = _TARGET_WORD_RE.findall(_fold(target_term))
    if any(len(word) > 2 for word in words):
        return tuple(word[: max(3, len(word) - 3)] for word in words if len(word) > 2)
    return tuple(word + "$" for word in words)


def _opens(word: str, stem: str) -> bool:
    """A stem opens a word; a ``$``-terminated stem (a rendering of short words) must equal it."""

    return word == stem[:-1] if stem.endswith("$") else word.startswith(stem)


def unmeasurable_reason(source_term: str, target_term: str) -> str | None:
    if _norm_key(source_term) == _norm_key(target_term):
        return "rendering_equals_source"
    letters = _ANY_LETTER_RE.findall(target_term)
    if letters and all(_LATIN_LETTER_RE.fullmatch(letter) for letter in letters):
        return "latin_rendering"
    if not target_stems(target_term):
        return "rendering_without_stem"
    return None


def load_entries(glossary_path: Path) -> tuple[list[Entry], dict[str, Any]]:
    data = json.loads(glossary_path.read_text(encoding="utf-8"))
    meta: dict[str, Any] = data if isinstance(data, dict) else {}
    raw = meta.get("terms") if meta else data
    entries: list[Entry] = []
    for position, item in enumerate(raw or []):
        if not isinstance(item, dict) or not item.get("source_term") or not item.get("target_term"):
            continue
        source, target = str(item["source_term"]), str(item["target_term"])
        kind, note = str(item.get("kind") or "term"), str(item.get("note") or "")
        entries.append(Entry(source_term=source, target_term=target, kind=kind, note=note, position=position))
    rendered_source = "all entries (no section data in the glossary file)"
    rendered_list = meta.get("rendered_terms")
    if isinstance(rendered_list, list):
        rendered_keys = {_norm_key(str(item.get("source_term") if isinstance(item, dict) else item)) for item in rendered_list}
        for entry in entries:
            entry.rendered = _norm_key(entry.source_term) in rendered_keys
        rendered_source = "rendered_terms"
    elif isinstance(meta.get("rendered_term_count"), int):
        count = int(meta["rendered_term_count"])
        for entry in entries:
            entry.rendered = entry.position < count
        rendered_source = "rendered_term_count (prefix of the stored order)"
    required_keys = {
        _norm_key(str(candidate.get("term") or ""))
        for candidate in meta.get("candidates") or []
        if isinstance(candidate, dict) and candidate.get("required")
    }
    for entry in entries:
        entry.required = _norm_key(entry.source_term) in required_keys
    info = {
        "status": meta.get("status"),
        "rendered_source": rendered_source,
        "rendered_term_count": meta.get("rendered_term_count"),
        "prompt_section_chars": meta.get("prompt_section_chars"),
        "prompt_max_chars": meta.get("prompt_max_chars"),
        "required_candidates": len(required_keys),
        "required_absent_from_glossary": list(meta.get("unrendered_terms") or []),
        "unrendered_required": meta.get("unrendered_required"),
    }
    return entries, info


# --- matching ----------------------------------------------------------------------------------


def _strip_markup(text: str) -> str:
    return re.sub(r"\*+", "", text or "")


def source_spans(entries: list[Entry], source_text: str) -> dict[int, list[tuple[int, int]]]:
    """Occurrence spans per entry index, an occurrence inside a longer rendered entry's dropped."""

    text = _strip_markup(source_text)
    spans: dict[int, list[tuple[int, int]]] = {}
    for index, entry in enumerate(entries):
        found = [match.span() for match in entry.pattern.finditer(text)]
        if found:
            spans[index] = found
    containers = [(span, index) for index, found in spans.items() if entries[index].rendered for span in found]
    kept: dict[int, list[tuple[int, int]]] = {}
    for index, found in spans.items():
        own = [
            span
            for span in found
            if not any(
                other != index and start <= span[0] and span[1] <= end and (end - start) > (span[1] - span[0])
                for (start, end), other in containers
            )
        ]
        if own:
            kept[index] = own
    return kept


def _target_words(target_text: str) -> list[str]:
    return _TARGET_WORD_RE.findall(_fold(_strip_markup(target_text)))


def _assign(stems: tuple[str, ...], words: list[str], lo: int, hi: int, used: set[int]) -> list[int] | None:
    def step(k: int, taken: list[int]) -> list[int] | None:
        if k == len(stems):
            return taken
        for position in range(lo, hi):
            if position in used or position in taken or not _opens(words[position], stems[k]):
                continue
            result = step(k + 1, [*taken, position])
            if result is not None:
                return result
        return None

    return step(0, [])


def find_renderings(stems: tuple[str, ...], words: list[str], used: set[int] | None = None) -> list[frozenset[int]]:
    """Non-overlapping occurrences of a rendering: all stems on distinct words in one window."""

    taken: set[int] = set(used or ())
    matches: list[frozenset[int]] = []
    if not stems:
        return matches
    width = len(stems) + WINDOW_SLACK
    for start in range(len(words)):
        if start in taken or not any(_opens(words[start], stem) for stem in stems):
            continue
        positions = _assign(stems, words, start, min(len(words), start + width), taken)
        if positions is not None and start in positions:
            matches.append(frozenset(positions))
            taken.update(positions)
    return matches


def partial_label(entry: Entry, words: list[str]) -> str:
    target_words = _rendering_words(entry.target_term)
    found = [
        original
        for original, stem in zip(target_words, entry.stems)
        if any(_opens(word, stem) for word in words)
    ]
    return "partial: " + " ".join(found) if found else "none"


# --- measurement -------------------------------------------------------------------------------


def _excerpt(text: str, start: int, width: int = 70) -> str:
    lo, hi = max(0, start - width), min(len(text), start + width)
    return ("…" if lo else "") + text[lo:hi].replace("\n", " ") + ("…" if hi < len(text) else "")


def _target_excerpt(entry: Entry, target_text: str, source_share: float) -> str:
    """Around the first word carrying a stem of the rendering; else at the place proportional to
    the term's place in the source (no alignment exists)."""

    folded = _fold(target_text)
    for stem in entry.stems:
        match = re.search(r"(?<![^\W\d_])" + re.escape(stem.rstrip("$")), folded)
        if match:
            return _excerpt(target_text, match.start())
    return _excerpt(target_text, int(source_share * len(target_text)))


def measure(
    pairs: list[dict[str, Any]],
    entries: list[Entry],
    *,
    include_headings: bool = False,
    min_occurrences: int = 3,
) -> dict[str, Any]:
    scope: Counter[str] = Counter()
    measured_pairs: list[tuple[dict[str, Any], dict[int, list[tuple[int, int]]], list[str]]] = []
    for pair in pairs:
        reason = scope_reason(pair, include_headings=include_headings)
        if reason is not None:
            scope[reason] += 1
            continue
        scope["measured"] += 1
        if pair.get("region") in (None, ""):
            scope["measured_region_unknown"] += 1
        spans = source_spans(entries, str(pair.get("source_text") or ""))
        if spans:
            measured_pairs.append((pair, spans, _target_words(str(pair.get("target_text") or ""))))

    rows: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        row: dict[str, Any] = {
            "source_term": entry.source_term,
            "target_term": entry.target_term,
            "kind": entry.kind,
            "note": entry.note,
            "position": entry.position + 1,
            "form": entry.form,
            "rendered": entry.rendered,
            "required": entry.required,
            "case_sensitive": entry.case_sensitive,
            "target_stems": list(entry.stems),
            "unmeasurable": entry.unmeasurable,
        }
        if entry.unmeasurable:
            rows.append(row)
            continue
        groups: dict[str, list[int]] = defaultdict(list)
        kept_in_latin: list[int] = []
        readings: list[dict[str, Any]] = []
        for pair, spans, words in measured_pairs:
            own = spans.get(index)
            if not own:
                continue
            target_text = str(pair.get("target_text") or "")
            kept = len(entry.pattern.findall(_strip_markup(target_text)))
            idx = int(pair.get("idx", -1))
            if kept >= len(own):
                kept_in_latin.append(idx)
                continue
            if find_renderings(entry.stems, words):
                groups["glossary"].append(idx)
                continue
            label = partial_label(entry, words)
            groups[label].append(idx)
            source_text = _strip_markup(str(pair.get("source_text") or ""))
            readings.append(
                {
                    "idx": idx,
                    "label": label,
                    "source": _excerpt(source_text, own[0][0]),
                    "target": _target_excerpt(entry, target_text, own[0][0] / max(1, len(source_text))),
                }
            )
        occurrences = sum(len(ids) for ids in groups.values())
        adherent = len(groups.get("glossary", []))
        dominant, dominant_ids = max(groups.items(), key=lambda item: (len(item[1]), item[0] == "glossary")) if groups else ("", [])
        dominant_share = len(dominant_ids) / occurrences if occurrences else None
        passes: bool | None = None
        if occurrences >= PASS_MIN_OCCURRENCES:
            passes = dominant == "glossary" and (dominant_share or 0) >= PASS_SHARE
        row.update(
            {
                "occurrences": occurrences,
                "adherent": adherent,
                "adherence": round(adherent / occurrences, 4) if occurrences else None,
                "dominant": dominant,
                "dominant_share": round(dominant_share, 4) if dominant_share is not None else None,
                "passes": passes,
                "non_dominant": {label: ids for label, ids in groups.items() if label != dominant},
                "groups": {label: ids for label, ids in groups.items()},
                "kept_in_latin": kept_in_latin,
                "reading_list": readings,
            }
        )
        rows.append(row)

    def bucket(row: dict[str, Any]) -> str:
        if row["unmeasurable"]:
            return f"unmeasurable:{row['unmeasurable']}"
        if not row.get("occurrences"):
            return "no_measured_occurrence"
        if not headline_form(row["form"]):
            return "single_lowercase_word"
        if not row["rendered"]:
            return "not_in_prompt"
        if row["occurrences"] < min_occurrences:
            return f"fewer_than_{min_occurrences}_occurrences"
        return "headline"

    for row in rows:
        row["bucket"] = bucket(row)

    def total(selected: list[dict[str, Any]]) -> dict[str, Any]:
        occurrences = sum(row["occurrences"] for row in selected)
        adherent = sum(row["adherent"] for row in selected)
        return {
            "entries": len(selected),
            "occurrences": occurrences,
            "adherent": adherent,
            "share": round(adherent / occurrences, 4) if occurrences else None,
        }

    headline_rows = [row for row in rows if row["bucket"] == "headline"]
    lowercase_rows = [
        row for row in rows if row["bucket"] == "single_lowercase_word" and row["rendered"] and row["occurrences"] >= min_occurrences
    ]
    judged = [row for row in headline_rows if row["passes"] is not None]
    result = {
        "scope": dict(scope),
        "entries_by_bucket": dict(Counter(row["bucket"] for row in rows)),
        "headline_forms": dict(Counter(row["form"] for row in headline_rows)),
        "headline": total(headline_rows),
        "pass_line": {
            "rule": f"dominant rendering = glossary and share >= {PASS_SHARE:.0%} for entries with >= {PASS_MIN_OCCURRENCES} occurrences",
            "judged": len(judged),
            "pass": sum(1 for row in judged if row["passes"]),
            "fail": [row["source_term"] for row in judged if not row["passes"]],
        },
        "single_lowercase_words": total(lowercase_rows),
        "not_in_prompt": total([row for row in rows if row["bucket"] == "not_in_prompt"]),
        "rows": rows,
        "contrast_pairs": contrast_pairs(entries, measured_pairs),
    }
    return result


def _word_owners(first: tuple[str, ...], second: tuple[str, ...], words: list[str]) -> tuple[set[int], set[int]]:
    """Words only one entry may use: a word belongs to the entry with the longest stem it opens.

    «денежной» opens both ``ден`` (деньги) and ``денеж`` (денежный) and belongs to the second;
    a word opening the same longest stem in both (``устойчиво``) belongs to neither alone.
    """

    only_first: set[int] = set()
    only_second: set[int] = set()
    for position, word in enumerate(words):
        best_first = max((len(stem) for stem in first if _opens(word, stem)), default=0)
        best_second = max((len(stem) for stem in second if _opens(word, stem)), default=0)
        if best_first > best_second:
            only_first.add(position)
        elif best_second > best_first:
            only_second.add(position)
    return only_first, only_second


def _nested(first: str, second: str) -> bool:
    """One source term is a run of the other's words (``value`` / ``create value``): the pair is
    a composition, which the longer entry governs, not two concepts that can collapse."""

    a = [word.casefold() for word in re.findall(_WORD, first)]
    b = [word.casefold() for word in re.findall(_WORD, second)]
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return bool(short) and any(long[i : i + len(short)] == short for i in range(len(long) - len(short) + 1))


def _stems_overlap(first: str, second: str) -> bool:
    """Some word opens both stems (``устойчиво`` / ``устойчиво``, ``ден`` / ``денеж``)."""

    if first.endswith("$") and second.endswith("$"):
        return first == second
    if first.endswith("$"):
        return _opens(first[:-1], second)
    if second.endswith("$"):
        return _opens(second[:-1], first)
    return first.startswith(second) or second.startswith(first)


def _renderings_overlap(first: Entry, second: Entry) -> bool:
    return any(_stems_overlap(x, y) for x in first.stems for y in second.stems)


def contrast_pairs(
    entries: list[Entry],
    measured_pairs: list[tuple[dict[str, Any], dict[int, list[tuple[int, int]]], list[str]]],
) -> list[dict[str, Any]]:
    """FR-004: two entries with different renderings side by side in one paragraph."""

    eligible = {index for index, entry in enumerate(entries) if entry.rendered and not entry.unmeasurable}
    table: dict[tuple[int, int], dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for pair, spans, words in measured_pairs:
        present = sorted(index for index in spans if index in eligible)
        target_text = _strip_markup(str(pair.get("target_text") or ""))
        for first, second in itertools.combinations(present, 2):
            a, b = entries[first], entries[second]
            if a.stems == b.stems or _nested(a.source_term, b.source_term) or not _renderings_overlap(a, b):
                continue
            if a.pattern.search(target_text) or b.pattern.search(target_text):
                continue  # one of the two is kept in Latin here: nothing to compare
            longer, shorter = (a, b) if len(a.stems) >= len(b.stems) else (b, a)
            owned_by_longer, owned_by_shorter = _word_owners(longer.stems, shorter.stems, words)
            long_matches = find_renderings(longer.stems, words, owned_by_shorter)
            used = set().union(*long_matches) if long_matches else set()
            short_matches = find_renderings(shorter.stems, words, used | owned_by_longer)
            n_long, n_short = len(long_matches), len(short_matches)
            src_long, src_short = (len(spans[first]), len(spans[second])) if longer is a else (len(spans[second]), len(spans[first]))
            sources = src_long + src_short
            if n_long and n_short:
                verdict = "distinct" if n_long >= src_long and n_short >= src_short else "partly"
            elif (n_long or n_short) and max(n_long, n_short) >= sources:
                verdict = "collapsed"
            elif n_long or n_short:
                verdict = "one_missing"
            else:
                verdict = "neither"
            table[(first, second)][verdict].append(int(pair.get("idx", -1)))
    out = []
    for (first, second), verdicts in table.items():
        a, b = entries[first], entries[second]
        together = sum(len(ids) for ids in verdicts.values())
        out.append(
            {
                "terms": [a.source_term, b.source_term],
                "renderings": [a.target_term, b.target_term],
                "together": together,
                "distinct": len(verdicts.get("distinct", [])),
                "partly": len(verdicts.get("partly", [])),
                "collapsed": len(verdicts.get("collapsed", [])),
                "one_missing": len(verdicts.get("one_missing", [])),
                "neither": len(verdicts.get("neither", [])),
                "idx": {verdict: ids for verdict, ids in verdicts.items()},
            }
        )
    out.sort(key=lambda row: (-row["collapsed"], -row["together"], row["terms"]))
    return out


def coverage(rows: list[dict[str, Any]], info: dict[str, Any]) -> dict[str, Any]:
    cut = [row for row in rows if not row["rendered"]]

    def brief(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "source_term": row["source_term"],
            "target_term": row["target_term"],
            "position": row["position"],
            "form": row["form"],
            "occurrences": row.get("occurrences", 0),
        }

    return {
        "entries": len(rows),
        "rendered": sum(1 for row in rows if row["rendered"]),
        "rendered_source": info["rendered_source"],
        "prompt_section_chars": info["prompt_section_chars"],
        "prompt_max_chars": info["prompt_max_chars"],
        "required_entries": sum(1 for row in rows if row["required"]),
        "required_cut": [brief(row) for row in cut if row["required"]],
        "form_selected_cut": [brief(row) for row in cut if headline_form(row["form"]) and not row["required"]],
        "single_lowercase_cut": [brief(row) for row in cut if not headline_form(row["form"]) and not row["required"]],
        "required_candidates": info["required_candidates"],
        "required_absent_from_glossary": info["required_absent_from_glossary"],
        "unrendered_required_from_artifact": info["unrendered_required"],
    }


# --- report ------------------------------------------------------------------------------------


def _share(value: Any) -> str:
    return "—" if value is None else f"{value:.1%}"


def print_report(result: dict[str, Any], show: int) -> None:
    rows = result["rows"]
    print("scope (pairs):", json.dumps(result["scope"], ensure_ascii=False, sort_keys=True))
    print("entries by bucket:", json.dumps(result["entries_by_bucket"], ensure_ascii=False, sort_keys=True))
    head = result["headline"]
    print(
        f"HEADLINE {_share(head['share'])} = {head['adherent']}/{head['occurrences']} occurrences over "
        f"{head['entries']} entries (forms {json.dumps(result['headline_forms'], ensure_ascii=False, sort_keys=True)})"
    )
    line = result["pass_line"]
    print(f"pass line: {line['pass']}/{line['judged']} entries pass ({line['rule']}); fail: {line['fail']}")
    low = result["single_lowercase_words"]
    print(f"single lowercase words (not in headline): {_share(low['share'])} = {low['adherent']}/{low['occurrences']} over {low['entries']} entries")
    cut = result["not_in_prompt"]
    print(f"cut from the prompt, selected by form: {_share(cut['share'])} = {cut['adherent']}/{cut['occurrences']} over {cut['entries']} entries")

    def table(title: str, selected: list[dict[str, Any]]) -> None:
        print(f"\n## {title}")
        for row in sorted(selected, key=lambda item: (item["adherence"] if item["adherence"] is not None else 2, item["source_term"])):
            mark = {True: "PASS", False: "FAIL", None: "    "}[row["passes"]]
            others = "; ".join(f"{label} {ids[:show]}" for label, ids in row["non_dominant"].items())
            print(
                f"{mark} {_share(row['adherence']):>6} {row['adherent']:>4}/{row['occurrences']:<4} "
                f"[{row['form']}] {row['source_term']} -> {row['target_term']}  dominant: {row['dominant']} "
                f"{_share(row['dominant_share'])}" + (f"  other: {others}" if others else "")
            )

    table("headline entries", [row for row in rows if row["bucket"] == "headline"])
    table("single lowercase words (apart)", [row for row in rows if row["bucket"] == "single_lowercase_word" and row["rendered"]])
    table("cut from the prompt (coverage, not adherence)", [row for row in rows if row["bucket"] == "not_in_prompt"])

    cov = result["coverage"]
    print(
        f"\n## coverage: rendered {cov['rendered']}/{cov['entries']} ({cov['rendered_source']}), section "
        f"{cov['prompt_section_chars']}/{cov['prompt_max_chars']} chars"
    )
    print(f"required entries cut: {len(cov['required_cut'])}/{cov['required_entries']} {[r['source_term'] for r in cov['required_cut']]}")
    print(
        "form-selected entries cut: "
        + str(len(cov["form_selected_cut"]))
        + " "
        + str([f"{r['source_term']} ({r['occurrences']})" for r in cov["form_selected_cut"]])
    )
    print(f"single lowercase entries cut: {len(cov['single_lowercase_cut'])}")
    print(f"required candidates absent from the glossary: {cov['required_absent_from_glossary']}")
    if cov["unrendered_required_from_artifact"] is not None:
        print(f"unrendered_required (artifact): {cov['unrendered_required_from_artifact']}")

    print("\n## contrast pairs (FR-004): two entries side by side, renderings differ")
    for row in result["contrast_pairs"]:
        if not (row["collapsed"] or row["together"] >= 2):
            continue
        print(
            f"{row['distinct']}/{row['together']} distinct, {row['partly']} partly, {row['collapsed']} collapsed, "
            f"{row['one_missing']} one missing, "
            f"{row['neither']} neither: {row['terms'][0]} -> {row['renderings'][0]} | {row['terms'][1]} -> {row['renderings'][1]}"
            + f"  collapsed idx {row['idx'].get('collapsed', [])[:show]}"
        )

    if show > 0:
        print("\n## reading list (harm is read, not computed): non-adherent pairs of headline entries")
        for row in rows:
            if row["bucket"] != "headline" or not row["reading_list"]:
                continue
            print(f"- {row['source_term']} -> {row['target_term']}")
            for item in row["reading_list"][:show]:
                print(f"    {item['idx']} [{item['label']}] EN: {item['source']}")
                print(f"    {' ' * len(str(item['idx']))}  RU: {item['target']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--pairs", type=Path, required=True)
    parser.add_argument("--glossary", type=Path, required=True)
    parser.add_argument("--paragraphs", type=Path, help="region/role source for pairs that lack them")
    parser.add_argument("--report", type=Path, help="the run's *_report.json: paragraph statuses")
    parser.add_argument("--headings", action="store_true", help="measure headings too")
    parser.add_argument("--min-occurrences", type=int, default=3)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--show", type=int, default=5, help="pair ids / reading pairs printed per entry")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

    pairs, filled = load_pairs(args.pairs, args.paragraphs, args.report)
    entries, info = load_entries(args.glossary)
    if not entries:
        print(f"glossary has no entries (status {info['status']}): nothing to measure")
        if args.json:
            args.json.write_text(json.dumps({"glossary": info, "rows": []}, ensure_ascii=False, indent=1), encoding="utf-8")
        return 0
    result = measure(pairs, entries, include_headings=args.headings, min_occurrences=args.min_occurrences)
    result["coverage"] = coverage(result["rows"], info)
    result["filled_from_side_inputs"] = filled
    if filled:
        print("filled from side inputs:", json.dumps(filled, sort_keys=True))
    print_report(result, args.show)
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
