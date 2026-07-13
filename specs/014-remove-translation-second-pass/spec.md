# Feature Specification: Remove the "translation second pass" feature (broken; superseded by edit mode)

Date: 2026-07-13
Status: DRAFT — removal spec, pre-implementation. Cuts the "Дополнительный литературный проход после перевода"
feature end-to-end (UI control, pipeline code, config fields, i18n keys, tests).
Owner surface: `ui/_ui.py` + `ui/_app.py` (the checkbox + plumbing), `pipeline/block_execution.py` (the pass),
`pipeline/setup.py` + `pipeline/late_phases.py` (effective flag / telemetry), `core/config*.py` + `config.toml`
(config fields), `locales/*.json` (i18n keys), and the second-pass tests.
Companion: `specs/013-ui-minimal-screen-and-result/spec.md` (the current UI batch — this is a follow-up on the same
branch or a sibling branch). Evidence for the decision is the correctness audit below.
Changelog:
- 2026-07-13 — Created after a correctness audit (orchestrator-verified by direct code reading) found the second
  pass is BROKEN in the default configuration and decided to remove it rather than repair the marker round-trip.
  Users obtain literary polishing by re-running the translated document through the existing, working
  "Литературное редактирование" (`operation == "edit"`) mode.

## Why remove (Verified findings — Constitution VIII, verified 2026-07-13 by direct code reading)

- **The feature fails the whole run in the default configuration.** Paragraph markers are ON by default
  (`config.toml:42 enable_paragraph_markers = true`). The first translation pass STRIPS the `[[DOCX_PARA_…]]`
  markers from its output (`generation/_generation.py:327-332`). The second pass then feeds that marker-free text
  into `generate_markdown_block(..., marker_mode=True, expected_paragraph_ids=…)` (`block_execution.py:614-624`),
  whose PRE-retry validation (`_generation.py:991`) calls `_split_marker_preserved_markdown`, finds no markers, and
  raises `MarkerValidationError("markers_missing")` (`_generation.py:277-283`) OUTSIDE any try/except. The
  exception propagates (`block_execution.py:785 → :1105 → handle_block_generation_failure`) → the run result is
  `failed` and the already-good first-pass translation is discarded. Net: ticking the checkbox on a normal
  translate run FAILS the run.
- **No test covers the failing combination.** All second-pass tests mock `generate_markdown_block`
  (`test_document_pipeline.py` ~:2934/:3186), so the real marker validation never executes; markers-ON +
  second-pass with paragraph-bearing jobs is untested.
- **Secondary defect:** even absent the marker issue, any second-pass failure aborts the entire document instead
  of falling back to the unpolished (valid) first-pass translation (`block_execution.py:614` uncaught).
- **It is redundant.** A separate, working `operation == "edit"` ("Литературное редактирование") mode already does
  literary editing in the target language. Removing the inline pass and pointing users at edit mode is simpler and
  correct. (Edit-mode correctness is being confirmed by a parallel audit; this removal assumes that confirmation —
  see Anti-regression.)
- **Not introduced by the UI batch** — `block_execution.py` / the generation validator predate spec 013; this is a
  pre-existing latent bug exposed by a pre-existing UI control.

## Scope — remove end-to-end (each is one verifiable task)

1. **UI control.** Remove the second-pass checkbox (`_ui.py:652-661`, `key="sidebar_translation_second_pass"`) and
   the `translation_second_pass_enabled` element from `render_sidebar`'s return tuple. Update ALL consumers of that
   tuple (`_app.py:791` unpack, `_app.py:799` `app_config["translation_second_pass_enabled"] = …`, and any test
   harness that unpacks the sidebar tuple) so the flag is fully gone and the tuple stays internally consistent.
2. **i18n keys.** Remove `sidebar.second_pass_label` and `sidebar.second_pass_help` from `ru.json` and `en.json`
   (keep the catalogs key-parity intact except the pre-existing intentional en-missing `sidebar.model_label`).
3. **Pipeline pass.** Remove `_should_run_translation_second_pass`, `_run_translation_second_pass`,
   `_resolve_translation_second_pass_model` and the call site (`block_execution.py:784-796`). Remove
   `_resolve_text_call_target` ONLY if it is used solely by the second pass (grep first; keep if shared).
