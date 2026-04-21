# File-Scoped Recommended Text Settings Spec

Date: 2026-04-18

## Goal

Introduce file-scoped recommended text settings that are derived after document analysis and applied gently to the current file without adding extra UI controls such as a dedicated “Apply file recommendations” button.

The implementation must make it harder for the user to start processing with stale global defaults when the analyzed file strongly suggests more appropriate text-transform settings.

This specification must preserve the current processing architecture and keep the interface simple.

## Relationship To Existing Specs

This specification depends on and complements:

1. `docs/specs/MULTILINGUAL_TEXT_TRANSFORM_SPEC_2026-04-18.md`
2. `docs/specs/MULTILINGUAL_TEXT_TRANSFORM_HARDENING_SPEC_2026-04-18.md`

Those specifications established:

1. explicit text operation modes: `edit` and `translate`
2. explicit `source_language` and `target_language`
3. deterministic advisory assessment for likely user mistakes
4. warning-oriented hardening rather than hard blocking

This specification adds one more layer:

1. post-analysis recommended settings scoped to the current file
2. one-time gentle auto-apply on newly analyzed files
3. protection against overwriting user-made manual changes

## Problem Statement

The current flow renders sidebar settings before file analysis completes.

That means the user initially sees global defaults from configuration, not file-aware recommendations.

Once the file has been analyzed, the application may already know enough to recommend better text-transform settings, for example:

1. `edit` is more appropriate than `translate`
2. `source_language` should be `auto`
3. `target_language` should remain unchanged because the file already looks like target-language content

Without a file-scoped recommendation layer, the product has two bad options:

1. leave global defaults untouched and let the user accidentally start with suboptimal settings
2. overwrite active widget state bluntly and risk destroying user intent

The product needs a middle path.

## Desired Outcome

After the file is analyzed:

1. the application computes `recommended_text_settings` for that specific file
2. those recommendations are stored in `session_state` and tied to the file identity
3. recommendations are auto-applied only once for a newly analyzed file
4. auto-apply occurs only while the user has not manually changed the relevant settings for that file
5. once the user changes a setting manually, the application must stop overwriting that setting for the same file
6. the UI must not gain a new button just to re-apply recommendations

## Non-Goals

This specification does not authorize:

1. a new expert panel or recommendation-management UI
2. per-block automatic routing or per-block setting changes
3. auto-changing model, chunk size, retries, or image mode in Phase 1
4. silent replacement of user choices after the user has manually interacted with settings for the same file
5. persistent recommendation history across sessions or saved user profiles

## Scope

### In scope

Phase 1 of this feature covers only text-transform settings:

1. `processing_operation`
2. `source_language`
3. `target_language`

### Out of scope

The following remain out of scope for this specification:

1. `model`
2. `chunk_size`
3. `max_retries`
4. `image_mode`
5. `keep_all_image_variants`

Those settings may eventually receive recommendation logic, but they should not be included in this first implementation.

## Core Design Decision

Recommended settings must be file-scoped, not global.

The application must treat recommendations as derived metadata attached to one analyzed file, not as a new replacement for configuration defaults.

This means the correct state model is:

1. global configuration still provides repository defaults
2. file analysis computes file-specific recommendations
3. file-specific recommendations can temporarily override the initial widget state for that file only

## File Identity

Recommendations must be keyed by stable file identity that already exists in the runtime.

Phase 1 canonical identity key:

1. `uploaded_file_token`

Phase 1 must not use the preparation request marker as the recommendation identity key.

Rationale:

1. recommendation ownership belongs to the uploaded file itself
2. preparation request markers may vary with preparation inputs such as `chunk_size`
3. changing preparation inputs for the same uploaded file must not make the recommendation system treat that file as a different identity

The important property is that recommendations must belong to one concrete uploaded source, not float globally.

## Session State Contract

Introduce file-scoped recommendation state in `st.session_state`.

Recommended shape:

