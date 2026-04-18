# Multilingual Text Transform Hardening Spec

Date: 2026-04-18

## Goal

Add a narrow hardening layer for multilingual text transformation so the project behaves safely and predictably when the user selects the wrong mode, provides the wrong source language, or submits mixed-language content.

This specification is intentionally separate from the core multilingual rollout spec. It does not redefine the Phase 1 multilingual architecture. It extends it with guardrails against user misconfiguration and ambiguous input.

The implementation must preserve the current document-processing architecture and avoid introducing a second translation pipeline.

## Relationship To Existing Spec

This specification depends on and extends:

1. `docs/specs/MULTILINGUAL_TEXT_TRANSFORM_SPEC_2026-04-18.md`

That base specification introduced:

1. `edit` and `translate` modes
2. source and target language selection
3. prompt composition based on operation and language context
4. prompt-neutral block processing

This hardening specification adds:

1. graceful fallback behavior when the selected mode conflicts with the actual text
2. warning and assessment layers for likely user mistakes
3. conservative handling for mixed-language and ambiguous text
4. a lightweight preflight assessment model that informs UI and prompt behavior without changing the block pipeline

## Problem Statement

The multilingual text-transform contract now allows the user to choose an operation and languages, but user-provided settings can still be wrong or incomplete.

The current implementation handles many such cases only implicitly through the LLM prompt. That is not sufficient for long-form documents.

Without explicit hardening, the following failure patterns remain likely:

1. `translate` is selected for text that is already in the target language.
2. `edit` is selected for text that still requires translation.
3. The user provides an incorrect `source_language`.
4. The document is mixed-language but the user assumes one dominant source language.
5. `auto` is used on short, noisy, or ambiguous content where language detection is unreliable.
6. The selected `source_language` and `target_language` are identical even though the user intended literary editing rather than translation.

These cases do not usually crash the pipeline. Instead, they silently degrade quality, which is more dangerous.

## Desired Outcome

The system should not blindly obey incorrect user settings when the text itself strongly contradicts them.

Instead, the system should degrade gracefully:

1. prefer the least destructive transformation
2. avoid repeated translation of already translated text
3. avoid aggressive rewriting when source-language confidence is low
4. preserve already-correct target-language segments in mixed-language input
5. warn the user when the selected settings are likely wrong

## Non-Goals

This specification does not authorize:

1. per-block routing into separate translation and editing pipelines
2. document-wide glossary extraction or terminology memory
3. a heavy language-detection subsystem or external service dependency
4. a redesign of `document.py`, `preparation.py`, or formatting restoration
5. a requirement to reject all ambiguous jobs before processing begins

## User Error Taxonomy

### 1. Wrong operation selected

Examples:

1. `translate` chosen for text already written in `target_language`
2. `edit` chosen for text still written in a foreign source language

Likely impact:

1. unnecessary re-translation
2. excessive paraphrasing instead of light editing
3. lower factual stability due to over-transformation

### 2. Wrong source language provided

Examples:

1. text is English but `source_language=de`
2. text is French but `source_language=es`
3. text is already Russian but user sets `en -> ru`

Likely impact:

1. wrong translation assumptions
2. stronger risk of interpretation drift
3. reduced consistency across blocks

### 3. Mixed-language input

Examples:

1. dominant language plus foreign quotations
2. partially translated chapters
3. tables, captions, headings, or metadata in a different language than body text
4. bilingual source text where some segments are already in `target_language`

Likely impact:

1. already-correct target-language segments get retranslated
2. foreign inserts that should remain untouched get normalized away
3. cross-block inconsistency in how inserts are handled

### 4. Source and target language are identical in translation mode

Examples:

1. `en -> en`
2. `ru -> ru`

Likely impact:

1. user probably wanted `edit`, but product runs a translation-oriented prompt
2. prompt contract becomes semantically ambiguous

### 5. Ambiguous `auto`

Examples:

1. text excerpt is too short
2. excerpt contains mostly names, numbers, or placeholders
3. OCR or encoding noise makes language estimation unstable

