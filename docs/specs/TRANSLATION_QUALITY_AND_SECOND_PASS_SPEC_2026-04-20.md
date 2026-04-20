# Translation Quality And Second Pass Spec

Date: 2026-04-20
Status: Proposed active specification
Scope type: product behavior and pipeline quality improvement
Primary inputs:

- live UI translation run analysis for Mariana Mazzucato document on 2026-04-20
- current translation prompts in `prompts/operation_translate.txt` and `prompts/system_prompt.txt`
- current text pipeline in `document_pipeline.py`, `generation.py`, `processing_service.py`, `processing_runtime.py`
- current UI controls in `ui.py`
- current config surface in `config.py`

## 1. Purpose

This specification defines a safe implementation plan for two linked improvements:

1. improve first-pass translation quality so English to Russian output is less calque-like, less mechanically literal, and more literary without weakening structure-preservation guarantees;
2. add an optional second literary pass for translation runs where the user explicitly wants higher stylistic polish.

This document is implementation-oriented. It defines scope, user-facing behavior, config surface, tests, and documentation updates.

## 2. Problem Statement

The current translation path already produces correct Russian output, but it remains stylistically conservative.

Observed current-state constraints:

1. `gpt-5.4-mini` is already the default text model in `config.py`, so the main bottleneck is not simply model tier.
2. `prompts/operation_translate.txt` asks for natural target-language text, but the instructions remain broad and weak against translationese.
3. `prompts/system_prompt.txt` adds strong conservative behavior, which is useful for correctness but dampens literary fluency.
4. `editorial_intensity_default` exists in `config.py`, but `load_system_prompt()` does not currently vary prompt content based on `editorial_intensity`.
5. The pipeline has only one text pass. There is no explicit post-translation literary-editing stage.
6. The current UI already exposes the natural location for text-transform controls: sidebar settings in `ui.render_sidebar()`.

## 3. Goals

This work must achieve the following:

1. make first-pass translation quality materially less literal for prose-like content;
2. keep existing structure-preservation contracts for markers, placeholders, paragraph count constraints, and DOCX reconstruction;
3. add a second-pass mode that is optional, explicit, and user-controlled rather than silently changing cost and latency for everyone;
4. make the new behavior inspectable in config, runtime logs/state, and user-visible controls;
5. keep the default path predictable and low-risk.

## 4. Non-Goals

This spec does not authorize the following:

1. changing the WSL-first runtime or test workflow;
2. replacing the current block-based text pipeline with document-wide generation;
3. broad UI redesign beyond the minimum settings surface needed for these features;
4. making the second pass mandatory for all translation runs;
5. changing pricing/model-selection strategy globally without follow-up evidence.

## 5. Current State

### 5.1 Prompt and config reality

Current reality in code:

1. `config.py` exposes `editorial_intensity_default` in `AppConfig` and reads it from file/env.
2. `config.load_system_prompt()` accepts `editorial_intensity`, but the final prompt template currently ignores that parameter.
3. `config.load_system_prompt()` is wrapped in `@lru_cache(maxsize=32)`, so once prompt composition starts using `editorial_intensity`, that value will correctly participate in the prompt cache key.
4. `document_pipeline._resolve_system_prompt()` is the real call site that forwards kwargs into `load_system_prompt()` via signature introspection; it currently knows only about `operation`, `source_language`, and `target_language`.
5. `generation.py` sends text requests with `temperature = 0.4`.
6. Translation prompt examples are generic and do not include explicit anti-calque examples.
7. `prompts/system_prompt.txt` currently has no placeholder for editorial-intensity-specific instructions.

### 5.2 UI reality

Current reality in UI:

1. sidebar already exposes `processing_operation`, `source_language`, `target_language`, and model choice in `ui.render_sidebar()`;
2. these values flow through `app.py` into background processing;
3. there is currently no user-visible control for editorial intensity or second pass;
4. `ui.render_sidebar()` currently returns a strict annotated 8-tuple;
5. `app._resolve_sidebar_settings()` explicitly accepts only the current 8-tuple contract or a legacy 5-tuple fallback used by older tests/mocks.

### 5.3 Pipeline reality

Current reality in runtime:

1. the current text pipeline is effectively single-pass;
2. the successful output of the pass becomes `latest_markdown`, then DOCX assembly proceeds;
3. final user-visible outputs are now persisted under `.run/ui_results/` and logged via `ui_result_artifacts_saved`;
4. `app.py` currently injects `processing_operation`, `source_language`, and `target_language` into `app_config` before processing starts, so `app_config` already acts as a lightweight parameter bag for text-transform runtime settings;
5. `processing_service.run_prepared_background_document()` is part of the active runtime/test surface and must stay aligned with any new per-run translation settings;
6. `processing_completed` is currently a structured `log_event(...)` event, not a typed class in `runtime_events.py`;
7. `ProcessingOutcome` remains a simple lifecycle enum with one running state; there is no existing typed multi-pass state machine.

## 6. Proposed Product Behavior

This spec introduces two layers of quality control.

### 6.1 Layer A: stronger first-pass translation contract

The translation prompt must become explicitly style-aware.

Required behavior:

1. first-pass translation should prefer idiomatic Russian syntax over source-language word order;
2. it should preserve argument, facts, tone, and rhetorical stance while allowing local restructuring for natural Russian prose;
3. it should explicitly avoid calques, bureaucratic phrasing, and source-language sentence skeletons when Russian literary prose would phrase the thought differently;
4. it must remain conservative for facts, named entities, numeric values, markers, placeholders, and paragraph boundaries.

### 6.2 Layer B: optional second literary pass

The system may perform a second pass after translation, but only when explicitly enabled.

Required behavior:

1. pass 1 translates the source block into the target language;
2. pass 2 rewrites only the already translated target-language text for literary fluency;
3. pass 2 must not change meaning, facts, structure markers, placeholders, or paragraph boundaries;
4. pass 2 is allowed to improve rhythm, diction, transitions, and register consistency;
5. pass 2 is only available for `processing_operation = translate`.

## 7. User-Facing Enablement

### 7.1 Who enables the second pass

The second pass is user-controlled.

Primary rule:

1. the user enables it in the sidebar;
2. the default remains off unless config explicitly changes the default later.

### 7.2 Where it appears in the UI

The control belongs in the existing text settings area in `ui.render_sidebar()`, not in a separate advanced admin-only panel.

Placement rule:

1. show it only when `Режим обработки текста = Перевод`;
2. place it after `Язык оригинала` / `Целевой язык` and before model selection, because it changes text behavior rather than infrastructure;
3. hide or disable it in `edit` mode.

Recommended UI shape:

1. checkbox: `Дополнительный литературный проход после перевода`
2. help text: `Делает второй проход только по уже переведённому тексту. Обычно улучшает стиль, но увеличивает время и стоимость обработки.`

Contract note:

1. adding this control changes the `render_sidebar()` return contract;
2. `app._resolve_sidebar_settings()` must be updated in the same slice;
3. legacy 5-tuple test mocks in `tests/test_app.py` and related call sites must be updated or consciously preserved through compatibility logic.

### 7.3 Config and env defaults

The control must also have config-level defaults for reproducible runs.

Required new settings:

1. `translation_second_pass_default = false`
2. `translation_second_pass_model = ""` meaning “use the selected text model unless overridden”
3. optional env override: `DOCX_AI_TRANSLATION_SECOND_PASS_DEFAULT`
4. optional env override: `DOCX_AI_TRANSLATION_SECOND_PASS_MODEL`

Decision rule:

1. product default is off;
2. config/env may pre-enable it for private deployments;
3. user toggle in sidebar remains the final per-run choice.

## 8. Prompt and Runtime Design

### 8.1 First-pass editorial intensity

`editorial_intensity` must become real behavior rather than dead config.

Proposed values:

1. `conservative`
2. `literary`

Behavior contract:

1. `conservative` preserves the current low-risk posture with modest anti-calque guidance;
2. `literary` explicitly prefers idiomatic, book-quality Russian phrasing while preserving meaning and structure;
3. translation mode defaults to `literary` unless config says otherwise.

Implementation rules:

1. add separate instruction fragments for editorial intensity rather than embedding everything in one monolithic template;
2. compose them in `load_system_prompt()`;
3. do not overload `operation_translate.txt` with all branching logic inline;
4. add a dedicated placeholder such as `{editorial_intensity_instructions}` to `prompts/system_prompt.txt`, because the current template does not expose any insertion point for intensity-specific behavior.

Recommended file shape:

1. keep `prompts/operation_translate.txt` for operation-level rules;
2. add one of:
   - `prompts/editorial_intensity_conservative.txt`
   - `prompts/editorial_intensity_literary.txt`
3. include the selected fragment into `system_prompt.txt` via the new placeholder.