```python
recommended_text_settings: {
    "file_token": str,
    "processing_operation": str,
    "source_language": str,
    "target_language": str,
    "reason_summary": str | None,
}

recommended_text_settings_applied_for_token: str | None

manual_text_settings_override_for_token: {
    "file_token": str,
    "processing_operation": bool,
    "source_language": bool,
    "target_language": bool,
}
```

Design notes:

1. `recommended_text_settings` stores the latest derived recommendation for the current file.
2. `recommended_text_settings_applied_for_token` records whether one-time auto-apply has already happened for that file.
3. `manual_text_settings_override_for_token` records which fields the user has manually changed for that file.
4. These keys must be registered in `init_session_state()` in `state.py` like other session-owned UI/runtime keys.

### Reset and cleanup behavior

The specification must explicitly define how recommendation state behaves under reset.

Required rules:

1. Full reset via `reset_run_state(..., preserve_preparation=False)` must clear `recommended_text_settings`, `recommended_text_settings_applied_for_token`, and `manual_text_settings_override_for_token`.
2. Partial reset via `reset_run_state(..., preserve_preparation=True)` may preserve those keys only if the preserved preparation context still belongs to the same file token.
3. If `selected_source_token` changes to a different file, recommendation state must be replaced for the new file rather than merged.
4. Recommendation state must not survive as a stale recommendation for a different file after full reset.

## Recommendation Derivation

Recommendation derivation must happen only after the file has been analyzed enough to produce prepared document context.

The preferred source is:

1. `prepared_run_context.source_text` as the analyzed text source
2. existing text-transform assessment output as the primary recommendation signal
3. selected current settings as a tie-breaker when the assessment is inconclusive

Phase 1 recommendation logic should stay conservative.

Recommended output rules:

1. if the analyzed text already looks like target-language content, recommend `edit`
2. if the analyzed text clearly does not look like target-language content, keep or recommend `translate`
3. if the source language is ambiguous, prefer `auto` rather than forcing a guessed Latin-script language
4. if the target language has already been explicitly chosen by the user for this file, do not rewrite it after manual override
5. in Phase 1, `target_language` should usually remain unchanged
6. in Phase 1, `target_language` may be rewritten only if the current value is invalid, missing, or violates an already-established repository/runtime contract

`prepared_run_context` itself is not the recommendation signal. It is the container that supplies `source_text` and file identity to the derivation helper.

## One-Time Gentle Auto-Apply

The auto-apply policy is the central UX rule of this specification.

It must work as follows:

1. When a new file is analyzed and recommendations become available, the application may auto-apply them once.
2. Auto-apply must happen only if those text settings have not already been manually changed for that same file.
3. Auto-apply must never keep re-firing on every rerun for the same file.
4. Auto-apply must be field-aware within that one application event: a field manually changed by the user must not be overwritten, even if another field from the same recommendation payload may still be auto-applied.
5. After that one auto-apply event is recorded for the file token, the application must not perform any second or later recommendation-driven widget rewrite for the same file token during the session.

This is intentionally softer than “overwrite all three values” and intentionally more proactive than “show a passive warning only”.

## Widget State Write Timing

The implementation must explicitly account for Streamlit widget lifecycle.

Current reality:

1. sidebar widgets render before file analysis completes
2. widget state for keyed selectboxes lives in `st.session_state`
3. recommendations become available only after preparation and assessment

Therefore the implementation must use a two-step timing rule:

1. when recommendations are first derived after analysis, write the recommended widget values into the relevant `st.session_state` widget keys and mark auto-apply as completed for that file token
2. immediately call `st.rerun()` once so the next render of `render_sidebar(...)` picks up the new widget state before processing starts

After that rerun:

1. the sidebar reads the already-updated widget state naturally
2. no further forced reruns are needed for the same recommendation application

This is the required Phase 1 mechanism. The specification does not leave widget timing implicit.

### Widget value format

Recommendations must store canonical internal codes:

1. `processing_operation` as values such as `edit` or `translate`
2. `source_language` as language codes such as `en`, `ru`, or `auto`
3. `target_language` as language codes such as `en` or `ru`

Auto-apply must convert those codes into actual widget-state values before writing to keyed sidebar widgets.

Examples:

1. `processing_operation="edit"` must be converted to the visible sidebar label used by `sidebar_text_operation`
2. `target_language="ru"` must be converted to the visible language label used by `sidebar_target_language`
3. `source_language="auto"` must be converted to the visible source selector value used by `sidebar_source_language`

## Protection Against Manual Overrides

The application must distinguish between:

1. values populated by global defaults
2. values populated by one-time recommendation auto-apply
3. values explicitly chosen by the user

Once the user changes any of the text-transform fields for the current file, that field must be considered user-owned for that file.

Required behavior:

1. changing `processing_operation` manually prevents further auto-overwrites of `processing_operation` for the same file
2. changing `source_language` manually prevents further auto-overwrites of `source_language` for the same file
3. changing `target_language` manually prevents further auto-overwrites of `target_language` for the same file

This protection must be scoped per file token.

When a different file is uploaded, recommendation ownership resets for the new file.

### Conditional widget visibility

`source_language` is conditionally visible only when `processing_operation == "translate"`.

Required behavior:

1. switching to `edit` must not destroy the stored `source_language` recommendation or manual-override ownership for that file
2. while the source-language widget is hidden, its stored value may remain in session state
3. if the user later returns to `translate` for the same file, the previous source-language value and ownership rules must still apply
4. auto-apply logic must not treat temporary widget invisibility as permission to overwrite a user-owned `source_language`

## No Additional Re-Apply Button

This feature must not introduce a new button such as:

1. “Apply file recommendations”
2. “Restore recommended settings”
3. any equivalent extra control in the sidebar or main page

Rationale:

1. the interface is already carrying multiple processing controls
2. recommendations are intended to be gentle and automatic, not a new control surface
3. a dedicated button would create another decision point and visual burden for a feature that should feel ambient

Instead, the product should rely on:

1. one-time auto-apply for a newly analyzed file
2. concise explanatory text when recommendations were applied automatically
3. continued respect for manual user changes thereafter

## UX Contract

The visible user experience should be:

1. user uploads a file
2. file is analyzed
3. if the file suggests more appropriate text settings, the sidebar quietly reflects those settings once
4. the user may continue with those settings or change them manually
5. after manual changes, the application stops “helping” for those fields on that file

The UX must feel like a helpful default refinement, not an active tug-of-war with the user.

## Recommendation Messaging

The product may show a concise note when recommendations were auto-applied.

Allowed forms:

1. caption near the sidebar text settings
2. short info/caption message in the main page after preparation

Recommended message intent:

1. “После анализа файла приложение скорректировало текстовые настройки до рекомендуемых для этого документа.”

`reason_summary` is allowed in Phase 1 only as a short internal or display-ready explanation string for why the recommendation exists.

Allowed use:

1. concise note such as “text already looks like target-language content”
2. concise note such as “source language is ambiguous; auto is safer”

If the implementation does not surface a more specific explanation, `reason_summary` may remain `None` without violating the contract.

The message must be informational only.

It must not require acknowledgment and must not introduce a revert button.

## Suggested Runtime Flow

### Current high-level flow

Today the flow is effectively:

1. load app config
2. render sidebar widgets
3. upload file
4. run preparation
5. obtain `prepared_run_context`
6. show results and allow processing start

### Required updated flow

The updated logic should become:

1. load app config
2. resolve current widget values from session state
3. upload file
4. run preparation
5. obtain `prepared_run_context`
6. derive `recommended_text_settings` for the file token
7. if this is a new file and the relevant fields are not manually owned, write recommended values into widget state once
8. immediately perform a single rerun
9. on the next render, `render_sidebar(...)` reads the updated widget state before the user starts processing