Likely impact:

1. weak or contradictory language inference
2. unpredictable transform style between blocks

## Product Principles

Hardening must follow these rules:

1. Prefer warnings over hard blocking where reasonable.
2. Prefer conservative fallback over aggressive text rewriting.
3. Prefer document-level or excerpt-level assessment over per-block routing.
4. Keep all changes within the existing prompt-composition, UI, and runtime-startup layers.
5. Do not require the user to understand language-detection internals.

## Proposed Design

### 1. Graceful fallback semantics in translation mode

`translate` mode must not mean “always force translation regardless of what the text already is”.

Instead, the effective contract should become:

1. translate source-language content into `target_language`
2. if a segment is already in `target_language`, do not retranslate it
3. if a block is already largely in `target_language`, degrade to light literary editing rather than retranslation
4. if `source_language` appears inconsistent with the actual block, prioritize the actual block language over the user setting

This is the single most important safety rule.

### 2. Conservative mixed-language handling

Mixed-language input must be treated as a normal scenario, not an exceptional failure.

The effective processing rules should be:

1. preserve segments already in `target_language`
2. translate only segments that clearly need translation into `target_language`
3. preserve placeholders, markers, code-like tokens, formulas, and internal document tokens
4. preserve foreign inserts when they appear intentional and should not obviously be normalized
5. if confidence is low, prefer preserving a segment over aggressively rewriting it

### 3. Lightweight preflight assessment

Add a lightweight assessment step before the main processing run starts.

This is not a second pipeline and not a document-level rewrite phase.

It should inspect a short excerpt of the prepared document and infer a small set of runtime hints.

Recommended assessment output shape:

1. `dominant_language`
2. `target_language_match`
3. `source_language_mismatch`
4. `mixed_language_detected`
5. `confidence`
6. `recommended_mode_hint`
7. `recommended_source_language`

This assessment should be best-effort and low-cost.

### 4. Warnings instead of hard failures

When the preflight assessment suggests a likely user mistake, the product should warn rather than block.

Recommended warnings:

1. “The text already appears to be in the target language; literary editing may be more appropriate than translation.”
2. “The selected source language does not match the detected dominant language of the document excerpt.”
3. “The document appears to contain multiple languages; translation quality may vary across segments.”
4. “Source and target languages are identical; if you want style improvement only, use literary editing mode.”

### 5. Prompt overlays informed by assessment

Prompt behavior should adapt based on assessment hints, but only through small overlays.

Do not create a new prompt system.

Instead, allow one optional hardening overlay fragment to be injected when needed.

Example intent of such an overlay:

1. if the target block already appears to be in `target_language`, do not perform repeated translation
2. preserve already-correct target-language segments
3. if the configured source language appears wrong, rely primarily on the factual language of the block
4. prefer conservative editing when confidence is low

## Detailed Changes

### 1. Strengthen the translation operation prompt

Update `prompts/operation_translate.txt` so translation mode becomes resilient to user error.

Required behavioral additions:

1. If the target block is already predominantly in `target_language`, do not retranslate it.
2. In that case, perform only light literary improvement.
3. If the configured `source_language` conflicts with the factual block language, prioritize the factual block language.
4. If the block is mixed-language, translate only the segments that actually require translation into `target_language`.
5. Preserve already-correct `target_language` segments unless there is a clear editorial reason to improve them lightly.
6. Preserve intentional foreign inserts, names, codes, placeholders, and document tokens unless translation is clearly required.
7. If confidence is low, prefer conservative handling over aggressive rewriting.

### 2. Add universal safety fallback language to system prompt

Update `prompts/system_prompt.txt` with a short, shared fallback section that applies across modes.

Required additions:

1. When the selected mode conflicts with the actual block language, choose the least destructive valid transformation.
2. Do not perform repeated translation of text already in `target_language`.
3. For mixed-language content, preserve already-correct `target_language` segments and transform only what clearly requires it.
4. When language confidence is low, prefer conservative output over aggressive rewriting.

This must remain concise. The shared system prompt should not become a long taxonomy of every edge case.

