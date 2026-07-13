# Feature Specification: OCR stamp / classification-marker furniture detection (BACKLOG)

Date: 2026-07-13
Status: BACKLOG — logged, not scheduled. A real content-quality defect found during the preparation-stage audit;
deferred by director decision (separate ticket, not bundled with the summary simplification `specs/015`).
Owner surface: `document/layout_cleanup.py` (furniture detector).

## Problem (verified 2026-07-13)

An OCR'd classification stamp such as "Secret" / "Секретно" / "Для служебного пользования", repeated across pages,
is NOT recognized as furniture and leaks into the translated output as content. Two causes:
1. It is absent from `BOILERPLATE_TOKENS` (`layout_cleanup.py:34-42` = confidential/draft/copyright/конфиденциально/
   черновик/все права защищены — no secret/classification markers).
2. The generic repeated-artifact path requires `layout_origin == "textbox"` (`layout_cleanup.py:319`); an OCR stamp
   imported as a normal paragraph (`layout_origin == "paragraph"`) never matches even when it repeats ≥3×, so it
   falls through to `uncertain_repeated_artifact` and is kept.
3. Even if flagged, cleanup runs in flag-only mode (`layout_cleanup.py:206-212`, `removed_paragraph_count=0`), so a
   flagged stamp is still not removed and is translated.

The reworked output gate will NOT catch it — a stamp present in source and faithfully carried to output is not a
formatting-TRANSFER discrepancy (the gate's axis), so it is invisible there.

## Likely fix surface (to be specced when scheduled)

- Extend furniture detection with a stamp/classification-marker set (multilingual) and/or a dedicated repeated-stamp
  detector that does not require textbox origin (repeated short uppercase marker across pages).
- Decide flag-vs-remove policy for stamps (removal needs `cleanup_mode="remove"` or a targeted drop, since flag mode
  never deletes) — universal rule only, no per-document literals (Constitution VII); anti-vacuum counter-proof that
  real repeated body text is not eaten.

## Non-goals (for now)

- Not part of `specs/015` (summary simplification) or `specs/016` (drop partial translation). This is a standalone
  content-quality fix to be scheduled separately.
