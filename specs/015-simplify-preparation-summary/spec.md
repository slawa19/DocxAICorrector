# Feature Specification: Simplify the preparation summary + prune stale prep telemetry

Date: 2026-07-13
Status: DRAFT — approved scope, pre-implementation. Presentation + dead-code cleanup: reduce the post-preparation
UI summary to only user-meaningful lines, and remove stale reason-labels / vestigial report status-notes left
over from the removed structure-recognition feature. NO change to what preparation computes (paragraphs, segments,
blocks, furniture flags) — only what it SURFACES and which dead strings it carries.
Owner surface: `ui/_ui.py::render_preparation_summary` (:416-487), `ui/_app.py::_store_preparation_summary`
(:394-453) + the recommended-text-settings notice (:520-560, :1070-1091), `processing/preparation.py` status-note
builders (:213-280) + stale `_REASON_LABELS` (:46-65).
Companion: `specs/013-ui-minimal-screen-and-result/spec.md` (same "minimal screen" theme);
`specs/016-*` (drop partial translation — follow-up); the OCR-stamp furniture defect is a SEPARATE ticket
(`specs/017-ocr-stamp-furniture-detection`).
Changelog:
- 2026-07-13 — Created after a preparation-stage audit (orchestrator-verified). Findings: the summary is ~85%
  internal telemetry; "Очистка: N служебных элементов" is misleading (cleanup runs flag-only — `layout_cleanup.py:206-212`
  `removed_paragraph_count=0`, nothing removed); "Восстановление структуры …" targets PDF-derived structure and is
  near-always 0 on DOCX; `_REASON_LABELS` is ~13/15 dead (only `first_block_mixed_*` still emitted). The prep stage
  itself is NEEDED (segmentation is load-bearing for full-document translate context) and is NOT superseded by the
  gate refactor (orthogonal: prep at import, gate post-translation) — so this spec trims surface + dead strings only.

## Verified findings (Constitution VIII — verified 2026-07-13 by direct code reading)

- Summary render path: `_store_preparation_summary` (`_app.py:394-453`) → `render_preparation_summary`
  (`_ui.py:416-487`) emits a title + `status_notes` + `meta_lines`.
- User-meaningful lines: the title "Документ подготовлен" (`_app.py:417`) and the source/duration/size line
  (`status.prep_source_meta` + `status.prep_size_meta`, `_ui.py:451-459`).
- Internal-only lines (leaked to user): "Восстановление структуры …" (`build_structure_repair_status_note`,
  `preparation.py:213-223`; PDF-oriented, ~0 on DOCX), "Очистка …" (`build_layout_cleanup_status_note`,
  `preparation.py:247-280`; flag-mode, nothing removed), "Structure fingerprint …" (`_ui.py:461-462`), the
  detector/segments/TOC diagnostics (`_ui.py:463-478`), the normalization caption (`_build_normalization_caption`,
  `_ui.py:188-209`), and the char-count + block-count within the size line (block count = `len(jobs)`, an internal
  chunking artifact).
- Language auto-adjust note ("… язык оригинала: изменено с English на Авто") is NOT a prep field — it is the
  recommended-text-settings notice injected as a status_note (`_app.py:1070-1074`, string at `:548-560`). It is
  marginally user-relevant but mis-placed and shown even framing internal wording.
- The cleanup/repair REPORTS' paragraph-level EFFECTS are consumed downstream (furniture flags → font-baseline
  heading exclusion `structure/layout_signals.py:122`; page-number hint `extraction.py:732`). The report OBJECTS /
  status-note STRINGS are consumed ONLY to render the two summary lines. So the flags stay; the note strings go.
- `_REASON_LABELS` (`preparation.py:46-65`): ~13/15 entries map to the removed structure-recognition/structure-risk
  gate; only `first_block_mixed_toc_and_epigraph` / `_and_body_start` are still emitted (`:307-309`).

## Scope

1. **Minimal user summary.** `render_preparation_summary` shows ONLY:
   - the title "Документ подготовлен";
   - ONE meta line merging source + duration + size + paragraphs + images (drop char count and block count).
   Remove from the user surface: the structure-repair note, the cleanup note, the fingerprint line, the
   detector/segments/TOC diagnostic lines, and the normalization caption. (These may remain in the run-log / debug
   artifacts / `report.json` for engineers — do not delete their underlying data, just stop rendering them here.)
2. **Relocate the language/settings-changed notice.** Show it near the settings (or as a distinct, clearly-worded
   one-liner) and ONLY when a real change occurred — not inside the prep-summary telemetry block. Re-word to
   plain user language (no "скорректировало текстовые настройки" jargon).
3. **Prune stale prep strings.** Remove `build_structure_repair_status_note` and `build_layout_cleanup_status_note`
   (and their call sites in `_store_preparation_summary`) since nothing else renders them. Trim `_REASON_LABELS`
   to the two still-emitted reasons (and any `humanize_quality_gate_reason` mapping that references removed keys).
   Do NOT remove the cleanup/repair computation or the furniture flags — only the UI-only note builders + dead
   labels.
4. **i18n.** Remove the now-unused summary string keys from `ru.json`/`en.json` (structure-repair, cleanup,
   fingerprint, detector/segments/TOC, normalization, char/block fragments), keeping catalog parity.

## Non-goals

- Do NOT change what preparation computes: paragraph normalization, layout cleanup FLAGGING, structure repair,
  segmentation, block building, fingerprint. Only the user-facing SURFACE and dead strings change.
- Do NOT touch the furniture-flag consumers (font-baseline / page-number hints).
- Do NOT fix the OCR-stamp ("Secret") detection gap — separate ticket `specs/017-ocr-stamp-furniture-detection`.
- Do NOT remove partial translation / the structure panel — that is `specs/016-*`.
- No new custom CSS; all copy via i18n `t()`.

## Anti-regression

- Preparation output is byte-identical: same `paragraphs` (with the same furniture flags), `segments`, `blocks`,
  `jobs`, `structure_fingerprint`. A test asserts the prepared context is unchanged (only the summary dict's
  rendered fields differ).
- Heading detection unchanged: the font-baseline exclusion still receives the same furniture flags
  (`layout_signals.py:122`) — the flagging logic is untouched.
- The retained summary line renders correctly for DOCX and PDF inputs; the clean/edge cases (no images, 0 s prep)
  don't crash.
- The language-change notice still appears when (and only when) a setting actually changed.
- Full suite green (except the documented pre-existing env corpus/typecheck items); pyright delta ≤ 0; catalog
  parity maintained (only the intentional en-missing `sidebar.model_label` remains ru-only).

## Verification (Constitution I/II/VIII)

- `wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh` — full suite green.
- Update/keep tests that asserted the removed summary lines / reason-labels; add a test that the minimal summary
  renders exactly the title + one meta line for a representative prepared context, and that the prepared context
  data is unchanged.
- Eyes-on: reload the running app, re-prepare a document, confirm the summary is now the title + one line (+ the
  relocated settings notice only when a setting changed).
