# Formatting Discrepancy Reporting Spec (UI presentation slice)

Date: 2026-06-15 (original) · **Rewritten 2026-07-11** as a presentation-only slice over the already-shipped
data/artifact contract.
Status: ACTIVE — presentation slice. The DATA and the human-readable FILE already exist and are tested; this
spec covers ONLY the front-end presentation over them.
Owner surface: the result-notice / activity surface that shows a finished run + a download for the review file.
Companion: `specs/010-production-acceptance-semantics/spec.md` (verdict vs review-data are separate axes),
`specs/011-unmapped-target-review-items/spec.md` (the target review items), `docs/specs/GATE_TRUSTWORTHINESS_AND_UI_DATA_REFACTOR_2026-07-09.md` ("Discharge status").
Changelog:
- 2026-07-11 — REWRITTEN. The 2026-06-15 draft predated the data/artifact work and had drifted from the code:
  it claimed discrepancies live only in `report.json`; proposed extending `build_formatting_diagnostics_user_feedback`
  as the presentation contract; named `.run/job_results/<job>/`; described the `formatting_review.txt` writer as
  future work; still listed `note_fragment`; did not reflect spec 010 (verdict ≠ review-data) or the spec 011
  mechanics (`aggregate_count` / sample cap / count-only fallback). All corrected below against the verified
  contract. This is NOT a reason to touch the pipeline — the data and the file are done; only the UI front-end
  remains.

## What already exists (verified 2026-07-11 — the UI does NOT build any of this)

- **The discrepancy DATA is a structured, promoted object, not raw `report.json`.** At finalize,
  `_build_result_quality_warning` (`late_phases.py:3687-3707`) produces a `quality_warning` dict **only when
  `quality_status ∈ {warn, fail}`** (line 3693) carrying `kind="translation_quality_gate"`, `message`,
  `formatting_review_items`, and `formatting_review_required_count`. It is persisted verbatim into the delivered
  meta file (`runtime/artifacts.py:199-200`). On a fully clean run (`quality_status == pass`) there is **no**
  `quality_warning` — the UI shows "clean".
- **Each review item** (`_build_formatting_review_item`, `late_phases.py:2301-2344`):
  `{reason, label (RU), count, severity ∈ {fix, review, defect}, aggregate_count?, action_style?, sample?}`.
  The capped emission (first 8 samples, `aggregate_count` on the first when capped, count-only fallback when no
  samples) is already implemented in the emitters (`_emit_unmapped_source_discrepancy_review_items` `:2650`,
  `_emit_unmapped_target_discrepancy_review_items` `:2704`, spec 011).
- **Severity → marker** is fixed in code: `runtime/artifacts.py:63`
  `{"fix": "[ПРАВКА]", "review": "[ПРОВЕРКА]", "defect": "[КРИТ]"}`.
- **The human-readable review FILE already exists, with retention and tests.**
  `_build_formatting_review_text` (`runtime/artifacts.py:88-169`) renders a Russian prose review; it is written
  as `<stem>.result.formatting_review.txt` into **`.run/ui_results/`** (NOT `.run/job_results/`) by
  `write_ui_result_artifacts` (`runtime/artifacts.py:172-263`), next to `<stem>.result.docx` /
  `<stem>.result.md` / `<stem>.result.meta.json`. Stem = `<YYYYMMDD_HHMMSS>_<sanitized-name>.result`. Retention
  prunes whole stem-groups (≤ 80 groups / ≤ 7 days, `artifact_retention.py:64-65`). Tests:
  `tests/test_runtime_artifacts.py` (`.result.formatting_review.txt` at `:95/:131`, aggregate-count capping
  `:165`, defect `:205`), `tests/test_runtime_artifact_retention.py:192`.

**So the UI slice is a thin FRONT-END:** read `quality_warning` from the delivered meta, show a notice + counts,
and offer a download of the already-written `.result.formatting_review.txt`. No new analysis, no new writer, no
pipeline change.

## Two axes the UI must NOT conflate (spec 010)

- **Acceptance verdict** — `acceptance_passed` (pass/fail) gates on the STRUCTURAL/HYGIENE axis only; the coverage
  axis is NOT-APPLICABLE in production (spec 010). A run can be **`acceptance_passed = true` AND
  `quality_status = warn`** simultaneously (observed live: Mazzucato/Creating Wealth/Lietaer 2026-07-11) — the
  book is accepted, but carries review items. The UI copy must make this non-alarming: a successful result can
  legitimately list items to review.
- **Review-data** — the `formatting_review_items` are DATA for human review, never a pass/fail. Coverage counts
  are shown as data, not as a verdict.

## Minimal UI scope (first increment — deliberately small)

