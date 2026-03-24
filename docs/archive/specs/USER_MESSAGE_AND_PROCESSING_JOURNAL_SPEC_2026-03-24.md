# User Message and Processing Journal Spec

Date: 2026-03-24
Status: Implemented
Scope type: targeted UX-contract and runtime-message hardening
Primary input: validated review of preparation, processing, stop/failure, and processing-journal messaging on 2026-03-24

## Implementation Status

Implementation completed on 2026-03-24.

Completed:

- Workstream A: user-facing runtime message precedence normalized for preparation, restartable stop/failure, and live-status titles.
- Workstream B: visible image result, fallback, and error entries restored in the canonical processing journal.
- Workstream C: centralized human-readable message formatting introduced through `message_formatting.py` and reused by state/UI layers.
- Workstream D: regression coverage updated for state, UI, app, and image-integration behavior.
- Open decision OD-001 resolved in favor of extending `run_log` into a typed visible journal schema.

Verification completed:

- Visible VS Code task `Run Full Pytest`
- Result: `512 passed, 5 skipped`

Remaining work for this spec:

- No mandatory implementation items remain open.
- Future wording refinements or UX polish should be treated as follow-up tasks, not as unfinished scope from this spec.

## 1. Problem Statement

The current runtime-message layer has drifted into two partially overlapping channels:

- `processing_status`, which drives the main live status panel;
- `run_log`, which now drives the visible processing journal;
- `activity_feed`, which still receives many transient runtime events but is no longer rendered in the journal.

That split created two classes of regressions:

1. contradictory user-facing status messages across preparation, stopped, failed, and restartable states;
2. loss of useful image-processing result/error messages after the verbose activity feed was removed from the visible journal.

The first regression is a correctness issue: the UI can still show success-oriented preparation copy in states that are actually stopped or failed.

The second regression is an observability issue: removing the noisy event stream also removed the only visible surface where image-processing outcomes had been reported. At the moment, block completion entries remain visible through `run_log`, but image-processing results are mostly reduced to aggregate metrics in `render_image_validation_summary()` and no longer appear in the journal as readable per-image results.

This specification defines a narrow hardening pass that restores a coherent user-message contract without bringing back the removed noisy event tape.

## 2. Goals

1. Eliminate contradictory user-facing status messages across preparation, processing, stop, failure, and restartable states.
2. Define one explicit contract for which runtime messages belong in the visible processing journal and which remain internal/transient activity.
3. Keep the journal free of low-value noise such as “block sent to OpenAI” and “block started”.
4. Restore visible image-processing result/error entries in the journal using human-readable wording.
5. Preserve the existing high-value block completion entries already shown in `run_log`.
6. Add regression coverage for state/message precedence and image-journal visibility.
7. Preserve the repository architecture where `app.py` stays a thin composition layer and business message policy lives in reusable runtime/state contracts rather than in UI branches.

## 3. Non-Goals

This spec does not authorize the following:

- redesigning the overall Streamlit layout;
- reintroducing the full chronological activity tape into the UI;
- changing document-processing semantics, image-generation algorithms, or validation logic;
- replacing the image validation summary metrics/cards with a journal-only view;
- broad runtime refactoring outside the message-routing and journal contracts;
- moving orchestration ownership back from `application_flow.py` and `processing_runtime.py` into `app.py` via ad hoc branch-local fixes;
- scattering user-facing wording policy across `image_pipeline.py`, `document_pipeline.py`, or `ui.py` call sites;
- altering startup-performance or WSL/bash test workflow contracts.

## 4. Protected Contracts

The following repository contracts remain in force throughout this work:

1. Startup performance contract in `docs/STARTUP_PERFORMANCE_CONTRACT.md`.
2. Existing WSL/bash pytest workflow and visible verification via VS Code tasks.
3. Existing processing semantics for block execution, image validation, and final DOCX generation.
4. The processing journal remains concise and outcome-oriented rather than a full debug/event trace.
5. `activity_feed` may continue to exist for internal/transient runtime use, but it is no longer the canonical user-visible journal surface.
6. Existing ownership boundaries remain protected: `application_flow.py` owns idle/restart/preparation flow decisions, `processing_runtime.py` owns event draining and runtime state application, `state.py` owns session-state mutation helpers, and `ui.py` renders already-decided state.