This flow is compatible with the current architecture because it does not require changing the block pipeline.

## Module Responsibilities

### Modules that gain new responsibility

1. `ui.py`
   Must read and write text-setting widget state in a way that supports recommended values and manual-override tracking.
2. `app.py`
   Must orchestrate recommendation derivation, one-time auto-apply, and file-scoped state transitions.
3. a thin recommendation helper or utility module
   Should derive `recommended_text_settings` from prepared document context and existing assessment signals.
4. `state.py`
   Must initialize and clear recommendation-related session keys consistently.

### Modules that must not change in role

1. `document.py`
2. `preparation.py`
3. `processing_service.py`
4. `document_pipeline.py`
5. prompt files and prompt loading contracts

This feature is about UI state and startup orchestration, not prompt semantics.

## Recommendation Derivation Rules For Phase 1

The recommendation helper should use conservative rules only.

Recommended Phase 1 logic:

1. If current assessment strongly suggests the text is already in `target_language`, recommend `processing_operation = "edit"`.
2. If the text does not appear to match `target_language`, recommend `processing_operation = "translate"`.
3. If `source_language` is not trivially knowable, recommend `source_language = "auto"` for translation mode.
4. Do not force a new `target_language` unless there is a clear repository-defined target default already in effect or the current target is invalid.
5. In normal Phase 1 operation, `target_language` should behave as a preserved user-facing intent, not as an aggressively inferred recommendation field.

This keeps the system from acting smarter than it really is.

## State Ownership Rules

The implementation must explicitly define ownership for each text setting field.

For each file token and field, the owner may be understood as:

1. `config_default`
2. `recommended_auto_apply`
3. `user_manual`

Phase 1 does not need to persist these labels literally, but the logic must behave as if it does.

Required precedence:

1. `user_manual` wins over everything for the same file
2. `recommended_auto_apply` may override `config_default` once for the same file
3. `config_default` applies only before file-specific recommendation takes effect

## Edge Cases

### 1. Same file re-runs repeatedly

Expected behavior:

1. recommendations stay available in state
2. auto-apply does not repeat once already applied
3. user manual choices remain respected

### 2. New file uploaded

Expected behavior:

1. recommendation state is recomputed for the new file token
2. manual-override protection resets for the new file
3. a one-time auto-apply may happen again for the new file

### 3. User changes only one field

Expected behavior:

1. only that field becomes protected from further auto-overwrite
2. other fields may still receive initial recommendation if not yet user-owned

### 4. Recommendation arrives after sidebar initially rendered

Expected behavior:

1. recommendation may update widget state once
2. rerun should show updated values before processing start
3. user should not need to re-upload the file

### 5. Preparation cache hit

Expected behavior:

1. if a cached prepared context is loaded for a newly selected file, recommendations may still be derived immediately
2. the one-time auto-apply rule remains the same

### 6. Restart without re-upload

Expected behavior:

1. if the user restarts processing for the same file token, recommendation state remains associated with that file
2. manual override tracking must not be reset merely because processing was restarted
3. recommendations must not auto-apply again just because the run outcome changed for the same file
4. if restart preserves preparation context, recommendation ownership should remain stable for that file

### 7. Full reset versus preparation-preserving reset

Expected behavior:

1. full reset clears recommendation state and manual-override ownership
2. preparation-preserving reset may keep recommendation state only for the same preserved file token
3. recommendation state must never outlive the file identity it belongs to

### 8. Hidden source-language widget

Expected behavior:

1. switching from `translate` to `edit` hides the widget but does not erase its value or ownership
2. switching back to `translate` restores the stored value for the same file
3. hidden widget state must not be misinterpreted as untouched state

## Risks

### 1. Silent user confusion

Risk:
The user may not understand why a setting changed after upload.

Mitigation:
Show a short explanatory note when recommendations were auto-applied.

### 2. Overwriting user intent

Risk:
The product keeps changing settings after the user already chose values.