1. **A final notice keyed on the MAX severity present** (`defect` > `fix` > `review` > none) — one line, Russian.
2. **Counts by severity**: `[КРИТ] N · [ПРАВКА] N · [ПРОВЕРКА] N` (from the items' `severity`, honoring
   `aggregate_count`).
3. **A download control for `<stem>.result.formatting_review.txt`** (the file already written next to the DOCX).
4. **A one-line explanation that a successful result can still contain review items** (the two-axes point above),
   so a passing run with `[ПРОВЕРКА]` items does not read as a failure.
5. **Correct copy for `short_note_or_marker`**: when an `unmapped_target` item's residue is a short note/marker
   (`residual_class == "short_note_or_marker"`, `formatting_transfer.py:318`), soften the wording ("похоже на
   сноску или маркер"). It is NOT a separate class — it rides inside `unmapped_target`.
6. **No internal terminology in user-facing copy** — never show `role_aware`, `retained residue`, `gate_source`,
   `basis`, strategy names, or paragraph ids. Only the RU `label` + the human marker.
7. **The DOCX download is always available regardless of severity** — reporting never blocks delivery (the DOCX
   and MD are always written; `runtime/artifacts.py:187-190`).

## Notice copy (concise, Russian; keyed on max severity)

- none (no `quality_warning`): `Готово. Оформление перенесено полностью.`
- `review` only: `Готово. N абзацев стоит проверить по оформлению — см. файл проверки.` (successful — items are
  advisory)
- `fix` present: `Готово. N заголовков/списков стали обычным текстом — нужна ручная правка. См. файл проверки.`
- `defect` present: `Внимание: N абзаца(ев) могли получить чужое оформление. См. файл проверки.`

Each notice names the review file so the user knows what to download. The activity feed gets the same headline
plus the per-severity counts.

## The review FILE (already produced — shown here for reference, NOT to be re-implemented)

`_build_formatting_review_text` already emits Russian prose ordered by document position, e.g.:

```
Проверка оформления — <имя книги>
Итог: КРИТ 0 · ПРАВКА 3 · ПРОВЕРКА 16
[ПРАВКА] Заголовок стал обычным текстом
  Где: после «…the local activities are run by a comm…»
  Как поправить: применить стиль заголовка.
[ПРОВЕРКА] Абзац без явного соответствия оригиналу
  «BerkShares — это местная валюта региона…» — проверьте оформление.
```

The UI links this file; it does not regenerate it. If the file's copy needs the `short_note_or_marker` softening
(scope item 5) and the writer does not yet apply it, that is a SMALL writer copy tweak (one function,
`_build_formatting_review_text`) — the only code touch this slice may need, and it is DATA-preserving.

## Non-goals

- **No new discrepancy analysis, no new writer, no pipeline change** — the data and the file exist and are tested.
- **No inline navigator, no clickable per-sample cards, no expandable cards per sample** in the first increment.
- **No auto-fixing / no programmatic Word-style reapplication** — the user fixes by hand; the file guides.
- **No blocking of the DOCX/MD download on any severity.**
- **No internal ids/jargon in user-facing copy.**
- **Not resurrecting `note_fragment`** as a class (scoped out — it is `short_note_or_marker` inside
  `unmapped_target`), and **not** citing `build_formatting_diagnostics_user_feedback` as the structured contract
  (it now supplies only the one-line `message`), nor `.run/job_results/` as the artifact location.

## Contract appendix (exact surfaces the UI reads)

**Object (from the delivered `<stem>.result.meta.json` → `quality_warning`; exists only when warn/fail):**
- `quality_warning.kind` = `"translation_quality_gate"`
- `quality_warning.quality_status` = `"warn"` | `"fail"`
- `quality_warning.gate_reasons` : `list[str]` (internal — for logs, not user copy)
- `quality_warning.message` : one-line RU summary
- `quality_warning.formatting_review_required_count` : `int` (honors `aggregate_count`)
- `quality_warning.formatting_review_items[]` : `{reason, label, count, severity, aggregate_count?, action_style?, sample?{text, source_text?, anchor_usable?}}`
- severity → marker (`runtime/artifacts.py:63`): `fix→[ПРАВКА]`, `review→[ПРОВЕРКА]`, `defect→[КРИТ]`

**Artifact files (in `.run/ui_results/`, stem `<YYYYMMDD_HHMMSS>_<name>.result`):**
- `<stem>.result.docx`, `<stem>.result.md` — always
- `<stem>.result.formatting_review.txt` — when `quality_warning` present (the download target)
- `<stem>.result.meta.json` — carries `quality_warning`
- Retention: whole-stem group, ≤ 80 groups / ≤ 7 days.

**Advisory (report-level, optional, not part of the first increment):**
`translation_quality_report.paragraph_break_count` / `.paragraph_break_samples` (spec 008, advisory).