Any implementation that pressures one of these contracts must document why and update the relevant canonical docs if behavior is intentionally changed.

## 5. Current-State Findings in Scope

### UM-001: Preparation UI can still communicate success when preparation actually failed

`render_live_status()` uses `phase == "preparing"` plus `is_running` to choose between “Идет анализ файла” and “Анализ файла завершён”. On preparation failure, `finalize_processing_status()` sets `is_running=False`, but does not change `phase`. That allows a failed preparation state to render under a success-oriented title.

Files in scope:

- `state.py`
- `processing_runtime.py`
- `ui.py`

### UM-002: Restartable outcomes are not presented through one consistent user-message contract

The app currently distinguishes restartable states through a mixture of:

- `processing_outcome` checks;
- `has_restartable_source()`;
- idle-view derivation;
- file-selected branch behavior.

This creates uneven user-facing copy between `STOPPED`, `FAILED`, and restored restartable flows. `STOPPED` currently gets a dedicated banner in one branch, while `FAILED` is mostly exposed only through raw error output.

Files in scope:

- `app.py`
- `application_flow.py`
- `workflow_state.py`

### UM-003: Preparation wait messaging conflates in-progress and lost-state scenarios

The current warning copy says the file preparation “еще не завершилась или состояние подготовки было сброшено”. That merges two materially different user situations:

1. the background preparation is still running;
2. the preparation state was lost or invalidated and may require recovery action.

Files in scope:

- `app.py`

### PJ-001: Removing the visible activity tape also removed visible image-processing result messages

`render_run_log()` now reads only `run_log`. This successfully removed noisy block-level activity entries, but `append_image_log()` still writes only to `activity_feed` through `push_activity()`. As a result, image-processing outcomes no longer appear in the visible processing journal.

Files in scope:

- `ui.py`
- `state.py`
- `processing_runtime.py`
- `image_pipeline.py`

### PJ-002: Image log payloads are currently shaped for technical activity output, not for user-facing journal output

The current image activity line format is:

`[IMG] {image_id}: {status} | conf: {confidence:.2f} | {decision}`

This is concise for debugging, but not suitable as the visible processing journal contract. It exposes implementation statuses like `validated`, `compared`, `fallback_original`, and `error` directly instead of communicating user-meaningful outcomes.

Files in scope:

- `state.py`
- `tests/test_state.py`

### PJ-003: Image pipeline emits both low-value progress activity and high-value results into the same stream

The image pipeline emits:

- low-value progress activity such as “Начата обработка изображения X из Y”; and
- high-value result/error activity such as fallback, final decision, or processing stop.

These should not share the same visible channel contract. The visible journal should keep only high-value result/error entries.

Files in scope:

- `image_pipeline.py`

## 6. Design Principles

Implementation must follow these principles:

1. The visible journal must contain outcomes, not transport noise.
2. User-facing titles must be derived from semantic state, not from one incidental flag like `is_running` alone.
3. Restartable flows must communicate one consistent recovery contract across stopped and failed outcomes.
4. Image-processing journal entries must be human-readable and decision-oriented.
5. Summary metrics and journal lines serve different purposes and must coexist rather than replace one another.
6. Prefer one explicit message-routing rule per state class over branch-local copy exceptions.
7. Decision logic and rendering logic must remain separate: UI renders message state, but does not reconstruct business-state meaning from incidental low-level flags when a shared runtime/state contract can represent it directly.
8. Session-state defaults, reset behavior, and visible journal schema must have one canonical contract rather than parallel hand-maintained shapes.
9. Pipelines should emit semantic payloads, not pre-baked UI text, when the same outcome may be rendered in multiple user-facing surfaces.

## 7. Target UX Contract

## 7.1 Live Status Panel Contract

The live status panel must represent the semantic state of the current run.

Required behavior:

1. Preparation in progress shows an in-progress analysis title.
2. Successful preparation shows a preparation-complete title and detail.
3. Preparation failure shows an error-oriented title and detail, not a success title.
4. Stopped processing shows a stopped-oriented title/detail.
5. Failed processing shows a failed/error-oriented title/detail.

The title-selection rule must not be based only on `is_running`. It must consider at least one of:

- explicit semantic stage class;
- processing outcome;
- non-preparing terminal error state.