Mitigation:
Track manual overrides per field and per file token.

### 3. Recommendation overconfidence

Risk:
The helper guesses too aggressively and pushes the wrong mode.

Mitigation:
Keep Phase 1 recommendation logic conservative and rely on existing hardening warnings.

### 4. Hidden state complexity

Risk:
Session-state logic becomes difficult to reason about.

Mitigation:
Use a small, explicit recommendation state contract and keep it isolated to text settings only.

## Verification Criteria

Implementation will be considered complete when all of the following are true:

1. the application stores `recommended_text_settings` in `session_state` scoped to a specific file token
2. newly analyzed files may receive a one-time auto-apply of recommended text settings
3. auto-apply does not repeat on every rerun for the same file
4. manual changes prevent further overwrite of the changed field for the same file
5. uploading a different file resets recommendation ownership for that new file
6. no new “apply recommendations” button is added to the interface
7. the user can still manually change any recommended setting before starting processing

## Suggested Implementation Order

1. Define the session-state contract for file-scoped recommendations and manual-override tracking.
2. Add a thin helper that derives `recommended_text_settings` from prepared context and existing assessment.
3. Update sidebar widget-state handling so recommendations can populate widget state once.
4. Add orchestration in `app.py` for one-time auto-apply on newly analyzed files.
5. Register and clear recommendation keys in `state.py`.
6. Add concise informational messaging when recommendations were auto-applied.
7. Add targeted tests for one-time apply, per-field manual override protection, restart behavior, and new-file reset behavior.

## Implementation Checklist

### Priority 0: Lock the UX contract

- [x] Confirm that recommendations are file-scoped, not global.
- [x] Confirm that only text-transform settings are included in Phase 1 recommendations.
- [x] Confirm that one-time gentle auto-apply is allowed for newly analyzed files.
- [x] Confirm that no new “apply recommendations” button will be added.
- [x] Confirm that manual field changes must block further auto-overwrite for that field and file.

### Priority 1: Session state contract

- [x] Add `recommended_text_settings` to session state.
- [x] Add a file-token-scoped marker showing whether recommendations were auto-applied.
- [x] Add per-field manual override tracking for text settings.
- [x] Register recommendation-related keys in `init_session_state()`.
- [x] Define cleanup behavior for those keys in `reset_run_state()`.

### Priority 2: Recommendation derivation

- [x] Implement a thin helper to derive `recommended_text_settings` from prepared context.
- [x] Keep recommendation logic conservative and limited to the current file.
- [x] Reuse existing assessment signals where available rather than duplicating analysis logic.

### Priority 3: Auto-apply logic

- [x] Auto-apply recommended text settings once for a newly analyzed file.
- [x] Prevent repeated auto-apply on reruns for the same file.
- [x] Apply recommendations only to fields that are not manually owned for that file.
- [x] Convert internal recommendation codes to actual widget-state labels before writing sidebar widget keys.
- [x] Write widget state and perform exactly one rerun after first recommendation application.

### Priority 4: UX messaging

- [x] Show a concise informational note when recommendations were auto-applied.
- [x] Do not add a recommendation-apply button.
- [x] Keep the interface visually simple.

### Priority 5: Tests

- [x] Add tests for file-scoped recommendation storage.
- [x] Add tests for one-time auto-apply.
- [x] Add tests for per-field manual override protection.
- [x] Add tests for new-file reset behavior.
- [x] Add tests for restart behavior without re-upload.
- [x] Add tests for conditional `source_language` widget visibility and persistence.
- [x] Add tests confirming that no extra apply button is introduced.

### Priority 6: Manual verification

- [ ] Verify that a newly uploaded file can update text settings once after analysis.
- [ ] Verify that manual edits stop further overwrites for the same file.
- [ ] Verify that uploading a different file allows a fresh one-time auto-apply.
- [ ] Verify that the UI remains simple and does not gain a recommendation-management button.