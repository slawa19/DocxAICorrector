# Feature Specification: UI minimal-screen, fewer-steps, and unified result (incl. formatting-review presentation)

Date: 2026-07-13
Status: DRAFT — approved scope (Tier-1 п.1–6 + Tier-2 п.7–10), pre-implementation. A UI/UX consolidation of the
Streamlit app: fewer always-visible controls, fewer clicks, canonical Streamlit styling (minimal custom CSS),
Russian consistency, and a single result screen — into which the formatting-review presentation slice is folded.
Owner surface: `ui/_app.py`, `ui/_ui.py`, `ui/structure_review_panel.py`, and the existing `quality_warning`
contract + review-text writer `runtime/artifacts.py::_build_formatting_review_text`.
Companion:
- `docs/specs/UI/FORMATTING_DISCREPANCY_REPORTING_SPEC_2026-06-15.md` (rewritten 2026-07-11) — the
  formatting-review presentation this slice discharges (folded into §9).
- `specs/010-production-acceptance-semantics/spec.md` (verdict ≠ review-data — the notice copy must not conflate).
- `specs/011-unmapped-target-review-items/spec.md` (the target review items shown, incl. `short_note_or_marker`).
Changelog:
- 2026-07-13 — Created narrow (formatting-review presentation only). Then BROADENED after a full UX audit
  (two read-only mapping passes + direct code reads, cited below) and user scope approval: Tier-1 п.1–6 (screen
  declutter, style cleanup, RU consistency, dedup) + Tier-2 п.7–10 (single run control, drop Confirm-Structure
  friction, unified result screen, remove chunk/retry from UI). Folder renamed
  `013-ui-formatting-review-notice` → `013-ui-minimal-screen-and-result`. п.11 (auto-reset on new upload) was
  considered and DEFERRED.
- 2026-07-13 (later) — Added Tier-3 п.12: full UI internationalization. User chose JSON language files and
  WHOLE-interface coverage. §5 (russify panel) is subsumed by п.12 — panel strings are EXTRACTED into the
  catalogs (RU translated, EN taken from the current English source), not hardcoded. No existing UI i18n infra
  exists (verified: `supported_languages` in `core/config.py:219` is the DOCUMENT language, not the UI language).

## Goal

Minimal screen, minimal steps, canonical Streamlit components with the least possible custom CSS. No pipeline,
data, or writer-LOGIC change — the discrepancy DATA and the review file already exist and are tested
(`late_phases.py:4688` → `write_ui_result_artifacts`; severity→marker `runtime/artifacts.py:63`).

## Verified findings (Constitution VIII — verified 2026-07-13 against current `origin/main`)

- **Sidebar shows 10 controls always** (`_ui.py:602-744`): operation, target lang, source lang (translate/
  audiobook), second-pass (translate), ElevenLabs (edit/translate), model + custom model, chunk-size slider
  (`_ui.py:691-697`), retry slider (`_ui.py:698-703`), image mode, keep-all-variants. Five are engineering knobs.
- **Secondary diagnostics always expanded**: run log and image-validation expanders are `expanded=True`
  (`_ui.py:538`, `_ui.py:572`) and are rendered in nearly every branch (EMPTY/processing/preparation/COMPLETED/
  RESTARTABLE/main).
- **Structure previews force-open** for every low-confidence segment (`structure_review_panel.py:1156`).
- **Dead / non-canonical style code**: `inject_ui_styles` is a no-op (`_ui.py:186-187`); `render_section_gap`
  spaces with blank `st.write("")` (`_ui.py:190-193`); `render_file_uploader_state_styles` hides the dropzone
  via internal `data-testid` (`_ui.py:121-137`); `render_intro_layout_styles` caps width via internal
  `data-testid` (`_ui.py:140-160`).
