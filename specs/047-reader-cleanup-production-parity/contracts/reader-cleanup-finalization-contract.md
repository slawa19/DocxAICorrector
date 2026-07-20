# Contract: Reader Cleanup Finalization

## Prerequisites

- Spec 044 delivery disposition/notices implemented.
- Spec 048 run/source diagnostics ownership implemented.

## Activation

- UI maps the supported resolved default to effective pipeline config.
- Default false, translation-only and explicit off remain binding.
- Edit and standalone audiobook do not execute reader cleanup.

## Final evidence

- Changed and no-op cleanup paths use final Markdown, final DOCX and final owned diagnostics.
- Superseded report is not presented as current after final report succeeds.
- Existing caption-conflict gate remains; review coverage is not a gate.

## Cancellation

- Check before and between every late side-effect boundary.
- In-flight call may finish; no subsequent work starts after observation.
- Terminal outcome is existing `stopped`; no accepted artifact persistence.

## Advisory failures/notices

- Cleanup advisory preserves base result and durable cleanup notice.
- Narration advisory is independent; neither overwrites the other.
- Spec-044 blocked disposition remains primary and cannot be softened.
- Cleanup, narration, and late-stop user messages exist in both current result-screen locales and are covered by renderer tests.

## Narration

- Additive translation narration derives from final accepted cleanup lineage and existing structural exclusions.
- Ambiguous projection omits narration with warning; never uses stale chunks.
- Standalone audiobook source, behavior, and warnings are unchanged.