### 8.2 Second-pass prompt contract

Second pass should not pretend to be another translation pass.

Required prompt behavior:

1. input is already on the target language;
2. task is literary editing only;
3. meaning preservation is strict;
4. paragraph markers and placeholders are preserved exactly;
5. if the text is already fluent, the model should make minimal changes.

Recommended artifact shape:

1. dedicated prompt fragment such as `prompts/operation_literary_polish.txt` or equivalent helper template;
2. no reuse of the normal `edit` prompt if it weakens the translation-specific preservation contract.

## 9. Proposed Work Order

The work should be done in two implementation slices, in order.

### Slice 1. Strengthen first-pass translation quality

Objective: improve output quality without changing cost/latency shape for default runs.

Code changes:

1. wire `editorial_intensity` through prompt assembly in `config.load_system_prompt()`;
2. add explicit editorial-intensity prompt fragments;
3. add `{editorial_intensity_instructions}` placeholder to `prompts/system_prompt.txt` and fill it from prompt assembly;
4. update `document_pipeline._resolve_system_prompt()` so the actual pipeline call site can forward `editorial_intensity` when the target callable accepts it;
5. use `app_config` as the simplest runtime parameter bag for first-pass `editorial_intensity`, mirroring the existing pattern for `processing_operation`, `source_language`, and `target_language`, instead of threading a new positional parameter through every intermediate signature unless a later refactor justifies it;
6. strengthen `prompts/operation_translate.txt` with sharper anti-calque instructions;
7. replace placeholder examples in `prompts/example_translate.txt` with concrete English-to-Russian examples showing:
   - literal-but-bad phrasing to avoid;
   - idiomatic literary Russian target phrasing to prefer;
   - preservation of facts and rhetorical force.
8. document `@lru_cache` behavior in this slice as an intentional design fact: different `editorial_intensity` values are expected to produce distinct cached prompts.

Implementation notes:

1. do not add the second pass in this slice;
2. do not add a new user-visible control for editorial intensity in the first rollout unless needed for debugging;
3. use config default first to keep the UI scope minimal.

Tests required:

1. `tests/test_config.py`
   - verify `load_system_prompt()` output changes when `editorial_intensity` changes;
   - verify config/env parsing for `editorial_intensity_default` remains stable.
2. `tests/test_document_pipeline.py` or `tests/test_processing_service.py`
   - verify translation runs pass `editorial_intensity` into `_resolve_system_prompt()` / prompt resolution.
3. prompt-shape tests
   - verify selected prompt text contains the intended intensity fragment;
   - verify marker-preservation instructions remain present.
4. cache-behavior test
   - verify distinct `editorial_intensity` values yield distinct prompt text without breaking cached reuse for identical inputs.

Documentation required:

1. update `.github/copilot-instructions.md` if agent guidance needs to mention new translation-quality controls;
2. update `AGENTS.md` if artifact/debugging guidance changes;
3. update user-facing docs if config keys are exposed in `README.md` or `docs/WORKFLOW_AND_IMAGE_MODES.md`.

Acceptance criteria:

1. `editorial_intensity` is no longer dead config;
2. prompt composition is test-covered;
3. no change to UI complexity yet;
4. output quality can improve without the second pass.

### Slice 2. Add optional second literary pass

Objective: add a premium-quality mode for users who want more fluent prose and accept extra latency/cost.

Code changes:

1. add config fields for second-pass default and optional override model;
2. add sidebar control in `ui.render_sidebar()` visible only in translate mode;
3. expand the `render_sidebar()` tuple contract and update `app._resolve_sidebar_settings()` in the same change-set;
4. update legacy tuple-based test mocks, especially in `tests/test_app.py`, that still return the older 5-tuple compatibility shape;
5. pass the new per-run choice through `app.py`, `processing_runtime.py`, `processing_service.py`, `processing_service.run_prepared_background_document()`, and `document_pipeline.py`;
6. implement second-pass processing at the block level after successful translation output and before final markdown is committed as the block result;
7. emit logging/state signals that make it inspectable when second pass was used.

Recommended runtime fields and signals:

1. per-run state field: `translation_second_pass_enabled`
2. start-of-run `log_event(...)` payload includes `translation_second_pass_enabled`
3. optional per-block debug log includes whether pass 2 ran for the block
4. `processing_completed` log event includes whether second pass was enabled

Clarification:

1. `processing_completed` here refers to the structured logging event emitted through `log_event(...)`, not a typed class in `runtime_events.py`;
2. no new typed runtime event is required in the first rollout unless later UX needs explicit pass-stage rendering.

Decision on model selection for pass 2:

1. default: use the same selected text model;
2. optional override via config `translation_second_pass_model`;
3. the UI does not need a separate second-pass model selector in the first rollout.

Failure policy:

1. if pass 1 fails, pass 2 must never run;
2. if pass 2 fails, fail the run rather than silently falling back, at least in the first implementation;
3. reason: a silent fallback would hide whether the user actually received the requested premium path.

Processing-state clarification:

1. do not introduce a new `ProcessingOutcome` enum value in the first rollout;
2. keep the outer lifecycle as `RUNNING` and track second-pass execution through log/state metadata instead;
3. only introduce a typed multi-pass state if the UI later needs distinct progress semantics for pass 1 vs pass 2.

Tests required:

1. `tests/test_ui.py`
   - control is shown only in translate mode;
   - control is hidden or ignored in edit mode;
   - sidebar returns the correct new flag and updated tuple shape.
2. `tests/test_app.py`
   - `_resolve_sidebar_settings()` accepts the new tuple contract;
   - per-run state flows into background processing start;
   - legacy mocks are updated or intentionally wrapped.
3. `tests/test_processing_service.py`
   - processing service forwards second-pass settings into pipeline implementation;
   - `run_prepared_background_document()` forwards second-pass settings too.
4. `tests/test_document_pipeline.py`
   - second pass runs only when enabled;
   - second pass is skipped in edit mode;
   - second pass output becomes final block markdown;
   - second-pass failure behavior is explicit and tested.
5. `tests/test_config.py`
   - parse new config/env defaults correctly.

Documentation required:

1. update `README.md` text-processing settings section;
2. update `AGENTS.md` to explain how to identify when second pass was enabled in logs/artifacts;
3. update `.github/copilot-instructions.md` if agent guidance for quality analysis needs the new event/setting;
4. update any config reference docs to include new keys.

Acceptance criteria:

1. the user can explicitly enable or disable second pass from the sidebar;
2. the setting is visible, documented, and test-covered;
3. runtime logs make it unambiguous whether second pass ran;
4. output path remains structurally safe.

## 10. Detailed Test Plan

The regression suite must protect both behavior and contract clarity.

### 10.1 Unit tests

1. prompt assembly tests for first-pass intensity selection;
2. config parsing tests for new defaults and env overrides;
3. UI tests for conditional visibility and state resolution of the second-pass toggle;
4. pipeline tests for second-pass branching and failure policy.

### 10.2 Contract tests

1. pass 2 preserves markers and placeholders exactly;
2. pass 2 does not run outside translation mode;
3. runtime logs/state include second-pass usage;
4. first-pass intensity selection is reflected in prompt composition, not only in config values.

### 10.3 Real-run verification

After implementation, verify at least one real English-to-Russian document through the normal UI path.

Required evidence:

1. compare translation with second pass off vs on;
2. confirm final outputs in `.run/ui_results/`;
3. confirm logs show whether second pass ran;
4. inspect that paragraph markers, headings, and image placeholders remain intact.

## 11. Documentation Deliverables

Minimum documentation set for completion:

1. this spec in `docs/specs/`;
2. config-key updates in the canonical user/developer docs;
3. agent guidance for artifact and log interpretation if second pass becomes inspectable via new log fields or state metadata;
4. optional note in translation prompt docs or review docs explaining why the prompt was strengthened before a model-tier upgrade.

## 12. Recommendation Summary

Recommended order of execution:

1. implement Slice 1 first;
2. evaluate quality on real prose documents;
3. only then implement Slice 2;
4. only after both slices are evaluated should the team consider a broader default move from `gpt-5.4-mini` to `gpt-5.4`.

Reasoning:

1. Slice 1 is cheaper, lower-risk, and likely to improve the main complaint directly;
2. Slice 2 gives an explicit premium path without forcing higher cost on every run;
3. model-tier escalation should be evidence-based after prompt and pipeline improvements are real.

## 13. Approval Gate

Implementation should proceed in this order:

1. approve Slice 1 prompt/intensity work;
2. ship and evaluate;
3. approve Slice 2 optional second-pass work if the quality delta still justifies the added complexity.

If the user explicitly wants both implemented in one change-set anyway, the code should still be developed and reviewed in the internal order defined above: first-pass quality contract first, second-pass wiring second.