## 7.2 Restartable Outcome Messaging Contract

Restartable outcomes are:

- `STOPPED`;
- `FAILED` when restart source is still available.

For restartable outcomes, the app must present:

1. a clear terminal message about what happened;
2. a clear recovery message about what the user can do next;
3. no contradictory success-oriented preparation summary;
4. no stale progress implying that processing is still actively advancing.

Preferred message model:

- `STOPPED`: “Обработка остановлена пользователем. Можно изменить настройки и запустить заново без повторной загрузки файла.”
- `FAILED`: “Обработка завершилась ошибкой. Можно скорректировать настройки и запустить заново без повторной загрузки файла.”

Exact wording may change during implementation, but the semantic distinction must remain explicit.

## 7.3 Processing Journal Contract

The visible processing journal is an outcome-oriented log.

It should contain:

- block completion entries from `run_log`;
- terminal document-level entries such as DONE/ERROR/STOP where applicable;
- image-processing result entries and image-processing error/fallback entries;
- notable image-pipeline stop/failure outcomes when they materially affect the document result.

It should not contain:

- “block started”;
- “block sent to OpenAI”;
- “image started”;
- generic heartbeat/progress noise;
- duplicate copies of information already shown in the status panel unless the journal entry records a completed result.

## 7.4 Image Journal Entry Contract

Image-processing journal entries must be visible in the same journal surface as block completion entries, but with human-readable wording.

The journal entry model should communicate:

- which image was processed;
- final outcome in user terms;
- whether the image was accepted, improved, compared, or fell back to original;
- why a fallback or error happened when that reason materially matters.

Preferred examples:

- `[IMG OK] Изображение img-1 | оставлен safe-вариант | confidence: 0.92`
- `[IMG OK] Изображение img-2 | оставлен оригинал | режим «Без изменения»`
- `[IMG WARN] Изображение img-3 | оставлен оригинал | кандидат не прошёл валидацию`
- `[IMG WARN] Изображение img-4 | обработка пропущена | неподдерживаемый формат исходного изображения`
- `[IMG ERR] Изображение img-5 | ошибка обработки | применён fallback на оригинал`

The exact prefix format may change, but the visible message must be understandable without knowing internal enum names.

## 8. Target Architecture

## 8.0 Responsibility Boundaries

This work must preserve and clarify the existing boundary model rather than collapsing it into local UI fixes.

Target ownership:

- `app.py`: composition root, widget order, top-level branch selection, no ad hoc message-policy reconstruction.
- `application_flow.py`: idle/restart/preparation flow decisions and state derivation helpers.
- `processing_runtime.py`: typed event draining and application of runtime state mutations.
- `state.py`: canonical session-state defaults, reset helpers, journal append helpers, and formatting adapters for visible journal entries.
- `ui.py`: rendering of already-normalized state and journal entries.
- `image_pipeline.py` and `document_pipeline.py`: emission of semantic outcome payloads, not direct ownership of visible journal wording policy.

The implementation should be rejected if it solves the problem by adding more branch-local message text in `app.py` or by teaching `ui.py` to decode low-level pipeline enums directly.

## 8.1 Separate Internal Activity From Visible Journal Entries

After implementation, the message system should explicitly distinguish:

1. transient runtime activity;
2. visible journal entries.

`activity_feed` remains appropriate for transient activity and optional diagnostics.

`run_log` or an equivalent visible-log structure becomes the canonical user-visible journal.

The implementation may choose one of these approaches:

### Option A: Extend `run_log` to support typed journal entries

Add a richer entry schema that can represent both block and image results while preserving chronological rendering.

Pros:

- one canonical visible journal;
- simpler rendering ownership;
- avoids dual visible lists.

Cons:

- requires widening current `run_log` entry contract and tests.

### Option B: Add a separate visible image journal collection and render it together with `run_log`

Keep block log and image log separate in state, but normalize them into one ordered journal during rendering.

Pros:

- smaller migration for block log schema.

Cons:

- more rendering orchestration and ordering logic;
- risks recreating parallel visible channels.

Preferred direction: Option A. One visible journal is the cleaner contract.

## 8.1.1 Canonical Visible Journal Schema

If Option A is chosen, the widened visible journal must become the single canonical schema for user-visible processing history.