- **`structure_review_panel.py` is entirely English** ("Review Sections Before Partial Translation", "Confirm
  Structure", "Process Selected", "Process Entire Book") while the rest of the app is Russian.
- **Redundancy in the panel**: confidence/status shown 4 ways (`:950`, `:1128-1132`, `:1152-1155`, `:1168-1169`);
  7+ stacked summary captions (`:1025`,`:1043`,`:1044`,`:1191`,`:1192-1208`); button tooltips restated as
  trailing captions (`:1317-1333` vs `:1362-1363`); the confirmation summary is rendered in both the confirmed
  and not-confirmed branches (`:1352-1360`, `:1369-1376`).
- **Two "start full processing" controls at once**: the panel's "Process Entire Book"
  (`structure_review_panel.py:1349`, action `start_full_book`) and the bottom "Начать обработку"
  (`_app.py:717`, `_app.py:1120`, action `start`) — both launch full-document processing in the same render.
- **Mandatory manual Confirm gate**: "Process Selected"/"Selected + Context"/"Retry Failed" are `disabled` until
  `structure_confirmed` (`structure_review_panel.py:1189`, `:1316`, `:1328`, `:1340`); confirming is a separate
  click + `st.rerun()` (`:1296-1312`). "Process Entire Book" is NOT gated (inconsistent).
- **Two completed-render paths** for the same result: `IdleViewState.COMPLETED` (`_app.py:927-943`) vs
  `FILE_SELECTED` + `has_completed_result` (`_app.py:1108-1117`); both render markdown-preview + result-bundle.
- **The formatting review is not surfaced in the UI at all**: `render_result_bundle` (`_ui.py:821-905`) offers
  only DOCX/MD/TTS; `completed_result` (`_app.py:936-943`) does not carry `quality_warning`.
- **chunk_size/max_retries are threaded from the sidebar tuple** into processing (`_app.py:363-364` and callers);
  removing the widgets means sourcing both from config defaults instead.

## Scope (approved batch — each item is one verifiable task)

### Tier 1 — screen declutter, canonical styling, consistency (behavior-preserving)

1. **Collapse engineering settings** into one `st.sidebar.expander("Дополнительно", expanded=False)`: Model +
   custom model, image mode + keep-all-variants (with §10, chunk/retry are removed entirely, not moved).
   Keep always-visible: operation, target language, source language (when translate/audiobook), and the
   translate/audiobook-specific checkboxes near operation. (`_ui.py:602-744`)
2. **Default secondary diagnostics collapsed**: run log and image-validation expanders → `expanded=False`
   (`_ui.py:538`, `_ui.py:572`).
3. **Structure previews collapsed by default**: drop the low-confidence force-open (`structure_review_panel.py:1156`);
   a single low-confidence marker stays (see §6), the preview opens on demand.
4. **Remove non-canonical style code**: delete `inject_ui_styles` (`_ui.py:186`) and its call sites; replace
   `render_section_gap` blank-writes with native spacing or removal (`_ui.py:190`); delete
   `render_file_uploader_state_styles` (`_ui.py:121`) and its call (rely on Streamlit's native uploaded-file
   chip). KEEP `render_intro_layout_styles` (`_ui.py:140`) as the single remaining custom style (width cap for
   readability) with a comment marking it the sole justified exception; do not add new custom CSS.
5. **Russify `structure_review_panel.py`** — SUBSUMED BY §12: its user-facing strings are extracted into the
   i18n catalogs with a Russian translation as the `ru` value and the existing English as the `en` value. No
   hardcoded Russian; no logic change.
6. **De-duplicate the panel**: show confidence/status ONCE (a compact per-item marker + one overview), collapse
   the 7+ stacked summary captions into a single concise summary line, and render the confirmation summary in
   one place. Prefer canonical widgets (`st.badge`/`st.progress` for the runtime badge, `st.metric`/`st.columns`
   for counts) over pipe-joined caption strings — WITHOUT adding custom CSS.

### Tier 2 — fewer steps / unified result (behavior-changing)

7. **Single run control.** Do not render "Process Entire Book" and the bottom "Начать обработку" simultaneously
   for the full-document path. Keep ONE canonical primary "Начать обработку" as the single start point; the panel
   keeps only the partial-selection actions ("Обработать выбранное" / "Выбранное + контекст" / "Повторить
   сбойные"). (`structure_review_panel.py:1349`, `_app.py:717/1120`)
8. **Remove Confirm-Structure friction.** The partial-processing actions perform confirmation IMPLICITLY (set
   `structure_confirmation_state` then start), removing the separate "Confirm Structure" click + rerun. Gating
   `disabled` flags keyed on `structure_confirmed` are dropped for those buttons; the underlying confirmation
   state is still set so downstream consumers are unchanged. (`structure_review_panel.py:1189/1296/1316/1328/1340`)
9. **Unified result screen** (folds in the formatting-review presentation). Collapse the two completed-render
   paths (`_app.py:927-943`, `:1108-1117`) into one helper that renders: markdown preview + the download bundle +
   the **formatting-review block**. The review block (presentation-only over `quality_warning`):
   - a final **notice keyed on max severity** (`defect > fix > review > clean`), one Russian line
     (`st.error/st.warning/st.info`), copy per the UI spec's "Notice copy";
   - **counts** `[КРИТ] N · [ПРАВКА] N · [ПРОВЕРКА] N` honoring `aggregate_count`;
   - a **"Скачать отчёт проверки" download button** whose bytes are regenerated in-process via
     `_build_formatting_review_text(source_name, quality_warning, created_at)` (NOT read from `.run/ui_results/`);
   - a one-line reassurance that an accepted result can still carry review items (spec 010);
   - shown ONLY when `quality_warning` is present; a clean run shows "Готово. Оформление перенесено полностью.";
   - DOCX/MD always downloadable regardless of severity.
   Plumbing: add `quality_warning` to `completed_result` (`_app.py`) and thread it to the unified renderer. Logic
   lives in a pure `build_review_presentation(quality_warning) -> {level, headline, counts, review_available}`
   tested without Streamlit. Also apply the `short_note_or_marker` copy softening in `_build_formatting_review_text`
   (`residual_class == "short_note_or_marker"`, `formatting_transfer.py:318`) — the ONE writer touch, data-preserving.
10. **Remove chunk-size and retry sliders from the UI.** Delete both sidebar widgets (`_ui.py:691-703`); source
    `chunk_size` and `max_retries` from config defaults where the sidebar tuple fed them (`_app.py:363-364` and
    downstream callers), so behavior is unchanged for a default user.

### Tier 3 — internationalization (language files for future switching)

12. **Full UI i18n via JSON language files.**
    - New `src/docxaicorrector/ui/locales/ru.json` + `en.json` — flat JSON of namespaced keys
      (`area.element`, e.g. `sidebar.operation_label`, `structure.confirm_button`, `result.notice_defect`,
      `download.docx_label`). `ru` is the complete default; `en` is filled where an English source already exists
      (the whole `structure_review_panel.py` is currently English → free) and mirrors the key set otherwise.
    - New `src/docxaicorrector/ui/i18n.py`:
      - `get_ui_language() -> str` — resolves `st.session_state.get("ui_language")` → config default → `"ru"`.
      - `t(key: str, /, **kwargs) -> str` — look up in the current-language catalog; fall back to `ru`, then to
        the key itself; apply `str.format(**kwargs)` for interpolation. Catalogs loaded once and cached
        (module-level, keyed by language); JSON parsed at first use.
    - **Extract ALL user-facing strings** across the `ui/` package (`_app.py`, `_ui.py`,
      `structure_review_panel.py`, `application_flow.py`, `app_runtime.py`, `recommended_text_settings.py`,
      `compare_panel.py`) into the catalogs and replace the literals with `t("…")`. Strings with runtime values
      use named placeholders (`t("structure.visible_count", visible=v, total=t)`), never f-string concatenation
      of translated fragments.
    - The language SWITCH widget is DEFERRED (future). Because `get_ui_language()` already reads
      `st.session_state["ui_language"]`, a future sidebar selectbox that sets that key enables switching with no
      further plumbing. Default stays `ru`.

## Non-goals

- No pipeline / data / writer-LOGIC change (only the §9 `short_note_or_marker` copy tweak, data-preserving).
- No new discrepancy analysis, navigator, per-sample expandable cards, or auto-fix of Word styles.
- No new custom CSS; do not restyle beyond swapping non-canonical constructs for canonical widgets.
- No internal jargon in user-facing copy (`role_aware`, `gate_source`, `basis`, strategy names, paragraph ids).
- Not resurrecting `note_fragment` as a class (it is `short_note_or_marker` inside `unmapped_target`).
- п.11 (auto-reset on new upload) is DEFERRED — out of this batch.
- Do NOT change the segmentation/confirmation DATA model — §8 only removes the extra CLICK, keeping the state set.
- i18n: the language-SWITCH widget is DEFERRED (only the files + lookup + wiring ship now). `en` completeness is
  best-effort (fallback to `ru`, then key) — not a blocker. No translated-fragment concatenation; placeholders only.
- i18n is a UI-only layer — it does NOT touch the document/content `supported_languages` config or any pipeline
  string.

## Anti-regression

- **Downloads unchanged**: DOCX/MD/TTS buttons and their layout work for every operation mode (edit/translate/
  audiobook) and every severity; reporting never blocks delivery (`_ui.py:887-905`).
- **Clean-run path unchanged**: no `quality_warning` → no notice/counts/review-download.
- **§10 default-preservation**: with sliders removed, `chunk_size`/`max_retries` equal the config defaults that
  were the slider defaults — a run with untouched settings produces the same result as before. Test asserts the
  values passed downstream equal the config defaults.
- **§8 state-preservation**: after starting partial processing without a separate Confirm click, the
  confirmation state consumed downstream is set to the same value the explicit Confirm produced — counter-proof
  test drives the partial-start path and asserts the downstream confirmation flag/context is identical.
- **§9 writer copy is data-preserving**: per-severity counts and the report totals line are byte-identical
  before/after the `short_note_or_marker` softening; only the one phrase changes (counter-proof test).
- **No behavior regression from Tier-1**: §1–6 are presentation/labels only; full suite green before and after.
- This slice introduces NO detection/credit/subtraction rule → Constitution VII anti-vacuum N/A (noted); no
  per-book literals — all copy generic Russian.
- pyright ratchet held ≤244 (`tests/test_typecheck.py::_ERROR_BASELINE`, not edited).

## Verification (Constitution I/II/VIII)

- `wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh` — full suite green.
- New/updated tests:
  - `tests/test_ui_review_presentation.py` — pure `build_review_presentation` (max-severity keying, counts with
    `aggregate_count`, per-severity copy, clean fallback).
  - Streamlit `AppTest` (headless) over the unified result renderer with a `quality_warning` fixture — asserts
    the notice text, counts row, review download control, and the unchanged DOCX button.
  - `tests/test_runtime_artifacts.py` — `short_note_or_marker` softening + the data-preserving counter-proof.
  - §8 counter-proof: partial-start sets the same confirmation state as explicit Confirm.
  - §10 counter-proof: downstream `chunk_size`/`max_retries` equal config defaults.
  - Sidebar/panel label tests updated to assert via `t(...)` keys (not hardcoded literals) and the
    collapsed-by-default expanders.
  - `tests/test_ui_i18n.py` — `t()` returns the `ru` value by default; falls back `current → ru → key`;
    interpolates named placeholders; both `ru.json` and `en.json` are valid JSON; `ru` has no missing key for any
    `t("…")` call site (a coverage test scanning the `ui/` package for `t("literal")` keys); `en` key set mirrors
    `ru` (missing `en` keys are allowed but reported, since they fall back to `ru`).
- pyright ratchet ≤244.
- Constitution VIII eyes-on (confirming step): run the Streamlit app on one prepared fixture and one completed
  result; verify the decluttered sidebar, single run button, no Confirm friction, and the result screen's notice
  + review download render correctly.

## Rollout

Single batch on `feat/ui-formatting-review-slice`, implemented via the delivery loop (implementing agent →
orchestrator independent verification: full `scripts/test.sh`, pyright ≤244, AppTest, eyes-on), merged to main as
one pass.