### 3. Add a lightweight text-transform assessment contract

Extend the internal text-transform context with an optional assessment payload.

Recommended shape:

```python
{
    "dominant_language": str | None,
    "target_language_match": bool | None,
    "source_language_mismatch": bool | None,
    "mixed_language_detected": bool,
    "confidence": str | None,
    "recommended_mode_hint": str | None,
    "recommended_source_language": str | None,
}
```

This assessment must remain optional and advisory.

### 4. Add a preflight assessment step at processing startup

Add a narrow preflight step after prepared document context exists and before full text processing starts.

Recommended behavior:

1. build a short excerpt from prepared source text
2. assess likely dominant language and ambiguity
3. compare selected source and target languages against the excerpt
4. populate assessment metadata
5. surface user-visible warnings when relevant

This step must not mutate the prepared document and must not introduce a second long-running stage.

### 5. Add UI warnings and help text

Update the sidebar and processing-startup UX to make common mistakes visible.

Required UI improvements:

1. translation mode help text should explain that it is intended for text not yet in `target_language`
2. if `source_language == target_language` in `translate`, show a warning recommending `edit`
3. if preflight indicates the excerpt already matches `target_language`, show a warning recommending `edit`
4. if preflight indicates mixed-language content, show an advisory warning rather than blocking processing
5. if preflight indicates likely source-language mismatch, show a warning before starting processing

### 6. Preserve Phase 1 simplicity

The hardening work must not explode the UI or add a new expert settings panel.

The preferred UX is:

1. existing mode and language controls stay as they are
2. user sees concise help and warnings
3. runtime adopts safer prompt behavior automatically

## Module Responsibilities

### Modules that gain new responsibility

1. `prompts/operation_translate.txt`
   Gains resilience rules for wrong mode, wrong source language, and mixed-language input.
2. `prompts/system_prompt.txt`
   Gains concise cross-mode safe-fallback rules.
3. `config.py`
   May gain optional loading hooks for a hardening overlay if implemented through prompt composition.
4. `ui.py`
   Gains warning/help presentation for likely misconfiguration.
5. `app.py`
   Gains preflight warning surfacing during startup.
6. `processing_service.py` or adjacent orchestration layer
   Gains a lightweight preflight assessment invocation.

### Modules that must not change in role

1. `document.py`
2. `preparation.py`
3. `formatting_transfer.py`
4. image pipeline modules
5. block execution semantics in `document_pipeline.py`, except for optional prompt-context consumption

## Recommended Assessment Strategy

The assessment implementation should follow these rules:

1. Use a short excerpt from the prepared document, not per-block routing.
2. Use a simple, cheap heuristic or lightweight detector.
3. Avoid introducing external infrastructure or a remote language-detection dependency.
4. Return low-confidence/unknown rather than pretending certainty.
5. Keep the assessment advisory, not authoritative.

## Error-Handling Matrix

### Case 1: `translate` selected for already translated text

Expected behavior:

1. show a warning suggesting `edit`
2. translate prompt degrades to light literary polishing
3. avoid repeated translation

### Case 2: `edit` selected for clearly foreign-language text

Expected behavior:

1. show a warning that the text may still require translation
2. do not auto-switch the mode in Phase 1 hardening
3. keep user control explicit

### Case 3: wrong `source_language`

Expected behavior:

1. show mismatch warning
2. prompt prioritizes factual block language over configured source language
3. processing continues conservatively

### Case 4: mixed-language text

Expected behavior:

1. show advisory mixed-language warning
2. preserve already-correct `target_language` segments
3. translate only clearly foreign segments
4. preserve intentional foreign inserts when uncertain

### Case 5: `source_language == target_language` in `translate`

Expected behavior:

1. show a warning recommending `edit`
2. allow the run to continue if user insists
3. translation prompt must avoid aggressive re-translation

### Case 6: ambiguous `auto`

Expected behavior:

1. do not claim high certainty
2. show advisory warning when confidence is low
3. choose conservative transform behavior

## Risks