Required properties of the schema:

- explicit entry kind, for example block, image, or document;
- explicit user-visible severity/status;
- one normalized text/detail field intended for display;
- enough structured metadata to support future rendering/tests without parsing display strings.

The state contract must not rely on two unrelated append shapes that merely happen to be rendered in one list later.

Preferred consequence:

- `append_log()` and `append_image_log()` should converge onto one normalized visible-journal append path or one shared lower-level helper.

## 8.1.2 Single Source of Truth for State Defaults and Journal State

Any new state keys introduced by this work must follow the repository rule that initialization and reset are driven by one contract.

That means:

- no second hidden default shape for visible journal entries;
- no separate reset logic for a new journal collection unless that collection is itself the canonical visible journal;
- no UI-only state defaults that bypass `state.py`.

## 8.2 Semantic Message Formatter for Image Outcomes

Image journal entries should not be constructed ad hoc in `image_pipeline.py` with inline string formatting.

Introduce one narrow formatter/helper that maps technical image state into user-facing journal text.

That formatter should consume inputs such as:

- `image_id`;
- final decision;
- final variant;
- status;
- confidence;
- suspicious reasons / missing labels.

It should output:

- journal severity or status label;
- human-readable details string.

Preferred location:

- a narrow helper owned by state/runtime message infrastructure rather than by `ui.py` or `image_pipeline.py`.

This avoids scattering user-language policy across pipeline branches.

## 8.2.1 Pipeline Emission Contract

The pipelines should emit semantic payloads such as status, decision, final variant, confidence, and reasons.

They should not be responsible for deciding final user-facing wording beyond the rare case where a literal string is already part of the domain contract.

In practice:

- `image_pipeline.py` may continue to emit technical outcome fields;
- the message formatter/journal appender layer should map those fields to user-visible wording;
- `ui.py` should render the normalized result and should not contain a second mapping table for the same outcome classes.

## 8.3 Preparation Message State Model

Preparation rendering should no longer infer completion solely through `is_running=False` while `phase==preparing`.

Preferred target:

- successful preparation carries an explicit preparation-complete semantic state;
- failed preparation carries an explicit preparation-failed semantic state;
- UI title selection keys off that semantic state.

This can be implemented either through:

1. extending `processing_status` with a terminal preparation status kind; or
2. tightening title logic around `stage` and failure conditions.

The chosen implementation must preserve current testability and avoid a broad runtime redesign.

Preferred architectural direction:

- represent preparation terminal semantics explicitly in runtime/state contracts rather than teaching `ui.py` to infer them from `phase + is_running + stage` combinations.

## 9. Workstreams

## 9.1 Workstream A: Normalize User-Facing Runtime Message Precedence

Files in scope:

- `app.py`
- `ui.py`
- `state.py`
- `processing_runtime.py`
- `application_flow.py`
- `workflow_state.py`

Required changes:

- define precedence rules for preparation success, preparation failure, stopped processing, failed processing, restartable idle states, and completed states;
- place those precedence rules in reusable state/flow helpers rather than in duplicated UI-branch conditionals;
- ensure no success-oriented preparation summary is rendered for restartable stop/failure states;
- ensure failure states do not inherit titles intended for successful analysis completion;
- separate “still preparing” copy from “state lost / invalidated” copy.

Acceptance:

- stopped and failed states never show “Анализ файла завершён” unless that message is semantically true for the current visible state;
- the user always receives one coherent next-step message;
- restartable failed state is communicated as restartable, not only as raw error text.

## 9.2 Workstream B: Restore Visible Image Result/Error Entries in the Processing Journal

Files in scope:

- `state.py`
- `ui.py`
- `processing_runtime.py`
- `image_pipeline.py`
- `app_runtime.py`

Required changes:

- move visible image result/error reporting out of `activity_feed`-only semantics;
- keep `app_runtime.py` as a thin facade and avoid moving display-policy decisions into it;
- route image completion/fallback/error events into the visible journal contract;
- keep low-value image progress activity out of the visible journal;
- preserve summary metrics in `render_image_validation_summary()`.

Acceptance:

- per-image outcomes are visible in the processing journal after image processing runs;
- image fallback and error cases appear as readable journal lines;
- deleting the noisy activity feed no longer hides important image results;
- the journal remains concise and readable.