4. **Effective flag / telemetry.** Remove `effective_translation_second_pass_enabled` (`setup.py:424-426`, `:499`,
   `:515`), `_is_translation_second_pass_effectively_enabled` and its use (`late_phases.py:4779/4832-4835`), and the
   related `log_event` fields.
5. **Config fields.** Remove `translation_second_pass_default` and `translation_second_pass_model` from
   `core/config.py` (`:215-216`, `:1159-1164`), `core/config_loader_layers.py` (`:61-62`),
   `core/config_runtime_sections.py` (`:470-478`, `:515-523`, `:544-545`), and from `config.toml`. Remove the env
   vars `DOCX_AI_TRANSLATION_SECOND_PASS_*`. Ensure config load does not require the removed fields.
6. **Tests.** Delete the second-pass tests (gate on/off, translate-only skip, audiobook stale-flag skip, effective
   logging, provider routing, hard-fail on raise — in `test_document_pipeline.py` ~:2672/:2714/:2896/:3141/:3183 and
   the `:399-467` routing test if it exists only for the second pass) and update any test that unpacks the sidebar
   tuple or reads the removed config fields. Register no new test files.

## Non-goals

- Do NOT repair the marker round-trip / re-enable the pass in any form — this spec REMOVES it. (If a future inline
  polish is ever wanted, it is a fresh design that feeds marker-preserved text and falls back on failure.)
- Do NOT change `operation == "edit"` / `translate` / `audiobook` behavior otherwise.
- Do NOT remove shared helpers still used by other paths (verify `_resolve_text_call_target` usage before deleting).
- No UI copy changes beyond removing the two second-pass strings.

## Anti-regression

- **Translate path unchanged:** the flag defaulted to off; with it removed, a translate run produces the same
  output as a translate run that never ticked the box. A translate test (mocked LLM) still passes and produces the
  first-pass result.
- **`render_sidebar` tuple:** its shape changes (one fewer element). EVERY unpack site + test updated in the same
  change; no site reads a stale index. A test asserts the new tuple arity and that no consumer references
  `translation_second_pass_enabled`.
- **Config load robust:** loading a config/`config.toml` without the removed fields does not raise; a test or a
  clean load proves it. Any external `config.toml` that still lists the old fields must not break (extra unknown
  keys ignored, or the fields are simply dropped from the schema).
- **No dangling references:** `grep -rn "second_pass" src/ tests/` returns ZERO after the change (except this spec /
  changelog). pyright delta ≤ 0. Full suite green (modulo the pre-existing environmental corpus/typecheck items).
- **Replacement is real — CONFIRMED (audit 2026-07-13, orchestrator-verified).** `operation == "edit"` runs the
  same marker-preserving generation machinery as the working first translate pass but is fed marker-ANNOTATED input
  (`block_execution.py:424` `target_text=payload.target_text_with_markers`), so it never hits the `markers_missing`
  crash; retry + recovery + source-text fallback all apply (`_generation.py:998-1104`). It performs an in-language
  literary edit in `target_language` (`prompts/operation_edit.txt`; no translation). So re-running a translated
  document through edit mode is a correct, non-failing polish path. Minor caveats (LOW, not blockers): a persistent
  per-block marker failure degrades that block to unedited source (graceful, logged); the user must set
  `target_language` to the document's actual language; no explicit edit-mode marker-round-trip test (machinery shared
  with translate, which is tested).

## Verification (Constitution I/II/VIII)

- `wsl.exe -d Debian --cd "D:\www\Projects\2025\DocxAICorrector" -- bash scripts/test.sh` — full suite green
  (except the documented pre-existing corpus/typecheck env items).
- `grep -rn "second_pass\|translation_second_pass" src/ tests/` → empty (proof of complete removal).
- pyright delta ≤ 0 (`tests/test_typecheck.py` baseline untouched).
- A translate run (mocked/no-LLM) still succeeds and yields the first-pass output.

## Rollout

Implement via the delivery loop (implementing agent → orchestrator independent verification: full `scripts/test.sh`,
grep-clean, pyright delta ≤0), on the current UI batch branch or a sibling, merged with (or right after) spec 013.
