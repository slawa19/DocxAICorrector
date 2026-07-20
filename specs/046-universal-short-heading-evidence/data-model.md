# Data Model: Universal Short-Heading Evidence

## PreparedParagraph

- text (not positive evidence)
- role and structural role
- heading level/source/hint
- confidence/provenance
- style and outline metadata
- font/form metadata and body-context form baseline

## HeadingEvidence

- `explicit_structural`: heading role, level, style or outline
- `supported_form`: existing universal form distinction represented in source metadata
- `none`: no reusable structural/form signal

Validation: text length, case, ordinal, punctuation and lexical content cannot upgrade `none`.

## Classification transitions

- explicit heading → preserve heading
- supported form candidate → existing bounded form decision
- no-signal body → remain body with no heading hint/source/level
- authoritative body/attribution/etc. → preserve classification