### 1. Prompt overgrowth

Risk:
Hardening rules make prompts too verbose and reduce signal quality.

Mitigation:
Keep hardening additions concise and principle-based.

### 2. False-positive warnings

Risk:
The system warns too often and trains users to ignore warnings.

Mitigation:
Show warnings only for high-confidence or high-impact mismatches.

### 3. Overreliance on weak language heuristics

Risk:
The assessment becomes a hidden source of bad assumptions.

Mitigation:
Keep assessment advisory and never let it silently replace user intent.

### 4. Product ambiguity

Risk:
Users think the product will fully auto-correct any bad selection.

Mitigation:
Document the behavior as graceful fallback, not perfect intent recovery.

## Verification Criteria

Implementation will be considered complete for this hardening phase when all of the following are true:

1. `translate` prompt no longer blindly assumes the text always still needs translation.
2. already translated text is handled conservatively in translation mode.
3. likely source-language mismatch produces a warning rather than silent failure.
4. mixed-language input is handled conservatively and does not force normalization of already correct target-language segments.
5. `source_language == target_language` in translation mode produces a warning recommending `edit`.
6. low-confidence `auto` does not lead to aggressive transform behavior.
7. the implementation does not introduce a second translation pipeline or per-block routing layer.

## Suggested Implementation Order

1. Update `operation_translate.txt` with graceful fallback rules.
2. Add concise cross-mode safe-fallback language to `system_prompt.txt`.
3. Add UI help text and static warnings for obvious user mistakes.
4. Introduce lightweight preflight assessment metadata.
5. Surface dynamic warnings from assessment.
6. Optionally inject a small hardening overlay into prompt composition.
7. Add targeted tests for warnings, mismatch handling, and conservative translation fallback.

## Implementation Checklist

### Priority 0: Lock the hardening contract

- [ ] Confirm that wrong user settings should trigger warnings rather than hard blocking in most cases.
- [ ] Confirm that translation mode should gracefully degrade to light editing when the text is already in `target_language`.
- [ ] Confirm that the system should prioritize the factual block language over an obviously incorrect configured source language.
- [ ] Confirm that mixed-language handling should be conservative and segment-preserving.

### Priority 1: Prompt hardening

- [ ] Update `prompts/operation_translate.txt` with safe fallback rules for already translated, wrong-source, and mixed-language cases.
- [ ] Add concise safe-fallback language to `prompts/system_prompt.txt`.
- [ ] Keep prompt additions short enough to avoid prompt bloat.

### Priority 2: UI warnings

- [ ] Add help text clarifying when `translate` should be used.
- [ ] Add warning for `source_language == target_language` in translation mode.
- [ ] Add startup warning for likely already-translated input.
- [ ] Add startup warning for likely source-language mismatch.
- [ ] Add advisory warning for mixed-language input.

### Priority 3: Runtime assessment

- [ ] Define a lightweight `text_transform_assessment` shape.
- [ ] Compute assessment from a short prepared-text excerpt.
- [ ] Carry assessment through processing startup as advisory metadata.
- [ ] Avoid per-block routing and avoid mutating prepared document data.

### Priority 4: Prompt-context adaptation

- [ ] Decide whether hardening hints are injected through system prompt overlay, operation fragment text, or both.
- [ ] If overlay is used, keep it optional and narrow.
- [ ] Ensure low-confidence assessment results bias toward conservative output.

### Priority 5: Tests

- [ ] Add tests for translation-mode fallback wording.
- [ ] Add tests for UI warnings on obvious mismatches.
- [ ] Add tests for conservative handling when source and target match.
- [ ] Add tests for assessment behavior on ambiguous input.
- [ ] Add tests that confirm no new pipeline branch was introduced.

### Priority 6: Manual verification

- [ ] Verify `translate` on already translated text behaves closer to light editing than retranslation.
- [ ] Verify mixed-language input preserves already-correct target-language segments.
- [ ] Verify wrong-source selection produces a warning and still yields conservative output.
- [ ] Verify low-confidence `auto` produces warnings but does not block processing.