## 9.3 Workstream C: Introduce a Human-Readable Image Message Formatter

Files in scope:

- `state.py`
- optionally one new narrow helper module if needed
- `tests/test_state.py`
- `tests/test_ui.py`

Required changes:

- centralize mapping from technical image status/decision/reason payloads to user-facing journal text;
- define approved wording for success, skipped, compared, fallback, and error outcomes;
- remove direct exposure of low-level enum names where they are not useful for end users.

Architectural constraint:

- do not implement one formatter in `state.py` and another parallel formatter in `ui.py`;
- do not leave inline humanization branches duplicated across `append_image_log()`, `render_run_log()`, and `render_image_validation_summary()`.

Acceptance:

- user-visible image journal lines are understandable without reading code;
- message wording stays stable through one formatter contract;
- test coverage protects the formatter output for the main outcome classes.

## 9.4 Workstream D: Regression Coverage for Message Contracts

Files in scope:

- `tests/test_app.py`
- `tests/test_ui.py`
- `tests/test_state.py`
- `tests/test_processing_runtime.py`

Required regression coverage:

- preparation failure does not render “Анализ файла завершён”;
- restartable `FAILED` outcome shows a recovery-oriented user message;
- in-progress preparation and lost/invalidated preparation state produce different user messages;
- image result/error/fallback entries appear in the visible journal;
- low-value image progress messages do not reappear in the visible journal;
- existing block completion journal behavior remains unchanged.
- state initialization/reset remains correct for any new journal schema or keys.

Acceptance:

- tests fail if image results disappear from the journal again;
- tests fail if success-oriented preparation text appears in stop/failure paths;
- tests fail if the journal regresses into noisy transport-level activity.
- tests fail if new state/journal keys are initialized and reset inconsistently.

## 10. Implementation Notes

1. Preserve the current decision to remove verbose block activity from the visible journal.
2. Do not reintroduce the old “События” panel as a catch-all workaround.
3. Prefer one canonical visible journal structure over parallel visible channels.
4. Keep image summary cards and fallback details; they are complementary to the journal, not redundant with it.
5. If `activity_feed` is retained for internal/debug purposes, make that role explicit in code comments or helper naming.
6. Prefer one new narrow helper/module if needed over distributed micro-fixes across UI and pipeline files.
7. Avoid solving the same message inconsistency twice in different layers; normalize once, render many times.

## 11. Verification Plan

Visible verification must use existing VS Code pytest tasks per repository contract.

Required verification targets:

1. `tests/test_app.py`
2. `tests/test_ui.py`
3. `tests/test_state.py`
4. `tests/test_processing_runtime.py`
5. full regression suite via the existing visible pytest task if implementation touches shared runtime/state code.

Primary visible verification path:

- VS Code task `Run Full Pytest`

Targeted debugging may use narrower selectors during development, but final verification should still use the repository-approved visible path.

## 12. Open Decisions

### OD-001: Should image journal entries live inside `run_log` or in a separate visible-log structure?

Resolved answer: extend `run_log` into a typed visible journal.

Architectural rationale:

- this preserves one visible source of truth;
- it avoids a second UI-owned merge layer;
- it better matches the existing separation where runtime/state own message data and UI owns rendering.

### OD-002: Should failed-but-restartable outcomes show `warning` or `error` styling in the main panel?

Preferred answer: keep terminal failure messaging visibly stronger than `STOPPED`, but pair it with actionable restart guidance.

### OD-003: Should image confidence always be shown in user-facing journal lines?

Preferred answer: include confidence only when it materially helps interpret the outcome. Do not force technical numeric detail into every visible line.

## 13. Acceptance Summary

This spec is complete when the implementation satisfies all of the following:

1. No stop/failure path can display a contradictory “analysis completed” message.
2. Preparation-in-progress and preparation-state-loss scenarios are messaged differently.
3. Restartable failure is communicated as a recoverable state, not only as a raw error.
4. Image results, fallbacks, and errors are visible in the processing journal again.
5. The removed verbose event tape does not return.
6. Tests explicitly protect both the message-precedence contract and the image-journal contract.
7. The implementation preserves clean responsibility boundaries instead of reintroducing business-message policy into `app.py` or `ui.py` branches.