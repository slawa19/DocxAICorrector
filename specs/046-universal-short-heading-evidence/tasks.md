# Tasks: Universal Short-Heading Evidence

**Input**: Design documents in `specs/046-universal-short-heading-evidence/`

**Global order**: 044 → 045 → 046 → 048 → 047; start after 045.

## Phase 1: Setup

- [X] T001 Reconfirm the fresh no-signal positive baseline in `tests/test_document_extraction.py`
- [X] T002 Run the focused pre-change canonical selector from `specs/046-universal-short-heading-evidence/quickstart.md`

## Phase 2: Foundational evidence matrix

- [X] T003 Define synthetic no-signal, explicit-heading, form-backed, and authoritative non-heading fixtures in `tests/test_document_extraction.py`

## Phase 3: User Story 1 - Keep short body as body (P1) MVP

**Independent Test**: No-signal short body remains body with no heading metadata in both modes.

- [X] T004 [US1] Replace the old promotion expectation with failing no-signal body assertions in `tests/test_document_extraction.py`
- [X] T005 [US1] Add text-shape invariance cases for capitalization, ordinals, punctuation and length in `tests/test_document_extraction.py`
- [X] T006 [US1] Remove the length-only promotion/hint bypass in `src/docxaicorrector/document/roles.py`

## Phase 4: User Story 2 - Preserve genuine headings (P2)

**Independent Test**: Explicit and supported form-backed short headings remain headings; matched no-form control remains body.

- [X] T007 [P] [US2] Add explicit heading semantics counter-proof in `tests/test_document_extraction.py`
- [X] T008 [P] [US2] Add matched form-backed/no-form anti-vacuum pair in `tests/test_document_extraction.py`
- [X] T009 [US2] Adjust only the existing form-evidence path if required to preserve documented precedence in `src/docxaicorrector/document/roles.py`

## Phase 5: User Story 3 - Preserve authoritative classifications (P3)

**Independent Test**: AI-confidence body and attribution metadata is unchanged.

- [X] T010 [US3] Add/retain authoritative body and attribution regression assertions in `tests/test_document_extraction.py`

## Final Phase: Verification

- [X] T011 Add a no-added-work assertion proving zero new external calls or preparation stages in `tests/test_document_extraction.py`
- [X] T012 Run focused canonical validation from `specs/046-universal-short-heading-evidence/quickstart.md`
- [X] T013 Review changed logic/tests for document literals or text-shape positives in `src/docxaicorrector/document/roles.py`
- [X] T014 Run VS Code `Run Full Pytest` and `git diff --check`

## Dependencies & strategy

T003 precedes story tests. T004/T005 must fail before T006. US2 positive proofs can be authored in parallel and must pass after the bounded removal. Complete 046 before 048.

## Parallel example

T007 and T008 are parallel test tasks; neither authorizes a new heuristic.
